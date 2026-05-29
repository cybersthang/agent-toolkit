"""Tests for tools/wave_planner.py — the auto-parallel wave decomposition.

Covers parsing (multi-line Touches, backticks, annotations), wave planning
(disjoint packing, dependency ordering, conservative fallbacks), and the
.parallel_wave.json emit path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import wave_planner as wp  # noqa: E402


def _md(*task_blocks: str) -> str:
    return "# Tasks\n\n" + "\n\n".join(task_blocks) + "\n"


def _task(tid: str, touches: str, deps: str = "none", goal: str = "do") -> str:
    return (f"## {tid} — {goal}\n\n"
            f"- **Touches:** {touches}\n"
            f"- **Depends on:** {deps}\n"
            f"- **Risk:** low")


# ── parsing ──────────────────────────────────────────────────────────────
def test_parse_basic():
    tasks = wp.parse_tasks(_md(_task("T1", "`a.py`"), _task("T2", "`b.py`", "T1")))
    assert [t["id"] for t in tasks] == ["T1", "T2"]
    assert tasks[0]["touches"] == ["a.py"]
    assert tasks[1]["deps"] == ["T1"]


def test_parse_multiline_touches_with_backticks_and_annotations():
    block = ("## T1 — x\n\n"
             "- **Touches:** `templates/a.py` (extend),\n"
             "  `templates/b.py` (new)\n"
             "- **Depends on:** none")
    tasks = wp.parse_tasks(_md(block))
    assert tasks[0]["touches"] == ["templates/a.py", "templates/b.py"]


def test_parse_self_and_duplicate_deps_filtered():
    tasks = wp.parse_tasks(_md(_task("T2", "`b.py`", "T1, T1, T2")))
    assert tasks[0]["deps"] == ["T1"]      # dedup + drop self-ref


# ── planning ─────────────────────────────────────────────────────────────
def test_disjoint_tasks_run_in_one_parallel_wave():
    plan = wp.plan_waves(wp.parse_tasks(_md(_task("T1", "`a.py`"), _task("T2", "`b.py`"))))
    assert plan["waves"] == [["T1", "T2"]]
    assert plan["parallel_waves"] == 1 and plan["max_width"] == 2


def test_shared_file_serializes():
    plan = wp.plan_waves(wp.parse_tasks(_md(_task("T1", "`a.py`"), _task("T2", "`a.py`"))))
    assert plan["waves"] == [["T1"], ["T2"]]
    assert plan["parallel_waves"] == 0


def test_dependency_forces_later_wave():
    plan = wp.plan_waves(wp.parse_tasks(_md(_task("T1", "`a.py`"), _task("T2", "`b.py`", "T1"))))
    assert plan["waves"] == [["T1"], ["T2"]]


def test_two_disjoint_then_a_joining_task():
    plan = wp.plan_waves(wp.parse_tasks(_md(
        _task("T1", "`a.py`"), _task("T2", "`b.py`"), _task("T3", "`c.py`", "T1, T2"))))
    assert plan["waves"] == [["T1", "T2"], ["T3"]]


def test_empty_touches_is_solo_unsafe():
    plan = wp.plan_waves(wp.parse_tasks(_md(_task("T1", "none"), _task("T2", "`b.py`"))))
    # T1 has no known scope → must not parallelize with anything
    assert ["T1"] in plan["waves"]
    assert not any(len(w) > 1 and "T1" in w for w in plan["waves"])


def test_glob_touch_is_conservative():
    plan = wp.plan_waves(wp.parse_tasks(_md(_task("T1", "`**/models/x.py`"), _task("T2", "`y.py`"))))
    # a glob can't be proven disjoint → separate waves
    assert plan["waves"] == [["T1"], ["T2"]]


def test_dependency_cycle_falls_back_to_sequential():
    plan = wp.plan_waves(wp.parse_tasks(_md(_task("T1", "`a.py`", "T2"), _task("T2", "`b.py`", "T1"))))
    assert plan["sequential_fallback"] is True
    assert "cycle" in plan["reason"] or "unsatisfiable" in plan["reason"]
    assert all(len(w) == 1 for w in plan["waves"])


# ── emit (.parallel_wave.json via parallel_wave) ─────────────────────────
def test_emit_writes_disjoint_zones(tmp_path: Path):
    md = tmp_path / "f.tasks.md"
    md.write_text(_md(_task("T1", "`a.py`"), _task("T2", "`b.py`")), encoding="utf-8")
    manifest = wp.emit_wave(tmp_path, md, 0)
    assert manifest["wave"] == "tasks-wave-0"
    agents = {z["agent_id"]: z["owned"] for z in manifest["zones"]}
    assert agents == {"T1": ["a.py"], "T2": ["b.py"]}
    # written to .parallel_wave.json where parallel_conflict_guard reads it
    written = json.loads((tmp_path / ".agent-toolkit" / ".parallel_wave.json").read_text())
    assert written["zones"] == manifest["zones"]


def test_emit_rejects_out_of_range_wave(tmp_path: Path):
    md = tmp_path / "f.tasks.md"
    md.write_text(_md(_task("T1", "`a.py`")), encoding="utf-8")
    try:
        wp.emit_wave(tmp_path, md, 5)
        assert False, "expected ValueError for out-of-range wave"
    except ValueError:
        pass
