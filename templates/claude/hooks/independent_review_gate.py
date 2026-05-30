#!/usr/bin/env python3
"""independent_review_gate.py — Stop gate (v0.31.0 independent-review).

Blocks a done-claim on a `status: verified` spec until a FRESH-CONTEXT reviewer
sub-agent has reviewed the current diff and 0 BLOCKERs remain. Trust-model:
verify EVIDENCE, never prose (mirrors evidence_audit / pass_contract).

Parts (one file, three logical phases):
  T5 — trigger by STATE (spec status=verified + feature-scope diff; ID-16,
       NOT done-text regex) · skip-trivial (ID-7) · sha-cache (ID-5).
  T6 — verify 3-layer (Task tool_use this turn + sub-agent transcript that
       consumed packet-sha + tail-capped read, ID-3/12/22) · packet-purity
       (ID-14) · jam-escape (ID-17).
  T7 — convergence: 0-BLOCKER, two counters non_progress_streak /
       absolute_round_ceiling (ID-27) · escalate via gap-cant-fix (ID-4/20).

review-sha is computed by the CLI (`tools/independent_review.py emit-context`,
single source of ID-18 algorithm) — the gate shells to it, never re-implements.
WARN default; strict→block (ID-3/11). NEVER permanent-jams (ID-17). Fail-open.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    wrap_utf8_stdio, run_main_safe, emit_fire_event, emit_stop_block,
    emit_stop_context, get_enforce_mode, read_jsonl_transcript,
    split_current_turn,
)

HOOK = "independent_review_gate.py"
CONFIG_REL = ".agent-toolkit/independent_review.json"
STATE_REL = ".agent-toolkit/.independent_review.json"
DEFAULT_SCOPE_RE = (
    r"(?:(?:models|controllers|wizard|wizards|jobs)/[^/]+\.py$)"
    r"|(?:^(?:tools|lib)/[^/]+\.py$)|(?:templates/claude/hooks/[^/]+\.py$)"
)
DONE_STATUS = ("verified",)            # ID-16 state-based done-boundary
_STATUS_RE = re.compile(r"^status:\s*(\S+)", re.MULTILINE)
_SLUG_RE = re.compile(r"^slug:\s*(\S+)", re.MULTILINE)


def _load(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else default
    except (OSError, json.JSONDecodeError):
        return default


def _save_state(ws: Path, st: Dict[str, Any]) -> None:
    try:
        (ws / STATE_REL).write_text(json.dumps(st, indent=2), encoding="utf-8")
    except OSError:
        pass


def _git(ws: Path, *a: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(ws), *a],
                           capture_output=True, text=True, timeout=10)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _scope_files(ws: Path, cfg: Dict[str, Any]) -> List[str]:
    rx = re.compile(cfg.get("feature_scope_regex") or DEFAULT_SCOPE_RE)
    files = set(_git(ws, "diff", "HEAD", "--name-only").splitlines())
    files.update(_git(ws, "ls-files", "--others", "--exclude-standard").splitlines())
    return [f for f in files if f.strip() and rx.search(f)]


def _diff_loc(ws: Path, files: List[str]) -> int:
    if not files:
        return 0
    d = _git(ws, "diff", "HEAD", "--", *files)
    return sum(1 for ln in d.splitlines()
               if ln[:1] in "+-" and ln[:2] not in ("++", "--"))


def _verified_spec(ws: Path) -> Optional[str]:
    # Both layouts: repo/dogfood uses `specs/`; consumer init uses
    # `.agent-toolkit/specs/<branch>/`. Check both (portability).
    best, best_mt = None, -1.0
    for sd in (ws / "specs", ws / ".agent-toolkit" / "specs"):
        if not sd.is_dir():
            continue
        for p in sd.rglob("*.md"):
            if p.name.endswith((".tasks.md", ".verify_report.md", ".implement-noted.md")):
                continue
            try:
                txt = p.read_text(encoding="utf-8")
            except OSError:
                continue
            m = _STATUS_RE.search(txt)
            if not m or m.group(1).lower() not in DONE_STATUS:
                continue
            mt = p.stat().st_mtime
            if mt > best_mt:
                s = _SLUG_RE.search(txt)
                best, best_mt = (s.group(1) if s else p.stem), mt
    return best


def _find_cli(ws: Path) -> Optional[Path]:
    for c in (ws / "tools" / "independent_review.py",
              ws / ".claude" / "tools" / "independent_review.py"):
        if c.exists():
            return c
    return None


def _review_sha(ws: Path, slug: str) -> Optional[str]:
    """Shell to the CLI — single source of the ID-18 hash. None if unavailable."""
    cli = _find_cli(ws)
    if cli is None:
        return None
    try:
        r = subprocess.run([sys.executable, str(cli), "emit-context", slug,
                            "--project-dir", str(ws)],
                           capture_output=True, text=True, timeout=15)
        return json.loads(r.stdout).get("packet_sha") if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _first_user_text(msgs: List[Dict[str, Any]]) -> str:
    """Text of the sub-agent's FIRST user message — i.e. the spawn prompt."""
    for rec in msgs:
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else rec
        if (msg.get("role") or rec.get("type")) != "user":
            continue
        c = msg.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\n".join(b.get("text", "") for b in c
                             if isinstance(b, dict) and b.get("type") == "text")
        return ""
    return ""


