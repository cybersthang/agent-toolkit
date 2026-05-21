#!/usr/bin/env python
"""One-off migration: apply run_main_safe wrapper to 21 hooks.

Closes P9 broken state from v0.8.0 — wrapper was defined in _common.py
but never actually called by any hook. This script:
  1. Adds `run_main_safe` to the `from _common import ...` line.
  2. Replaces `sys.exit(main())` -> `sys.exit(run_main_safe(main))` in
     the `if __name__ == "__main__":` block.

Idempotent: re-running on an already-migrated hook is a no-op.
Public-project safe: no hardcoded names.

CLI:
  python tests/fixtures/migrate_hooks_to_run_main_safe.py [--apply]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "claude" / "hooks"

# Hooks excluded — _common.py defines run_main_safe; _patterns.py + _audit/* are helpers
EXCLUDED = {"_common.py", "_patterns.py", "__init__.py"}


def migrate_hook(path: Path) -> dict:
    """Return {applied: bool, reason: str, old_exit: str, new_exit: str}."""
    text = path.read_text(encoding="utf-8")
    result = {"file": path.name, "applied": False, "reason": ""}

    # Detect __main__ pattern
    main_pat = re.compile(
        r"if __name__ == [\"\']__main__[\"\']:\s*\n\s*sys\.exit\((\w+)\(\)\)",
        re.MULTILINE,
    )
    m = main_pat.search(text)
    if not m:
        result["reason"] = "no __main__ sys.exit(main()) pattern"
        return result

    main_fn = m.group(1)
    new_exit = f'if __name__ == "__main__":\n    sys.exit(run_main_safe({main_fn}))'

    # Skip if already migrated
    if "run_main_safe" in text:
        result["reason"] = "already-migrated"
        return result

    # Replace exit
    new_text = main_pat.sub(new_exit, text)

    # Ensure import — find existing `from _common import ...`
    import_pat = re.compile(
        r"^(from _common import\s+(?:\([^)]*\)|.+?))$",
        re.MULTILINE | re.DOTALL,
    )
    im = import_pat.search(new_text)
    if im:
        existing = im.group(0)
        # Parse imported names
        if "run_main_safe" not in existing:
            # Append to the import. Handle both parenthesized + single-line.
            if "(" in existing:
                # Parenthesized — insert before closing paren
                replaced = existing.rstrip()
                if replaced.endswith(")"):
                    replaced = replaced[:-1].rstrip().rstrip(",")
                    replaced = replaced + ", run_main_safe)"
                else:
                    replaced = existing + ", run_main_safe"
            else:
                replaced = existing.rstrip() + ", run_main_safe"
            new_text = new_text.replace(existing, replaced)
    else:
        # No existing _common import — add one near top after sys.path.insert
        sys_path_pat = re.compile(
            r"(sys\.path\.insert\(0, str\(Path\(__file__\)\.parent\)\))",
        )
        spm = sys_path_pat.search(new_text)
        if spm:
            new_text = sys_path_pat.sub(
                spm.group(0) + "\nfrom _common import run_main_safe",
                new_text,
            )
        else:
            # Last resort: add after first `import sys`
            new_text = new_text.replace(
                "import sys\n",
                "import sys\nsys.path.insert(0, str(Path(__file__).parent))\nfrom _common import run_main_safe\n",
                1,
            )

    result["applied"] = True
    result["new_text"] = new_text
    result["old_main_fn"] = main_fn
    return result


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Actually write changes (default: dry-run preview)")
    ns = ap.parse_args(argv[1:])

    applied = 0
    skipped = 0
    for hook in sorted(HOOKS_DIR.glob("*.py")):
        if hook.name in EXCLUDED:
            continue
        result = migrate_hook(hook)
        if not result["applied"]:
            print(f"  SKIP  {hook.name}: {result['reason']}")
            skipped += 1
            continue
        if ns.apply:
            hook.write_text(result["new_text"], encoding="utf-8")
            print(f"  MIGR  {hook.name} ({result['old_main_fn']} -> run_main_safe)")
        else:
            print(f"  WOULD {hook.name} ({result['old_main_fn']} -> run_main_safe)")
        applied += 1

    mode = "APPLY" if ns.apply else "DRY-RUN"
    print(f"\n{mode}: {applied} migrated, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
