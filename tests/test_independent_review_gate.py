"""Tests for v0.31.0 independent_review_gate.py + tools/independent_review.py.

Covers the acceptance_evals of spec independent-review-subagent:
  us1-gate-blocks-done-without-review  -> test_blocks_done_*
  us2-independence-packet-code-assembled -> test_packet_sha_deterministic
  us3-convergence-terminates           -> test_jam_escape_*
  us4-token-skip-trivial-and-cache     -> test_skip_or_cache_*
Plus state-based trigger (ID-16), recursion guard, fail-open, dual spec layout.

Real fixtures: a tmp git repo with the CLI copied in (the gate shells to it).
NO synthetic envelope fields beyond the real Stop schema (lesson from the
inert-gate / R8 bugs: do not invent transcript fields).

Run: pytest tests/test_independent_review_gate.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "independent_review_gate.py"
CLI = TOOLKIT_ROOT / "tools" / "independent_review.py"
sys.path.insert(0, str(TOOLKIT_ROOT / "templates" / "claude" / "hooks"))
import independent_review_gate as gate  # noqa: E402


def _git(ws: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(ws), *a], capture_output=True, text=True,
                   encoding="utf-8", check=False)


def _mk_repo(tmp: Path, *, spec_status: str = "verified",
             spec_dir: str = "specs", config: dict | None = None,
             scope_loc: int = 0) -> Path:
    ws = tmp / "proj"
    (ws / spec_dir).mkdir(parents=True, exist_ok=True)
    (ws / ".agent-toolkit").mkdir(parents=True, exist_ok=True)
    (ws / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy(CLI, ws / "tools" / "independent_review.py")
    _git(ws, "init")
    _git(ws, "config", "user.email", "t@t")
    _git(ws, "config", "user.name", "t")
    (ws / "README.md").write_text("x", encoding="utf-8")
    (ws / "tools" / "feat_change.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-m", "base")
    # tracked modification → shows in `git diff HEAD` (untracked would not)
    (ws / "tools" / "feat_change.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    (ws / spec_dir / "feat.md").write_text(
        "---\nslug: feat\nstatus: " + spec_status + "\n---\n# feat\n", encoding="utf-8")
    cfg = {"enabled": True, "skip_trivial_loc": scope_loc,
           "feature_scope_regex": r"^tools/[^/]+\.py$"}
    if config:
        cfg.update(config)
    (ws / ".agent-toolkit" / "independent_review.json").write_text(
        json.dumps(cfg), encoding="utf-8")
    return ws


def _run(ws: Path, envelope: dict, strict: bool = False,
         home: Path | None = None) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if strict:
        env["AGENT_TOOLKIT_STRICT"] = "1"
    if home is not None:                       # override Path.home() in the subprocess
        env["HOME"] = str(home)                # POSIX expanduser('~')
        env["USERPROFILE"] = str(home)         # Windows: Path.home() reads USERPROFILE,
        #                                        NOT $HOME — set both for cross-platform.
    # encoding="utf-8" is REQUIRED: the hook emits UTF-8 (Vietnamese + `→`); on
    # Windows `text=True` would otherwise decode stdout with cp1252 and crash the
    # reader thread (UnicodeDecodeError) → r.stdout=None → TypeError downstream.
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(envelope),
                       capture_output=True, text=True, encoding="utf-8",
                       env=env, timeout=30)
    return r.returncode, r.stdout


def _env(ws: Path, **kw) -> dict:
    e = {"transcript_path": str(ws / "no.jsonl"), "stop_hook_active": False,
         "cwd": str(ws)}
    e.update(kw)
    return e


# ---------- trigger / config (ID-16) ----------

def test_disabled_is_silent(tmp_path):
    ws = _mk_repo(tmp_path, config={"enabled": False})
    rc, out = _run(ws, _env(ws))
    assert rc == 0 and '"decision"' not in out


def test_recursion_guard(tmp_path):
    ws = _mk_repo(tmp_path)
    rc, out = _run(ws, _env(ws, stop_hook_active=True))
    assert rc == 0 and '"decision"' not in out


def test_no_verified_spec_is_silent(tmp_path):
    ws = _mk_repo(tmp_path, spec_status="implementing")
    rc, out = _run(ws, _env(ws))
    assert rc == 0 and '"decision"' not in out


def test_state_trigger_finds_verified_spec_both_layouts(tmp_path):
    # ID portability fix: gate finds a verified spec under specs/ AND
    # .agent-toolkit/specs/.
    for d in ("specs", ".agent-toolkit/specs"):
        ws = _mk_repo(tmp_path / d.replace("/", "_"), spec_dir=d)
        assert gate._verified_spec(ws) == "feat"


# ---------- skip-trivial / cache (us4) ----------

def test_skip_or_cache_trivial_diff(tmp_path):
    ws = _mk_repo(tmp_path, scope_loc=9999)  # any diff < 9999 → skipped
    rc, out = _run(ws, _env(ws))
    assert rc == 0 and '"decision"' not in out


def test_skip_or_cache_cached_when_pass(tmp_path):
    # v0.32 BLOCKER-1: a 'pass' verdict is honored (cached, silent) ONLY when a
    # real reviewer sub-agent CONSUMED this packet-sha in the session — seed both.
    ws = _mk_repo(tmp_path)
    sha = gate._review_sha(ws, "feat")
    assert sha, "CLI should compute a sha"
    (ws / ".agent-toolkit" / ".independent_review.json").write_text(
        json.dumps({sha: {"verdict": "pass"}}), encoding="utf-8")
    home = tmp_path / "home"
    main_tp = _seed_subagent(home, ws, "sessC", "agent-1.jsonl",
                             f"Read packet. packet_sha {sha}. Review only from packet.")
    rc, out = _run(ws, _env(ws, transcript_path=str(main_tp)), strict=True, home=home)
    assert rc == 0 and '"decision"' not in out, out


def test_pass_without_consumption_not_honored(tmp_path):
    # v0.32 BLOCKER-1 regression: a self-written 'pass' verdict with NO reviewer
    # consumption evidence must NOT skip the gate (strict → block). One JSON line
    # can no longer forge a clean review.
    ws = _mk_repo(tmp_path)
    sha = gate._review_sha(ws, "feat")
    (ws / ".agent-toolkit" / ".independent_review.json").write_text(
        json.dumps({sha: {"verdict": "pass"}}), encoding="utf-8")
    rc, out = _run(ws, _env(ws), strict=True)
    assert '"decision": "block"' in out, out


def test_diff_loc_counts_untracked(tmp_path):
    # v0.32 BLOCKER-2 regression: a feature in NEW (untracked) files must NOT
    # score 0 LOC — `git diff HEAD` is blind to untracked, so count their lines.
    ws = _mk_repo(tmp_path)
    (ws / "tools" / "new_feat.py").write_text(
        "\n".join(f"line{i} = 1" for i in range(40)) + "\n", encoding="utf-8")
    cfg = json.loads((ws / ".agent-toolkit" / "independent_review.json").read_text())
    files = gate._scope_files(ws, cfg)
    assert "tools/new_feat.py" in files
    assert gate._diff_loc(ws, files) >= 40, "untracked feature lines must be counted"


# ---------- block (us1) ----------

def test_blocks_done_without_review_strict(tmp_path):
    ws = _mk_repo(tmp_path)
    rc, out = _run(ws, _env(ws), strict=True)
    assert '"decision": "block"' in out, out


def test_warn_does_not_block(tmp_path):
    ws = _mk_repo(tmp_path)  # default mode warn (no strict, no enforce_mode)
    rc, out = _run(ws, _env(ws))
    assert '"decision": "block"' not in out  # warn → additionalContext only


# ---------- jam-escape / convergence (us3) ----------

def test_jam_escape_emits_escalate(tmp_path):
    ws = _mk_repo(tmp_path, config={"block_streak_before_escalate": 1})
    rc, out = _run(ws, _env(ws), strict=True)
    assert "escalate" in out and "gap-cant-fix" in out, out


# ---------- packet determinism (us2) ----------

def test_packet_sha_deterministic(tmp_path):
    ws = _mk_repo(tmp_path)
    a = gate._review_sha(ws, "feat")
    b = gate._review_sha(ws, "feat")
    assert a and a == b


# ---------- fail-open ----------

def test_missing_cli_fails_open(tmp_path):
    ws = _mk_repo(tmp_path)
    (ws / "tools" / "independent_review.py").unlink()  # CLI gone
    rc, out = _run(ws, _env(ws), strict=True)
    assert rc == 0 and '"decision"' not in out  # no jam, fail-open


# ---------- regression: bugs caught by the feature reviewing ITSELF ----------

def test_normalize_comment_only_diff_stable():
    """B-rev3 (found by independent review of this feature): a comment-only
    diff edit must NOT change the review-sha (ID-18), and a real code change
    MUST. git-diff metadata (index/@@/path headers) is volatile → excluded."""
    import hashlib
    sys.path.insert(0, str(TOOLKIT_ROOT / "tools"))
    import independent_review as ir
    base = ("diff --git a/f b/f\nindex aaa..bbb 100644\n--- a/f\n+++ b/f\n"
            "@@ -1,1 +1,2 @@\n x = 1\n+y = 2")
    with_comment = ("diff --git a/f b/f\nindex aaa..ccc 100644\n--- a/f\n+++ b/f\n"
                    "@@ -1,2 +1,3 @@\n x = 1\n+# comment\n+y = 2")
    code_change = ("diff --git a/f b/f\nindex aaa..ddd 100644\n--- a/f\n+++ b/f\n"
                   "@@ -1,1 +1,2 @@\n x = 1\n+z = 99")
    def h(t):
        return hashlib.sha256(ir.normalize_for_hash(t).encode()).hexdigest()
    assert h(base) == h(with_comment), "comment-only edit must keep sha stable"
    assert h(base) != h(code_change), "real code change must change sha"


def test_escalate_writes_terminal_verdict(tmp_path):
    """B-rev1/B-rev2 (found by self-review): convergence escalation must write a
    TERMINAL verdict so a later same-sha Stop short-circuits (no re-escalate
    loop). Here we assert the gate, once it has escalated, treats verdict
    'escalated' as terminal (returns 0, no block)."""
    ws = _mk_repo(tmp_path)
    sha = gate._review_sha(ws, "feat")
    assert sha
    (ws / ".agent-toolkit" / ".independent_review.json").write_text(
        json.dumps({sha: {"verdict": "escalated", "round": 5}}), encoding="utf-8")
    rc, out = _run(ws, _env(ws), strict=True)
    assert rc == 0 and '"decision"' not in out  # terminal → allow, no re-block


def _seed_subagent(home, ws, sess, fname, prompt_text):
    import re
    enc = re.sub(r"[^A-Za-z0-9]", "-", str(ws.resolve()))
    proj = home / ".claude" / "projects" / enc
    main_tp = proj / (sess + ".jsonl")
    main_tp.parent.mkdir(parents=True, exist_ok=True)
    main_tp.write_text("\n".join(json.dumps(m) for m in [
        {"type": "user", "message": {"role": "user",
         "content": [{"type": "text", "text": "go"}]}},
        {"type": "assistant", "message": {"role": "assistant",
         "content": [{"type": "tool_use", "name": "Task", "id": "t1", "input": {}}]}},
    ]), encoding="utf-8")
    sub = proj / sess / "subagents" / fname
    sub.parent.mkdir(parents=True, exist_ok=True)
    sha_echo = prompt_text.split("packet_sha ")[-1].split()[0] if "packet_sha " in prompt_text else ""
    sub.write_text("\n".join(json.dumps(m) for m in [
        {"type": "user", "message": {"role": "user",
         "content": [{"type": "text", "text": prompt_text}]}},
        # reviewer ECHOES the sha in an assistant turn (ID-12 consumption proof)
        {"type": "assistant", "message": {"role": "assistant",
         "content": [{"type": "text", "text": f"packet_sha {sha_echo} — reviewing."}]}},
    ]), encoding="utf-8")
    return main_tp


def test_reviewer_evidence_positive_purity_and_session_scope(tmp_path, monkeypatch):
    """M4 (positive path) + M2 (purity = small prompt) + M3 (session scope).
    Found missing by the feature's self-review."""
    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "home"
    monkeypatch.setattr(gate.Path, "home", staticmethod(lambda: home))
    sha = "a" * 64
    cfg = {"reviewer_prompt_max_bytes": 4096}
    # (1) clean reviewer this session: small prompt echoing sha → evidence True
    main_tp = _seed_subagent(home, ws, "sessX", "agent-1.jsonl",
                             f"Read packet. packet_sha {sha}. Review only from packet.")
    env = {"transcript_path": str(main_tp), "cwd": str(ws)}
    assert gate._reviewer_evidence(ws, env, sha, cfg) is True
    # (2) tainted: bloated prompt (injected context) → evidence False (M2)
    _seed_subagent(home, ws, "sessX", "agent-1.jsonl",
                   f"packet_sha {sha} " + "X" * 6000)
    assert gate._reviewer_evidence(ws, env, sha, cfg) is False
    # (3) cross-session: reviewer transcript under a DIFFERENT session → False (M3)
    _seed_subagent(home, ws, "OTHERsess", "agent-9.jsonl",
                   f"Read packet. packet_sha {sha}.")
    env2 = {"transcript_path": str(home / ".claude" / "projects" /
            __import__("re").sub(r"[^A-Za-z0-9]", "-", str(ws.resolve())) /
            "sessX.jsonl"), "cwd": str(ws)}
    # sessX has only the tainted agent now → still False; OTHER session must not count
    assert gate._reviewer_evidence(ws, env2, sha, cfg) is False


