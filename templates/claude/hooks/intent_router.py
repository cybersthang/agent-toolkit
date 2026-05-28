#!/usr/bin/env python
"""UserPromptSubmit hook — intent → skill router.

Reads the user's prompt from stdin (Claude Code hook JSON envelope) and,
if it matches one of the configured intent patterns, prints a brief
"consider opening skill X" reminder to stdout. Claude Code injects
stdout into the conversation as a <system-reminder>, so the model sees
the suggestion BEFORE generating its response — even when AGENTS.md has
scrolled far out of the visible context.

Stays silent (exit 0, no output) when:
  - no pattern matches
  - the prompt is short (likely a yes/no / interjection)
  - the prompt already references a skill by name (avoid double-nagging)

Templated at install time by the toolkit; `odoo` and
`12` are substituted with concrete values
(e.g. `odoo` and `12`).

Edit this file to extend or tune the routing table. It's plain Python
and the install-time templating only touches the two stack placeholders.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Claude Code pipes the hook envelope as UTF-8 JSON. On Windows the
# default stdin/stdout encoding is cp1252, which mangles Vietnamese
# (and any non-Latin) characters in the user's prompt. Re-wrap both
# streams as UTF-8 before any read/print.
sys.path.insert(0, str(Path(__file__).parent))
from _common import wrap_utf8_stdio, run_main_safe, atomic_write_json  # noqa: E402
from _patterns import (  # noqa: E402
    BYPASS_INVARIANT_RE, SKIP_CLARIFICATION_RE, BYPASS_GAP_GATE_RE,
    BYPASS_GIT_GUARD_RE, BYPASS_DEBUG_SENTRY_RE, BYPASS_SCOPE_GATE_RE,
)

wrap_utf8_stdio()

INTENT_MAP_REL = ".agent-toolkit/intent_map.json"
BYPASS_FILE_REL = ".agent-toolkit/.bypass_next_edit.json"
BYPASS_TTL_SECONDS = 300  # 5 min — long enough for agent to reach Edit, short
                          # enough to avoid leaking into a later session.

# v0.13.0 — clarification-gate enforcer state files (D8/D9).
LAST_INTENT_SUGGESTED_REL = ".agent-toolkit/.last_intent_suggested.json"
SKIP_CLARIFICATION_REL = ".agent-toolkit/.skip_clarification_next.json"
SKIP_CLARIFICATION_TTL_SECONDS = 600

# v0.20.0 — git-guardrails bypass token.
SKIP_GIT_GUARD_REL = ".agent-toolkit/.skip_git_guard_next.json"
SKIP_GIT_GUARD_TTL_SECONDS = 600

# v0.21 T16 (M13) — debug-sentry bypass token.
SKIP_DEBUG_SENTRY_REL = ".agent-toolkit/.skip_debug_sentry_next.json"
SKIP_DEBUG_SENTRY_TTL_SECONDS = 600

# v0.23.0 R9 — scope-completeness-gate bypass token.
SKIP_SCOPE_GATE_REL = ".agent-toolkit/.skip_scope_gate_next.json"
SKIP_SCOPE_GATE_TTL_SECONDS = 600

# v0.23 R3-fallback — canonical-lookup expectation marker. Claude Code has
# NO PreResponse event, so we cannot enforce "call lookup_canonical_decision
# before answering" mechanically. Fallback: when a prompt matches a
# recurring-decision (canonical-topic) pattern, intent_router (UserPromptSubmit)
# injects an explicit ⚠️ CANONICAL CHECK reminder AND writes this marker.
# FORWARD-PREP: the marker is NOT YET consumed by any hook. A FUTURE Stop hook
# (evidence_audit) could read it to flag "canonical topic matched but no
# lookup_canonical_decision call observed this turn". Until that consumer
# ships, the file is written best-effort and harmlessly ignored.
CANONICAL_EXPECTED_REL = ".agent-toolkit/.canonical_expected.json"
CANONICAL_EXPECTED_TTL_SECONDS = 600
# Mirror of the canonical-topic ("recurring decision") alias used in the
# INTENT_MAP entry that suggests `odoo-deterministic-answers`. Kept as a
# standalone compiled pattern so _format_reminder / the marker writer can
# detect a canonical hit without re-deriving which intent entry matched.
CANONICAL_TOPIC_RE = re.compile(
    r"\b(how\s*do\s*we|convention|recurring|canonical|"
    r"làm\s*sao.*project|chuẩn.*project|theo\s*chuẩn)\b",
    flags=re.IGNORECASE | re.UNICODE,
)


def _load_intent_map(workspace: Path) -> Tuple[str, str, List[Tuple[str, List[str]]]]:
    """Load INTENT_MAP from .agent-toolkit/intent_map.json. Substitute
    {stack} / {stack_bare} placeholders in skill names. Returns
    (stack, stack_bare, entries). Falls back to built-in defaults below
    if file missing or malformed."""
    path = workspace / INTENT_MAP_REL
    if not path.exists():
        return _FALLBACK_STACK, _FALLBACK_STACK_BARE, _FALLBACK_ENTRIES
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return _FALLBACK_STACK, _FALLBACK_STACK_BARE, _FALLBACK_ENTRIES
    stack = data.get("stack") or _FALLBACK_STACK
    stack_bare = data.get("stack_bare") or _FALLBACK_STACK_BARE
    out: List[Tuple[str, List[str]]] = []
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        pat = entry.get("pattern")
        skills = entry.get("skills") or []
        if not pat or not isinstance(skills, list):
            continue
        resolved = [
            s.format(stack=stack, stack_bare=stack_bare) if isinstance(s, str) else s
            for s in skills
        ]
        out.append((pat, resolved))
    if not out:
        return _FALLBACK_STACK, _FALLBACK_STACK_BARE, _FALLBACK_ENTRIES
    return stack, stack_bare, out


# Fallback for projects that haven't run `setup.py update` yet — these
# are the same patterns the JSON file would carry, hardcoded as Python.
_FALLBACK_STACK = "odoo-12"
_FALLBACK_STACK_BARE = "odoo"
_FALLBACK_ENTRIES: List[Tuple[str, List[str]]] = [
    # ---------- Clarification gate (action verbs — mutates state) ----------
    # Trigger BEFORE any other action skill so the agent emits
    # UNDERSTANDING/ASSUMPTIONS/QUESTIONS before touching Edit/Write/Bash.
    # The user can opt out per-prompt by saying "just do it" / "không
    # cần hỏi" / "implement luôn" — the skill itself documents the skip
    # rules; the regex just surfaces the suggestion.
    (
        r"\b(implement|build|deploy|sửa|fix|refactor|tạo|viết|làm|thêm|add|remove|xóa|delete|update|cập\s*nhật|đổi|change|modify|tối\s*ưu|optimize|migrate|chuyển|rewrite|làm\s*lại|làm\s*gọn|dọn|clean\s*up|move|rename|extract|inline)\b",
        ["clarification-gate"],
    ),

    # ---------- Clarification gate (ambiguous reference triggers) ----------
    # Fire the gate even WITHOUT an action verb when the prompt contains
    # high-risk ambiguity markers — demonstratives, spatial words, vague
    # qualitative words, and (most importantly) numeric quantifiers with
    # generic counter-nouns ("6 cái", "2 thằng"). The skill's Trap 5
    # documents why these need a Q, not a silent inference. Without this
    # trigger, prompts like *"werkzeug chạy 6 cái"* or *"2 cái này khác
    # nhau"* would slip past the gate and the agent would vibe-translate.
    (
        r"(\b\d+\s*(cái|cái này|cái kia|thằng|thằng này|thằng kia|items?|things?|cụm|chỗ)\b"
        r"|\b2\s*cái\s*này\b|\bcái\s*này\b|\bcái\s*kia\b|\bchỗ\s*này\b|\bchỗ\s*kia\b"
        r"|\bnày\s*khác\b|\bcùng\s*một\b)",
        ["clarification-gate"],
    ),

    # ---------- Review / audit ----------
    (
        r"\b(review|audit|phân\s*tích\s*sâu|tìm\s*bug|kiểm\s*tra\s*code|còn\s*gì.*fix|lỗ\s*hổng|nguy\s*hiểm)\b",
        ["code-review", "odoo-code-review", "doubt-driven-review"],
    ),
    (
        r"\b(double[-\s]?check|are\s*you\s*sure|chắc.*không|chắc.*chưa|sure\?)\b",
        ["doubt-driven-review"],
    ),

    # ---------- Discovery / lookup ----------
    (
        r"\b(how\s*do\s*we|convention|recurring|canonical|làm\s*sao.*project|chuẩn.*project|theo\s*chuẩn)\b",
        ["odoo-deterministic-answers"],
    ),
    (
        r"\b(where\s*is|tìm\s*file|find.*file|trace.*call|locate|định\s*nghĩa.*ở\s*đâu|đọc\s*hiểu\s*module)\b",
        ["odoo-codebase-discovery"],
    ),

    # ---------- Verify against real data ----------
    (
        r"\b(real\s*db|prod\s*data|verify.*real|kiểm\s*tra.*dữ\s*liệu|live\s*verify|thật\s*hay\s*không)\b",
        ["odoo-data-verification"],
    ),

    # ---------- Classifier / count / prove-tag intent (real-data-proof) ----
    # Matches the canonical DEV pattern: "count X and classify each as Y/Z";
    # "prove that tag T is correct"; "phân loại"; "BLOCK/ASYNC"; etc.
    # Pulls in real-data-proof for the 4-step mandatory workflow plus
    # claim-falsification (its recipe catalog) and classifier-output-audit
    # (for finding mis-tag candidates first).
    (
        r"\b(classify|classification|phân\s*loại|tag\s*(each|every|từng)|"
        r"gán\s*nhãn|nhãn\s*nào|"
        r"block\s*vs\s*async|block\s*hay\s*async|sync\s*vs\s*async|"
        r"prove.*(tag|label|classification)|chứng\s*minh.*(tag|nhãn|đúng)|"
        r"falsif(y|ication)|perturb[-\s]?test|inverse\s*perturb|"
        r"count.*requests?.*(classify|tag|phân\s*loại)|"
        r"đếm.*request.*phân\s*loại|"
        r"sleep\s*inject|inject\s*sleep)\b",
        ["real-data-proof", "claim-falsification", "classifier-output-audit"],
    ),

    # ---------- Debug ----------
    (
        r"\b(bug|lỗi|error|exception|traceback|không\s*chạy|crash|stuck|treo|hang|fail.*test)\b",
        ["odoo-debug-troubleshoot"],
    ),

    # ---------- Spec Kit workflow ----------
    (
        r"\b(/plan\b|feature\s*mới|new\s*feature|tính\s*năng\s*mới|thêm.*tính\s*năng|add.*feature|write\s*(a\s*)?prd|create.*spec|tạo\s*spec)\b",
        ["plan-feature"],
    ),
    (
        r"\b(/clarify\b|grill\s*me|stress[-\s]*test\s*(the\s*)?spec|challenge\s*me|đóng\s*gap|refine\s*spec)\b",
        ["clarify"],
    ),
    (
        r"\b(/tasks\b|rã\s*task|task\s*breakdown|emit\s*tasks)\b",
        ["tasks-breakdown"],
    ),
    (
        r"\b(/analyze\b|cross[-\s]*artifact|lint\s*spec|artifact\s*consistency)\b",
        ["analyze-artifacts"],
    ),
    (
        r"\b(/implement\b|bắt\s*đầu\s*code|execute\s*tasks|start\s*implement|implement\s*đi|implement\b|refactor)\b",
        ["analyze-artifacts", "verify-feature"],
    ),

    # ---------- Module scaffold (after spec exists) ----------
    (
        r"\b(tạo\s*module|scaffold|new\s*module|module\s*mới)\b",
        ["plan-feature", "odoo-module-scaffold"],
    ),

    # ---------- TDD ----------
    (
        r"\b(tdd|test\s*driven|viết\s*test\s*trước|test\s*first|red.*green.*refactor)\b",
        ["odoo-tdd"],
    ),

    # ---------- Patterns / Jira ----------
    (
        r"\b(theo\s*pattern|follow.*style|tuân.*chuẩn|project\s*style|code\s*style)\b",
        ["odoo-code-patterns"],
    ),
    (
        r"\b(jira|nkv[-\s]?\d+|ticket|sprint)\b",
        ["odoo-jira-workflow"],
    ),
]


def _normalize(text: str) -> str:
    """Collapse whitespace + lowercase for regex matching."""
    return re.sub(r"\s+", " ", text).lower()


def _matched_skills(prompt: str, intent_map: List[Tuple[str, List[str]]]) -> List[str]:
    """Return ordered, deduplicated list of skill names suggested by the prompt.

    Priority rule: when an action-verb prompt triggers
    `clarification-gate`, that skill is returned EXCLUSIVELY — the
    follow-up skills (debug-troubleshoot, plan-feature, etc.)
    are suppressed for this turn so the agent doesn't load ~1500 lines
    of SKILL.md content at once and lose focus on the user's prompt.
    Those skills re-emerge on the next turn ("go" / answers to the
    gate's questions), which typically won't contain action verbs and
    won't re-trigger the gate.
    """
    norm = _normalize(prompt)
    seen = set()
    out: List[str] = []
    for pattern, skills in intent_map:
        if re.search(pattern, norm, flags=re.IGNORECASE | re.UNICODE):
            for s in skills:
                if s not in seen:
                    seen.add(s)
                    out.append(s)

    # Priority: if the clarification-gate is on the list, return ONLY
    # it for current turn — but cache the downstream skills so
    # clarification_gate_enforcer can inject them as "deferred" on
    # post-satisfy (fixes M12 — downstream skills never re-fired before).
    if "clarification-gate" in seen:
        return ["clarification-gate"]
    return out


def _matched_skills_with_deferred(prompt: str,
                                  intent_map: List[Tuple[str, List[str]]]
                                  ) -> Tuple[List[str], List[str]]:
    """v0.21 T15 (M12) — return (primary_skills, deferred_skills).

    primary = [clarification-gate] if gate triggered, else all matches.
    deferred = downstream skills suppressed during gate turn, re-injected
    by clarification_gate_enforcer on shape-ok.
    """
    norm = _normalize(prompt)
    seen = []
    for pattern, skills in intent_map:
        if re.search(pattern, norm, flags=re.IGNORECASE | re.UNICODE):
            for s in skills:
                if s not in seen:
                    seen.append(s)
    if "clarification-gate" in seen:
        primary = ["clarification-gate"]
        deferred = [s for s in seen if s != "clarification-gate"]
        return primary, deferred
    return seen, []


def _already_referenced(prompt: str, skills: List[str]) -> bool:
    """Skip nag when the user already named (any of) the matched skills."""
    norm = prompt.lower()
    return any(s.lower() in norm for s in skills)


# Per-skill expected output fields. Replaces the previous generic
# reminder text that listed (Proof, Doubt-pass, acceptance criterion)
# regardless of which skill matched — that wording confused the agent
# whenever `clarification-gate` was the matched skill (it expects
# UNDERSTANDING/ASSUMPTIONS/QUESTIONS, not Proof lines).
SKILL_OUTPUT_FIELDS = {
    "clarification-gate": (
        "UNDERSTANDING (quote 1-3 literal phrases from the prompt + "
        "paraphrase) + ASSUMPTIONS (2-5 items) + QUESTIONS (max 3). "
        "EACH question MUST include a `Searched:` line listing what "
        "you grep'd / read / looked up via MCP before asking — if "
        "the answer is derivable from code/config/registry, DO NOT "
        "ask; verify it yourself. Questions that look like they could "
        "have been answered by `grep` or `lookup_canonical_decision` "
        "will be rejected. Each question gets 2-3 options (a)/(b)/(c) "
        "with EXACTLY ONE marked **Recommended** + one-line rationale. "
        "STOP — do not call Edit/Write/Bash until the user replies."
        "\n\nADDITIONALLY: if the task involves editing a feature-scope "
        "file (controllers/models/wizards/jobs per coverage_config.json), "
        "emit a `PROBE_READINESS` block — 4-row checklist with "
        "`description / measurement_command / falsification recipe / "
        "MCP evidence tool` and status ✓ or NEED ASK. If any row is "
        "NEED ASK, add the missing-info questions to QUESTIONS. After "
        "grill, agent must write FULL probe entry (no `_stub`, no TODO) "
        "to `.agent-toolkit/acceptance-probes.json`. probe_autostub will "
        "WARN if a feature-scope edit lands without a covering probe."
    ),
    # v0.23 R3-fallback — strengthen the canonical-topic skill entry with an
    # explicit "look it up before answering" contract. The dedicated
    # ⚠️ CANONICAL CHECK block in _format_reminder is the loud signal; this
    # per-skill line reinforces the expected output shape.
    "odoo-deterministic-answers": (
        "BEFORE answering, call `mcp__codebase__lookup_canonical_decision` "
        "(or grep `.codex/canonical_decisions.*.json`) to check for an "
        "existing canonical answer. Answering from memory without checking "
        "= determinism drift. If a canonical decision exists, cite its `id` "
        "verbatim and follow it; if none exists, say so explicitly before "
        "proposing a new convention."
    ),
    "code-review": (
        "Count table (BLOCKER/MEDIUM/LOW) + per-finding Proof line "
        "tracing trigger → observable failure. Proof line MUST cite "
        "`path:line` AND the MCP/tool call you used to verify (e.g. "
        "`postgres.query_readonly` for runtime claims, `Read` for "
        "static claims). Claims without a tool reference are rejected "
        "by the `evidence-audit` Stop hook."
    ),
    "doubt-driven-review": (
        "Each finding adds a `Doubt-pass:` line stating the strongest "
        "doubt + how it was refuted (or 'unknown — user question')."
    ),
    "plan-feature": (
        "8-section spec (Problem / Solution / Affected Modules / User "
        "Stories / Implementation Decisions / Testing / Out-of-scope / "
        "Open Questions) plus `acceptance_evals:` skeleton in "
        "frontmatter, then STOP for `/clarify`. Before writing the spec, "
        "run codebase MCP discovery for the affected modules — Affected "
        "Modules section must cite concrete `path:line` refs from the "
        "search, not invented paths. Spec lives at "
        "`.agent-toolkit/specs/<branch>/<slug>.md` (branch-scoped)."
    ),
    "clarify": (
        "One Q per turn, 5-layer self-resolve before each Q (ADR / "
        "canonical_decisions / invariants / constitution / memory). "
        "Each Q has (a)/(b)/(c) with EXACTLY ONE Recommended + Why. "
        "On DEV 'done': refine `acceptance_evals` (set grader/layer/"
        "expected, smoke-test ≥1 probe) → set spec `status: clarified` "
        "→ auto-fire `/tasks <slug>` → STOP. Do NOT auto-fire /implement."
    ),
    "tasks-breakdown": (
        "Emit `tasks.md` next to the spec — one task per ≤30 LOC unit. "
        "Each task has Touches / Depends on / Acceptance / Verification / "
        "Risk lines. Every User Story covered by ≥1 task; every "
        "`acceptance_evals` entry cited by exactly 1 task. STOP after "
        "emit — DEV review gate before `/implement`."
    ),
    "analyze-artifacts": (
        "Run 7 cross-artifact checks (story coverage / eval coverage / "
        "out-of-scope guard / invariant compat / constitution compat / "
        "path realism / verification concreteness). Emit `analyze-report.md`"
        " next to tasks.md. Return verdict READY / READY-with-warnings / "
        "HALT. HALT stops the `/implement` auto-chain."
    ),
    "verify-feature": (
        "Probes in parallel via realdata_test/postgres/Playwright MCP "
        "(spread < 3s). Each User Story → 1 row in the PASS/GAP/BLOCKER "
        "table. Re-use `acceptance_evals` defined in spec frontmatter; "
        "do NOT re-design. Update spec status to verified/gaps-found/"
        "blocked. Trigger `verify_lint` Stop hook via `.codex/lint_"
        "verify_report.py`."
    ),
    "real-data-proof": (
        "4 mandatory steps: (1) acquire REAL data — cite source + "
        "realism (no synthetic-only fixtures); (2) emit DISTRIBUTION "
        "table per tag with sample input_ids (count + % per label); "
        "(3) FALSIFY each distinct tag value via `claim-falsification` "
        "recipe (sleep-inject for BLOCK/ASYNC, etc.) — min 1 perturb-test "
        "per tag including `default` bucket if non-empty, baseline + "
        "perturb 3 runs each take median; (4) emit Real-Data Proof Report "
        "(Data source / Distribution / Falsification table with Δ "
        "predicted vs measured / Verdict / Revert checklist with "
        "`grep PERTURB-TEST` = 0). See `references/block-async-worked-"
        "example.md` for the canonical end-to-end shape. REFUTED on "
        "any tag = BLOCKER for merge."
    ),
    "claim-falsification": (
        "Pick a recipe from the 15-recipe catalog matching the claim "
        "shape (P, X.kind). Instantiate (perturbation D, observable Y, "
        "predicted Δ). Run baseline + perturb (3+3 runs minimum, take "
        "median). Verdict CONSISTENT / REFUTED / inconclusive. ALWAYS "
        "revert D — `grep PERTURB-TEST` must be empty before STOP. "
        "Y must be INDEPENDENT of the classifier's output (no circular "
        "self-reads). When subject is a classifier emitting N labels at "
        "scale → escalate to `classifier-output-audit` (N-claim wrapper)."
    ),
    "classifier-output-audit": (
        "Build path × signal matrix from the classifier source. Sample "
        "K ≥ max(10, sqrt(n)) rows stratified by tag. Re-derive "
        "T_expected from the FULL signal set (not just signals the "
        "handling path read). Group mismatches by (path, deciding_"
        "signal) and escalate the largest group to `claim-falsification`. "
        "Emit Classifier Audit Report (matrix + sample table + mismatch "
        "groups + proposed fix + verdict 🟢/🟡/🔴). Mis-tag rate > 5% "
        "on sample = BLOCKER."
    ),
}


def _canonical_check_block() -> str:
    """v0.23 R3-fallback — loud, explicit canonical-lookup reminder.

    Emitted when the prompt matches CANONICAL_TOPIC_RE. Because Claude Code
    lacks a PreResponse event, this UserPromptSubmit-injected text is the
    only place we can nudge the agent to consult the canonical registry
    BEFORE answering a recurring-decision question.
    """
    return (
        "\n\n⚠️ CANONICAL CHECK: This prompt matches a recurring-decision "
        "pattern.\nBEFORE answering, you MUST call "
        "`mcp__codebase__lookup_canonical_decision`\n(or grep "
        ".codex/canonical_decisions.*.json) to check if a canonical answer\n"
        "exists. Answering from memory without checking = determinism drift.\n"
        "Cite the canonical decision id if found."
    )


def _format_reminder(skills: List[str], prompt: str = "") -> str:
    """Render the system reminder; tailor expectations per matched skill.

    v0.23 R3-fallback: `prompt` is used only to detect a canonical-topic hit
    so the ⚠️ CANONICAL CHECK block can be appended. Defaulted to "" so
    existing callers / tests that pass only `skills` keep working.
    """
    skill_list = ", ".join(f"`{s}`" for s in skills)
    expectations = []
    for s in skills:
        fields = SKILL_OUTPUT_FIELDS.get(s)
        if fields:
            expectations.append(f"  - `{s}`: {fields}")
    if expectations:
        exp_block = "\n".join(expectations)
        format_note = (
            "\nExpected output per skill:\n" + exp_block +
            "\nFor any skill not listed here, read its SKILL.md to "
            "find the output contract."
        )
    else:
        format_note = (
            " Read each skill's SKILL.md for its specific output "
            "contract — do NOT assume a generic Proof/Doubt-pass shape."
        )
    # v0.23 R3-fallback: prepend the loud canonical-check block when the
    # prompt matches a recurring-decision pattern (additive — leaves the rest
    # of the reminder intact).
    canonical_block = (
        _canonical_check_block() if prompt and CANONICAL_TOPIC_RE.search(prompt)
        else ""
    )
    return (
        f"[intent-router] Detected intent in user prompt. Open these "
        f"skills BEFORE answering: {skill_list}. Apply each skill's "
        f"STOP checkpoints." + format_note + canonical_block +
        "\n\nHARD RULES (enforced by other hooks, not optional):\n"
        "- `invariant-guard` will BLOCK any Edit/Write that strips a "
        "  pattern listed in `.agent-toolkit/invariants.json`.\n"
        "- `evidence-audit` will REJECT the response if it makes claims "
        "  ('X is slow', 'root cause is Y', 'Z is missing') without a "
        "  prior Read/Grep/Glob/MCP call in this turn — tag as "
        "  `[assumption]` if you cannot verify.\n"
        "- DO NOT ASK the user a question whose answer is in the code; "
        "  search first. The clarification-gate skill rejects questions "
        "  without a `Searched:` line.\n\n"
        "Suppress this reminder by referencing the skill name "
        "explicitly in your next turn."
    )


def _write_last_intent_suggested(workspace: Path, skills: List[str],
                                  prompt: str,
                                  deferred_skills: Optional[List[str]] = None
                                  ) -> None:
    """v0.13.0 — record that intent_router suggested skill X for this turn.
    v0.21 T15 (M12) — also persist `deferred_skills` so
    clarification_gate_enforcer can re-inject them post-satisfy.

    clarification_gate_enforcer.py reads this state file on Stop to know
    whether the current turn's response must satisfy the skill's shape
    contract (4 markers for clarification-gate). Single-use is NOT
    required — state expires by TTL (600s default in enforcer).
    """
    import hashlib
    import time
    path = workspace / LAST_INTENT_SUGGESTED_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": int(time.time()),
            "skills": list(skills),
            "deferred_skills": list(deferred_skills or []),
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8],
        }
        # v0.21 T03 (B4): atomic write — concurrent prompts can race.
        atomic_write_json(path, payload)
    except OSError:
        # Best-effort: silent on failure (don't break UserPromptSubmit flow).
        pass


def _capture_bypass_gap_gate(workspace: Path, prompt: str) -> None:
    """v0.19.0 — write a single-shot bypass token into `.open_gaps.json`
    `pending_bypass` field when user typed `bypass-gap-gate: <reason ≥ 8>`.

    Mirrors `_capture_skip_clarification` (token TTL + single-use). The
    gap_completeness_gate Stop hook consumes (pops `pending_bypass`) on
    next stop attempt, appends to `bypass_history` for audit.
    """
    import time
    m = BYPASS_GAP_GATE_RE.search(prompt)
    if not m:
        return
    reason = m.group(1).strip()
    if not reason:
        return
    open_gaps_path = workspace / ".agent-toolkit" / ".open_gaps.json"
    try:
        state = {}
        if open_gaps_path.exists():
            try:
                state = json.loads(open_gaps_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                state = {}
        if not isinstance(state, dict):
            state = {}
        state.setdefault("version", 1)
        state.setdefault("gaps", [])
        state["pending_bypass"] = {"ts": int(time.time()), "reason": reason}
        # v0.21 T03 (B4): atomic write.
        atomic_write_json(open_gaps_path, state)
    except OSError:
        pass


def _capture_skip_clarification(workspace: Path, prompt: str) -> None:
    """v0.13.0 — write ephemeral skip-token file when user typed
    `skip-clarification: <reason>` (reason ≥ 8 non-whitespace chars per D9).

    Mirrors _capture_bypass_invariant pattern. Single-use: enforcer
    consumes (unlinks) the file on hit. TTL 300s safety net.
    """
    import time
    m = SKIP_CLARIFICATION_RE.search(prompt)
    if not m:
        return
    reason = m.group(1).strip()
    if not reason:
        return
    path = workspace / SKIP_CLARIFICATION_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": int(time.time()),
            "reason": reason,
            "ttl_seconds": SKIP_CLARIFICATION_TTL_SECONDS,
        }
        # v0.21 T03 (B4): atomic write.
        atomic_write_json(path, payload)
    except OSError:
        pass


def _capture_canonical_expected(workspace: Path, prompt: str) -> None:
    """v0.23 R3-fallback — write a forward-prep marker when the prompt matches
    a canonical-topic (recurring-decision) pattern.

    Claude Code has NO PreResponse event, so we cannot mechanically enforce
    "agent must call lookup_canonical_decision before answering". This marker
    records the EXPECTATION so a FUTURE Stop hook (e.g. evidence_audit) could
    later verify whether a `lookup_canonical_decision` / canonical-grep call
    actually happened this turn and warn on drift.

    NOTE: this file is NOT YET consumed by any hook. It is pure forward-prep —
    written best-effort, harmless if ignored. Single-use / TTL semantics are
    left to the future consumer (we record `ts` + `ttl_seconds` so it can
    apply the same pattern as the other state files).
    """
    import hashlib
    import time
    if not CANONICAL_TOPIC_RE.search(prompt):
        return
    path = workspace / CANONICAL_EXPECTED_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": int(time.time()),
            "ttl_seconds": CANONICAL_EXPECTED_TTL_SECONDS,
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8],
            # Documents intent for the future consumer; no hook reads this yet.
            "expected_call": "mcp__codebase__lookup_canonical_decision",
            "consumed": False,
        }
        atomic_write_json(path, payload)
    except OSError:
        # Best-effort: silent on failure (don't break UserPromptSubmit flow).
        pass


def _capture_bypass_debug_sentry(workspace: Path, prompt: str) -> None:
    """v0.21 T16 (M13) — write single-shot debug_sentry bypass token when
    user types `bypass-debug-sentry: <reason ≥ 8 chars>`.

    Symmetric with _capture_skip_git_guard. debug_sentry.py reads
    `.skip_debug_sentry_next.json` (TTL 600s, single-use) to skip
    enforcement on the next Stop.
    """
    import time
    m = BYPASS_DEBUG_SENTRY_RE.search(prompt)
    if not m:
        return
    reason = m.group(1).strip()
    if not reason:
        return
    path = workspace / SKIP_DEBUG_SENTRY_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": int(time.time()),
            "reason": reason,
            "ttl_seconds": SKIP_DEBUG_SENTRY_TTL_SECONDS,
        }
        atomic_write_json(path, payload)
    except OSError:
        pass


def _capture_bypass_scope_gate(workspace: Path, prompt: str) -> None:
    """v0.23.0 R9 — write single-shot scope_completeness_gate bypass token
    when user types `bypass-scope-gate: <reason ≥ 8 chars>`.

    Symmetric with _capture_bypass_gap_gate. scope_completeness_gate.py
    reads `.skip_scope_gate_next.json` (TTL 600s, single-use) and consumes
    it on the next Stop.
    """
    import time
    m = BYPASS_SCOPE_GATE_RE.search(prompt)
    if not m:
        return
    reason = m.group(1).strip()
    if not reason:
        return
    path = workspace / SKIP_SCOPE_GATE_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": int(time.time()),
            "reason": reason,
            "ttl_seconds": SKIP_SCOPE_GATE_TTL_SECONDS,
        }
        atomic_write_json(path, payload)
    except OSError:
        pass


def _capture_skip_git_guard(workspace: Path, prompt: str) -> None:
    """v0.20.0 — write single-shot git-guard bypass token when user types
    `bypass-git-guard: <reason ≥ 8 chars>`.

    Mirrors _capture_skip_clarification pattern. git_guardrails.py reads
    `.skip_git_guard_next.json` (mtime TTL 600s, single-use) to pre-authorize
    one agent-driven git op without disabling the hook globally.
    """
    import time
    m = BYPASS_GIT_GUARD_RE.search(prompt)
    if not m:
        return
    reason = m.group(1).strip()
    if not reason:
        return
    path = workspace / SKIP_GIT_GUARD_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": int(time.time()),
            "reason": reason,
            "ttl_seconds": SKIP_GIT_GUARD_TTL_SECONDS,
        }
        # v0.21 T03 (B4): atomic write.
        atomic_write_json(path, payload)
    except OSError:
        pass


def _capture_bypass_invariant(workspace: Path, prompt: str) -> None:
    """G2 v0.10.0 — write ephemeral bypass file when user typed
    `bypass-invariant: <id>` in their prompt.

    Why this exists: Claude Code's PreToolUse envelope does NOT contain
    the user prompt (only tool_name / tool_input / cwd / session_id).
    The legacy `invariant_guard._bypass_requested()` read
    `envelope.get("user_prompt")` which was always None → bypass marker
    never fired in production. UserPromptSubmit fires BEFORE PreToolUse
    and DOES have the prompt, so we write a session-local file that
    invariant_guard reads + consumes on next Edit.

    Single-use semantics: invariant_guard deletes the file on hit, so
    one `bypass-invariant: INV-1` token covers exactly one matching Edit.
    TTL prevents stale tokens leaking into a later session.
    """
    import time
    matches = BYPASS_INVARIANT_RE.findall(prompt)
    if not matches:
        return
    ids: list = []
    for chunk in matches:
        ids.extend(item.strip() for item in chunk.replace(",", " ").split() if item.strip())
    if not ids:
        return
    path = workspace / BYPASS_FILE_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ids": ids,
            "ts": int(time.time()),
            "ttl_seconds": BYPASS_TTL_SECONDS,
        }
        # v0.21 T03 (B4): atomic write.
        atomic_write_json(path, payload)
    except OSError:
        # Best-effort: silent on failure (don't break UserPromptSubmit flow).
        pass


def main() -> int:
    # Kill-switch: env var disables all enforcement (emergency).
    if os.environ.get("AGENT_TOOLKIT_DISABLE") == "1":
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        return 0

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        # Older Claude Code versions pass the prompt as plain stdin.
        envelope = {"prompt": raw}

    prompt = envelope.get("prompt") or envelope.get("user_prompt") or ""
    prompt = prompt.strip()

    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()

    # G2: capture bypass-invariant marker BEFORE the short-prompt early-out,
    # because a bare `bypass-invariant: INV-1` is short but load-bearing.
    # v0.13.0: same logic for `skip-clarification: <reason>`.
    if prompt:
        _capture_bypass_invariant(workspace, prompt)
        _capture_skip_clarification(workspace, prompt)
        _capture_bypass_gap_gate(workspace, prompt)
        _capture_skip_git_guard(workspace, prompt)
        _capture_bypass_debug_sentry(workspace, prompt)
        _capture_bypass_scope_gate(workspace, prompt)
        # v0.23 R3-fallback: forward-prep canonical-expectation marker.
        _capture_canonical_expected(workspace, prompt)

    # Heuristic skip for very short replies (yes/no/ok), questions about
    # earlier output, or empty prompts.
    if len(prompt) < 12:
        return 0

    _stack, _stack_bare, intent_map = _load_intent_map(workspace)

    # v0.21 T15 (M12): get primary skills + deferred ones for cache.
    skills, deferred = _matched_skills_with_deferred(prompt, intent_map)
    if not skills:
        return 0

    if _already_referenced(prompt, skills):
        return 0

    # v0.13.0 + v0.21: record suggested skills + deferred list.
    _write_last_intent_suggested(workspace, skills, prompt,
                                 deferred_skills=deferred)

    reminder = _format_reminder(skills, prompt)

    # JSON envelope is the documented Claude Code hook output shape;
    # plain stdout is the fallback for older harnesses.
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": reminder,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(run_main_safe(main))
