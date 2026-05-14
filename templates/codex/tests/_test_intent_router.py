"""Smoke test for the intent_router UserPromptSubmit hook.

Run manually after `setup.py update <project>`:

    python .claude/hooks/intent_router.py < /dev/null  # smoke
    python <toolkit>/templates/codex/tests/_test_intent_router.py <project_root>

The script feeds canned prompts through the hook, prints the skill list
each prompt resolved to, and asserts the expected resolution. Useful
both for verifying a fresh install and for catching regex regressions
when editing INTENT_MAP.

Exits 0 on success, 1 on any failing case.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CASES = [
    # (label, prompt, must_contain_skills, must_NOT_contain_skills)
    # Prompts intentionally use generic placeholders / common verbs so
    # the test does not encode any specific module/model name — the
    # toolkit is module-agnostic. Real prompts will reference real
    # modules at runtime via the codebase MCP.
    (
        "ambiguous-action",
        "thêm tính năng phát hiện job bị treo",
        ["clarification-gate"],
        [],
    ),
    (
        "readonly-no-action",
        "liệt kê models trong module hiện tại",
        [],  # liệt kê = read; no action verb in current INTENT_MAP
        ["clarification-gate"],
    ),
    (
        "explicit-skip-still-suggested",
        "just do it - thêm field timestamp vào model",
        # The skill suggestion still fires; the skill SKILL.md itself
        # documents the opt-out logic the agent applies on read.
        ["clarification-gate"],
        [],
    ),
    (
        "discovery-only",
        "where is the model defined",
        [],  # discovery skill matched but not clarification-gate
        ["clarification-gate"],
    ),
    (
        "action-plus-review",
        "fix bug N+1 trong module này và audit lại",
        # Priority filter: clarification-gate fires exclusively when
        # an action verb is present. Other skills emerge next turn
        # after the gate is acknowledged. Test that nothing else leaks.
        ["clarification-gate"],
        ["code-review", "doubt-driven-review"],
    ),
    (
        "tdd-explicit",
        "viết test trước cho feature mới theo TDD",
        # Same: action verb -> only the gate is suggested this turn.
        ["clarification-gate"],
        [],
    ),
    (
        "ambiguous-reference-vague",
        "2 cái này khác nhau ko cùng là action load kanban nhưng trên 1 kiểu dưới 1 kiểu",
        # Demonstrative "2 cái này" triggers the gate even without an
        # action verb (Trap 1 + Trap 5).
        ["clarification-gate"],
        [],
    ),
    (
        "numeric-quantifier-bare-noun",
        "werkzeug chỉ chạy 6 cái, xác định được trên dashboard 6 cái nào",
        # "6 cái" without explicit noun (Trap 5). The gate must fire
        # so the agent quotes the literal "cái" and asks instead of
        # silently filling in "thread"/"worker".
        ["clarification-gate"],
        [],
    ),
    (
        "explicit-noun-no-trigger",
        "có 5 record trong bảng nakivo đếm đúng không",
        # "5 record" — number + EXPLICIT noun "record" — no trap.
        # No action verb either. Should stay silent.
        [],
        ["clarification-gate"],
    ),
]


def run_hook(hook_path: Path, py_bin: Path, prompt: str) -> list[str]:
    data = json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run(
        [str(py_bin), str(hook_path)],
        input=data,
        capture_output=True,
        check=False,
    )
    out = proc.stdout.decode("utf-8").strip()
    if not out:
        return []
    parsed = json.loads(out)
    ctx = parsed["hookSpecificOutput"]["additionalContext"]
    # Extract from the "Open these skills..." sentence only, not from the
    # per-skill expectations block (which mentions each name again).
    m = re.search(r"Open these skills BEFORE answering:\s*([^.]+)\.", ctx)
    if not m:
        return []
    return re.findall(r"`([^`]+)`", m.group(1))


def main(project_root: Path) -> int:
    hook = project_root / ".claude" / "hooks" / "intent_router.py"
    if not hook.exists():
        print(f"FAIL: hook not found at {hook}")
        return 1
    py_bin = Path(sys.executable)

    failures = 0
    for label, prompt, must_have, must_not in CASES:
        skills = run_hook(hook, py_bin, prompt)
        missing = [s for s in must_have if s not in skills]
        leaked = [s for s in must_not if s in skills]
        status = "OK" if not (missing or leaked) else "FAIL"
        print(f"[{status}] {label}: {skills}")
        if missing:
            print(f"   missing: {missing}")
        if leaked:
            print(f"   leaked: {leaked}")
        if status == "FAIL":
            failures += 1

    print()
    if failures:
        print(f"{failures} case(s) failed")
        return 1
    print("all cases passed")
    return 0


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    sys.exit(main(root))