def _reviewer_evidence(ws: Path, envelope: Dict[str, Any], sha: str,
                       cfg: Dict[str, Any]) -> bool:
    """3-layer (ID-3/12/14/22): (A) a Task/Agent tool_use THIS turn, (B) a
    session-scoped sub-agent transcript that CONSUMED the packet-sha, (C)
    packet-purity — the sub-agent's spawn prompt (first user msg) must be SMALL.
    The skill passes the packet by PATH (the sub-agent Reads it), so a legit
    prompt is tiny; a bloated first-user msg = injected reasoning/context =
    tainted (ID-14 anti-leak). Measures the PROMPT, not the whole transcript."""
    tp = envelope.get("transcript_path")
    task_used = False
    if tp and Path(tp).exists():
        for rec in split_current_turn(read_jsonl_transcript(Path(tp))):
            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            content = msg.get("content")
            if isinstance(content, list):
                for blk in content:
                    if (isinstance(blk, dict) and blk.get("type") == "tool_use"
                            and blk.get("name") in ("Task", "Agent")):
                        task_used = True
    if not task_used or not tp:
        return False
    max_prompt = int(cfg.get("reviewer_prompt_max_bytes", 4096))
    enc = re.sub(r"[^A-Za-z0-9]", "-", str(ws.resolve()))
    proj = Path.home() / ".claude" / "projects" / enc
    # M3 fix: scope to the CURRENT session's sub-agents only — `tp` is
    # `<proj>/<sessionUUID>.jsonl`; sub-agents live under `<sessionUUID>/subagents/`.
    sub_dir = proj / Path(tp).stem / "subagents"
    if not sub_dir.is_dir():
        return False
    for sub in sub_dir.glob("*.jsonl"):
        msgs = read_jsonl_transcript(sub)
        if not msgs:
            continue
        # R2-MEDIUM fix (ID-12): consumption = the reviewer ECHOED the sha in an
        # ASSISTANT text turn — NOT merely that the sha appears anywhere (it also
        # appears inside the Read tool_result of the packet, which a no-op
        # sub-agent would produce). Require the echo.
        echoed = False
        for m in msgs:
            mm = m.get("message") if isinstance(m.get("message"), dict) else m
            if (mm.get("role") or m.get("type")) != "assistant":
                continue
            c = mm.get("content")
            txt = c if isinstance(c, str) else (
                " ".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
                if isinstance(c, list) else "")
            if sha in txt:
                echoed = True
                break
        if not echoed:
            continue                          # this sub-agent didn't review our packet
        # M2: anti-leak = small spawn prompt (not whole-transcript size).
        if len(_first_user_text(msgs).encode("utf-8")) <= max_prompt:
            return True                       # clean reviewer ran this cycle
        # else: bloated prompt → injected context → not valid → block (re-review clean)
    return False


def _verdict_for(ws: Path, sha: str) -> str:
    """Read artifact verdict for this review-sha. 'open' if absent."""
    rec = (_load(ws / STATE_REL, {}) or {}).get(sha) or {}
    return rec.get("verdict", "open")


