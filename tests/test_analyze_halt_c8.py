"""v0.34 T4 — analyze_halt_gate C8: mechanical zero-eval feature-spec HALT (F1.2).

Run the hook as a subprocess (no import side-effects; UTF-8 in/out for Windows).
The C8 gate reads the slug from `.autonomy_active.json`, inspects the spec
frontmatter directly (NOT an agent-authored verdict), and blocks source edits for
a feature-scope spec with 0 `acceptance_evals`. Block-CAPABLE @ WARN.

Acceptance eval: ev1c-noevals-blocks-implement.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = TOOLKIT_ROOT / "templates" / "claude" / "hooks" / "analyze_halt_gate.py"
PYTHON = sys.executable


def _mk_ws(tmp: Path, slug: str = "feat", fm_extra=(), evals: bool = False) -> Path:
    ws = tmp / "proj"
    spec_dir = ws / ".agent-toolkit" / "specs" / "main" / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"slug: {slug}"]
    lines += list(fm_extra)
    if evals:
        lines += ["acceptance_evals:",
                  "  - id: us1-x", "    story: x", "    grader: data"]
    lines += ["---", "# body"]
    (spec_dir / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ws


def _autonomy(ws: Path, slug: str = "feat", expires=None) -> None:
    d = {"spec": slug, "approved_by": "/implement"}
    if expires is not None:
        d["expires_at"] = expires
    (ws / ".agent-toolkit" / ".autonomy_active.json").write_text(
        json.dumps(d), encoding="utf-8")


def _src(ws: Path) -> Path:
    f = ws / "src" / "feature.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    return f


def _run(ws: Path, file_path: Path, strict: bool = False):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("AGENT_TOOLKIT_DISABLE", None)
    if strict:
        env["AGENT_TOOLKIT_STRICT"] = "1"
    else:
        env.pop("AGENT_TOOLKIT_STRICT", None)
    envelope = {"tool_input": {"file_path": str(file_path)}, "cwd": str(ws)}
    p = subprocess.run([PYTHON, str(HOOK)], input=json.dumps(envelope).encode("utf-8"),
                       capture_output=True, timeout=15, env=env)
    return (p.returncode,
            p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def test_zero_eval_feature_blocks_strict(tmp_path):
    # ev1c: feature-scope spec, 0 frontmatter evals, /implement active → block.
    ws = _mk_ws(tmp_path, evals=False)
    _autonomy(ws)
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision": "block"' in out, (out, err)
    assert "eval-define" in out


def test_zero_eval_feature_warns_default(tmp_path):
    # block-CAPABLE @ WARN: default mode only warns (stderr), never blocks.
    ws = _mk_ws(tmp_path, evals=False)
    _autonomy(ws)
    rc, out, err = _run(ws, _src(ws), strict=False)
    assert '"decision"' not in out, out
    assert "eval-define" in err or "acceptance_evals" in err


def test_spec_with_frontmatter_evals_allows_strict(tmp_path):
    # Spec that DOES declare acceptance_evals → C8 does not fire.
    ws = _mk_ws(tmp_path, evals=True)
    _autonomy(ws)
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision"' not in out, (out, err)


def test_non_feature_spec_allows_strict(tmp_path):
    # `feature_scope: false` → non-feature → C8 exempt (blast-radius limit).
    ws = _mk_ws(tmp_path, fm_extra=("feature_scope: false",), evals=False)
    _autonomy(ws)
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision"' not in out, (out, err)


def test_feature_kind_meta_allows_strict(tmp_path):
    ws = _mk_ws(tmp_path, fm_extra=("feature_kind: meta",), evals=False)
    _autonomy(ws)
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision"' not in out, (out, err)


def test_no_autonomy_allows_strict(tmp_path):
    # C8 is targeted at the /implement context — no autonomy file → does not fire.
    ws = _mk_ws(tmp_path, evals=False)
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision"' not in out, (out, err)


def test_allowlisted_path_allows_strict(tmp_path):
    # Toolkit-managed file edits are always allowed (agent must fix spec/report).
    ws = _mk_ws(tmp_path, evals=False)
    _autonomy(ws)
    target = ws / ".agent-toolkit" / "specs" / "main" / "feat" / "feat.md"
    rc, out, err = _run(ws, target, strict=True)
    assert '"decision"' not in out, (out, err)


def test_bypass_marker_allows_strict(tmp_path):
    # DEV emergency `.analyze-bypass` escapes C8 too.
    ws = _mk_ws(tmp_path, evals=False)
    _autonomy(ws)
    (ws / ".agent-toolkit" / ".analyze-bypass").write_text("", encoding="utf-8")
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision"' not in out, (out, err)


def test_stale_expired_autonomy_does_not_fire_strict(tmp_path):
    # review round-1 MED fix: a lapsed-but-lingering autonomy file → C8 dormant.
    ws = _mk_ws(tmp_path, evals=False)
    _autonomy(ws, expires="2020-01-01T00:00:00")
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision"' not in out, (out, err)


def test_active_future_autonomy_blocks_strict(tmp_path):
    # the converse: a non-expired autonomy still fires C8 under strict.
    ws = _mk_ws(tmp_path, evals=False)
    _autonomy(ws, expires="2099-01-01T00:00:00")
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision": "block"' in out, (out, err)


def test_body_placed_evals_allows_strict(tmp_path):
    # review round-1 HIGH fix: acceptance_evals in the BODY (not frontmatter) → C8
    # must not FP-block (location-agnostic detection).
    ws = _mk_ws(tmp_path, evals=False)
    spec = ws / ".agent-toolkit" / "specs" / "main" / "feat" / "feat.md"
    spec.write_text(
        "---\nslug: feat\neval_status: defined\n---\n\n"
        "## 6. acceptance_evals\n\n```yaml\nacceptance_evals:\n"
        "  - id: us1-x\n    story: x\n```\n", encoding="utf-8")
    _autonomy(ws)
    rc, out, err = _run(ws, _src(ws), strict=True)
    assert '"decision"' not in out, (out, err)
