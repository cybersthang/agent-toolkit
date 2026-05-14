"""Verify the AGENT-side artefacts are wired correctly.

Reads `agent-toolkit.config.json` to discover which preset is installed
and what shape to expect, then checks:

- `AGENTS.md` exists at workspace root.
- Each `.cursor/rules/<name>.mdc` has YAML-ish frontmatter with `description`.
- Each `.cursor/skills/<name>/SKILL.md` has frontmatter `name` + `description`
  (Karpathy format).
- Each `start_<server>_mcp.py` from the preset's `mcp_servers` list exists.
- `.codex/canonical_decisions.json` loads, has integer `version`, every
  decision has a unique `id` + the required fields, and includes the
  baseline topics (`stack`, `addon roots`, `verification`, `mcp routing`,
  `determinism`, `module agnostic`, `response language`).
- (Optional) `.agent-toolkit/invariants.json` parses cleanly when present.
- (Optional) `.claude/hooks/*.py` referenced from `.claude/settings.json`
  all exist on disk.

The script is preset-agnostic — it derives the required set from the
installed config rather than hard-coding stack names.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / ".cursor" / "rules"
SKILLS_DIR = ROOT / ".cursor" / "skills"
REGISTRY_PATH = ROOT / ".codex" / "canonical_decisions.json"
AGENTS_MD = ROOT / "AGENTS.md"
CONFIG_PATH = ROOT / "agent-toolkit.config.json"
INVARIANTS_PATH = ROOT / ".agent-toolkit" / "invariants.json"
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"

# Topics every preset's canonical_decisions seed must answer for the
# `*-deterministic-answers` skill to function. Stack-specific topics
# (jira_production/preproduction) are added below only when the matching
# MCP server is installed.
BASELINE_REGISTRY_TOPICS = (
    "stack",
    "addon roots",
    "verification",
    "mcp routing",
    "determinism",
    "module agnostic",
    "response language",
)

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


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def check_rules(failures: List[str]) -> None:
    if not RULES_DIR.exists():
        failures.append(f"missing rules dir: {RULES_DIR}")
        return
    rules = list(RULES_DIR.glob("*.mdc"))
    if not rules:
        failures.append(f"no .mdc rules found in {RULES_DIR}")
        return
    for rule in rules:
        fm = parse_frontmatter(rule.read_text(encoding="utf-8"))
        if "description" not in fm:
            failures.append(f"rule {rule.name}: frontmatter missing 'description'")


def check_skills(failures: List[str]) -> None:
    if not SKILLS_DIR.exists():
        failures.append(f"missing skills dir: {SKILLS_DIR}")
        return
    skills = [p for p in SKILLS_DIR.iterdir() if p.is_dir()]
    if not skills:
        failures.append(f"no skills found in {SKILLS_DIR}")
        return
    for skill_dir in skills:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            failures.append(f"skill {skill_dir.name}: missing SKILL.md")
            continue
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        if fm.get("name") != skill_dir.name:
            failures.append(
                f"skill {skill_dir.name}: frontmatter name={fm.get('name')!r}"
                f" (expected {skill_dir.name!r})"
            )
        if not fm.get("description"):
            failures.append(f"skill {skill_dir.name}: frontmatter missing 'description'")


def check_registry(failures: List[str], extra_required_topics: List[str]) -> None:
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
    for required in BASELINE_REGISTRY_TOPICS:
        if required not in topics:
            failures.append(f"registry: missing baseline topic '{required}'")
    for required in extra_required_topics:
        if required not in topics:
            failures.append(f"registry: missing preset topic '{required}'")
    seen_ids = set()
    for decision in decisions:
        decision_id = decision.get("id")
        if not decision_id:
            failures.append("registry: a decision is missing 'id'")
        elif decision_id in seen_ids:
            failures.append(f"registry: duplicate id '{decision_id}'")
        else:
            seen_ids.add(decision_id)
        for required_field in ("topic", "question", "answer", "source"):
            if not decision.get(required_field):
                failures.append(
                    f"registry: decision id={decision_id!r} missing '{required_field}'"
                )


def check_agents_md(failures: List[str], mcp_servers: List[str]) -> None:
    if not AGENTS_MD.exists():
        failures.append("missing AGENTS.md at workspace root")
        return
    text = AGENTS_MD.read_text(encoding="utf-8")
    expected_phrases = ["MCP", "canonical_decisions.json", "Karpathy"]
    for server in mcp_servers:
        expected_phrases.append(server)
    for phrase in expected_phrases:
        if phrase not in text:
            failures.append(f"AGENTS.md: missing reference to '{phrase}'")


def check_mcp_starters(failures: List[str], mcp_servers: List[str]) -> None:
    for server in mcp_servers:
        starter = ROOT / ".codex" / f"start_{server}_mcp.py"
        if not starter.exists():
            failures.append(f"missing MCP starter for '{server}': {starter}")


def check_invariants(failures: List[str]) -> None:
    if not INVARIANTS_PATH.exists():
        return
    try:
        data = json.loads(INVARIANTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f"invariants.json invalid JSON: {exc}")
        return
    invariants = data.get("invariants")
    if invariants is None:
        failures.append("invariants.json: missing 'invariants' array")
        return
    for idx, inv in enumerate(invariants):
        if not isinstance(inv, dict):
            failures.append(f"invariants.json: entry [{idx}] is not an object")
            continue
        for field in ("id", "description", "severity"):
            if not inv.get(field):
                failures.append(
                    f"invariants.json: entry [{idx}] missing '{field}'"
                )
        sev = (inv.get("severity") or "").lower()
        if sev and sev not in ("blocker", "warn"):
            failures.append(
                f"invariants.json: entry id={inv.get('id')!r} has invalid"
                f" severity={sev!r} (expected blocker|warn)"
            )


def check_claude_hooks(failures: List[str]) -> None:
    if not CLAUDE_SETTINGS.exists():
        return
    try:
        settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        failures.append(f".claude/settings.json invalid JSON: {exc}")
        return
    hooks = settings.get("hooks") or {}
    for event, groups in hooks.items():
        for group in groups or []:
            for hook in group.get("hooks") or []:
                cmd = hook.get("command") or ""
                # Find any .py file path referenced in the command and
                # confirm it exists. Cheap heuristic — splits on space and
                # checks each token that ends with `.py`.
                for token in cmd.split():
                    if token.endswith(".py") and "/" in token:
                        path = Path(token)
                        if not path.exists():
                            failures.append(
                                f"hook {event}: command references missing"
                                f" script {token}"
                            )


def derive_preset_topics(config: Dict[str, Any]) -> List[str]:
    """Topics the canonical_decisions registry must include based on the
    MCP servers chosen for this install."""
    extra: List[str] = []
    mcp = config.get("mcp_servers") or []
    if any(name.startswith("jira") for name in mcp):
        extra.append("jira")
    return extra


def main() -> int:
    print(f"Workspace: {ROOT}")
    config = load_config()
    preset = config.get("preset") or "?"
    mcp_servers = list(config.get("mcp_servers") or [])
    print(f"Preset:    {preset}")
    print(f"MCP servers expected: {', '.join(mcp_servers) if mcp_servers else '(none)'}")

    failures: List[str] = []
    check_agents_md(failures, mcp_servers)
    check_rules(failures)
    check_skills(failures)
    check_registry(failures, derive_preset_topics(config))
    check_mcp_starters(failures, mcp_servers)
    check_invariants(failures)
    check_claude_hooks(failures)

    rule_count = len(list(RULES_DIR.glob("*.mdc"))) if RULES_DIR.exists() else 0
    skill_count = (
        sum(1 for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())
        if SKILLS_DIR.exists()
        else 0
    )
    decision_count = 0
    if REGISTRY_PATH.exists():
        try:
            decision_count = len(
                json.loads(REGISTRY_PATH.read_text(encoding="utf-8")).get("decisions") or []
            )
        except json.JSONDecodeError:
            pass
    invariant_count = 0
    if INVARIANTS_PATH.exists():
        try:
            invariant_count = len(
                json.loads(INVARIANTS_PATH.read_text(encoding="utf-8")).get("invariants") or []
            )
        except json.JSONDecodeError:
            pass

    print(f"AGENTS.md: {'PASS' if AGENTS_MD.exists() else 'FAIL'}")
    print(f".cursor/rules/*.mdc: {rule_count} files")
    print(f".cursor/skills/*/SKILL.md: {skill_count} files")
    print(f"canonical_decisions.json: {decision_count} entries")
    print(f".agent-toolkit/invariants.json: {invariant_count} invariants")

    if failures:
        print("\nFAIL:")
        for issue in failures:
            print(f"  - {issue}")
        return 1
    print("\nPASS: AGENT structure complete and consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
