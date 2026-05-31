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
    loc = sum(1 for ln in d.splitlines()
              if ln[:1] in "+-" and ln[:2] not in ("++", "--"))
    # BLOCKER-2 fix (v0.32): untracked files don't appear in `git diff HEAD`, so a
    # whole feature in NEW files would score 0 LOC and be treated as trivial/skipped.
    # Count their lines too (scope already includes them via `ls-files --others`).
    untracked = set(_git(ws, "ls-files", "--others", "--exclude-standard").splitlines())
    for f in files:
        if f in untracked:
            try:
                loc += sum(1 for _ in (ws / f).open(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return loc


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


def _has_review_task_this_turn(envelope: Dict[str, Any]) -> bool:
    """Layer A (ID-3): a Task/Agent tool_use in the CURRENT turn."""
    tp = envelope.get("transcript_path")
    if not tp or not Path(tp).exists():
        return False
    for rec in split_current_turn(read_jsonl_transcript(Path(tp))):
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        content = msg.get("content")
        if isinstance(content, list):
            for blk in content:
                if (isinstance(blk, dict) and blk.get("type") == "tool_use"
                        and blk.get("name") in ("Task", "Agent")):
                    return True
    return False


def _reviewer_consumed_sha(ws: Path, envelope: Dict[str, Any], sha: str,
                           cfg: Dict[str, Any]) -> bool:
    """Layers B+C (ID-12/14, session-scoped, turn-AGNOSTIC): a sub-agent transcript
    in the CURRENT session ECHOED the packet-sha in an ASSISTANT turn (consumption)
    AND its spawn prompt (first user msg) is SMALL (purity — a bloated prompt =
    injected context = tainted, ID-14). This is the un-forgeable-ish anchor that a
    real reviewer reviewed THIS exact packet; it survives across turns, so a
    prior-turn review still backs a later done-claim (the cache path). Forging it
    needs a fabricated session sub-agent jsonl — far harder than one verdict line."""
    tp = envelope.get("transcript_path")
    if not tp:
        return False
    max_prompt = int(cfg.get("reviewer_prompt_max_bytes", 4096))
    enc = re.sub(r"[^A-Za-z0-9]", "-", str(ws.resolve()))
    proj = Path.home() / ".claude" / "projects" / enc
    # M3: scope to the CURRENT session's sub-agents only — `tp` is
    # `<proj>/<sessionUUID>.jsonl`; sub-agents live under `<sessionUUID>/subagents/`.
    sub_dir = proj / Path(tp).stem / "subagents"
    if not sub_dir.is_dir():
        return False
    for sub in sub_dir.glob("*.jsonl"):
        msgs = read_jsonl_transcript(sub)
        if not msgs:
            continue
        # R2-MEDIUM (ID-12): consumption = reviewer ECHOED the sha in an ASSISTANT
        # turn — NOT merely the sha appearing in a Read tool_result of the packet.
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
            continue
        # M2: anti-leak = small spawn prompt (not whole-transcript size).
        if len(_first_user_text(msgs).encode("utf-8")) <= max_prompt:
            return True
    return False


def _reviewer_evidence(ws: Path, envelope: Dict[str, Any], sha: str,
                       cfg: Dict[str, Any]) -> bool:
    """Full 3-layer evidence: (A) a Task/Agent spawn THIS turn AND (B+C) a session
    reviewer transcript that consumed this packet-sha purely. Kept for the
    same-turn review→done path + the test contract; the cache path uses
    _reviewer_consumed_sha alone (turn-agnostic) so a prior-turn review still counts."""
    return (_has_review_task_this_turn(envelope)
            and _reviewer_consumed_sha(ws, envelope, sha, cfg))


def _verdict_for(ws: Path, sha: str) -> str:
    """Read artifact verdict for this review-sha. 'open' if absent."""
    rec = (_load(ws / STATE_REL, {}) or {}).get(sha) or {}
    return rec.get("verdict", "open")


# F4.2 (T9): the reviewer states its OWN verdict in its (harness-written,
# no-subagents-forge-protected) transcript as `REVIEW-VERDICT: <packet_sha> PASS|FAIL`.
# sha floor 8 (review round-1 LOW): a 6-hex prefix collides too cheaply.
_REVIEW_VERDICT_RE = re.compile(
    r"REVIEW-VERDICT\s*:\s*([0-9a-f]{8,64})\s+(PASS|FAIL)\b", re.IGNORECASE)


def _reviewer_verdict_from_transcript(ws: Path, envelope: Dict[str, Any], sha: str,
                                      cfg: Dict[str, Any]) -> Optional[str]:
    """F4.2 (T9, downscoped to consumption-required): read the verdict FROM the
    reviewer's own pure sub-agent transcript (`REVIEW-VERDICT: <sha> PASS|FAIL`),
    NOT the main-agent-writable `.independent_review.json`. Returns 'fail' if ANY
    matching reviewer emitted FAIL for this sha (review round-1 HIGH-2: FAIL-
    PRECEDENCE — scan ALL session sub-agents so a second 'PASS' echo-bot can't
    shadow a genuine reviewer FAIL), else 'pass' if ≥1 PASS, else None.

    KNOWN RESIDUAL (review round-1 HIGH-1, = the spec's v0.35 crypto gap): the
    packet-sha is NOT secret (the main agent derives it from the in-repo CLI), so a
    cooperative-but-lazy agent can still manufacture a clean PASS by spawning a
    throwaway echo sub-agent that prints `REVIEW-VERDICT: <sha> PASS`. consumption-
    required only proves *a* sub-agent saw the sha, not that it reviewed. Closing
    this needs a per-Stop nonce the gate injects OR a crypto-signed verdict — v0.35.
    What F4.2 DOES close: a main agent that writes `pass` over a REAL reviewer's FAIL
    (FAIL-precedence above) — the meaningful forged-verdict case."""
    tp = envelope.get("transcript_path")
    if not tp:
        return None
    enc = re.sub(r"[^A-Za-z0-9]", "-", str(ws.resolve()))
    sub_dir = Path.home() / ".claude" / "projects" / enc / Path(tp).stem / "subagents"
    if not sub_dir.is_dir():
        return None
    max_prompt = int(cfg.get("reviewer_prompt_max_bytes", 4096))
    found_pass = False
    for sub in sub_dir.glob("*.jsonl"):
        msgs = read_jsonl_transcript(sub)
        if not msgs:
            continue
        # purity (same anchor as _reviewer_consumed_sha): a small spawn prompt
        if len(_first_user_text(msgs).encode("utf-8")) > max_prompt:
            continue
        for m in msgs:
            mm = m.get("message") if isinstance(m.get("message"), dict) else m
            if (mm.get("role") or m.get("type")) != "assistant":
                continue
            c = mm.get("content")
            txt = c if isinstance(c, str) else (
                " ".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
                if isinstance(c, list) else "")
            for vm in _REVIEW_VERDICT_RE.finditer(txt):
                token_sha = vm.group(1).lower()
                # tie the verdict to THIS packet — token sha must be a prefix of
                # (or equal to) the current sha, so a stale verdict can't be replayed.
                if sha.lower().startswith(token_sha) or token_sha == sha.lower():
                    if vm.group(2).upper() == "FAIL":
                        return "fail"          # FAIL-precedence — any FAIL wins
                    found_pass = True
    return "pass" if found_pass else None


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
    if verdict == "escalated":                # terminal — already handed to DEV
        emit_fire_event(HOOK, "ok")           # short-circuit BEFORE re-evidence
        return 0

    mode = get_enforce_mode(ws, "independent_review_gate", default="warn")

    # ---- T6: verify reviewer evidence + jam-escape ----
    # BLOCKER-1 fix (v0.32): "reviewed?" = a real reviewer sub-agent CONSUMED this
    # packet-sha (session-scoped, un-forgeable-ish), NOT a bare agent-written
    # verdict. A 'pass' verdict is honored ONLY with that consumption evidence —
    # one self-written `{"<sha>":{"verdict":"pass"}}` line no longer skips the gate.
    consumed = _reviewer_consumed_sha(ws, envelope, sha, cfg)
    # F4.2 (T9): a cached 'pass' is honored UNLESS the reviewer's OWN transcript says
    # FAIL. rv=='pass' (reviewer-confirmed) or rv is None (no token → consumption-only
    # warn-capable fallback; the throwaway-echo residual = v0.35, see the helper).
    rv = _reviewer_verdict_from_transcript(ws, envelope, sha, cfg) if consumed else None
    if verdict == "pass" and consumed and rv != "fail":
        emit_fire_event(HOOK, "cached")
        return 0
    rec = state.get(sha) or {"round": 0, "non_progress": 0, "block_streak": 0}
    # `forged` = artifact says 'pass' but the reviewer transcript says FAIL. It shares
    # the not-consumed jam-escape path (review round-1 MED-1) so a forged verdict can
    # never loop forever — block_streak escalates exactly like a missing reviewer.
    forged = (verdict == "pass" and consumed and rv == "fail")
    if not consumed or forged:
        rec["block_streak"] = int(rec.get("block_streak", 0)) + 1
        state[sha] = rec
        _save_state(ws, state)
        # ID-17 jam-escape: too many blocks w/o progress → degrade+escalate (terminal).
        if rec["block_streak"] >= int(cfg.get("block_streak_before_escalate", 3)):
            emit_fire_event(HOOK, "escalate")
            emit_stop_context(
                f"[independent-review] escalate: "
                f"{'verdict bị ghi đè' if forged else 'reviewer chưa chạy được'} sau "
                f"{rec['block_streak']} lần cho spec '{slug}'. Đề nghị DEV: "
                f"`gap-cant-fix: independent-review "
                f"{'forged-verdict' if forged else 'reviewer-unavailable'}`.")
        msg = ((f"[independent-review] artifact verdict='pass' cho '{slug}' NHƯNG "
                f"transcript reviewer (sha {sha[:8]}) ghi `REVIEW-VERDICT: FAIL` — "
                f"verdict bị main-agent ghi đè. Sửa BLOCKER reviewer nêu rồi re-review; "
                f"KHÔNG tự ghi 'pass' vào .independent_review.json.") if forged else
               (f"[independent-review] done-claim trên spec '{slug}' (verified) cần "
                f"review độc lập. Chạy skill `independent-review` / "
                f"`/review-independent {slug}` (spawn reviewer sub-agent với packet "
                f"sha {sha[:8]}), rồi mới chốt done."))
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
    # P2#10 (v0.32): absolute Stop hard-cap — guarantees termination even if
    # round/non_progress never advance (flat sha + evidence present + no
    # fingerprints would otherwise block every Stop). Defense-in-depth atop
    # stop_hook_active + the per-cycle counters.
    srec["total_stops"] = int(srec.get("total_stops", 0)) + 1
    hard_cap = int(cfg.get("absolute_stop_hard_cap", 8))
    ceil = int(cfg.get("absolute_round_ceiling", 5))
    streak = int(cfg.get("non_progress_streak", 3))
    if (srec["round"] >= ceil or srec["non_progress"] >= streak
            or srec["total_stops"] >= hard_cap):
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
