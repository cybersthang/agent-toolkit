#!/usr/bin/env python
"""Falsifier — empirical timing_perturb runner.

Implements dev's stated test method:
  "Nếu thực sự là BLOCK thì gắn time.sleep vào, nếu block thật thì
   downstream phải chờ sleep xong UI mới load."

Workflow:
  1. Read a probe's `falsification.runner` config from
     `.agent-toolkit/acceptance-probes.json`.
  2. Snapshot the target file (controller / handler).
  3. Inject `time.sleep(N)` at the line matching `target_line_pattern`.
  4. Run `measurement_command` (e.g. curl -w "%{time_total}" → endpoint).
  5. Restore the original file.
  6. Compare delta-vs-baseline against `expected_delta_seconds ± tolerance`.
  7. Exit 0 if block-behavior empirically verified; 1 if not.

Usage:
  python .codex/tools/falsify.py --probe <probe-id> [--baseline-seconds N]
  python .codex/tools/falsify.py --probe load-views-blocking
  python .codex/tools/falsify.py --probe load-views-blocking --dry-run

Schema extension expected in acceptance-probes.json:
  "falsification": {
    "type": "timing_perturb",
    "description": "<human readable>",
    "runner": {
      "target_file": "<addon-root>/<module>/controllers/<controller>.py",
      "target_line_pattern": "def <handler_name>\\(",  # regex
      "inject_after_match": true,                  # inject BELOW the matched line, not above
      "sleep_seconds": 2,
      "measurement_command": "curl -s -o /dev/null -w '%{time_total}' https://example/<route>",
      "baseline_command": "curl -s -o /dev/null -w '%{time_total}' https://example/<route>",
      "expected_delta_seconds": 2.0,
      "tolerance": 0.3
    }
  }
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _force_utf8_streams() -> None:
    """Reconfig stdout/stderr to UTF-8. CLI-only — module-level reconfig
    breaks pytest's capture machinery when this module is imported as a
    library. Called from `main()` so it only fires when invoked as a
    subprocess (tests / pre-commit / DEV CLI). Without this, Python 3.8
    on Windows writes cp1252 bytes (e.g. 0xB1 for `±`) to its captured
    pipe, and the UTF-8-decoding parent then fails."""
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES_PATH = REPO_ROOT / ".agent-toolkit" / "acceptance-probes.json"


def _load_probe(probe_id: str) -> Optional[Dict[str, Any]]:
    if not PROBES_PATH.exists():
        return None
    try:
        data = json.loads(PROBES_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[falsify] failed to read probes: {e}", file=sys.stderr)
        return None
    for p in (data.get("probes") or []):
        if isinstance(p, dict) and p.get("id") == probe_id:
            return p
    return None


# Sandbox: only allow these binaries in measurement_command. No shell
# metacharacters (|, &, ;, >, <, `, $, ()) — they would enable
# command injection if probe config is malicious.
_ALLOWED_BINARIES = {
    "curl", "wget", "http", "httpie", "ab", "wrk",
    "echo", "sleep", "true", "false",
    "python", "python3", "node", "npx", "ruby",
    "grep", "rg", "find", "cat", "head", "tail",
    "psql", "mysql", "sqlite3", "redis-cli",
    "git",
    "playwright",  # direct invocation if installed globally
}
_SHELL_METACHARS = re.compile(r"[|&;`$()<>]")


def _scan_unquoted_metachars(cmd: str) -> Optional[str]:
    """Quote-aware metachar scan. Returns offending char if a shell
    metachar appears OUTSIDE any quoted region; None if all metachars
    are safely quoted. Handles single/double quotes + backslash escape.
    """
    in_single = False
    in_double = False
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and i + 1 < len(cmd):
            i += 2
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            i += 1
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            i += 1
            continue
        if not in_single and not in_double:
            if c in "|&;<>`":
                return c
            if c == "$" and i + 1 < len(cmd) and cmd[i + 1] == "(":
                return "$("
        i += 1
    return None


def _validate_command(cmd: str) -> Optional[str]:
    """Validate measurement_command before exec.

    Sandbox layers:
      1. shell=False is enforced at run-site → quoted metachars become
         literal argv (safe), only unquoted ones would have been shell-
         interpreted (caught here).
      2. Binary whitelist — first token must be in `_ALLOWED_BINARIES`.
      3. shlex.split must succeed (malformed quoting = reject).

    Returns error string if invalid, None if OK.
    """
    if not cmd or not cmd.strip():
        return "empty command"
    meta = _scan_unquoted_metachars(cmd)
    if meta is not None:
        return (
            f"unquoted shell metachar {meta!r} in command "
            f"(would be shell-interpreted): {cmd[:80]}"
        )
    try:
        import shlex
        tokens = shlex.split(cmd, posix=True)
    except ValueError as e:
        return f"unparseable command: {e}"
    if not tokens:
        return "no tokens after parse"
    binary = tokens[0]
    bare = Path(binary).name
    if bare.lower().endswith(".exe"):
        bare = bare[:-4]
    if bare not in _ALLOWED_BINARIES:
        return (
            f"binary {bare!r} not in whitelist. Allowed: "
            f"{sorted(_ALLOWED_BINARIES)}. Edit "
            ".codex/tools/falsify.py:_ALLOWED_BINARIES to extend "
            "(requires PR review)."
        )
    return None


def _run_command(cmd: str, timeout: int = 60) -> Tuple[Optional[float], str]:
    """Run a sandboxed command. Sandbox: shell=False, binary whitelist
    enforced. Parse stdout as seconds (float). Returns (seconds, raw)."""
    err = _validate_command(cmd)
    if err:
        return None, f"<sandbox-reject> {err}"
    try:
        import shlex
        tokens = shlex.split(cmd, posix=True)
        proc = subprocess.run(
            tokens, shell=False, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None, f"<timeout after {timeout}s>"
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return None, f"<exit {proc.returncode}> {raw} {proc.stderr[:200]}"
    # Try to parse a float (curl -w '%{time_total}' outputs e.g. "0.234567")
    try:
        return float(raw), raw
    except ValueError:
        # Fallback: extract first float-looking token
        m = re.search(r"(\d+\.\d+)", raw)
        if m:
            return float(m.group(1)), raw
    return None, raw


def _inject_sleep(file_path: Path, line_pattern: str, sleep_seconds: float,
                  inject_after_match: bool = True) -> Path:
    """Atomic-write inject `time.sleep(N)` after first line matching pattern.

    Atomicity strategy:
      1. Read original text.
      2. Write backup to <file>.falsify_backup (separate file, untouched).
      3. Write modified content to <file>.falsify_tmp (separate file).
      4. os.replace() <file>.falsify_tmp → <file> (atomic on same volume).
    If step 3 or 4 fails, the original file remains intact (no partial state).
    Backup is independent of tmp — caller's `_restore` uses it.
    """
    import os
    text = file_path.read_text(encoding="utf-8")
    backup = file_path.with_suffix(file_path.suffix + ".falsify_backup")
    tmp = file_path.with_suffix(file_path.suffix + ".falsify_tmp")
    backup.write_text(text, encoding="utf-8")
    try:
        lines = text.splitlines(keepends=True)
        pat = re.compile(line_pattern)
        out_lines = []
        injected = False
        for line in lines:
            out_lines.append(line)
            if not injected and pat.search(line):
                indent = "    "
                inject = f"{indent}import time as _falsify_time; _falsify_time.sleep({sleep_seconds})\n"
                if inject_after_match:
                    out_lines.append(inject)
                injected = True
        if not injected:
            backup.unlink(missing_ok=True)
            raise RuntimeError(
                f"target_line_pattern {line_pattern!r} did not match any line in {file_path}"
            )
        tmp.write_text("".join(out_lines), encoding="utf-8")
        # Atomic replace — on Windows + same volume, this is rename-or-replace.
        os.replace(str(tmp), str(file_path))
    except Exception:
        # Cleanup tmp on any failure; backup remains so caller can recover.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return backup


def _restore(file_path: Path, backup: Path) -> None:
    """Atomic restore: read backup → write to .restore_tmp → atomic-replace.
    Then unlink backup. If atomic replace fails, backup remains for manual
    recovery."""
    import os
    if not backup.exists():
        return
    tmp = file_path.with_suffix(file_path.suffix + ".falsify_restore_tmp")
    try:
        text = backup.read_text(encoding="utf-8")
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(file_path))
    except OSError:
        # Leave backup in place for manual recovery.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    try:
        backup.unlink()
    except OSError:
        pass


def _run_side_effect_inject(probe: Dict[str, Any], dry_run: bool) -> int:
    """side_effect_inject — wrap a function in a monkey-patch that records
    invocation, run the measurement command, assert the call happened.

    Probe schema:
      "falsification": {
        "type": "side_effect_inject",
        "runner": {
          "target_file": "path/to/file.py",
          "target_function": "fully.qualified.module.func_name",
          "injection_marker_command": "python -c \"import sys; sys.path.insert(0, '.'); import path.to.file as M; M.func_name = lambda *a, **k: open('.codex/logs/.falsify_marker', 'w').write('called') or M._orig(*a, **k)\"",
          "measurement_command": "curl ...",
          "marker_path": ".codex/logs/.falsify_marker",
          "marker_required": true  # true = marker must exist after run; false = must NOT exist
        }
      }

    Implementation v1: simpler — dev declares a `marker_path` that the
    target function should touch when invoked (via temporary monkey-
    patch they manually apply). Falsifier just checks if the marker
    file was created after measurement_command ran. This avoids
    arbitrary code injection in the probe schema.
    """
    falsi = probe.get("falsification") or {}
    runner = falsi.get("runner") or {}
    measurement = runner.get("measurement_command")
    marker_rel = runner.get("marker_path")
    marker_required = bool(runner.get("marker_required", True))

    if not measurement or not marker_rel:
        print(f"[falsify] side_effect_inject runner missing measurement_command or marker_path",
              file=sys.stderr)
        return 2

    print(f"[falsify] probe: {probe.get('id')}")
    print(f"          type: side_effect_inject")
    print(f"          marker: {marker_rel} (required={marker_required})")
    print(f"          measurement: {measurement}")

    if dry_run:
        print("[falsify] DRY RUN — no command executed.")
        return 0

    marker_path = REPO_ROOT / marker_rel
    # Clear marker before run
    if marker_path.exists():
        try:
            marker_path.unlink()
        except OSError:
            pass

    seconds, raw = _run_command(measurement)
    print(f"[falsify] measurement done ({seconds}s)")

    marker_present = marker_path.exists()
    if marker_required and marker_present:
        print(f"[falsify] PROVEN: side-effect marker created — function was invoked.")
        return 0
    if not marker_required and not marker_present:
        print(f"[falsify] PROVEN: marker absent — function was NOT invoked (as required).")
        return 0

    print(f"[falsify] REFUTED: marker {'absent' if marker_required else 'present'} "
          f"contradicts marker_required={marker_required}.", file=sys.stderr)
    return 1


def _run_log_assertion(probe: Dict[str, Any], dry_run: bool) -> int:
    """log_assertion — run measurement_command, grep output for
    required/forbidden patterns.

    Probe schema:
      "falsification": {
        "type": "log_assertion",
        "runner": {
          "measurement_command": "curl ...",
          "required_patterns": ["pattern1", "pattern2"],   # all MUST appear
          "forbidden_patterns": ["error", "traceback"]      # none MAY appear
        }
      }
    """
    falsi = probe.get("falsification") or {}
    runner = falsi.get("runner") or {}
    measurement = runner.get("measurement_command")
    required_pats = runner.get("required_patterns") or []
    forbidden_pats = runner.get("forbidden_patterns") or []

    if not measurement:
        print(f"[falsify] log_assertion runner missing measurement_command", file=sys.stderr)
        return 2
    if not required_pats and not forbidden_pats:
        print(f"[falsify] log_assertion runner needs at least one required_/forbidden_patterns",
              file=sys.stderr)
        return 2

    print(f"[falsify] probe: {probe.get('id')}")
    print(f"          type: log_assertion")
    print(f"          required: {required_pats}")
    print(f"          forbidden: {forbidden_pats}")
    print(f"          measurement: {measurement}")

    if dry_run:
        print("[falsify] DRY RUN — no command executed.")
        return 0

    # Validate command first
    err = _validate_command(measurement)
    if err:
        print(f"[falsify] sandbox-reject: {err}", file=sys.stderr)
        return 2

    try:
        import shlex
        proc = subprocess.run(
            shlex.split(measurement, posix=True),
            shell=False, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print(f"[falsify] measurement TIMEOUT", file=sys.stderr)
        return 2
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    missing = [p for p in required_pats if not re.search(p, output)]
    seen_forbidden = [p for p in forbidden_pats if re.search(p, output)]

    if not missing and not seen_forbidden:
        print(f"[falsify] PROVEN: all required patterns matched, no forbidden patterns seen.")
        return 0

    if missing:
        print(f"[falsify] REFUTED: missing required pattern(s): {missing}", file=sys.stderr)
    if seen_forbidden:
        print(f"[falsify] REFUTED: forbidden pattern(s) appeared: {seen_forbidden}",
              file=sys.stderr)
    print(f"[falsify] output sample: {output[:300]}", file=sys.stderr)
    return 1


def _run_playwright(probe: Dict[str, Any], dry_run: bool) -> int:
    """playwright — spawn `npx playwright test <spec>` and parse JSON
    reporter output. PROVEN if all tests passed, REFUTED if any failed,
    ERROR (rc=2) if Playwright not installed / spec missing / sandbox reject.

    Probe schema:
      "falsification": {
        "type": "playwright",
        "description": "<human readable>",
        "runner": {
          "spec_file": "tests/e2e/load_views.spec.ts",  # required
          "browser": "chromium",                          # chromium|firefox|webkit (default: chromium)
          "timeout_ms": 30000,                            # per-test timeout (default: 30000)
          "headed": false,                                # default: false (CI mode)
          "workers": 1,                                   # parallel workers (default: 1 — sequential)
          "config": "playwright.config.ts"                # optional Playwright config path
        }
      }

    Verdict:
      - rc=0 (npx returns 0) AND no "failed" status in JSON report → PROVEN
      - rc=1 (npx returns non-zero) OR any "failed" status → REFUTED
      - sandbox reject / no spec → ERROR (rc=2)

    Note: this runner requires `npx` + a working Playwright install in the
    project root (or `playwright.config.ts` path specified). It does NOT
    install Playwright for you — that's a project-setup concern. If
    `npx playwright --version` fails, returns ERROR.
    """
    falsi = probe.get("falsification") or {}
    runner = falsi.get("runner") or {}
    spec_file = runner.get("spec_file")
    browser = runner.get("browser") or "chromium"
    timeout_ms = int(runner.get("timeout_ms") or 30000)
    headed = bool(runner.get("headed", False))
    workers = int(runner.get("workers") or 1)
    config_path = runner.get("config")

    if not spec_file:
        print(f"[falsify] playwright runner missing spec_file", file=sys.stderr)
        return 2
    if browser not in ("chromium", "firefox", "webkit"):
        print(f"[falsify] playwright runner: browser '{browser}' invalid "
              f"(must be chromium|firefox|webkit)", file=sys.stderr)
        return 2

    # Build command. We always shell=False; the binary is `npx`, sandbox-allowed.
    cmd_parts = ["npx", "playwright", "test", spec_file,
                 "--reporter=json",
                 f"--browser={browser}",
                 f"--timeout={timeout_ms}",
                 f"--workers={workers}"]
    if headed:
        cmd_parts.append("--headed")
    if config_path:
        cmd_parts.extend(["--config", config_path])

    print(f"[falsify] probe: {probe.get('id')}")
    print(f"          type: playwright")
    print(f"          spec: {spec_file}")
    print(f"          browser: {browser} (timeout={timeout_ms}ms, workers={workers})")
    print(f"          command: {' '.join(cmd_parts)}")

    if dry_run:
        print("[falsify] DRY RUN — no command executed.")
        return 0

    # Validate via sandbox (npx is whitelisted; spec_file should be safe path).
    cmd_str = " ".join(cmd_parts)
    err = _validate_command(cmd_str)
    if err:
        print(f"[falsify] sandbox-reject: {err}", file=sys.stderr)
        return 2

    spec_path = REPO_ROOT / spec_file
    if not spec_path.exists():
        print(f"[falsify] playwright spec not found: {spec_path}", file=sys.stderr)
        return 2

    try:
        proc = subprocess.run(
            cmd_parts, shell=False, capture_output=True, text=True,
            timeout=max(60, (timeout_ms / 1000) * 3),
            cwd=str(REPO_ROOT),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[falsify] playwright invocation failed: {e}", file=sys.stderr)
        print(f"          (is `npx` installed? is Playwright set up in project?)",
              file=sys.stderr)
        return 2

    output = (proc.stdout or "") + (proc.stderr or "")
    # Try to parse JSON reporter output for structured verdict.
    failed_count = 0
    passed_count = 0
    try:
        # Playwright JSON reporter outputs a single JSON object on stdout.
        report = json.loads(proc.stdout or "{}")
        for suite in (report.get("suites") or []):
            for spec in (suite.get("specs") or []):
                for test in (spec.get("tests") or []):
                    for result in (test.get("results") or []):
                        status = (result.get("status") or "").lower()
                        if status == "passed":
                            passed_count += 1
                        elif status in ("failed", "timedout"):
                            failed_count += 1
    except (json.JSONDecodeError, AttributeError):
        # Fallback: regex scan of output text
        passed_count = len(re.findall(r"\b(\d+)\s+passed", output))
        failed_count = len(re.findall(r"\b(\d+)\s+failed", output))

    print(f"[falsify] tests: {passed_count} ok / {failed_count} failed (rc={proc.returncode})")

    if proc.returncode == 0 and failed_count == 0:
        print(f"[falsify] PROVEN: all playwright tests succeeded.")
        return 0
    print(f"[falsify] REFUTED: playwright reports failures.", file=sys.stderr)
    if proc.stderr:
        print(f"[falsify] stderr sample:\n{proc.stderr[:500]}", file=sys.stderr)
    return 1


def main() -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(description="Empirical timing_perturb falsifier")
    parser.add_argument("--probe", required=True, help="probe id from acceptance-probes.json")
    parser.add_argument("--baseline-seconds", type=float, default=None,
                        help="Skip baseline measurement; use this value")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print config + injection diff, don't execute commands")
    args = parser.parse_args()

    probe = _load_probe(args.probe)
    if not probe:
        print(f"[falsify] probe '{args.probe}' not found in {PROBES_PATH}", file=sys.stderr)
        return 2

    falsi = probe.get("falsification") or {}
    ftype = (falsi.get("type") or "").lower()
    if ftype not in ("timing_perturb", "side_effect_inject", "log_assertion", "playwright"):
        print(f"[falsify] probe '{args.probe}' is type "
              f"'{falsi.get('type')}' — supported: timing_perturb, "
              f"side_effect_inject, log_assertion, playwright",
              file=sys.stderr)
        return 2

    if ftype == "side_effect_inject":
        return _run_side_effect_inject(probe, args.dry_run)
    if ftype == "log_assertion":
        return _run_log_assertion(probe, args.dry_run)
    if ftype == "playwright":
        return _run_playwright(probe, args.dry_run)

    # Fall through to timing_perturb (original implementation below).
    runner = falsi.get("runner") or {}
    target_file_rel = runner.get("target_file")
    pattern = runner.get("target_line_pattern")
    sleep_s = float(runner.get("sleep_seconds", 2))
    measurement = runner.get("measurement_command")
    # Sensible defaults — reduce DEV-fill burden:
    #   baseline_command defaults to measurement_command (run same endpoint twice)
    #   expected_delta_seconds defaults to sleep_seconds (physics: N sec sleep = N sec extra)
    #   tolerance defaults to 0.3s (curl jitter band)
    #   inject_after_match defaults to true (inject INSIDE function body)
    baseline_cmd = runner.get("baseline_command") or measurement
    expected_delta = float(runner.get("expected_delta_seconds") or sleep_s)
    tolerance = float(runner.get("tolerance") or 0.3)
    inject_after = bool(runner.get("inject_after_match", True))

    # Stub detection: measurement_command containing "TODO" = unfilled.
    if measurement and "TODO" in measurement.upper():
        print(f"[falsify] probe '{args.probe}' has TODO in measurement_command — "
              f"DEV must fill the runner before live falsifier.", file=sys.stderr)
        return 2

    missing = [
        k for k, v in [
            ("target_file", target_file_rel),
            ("target_line_pattern", pattern),
            ("measurement_command", measurement),
        ] if not v
    ]
    if missing:
        print(f"[falsify] runner config missing: {missing}", file=sys.stderr)
        return 2

    target_file = REPO_ROOT / target_file_rel
    if not target_file.exists():
        print(f"[falsify] target_file does not exist: {target_file}", file=sys.stderr)
        return 2

    print(f"[falsify] probe: {args.probe}")
    print(f"          target: {target_file_rel}")
    print(f"          pattern: {pattern!r}")
    print(f"          sleep: {sleep_s}s")
    print(f"          expected delta: {expected_delta}s ± {tolerance}s")

    if args.dry_run:
        print("[falsify] DRY RUN — no command executed.")
        return 0

    # Step 1: baseline
    if args.baseline_seconds is not None:
        baseline = args.baseline_seconds
        print(f"[falsify] baseline (provided): {baseline:.3f}s")
    else:
        print(f"[falsify] running baseline: {baseline_cmd!r}")
        baseline, raw = _run_command(baseline_cmd)
        if baseline is None:
            print(f"[falsify] baseline FAILED: {raw}", file=sys.stderr)
            return 2
        print(f"[falsify] baseline: {baseline:.3f}s")

    # Step 2: inject sleep
    try:
        backup = _inject_sleep(target_file, pattern, sleep_s, inject_after)
    except RuntimeError as e:
        print(f"[falsify] {e}", file=sys.stderr)
        return 2
    print(f"[falsify] injected time.sleep({sleep_s}) into {target_file_rel}")

    perturbed = None
    raw = ""
    try:
        # Give the runtime a moment to reload (Odoo dev mode typically picks up
        # changes via inotify; if not, dev may need --dev=all flag).
        time.sleep(0.5)
        # Step 3: measurement
        print(f"[falsify] running measurement: {measurement!r}")
        perturbed, raw = _run_command(measurement)
    finally:
        _restore(target_file, backup)
        print(f"[falsify] restored {target_file_rel}")

    if perturbed is None:
        print(f"[falsify] measurement FAILED: {raw}", file=sys.stderr)
        return 2
    print(f"[falsify] perturbed: {perturbed:.3f}s")

    # Step 4: compare
    delta = perturbed - baseline
    band_lo = expected_delta - tolerance
    band_hi = expected_delta + tolerance
    print(f"[falsify] delta: {delta:.3f}s (expect {expected_delta}±{tolerance}, "
          f"band [{band_lo:.2f}, {band_hi:.2f}])")
    if band_lo <= delta <= band_hi:
        print(f"[falsify] PROVEN: claim '{probe.get('description', args.probe)}' "
              f"is empirically supported (delta in expected band).")
        return 0
    else:
        print(f"[falsify] REFUTED: delta {delta:.3f}s is OUTSIDE expected band "
              f"[{band_lo:.2f}, {band_hi:.2f}].", file=sys.stderr)
        print(f"          → claim is likely FALSE; the suspect call may not "
              f"actually be blocking.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