def test_reviewer_evidence_requires_assistant_echo_not_tool_result(tmp_path, monkeypatch):
    """R2-MEDIUM regression (found in self-review round 2): the sha appearing in
    a Read tool_result (the packet the sub-agent Read) must NOT count as
    consumption — only an ASSISTANT echo does (ID-12)."""
    import re
    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "home"
    monkeypatch.setattr(gate.Path, "home", staticmethod(lambda: home))
    sha = "b" * 64
    enc = re.sub(r"[^A-Za-z0-9]", "-", str(ws.resolve()))
    proj = home / ".claude" / "projects" / enc
    main_tp = proj / "sX.jsonl"
    main_tp.parent.mkdir(parents=True, exist_ok=True)
    main_tp.write_text("\n".join(json.dumps(m) for m in [
        {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "go"}]}},
        {"type": "assistant", "message": {"role": "assistant",
         "content": [{"type": "tool_use", "name": "Task", "id": "t", "input": {}}]}},
    ]), encoding="utf-8")
    sub = proj / "sX" / "subagents" / "agent-1.jsonl"
    sub.parent.mkdir(parents=True, exist_ok=True)
    # sha present ONLY in a tool_result (Read of packet) + assistant has NO echo
    sub.write_text("\n".join(json.dumps(m) for m in [
        {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "Read packet."}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "r1", "content": f"packet_sha: {sha}"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok done"}]}},
    ]), encoding="utf-8")
    env = {"transcript_path": str(main_tp), "cwd": str(ws)}
    assert gate._reviewer_evidence(ws, env, sha, {"reviewer_prompt_max_bytes": 4096}) is False