def main() -> int:
    wrap_utf8_stdio()
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if envelope.get("stop_hook_active"):      # primary recursion break
        return 0
    ws = Path(envelope.get("cwd") or ".").resolve()
    cfg = _load(ws / CONFIG_REL, {})
    if not cfg.get("enabled", False):
        emit_fire_event(HOOK, "off")
        return 0

    # ---- T5: STATE trigger ----
    slug = _verified_spec(ws)
    if slug is None:                          # not at done-boundary → silent
        emit_fire_event(HOOK, "ok")
        return 0
    files = _scope_files(ws, cfg)
    if not files or _diff_loc(ws, files) <= int(cfg.get("skip_trivial_loc", 200)):
        emit_fire_event(HOOK, "skipped")
        return 0
    sha = _review_sha(ws, slug)
    if sha is None:                           # CLI missing → fail-open, don't jam
        emit_fire_event(HOOK, "warn")
        return 0
    state = _load(ws / STATE_REL, {}) or {}
    verdict = _verdict_for(ws, sha)
    if verdict == "pass":                     # sha-cache: reviewed & clean
        emit_fire_event(HOOK, "cached")
        return 0
    if verdict == "escalated":                # terminal — already handed to DEV
        emit_fire_event(HOOK, "ok")           # short-circuit BEFORE re-evidence
        return 0

    mode = get_enforce_mode(ws, "independent_review_gate", default="warn")

    # ---- T6: verify reviewer evidence + jam-escape ----
    rec = state.get(sha) or {"round": 0, "non_progress": 0, "block_streak": 0}
    if not _reviewer_evidence(ws, envelope, sha, cfg):
        rec["block_streak"] = int(rec.get("block_streak", 0)) + 1
        state[sha] = rec
        _save_state(ws, state)
        # ID-17 jam-escape: too many blocks w/o a valid reviewer → degrade+escalate
        if rec["block_streak"] >= int(cfg.get("block_streak_before_escalate", 3)):
            emit_fire_event(HOOK, "escalate")
            emit_stop_context(
                f"[independent-review] escalate: reviewer chưa chạy được sau "
                f"{rec['block_streak']} lần cho spec '{slug}'. Đề nghị DEV: "
                f"`gap-cant-fix: independent-review reviewer-unavailable`.")
        msg = (f"[independent-review] done-claim trên spec '{slug}' (verified) "
               f"cần review độc lập. Chạy skill `independent-review` / "
               f"`/review-independent {slug}` (spawn reviewer sub-agent với packet "
               f"sha {sha[:8]}), rồi mới chốt done.")
        emit_fire_event(HOOK, "block" if mode == "block" else "warn")
        emit_stop_block(msg) if mode == "block" else emit_stop_context(msg)
        return 0

    # ---- T7: convergence — PER-SPEC counters (M1 fix) ----
    # Per-sha `rec` resets every round (a fix changes review_sha), so round /
    # non_progress must live per-spec. non_progress increments only on
    # OSCILLATION (every current BLOCKER fingerprint was already seen → "fix"
    # didn't make progress); a genuinely NEW blocker in another area is legit
    # (ID-20) → reset. blocker_fingerprints come from the reviewer artifact.
    spec_key = "__spec__::" + slug
    srec = state.get(spec_key) or {"round": 0, "non_progress": 0, "seen_fp": []}
    cur_fp = (state.get(sha) or {}).get("blocker_fingerprints") or []
    seen = set(srec.get("seen_fp") or [])
    new_fp = [f for f in cur_fp if f not in seen]
    if sha != srec.get("last_sha"):           # count REVIEW CYCLES (diff changed),
        srec["round"] = int(srec.get("round", 0)) + 1   # not every Stop — avoids
        srec["last_sha"] = sha                # premature escalate while fixing.
        if cur_fp and not new_fp:             # oscillation: nothing new fixed
            srec["non_progress"] = int(srec.get("non_progress", 0)) + 1
        else:                                 # new/legit blockers → progressing
            srec["non_progress"] = 0
            srec["seen_fp"] = sorted(seen | set(cur_fp))
    ceil = int(cfg.get("absolute_round_ceiling", 5))
    streak = int(cfg.get("non_progress_streak", 3))
    if srec["round"] >= ceil or srec["non_progress"] >= streak:
        # B-rev1/B-rev2 fix: TERMINAL verdict (later same-sha Stop short-circuits,
        # no re-escalate loop) + emit per MODE. Reset the per-spec counter so a
        # later DEV fix (new sha) starts a fresh cycle, not an instant re-escalate.
        rec["verdict"] = "escalated"
        state[sha] = rec
        state[spec_key] = {"round": 0, "non_progress": 0, "seen_fp": []}
        _save_state(ws, state)
        emit_fire_event(HOOK, "escalate")
        emsg = (f"[independent-review] escalate: spec '{slug}' chưa hội tụ sau "
                f"{srec['round']} vòng → DEV xử `gap-cant-fix: independent-review "
                f"non-convergent`.")
        emit_stop_block(emsg) if mode == "block" else emit_stop_context(emsg)
        return 0
    state[sha] = rec
    state[spec_key] = srec
    _save_state(ws, state)
    # tainted-review (ID-14) or open-with-blockers → block/warn per mode
    reason = ("tainted-review (reviewer có thể đã nhận thêm context ngoài packet)"
              if verdict == "tainted-review" else "còn BLOCKER độc-lập chưa fix")
    msg = (f"[independent-review] {reason} — spec '{slug}'. Xem "
           f".agent-toolkit/.independent_review.json[{sha[:8]}], fix BLOCKER rồi re-review.")
    emit_fire_event(HOOK, "block" if mode == "block" else "warn")
    emit_stop_block(msg) if mode == "block" else emit_stop_context(msg)
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
