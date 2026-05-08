"""Verify the AGENT-side artefacts are wired correctly:

- AGENTS.md exists at workspace root.
- Each .cursor/rules/<name>.mdc has YAML-ish frontmatter with `description`.
- Each .cursor/skills/<name>/SKILL.md has frontmatter `name` + `description` (Karpathy format).
- Canonical decisions JSON loads and exposes the topics referenced by rules.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / ".cursor" / "rules"
SKILLS_DIR = ROOT / ".cursor" / "skills"
REGISTRY_PATH = ROOT / ".codex" / "canonical_decisions.json"
AGENTS_MD = ROOT / "AGENTS.md"

REQUIRED_RULES = [
    "karpathy-guidelines.mdc",
    "decision-consistency.mdc",
    "mcp-routing.mdc",
    "odoo-12-generic.mdc",
    "odoo-12-backend.mdc",
    "odoo-12-project-context.mdc",
]
REQUIRED_SKILLS = [
    "karpathy-guidelines",
    "odoo-12-codebase-discovery",
    "odoo-12-data-verification",
    "odoo-12-jira-workflow",
    "odoo-12-deterministic-answers",
    "odoo-12-code-patterns",
    "odoo-12-debug-troubleshoot",
    "odoo-12-module-scaffold",
]
REQUIRED_REGISTRY_TOPICS = [
    "stack",
    "addon roots",
    "api decorators",
    "loop anti-patterns",
    "sudo",
    "verification",
    "mcp routing",
    "jira production",
    "jira preproduction",
    "determinism",
    "module agnostic",
    "response language",
]


FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<body>.*?)\n---", re.DOTALL)


def parse_frontmatter(text: str) -> Dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: Dict[str, str] = {}
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields


def check_rules(failures: List[str]) -> None:
    if not RULES_DIR.exists():
        failures.append(f"missing rules dir: {RULES_DIR}")
        return
    present = {p.name for p in RULES_DIR.glob("*.mdc")}
    for required in REQUIRED_RULES:
        if required not in present:
            failures.append(f"missing rule file: {required}")
            continue
        text = (RULES_DIR / required).read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if "description" not in fm:
            failures.append(f"rule {required}: frontmatter missing 'description'")


def check_skills(failures: List[str]) -> None:
    if not SKILLS_DIR.exists():
        failures.append(f"missing skills dir: {SKILLS_DIR}")
        return
    for required in REQUIRED_SKILLS:
        skill_md = SKILLS_DIR / required / "SKILL.md"
        if not skill_md.exists():
            failures.append(f"missing SKILL.md: {required}")
            continue
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        if fm.get("name") != required:
            failures.append(
                f"skill {required}: frontmatter name={fm.get('name')!r} (expected {required!r})"
            )
        if not fm.get("description"):
            failures.append(f"skill {required}: frontmatter missing 'description'")


def check_registry(failures: List[str]) -> None:
    if not REGISTRY_PATH.exists():
        failures.append(f"missing registry: {REGISTRY_PATH}")
        return
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"registry JSON invalid: {exc}")
        return
    if not isinstance(registry.get("version"), int):
        failures.append("registry: 'version' must be an integer")
    decisions = registry.get("decisions") or []
    topics = {d.get("topic") for d in decisions}
    for required in REQUIRED_REGISTRY_TOPICS:
        if required not in topics:
            failures.append(f"registry: missing topic '{required}'")
    seen_ids = set()
    for decision in decisions:
        decision_id = decision.get("id")
        if not decision_id:
            failures.append("registry: a decision is missing 'id'")
        elif decision_id in seen_ids:
            failures.append(f"registry: duplicate id '{decision_id}'")
        seen_ids.add(decision_id)
        for required_field in ("topic", "question", "answer", "source"):
            if not decision.get(required_field):
                failures.append(
                    f"registry: decision id={decision_id!r} missing '{required_field}'"
                )


def check_agents_md(failures: List[str]) -> None:
    if not AGENTS_MD.exists():
        failures.append("missing AGENTS.md at workspace root")
        return
    text = AGENTS_MD.read_text(encoding="utf-8")
    expected_phrases = [
        "MCP",
        "canonical_decisions.json",
        "jira_production",
        "jira_preproduction",
        "Karpathy",
    ]
    for phrase in expected_phrases:
        if phrase not in text:
            failures.append(f"AGENTS.md: missing reference to '{phrase}'")


def main() -> int:
    print(f"Workspace: {ROOT}")
    failures: List[str] = []
    check_agents_md(failures)
    check_rules(failures)
    check_skills(failures)
    check_registry(failures)

    rule_count = len(list(RULES_DIR.glob("*.mdc"))) if RULES_DIR.exists() else 0
    skill_count = sum(1 for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists()) if SKILLS_DIR.exists() else 0
    decision_count = 0
    if REGISTRY_PATH.exists():
        try:
            decision_count = len(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")).get("decisions") or [])
        except json.JSONDecodeError:
            pass

    print(f"AGENTS.md: {'PASS' if AGENTS_MD.exists() else 'FAIL'}")
    print(f".cursor/rules/*.mdc: {rule_count} files")
    print(f".cursor/skills/*/SKILL.md: {skill_count} files")
    print(f"canonical_decisions.json: {decision_count} entries")

    if failures:
        print("\nFAIL:")
        for issue in failures:
            print(f"  - {issue}")
        return 1
    print("\nPASS: AGENT structure complete and consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
