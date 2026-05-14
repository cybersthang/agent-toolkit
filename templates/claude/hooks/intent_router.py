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

Templated at install time by the toolkit; `{{STACK_FRAMEWORK}}` and
`{{STACK_FRAMEWORK_VERSION}}` are substituted with concrete values
(e.g. `odoo` and `12`).

Edit this file to extend or tune the routing table. It's plain Python
and the install-time templating only touches the two stack placeholders.
"""
from __future__ import annotations

import io
import json
import re
import sys
from typing import List, Tuple

# Claude Code pipes the hook envelope as UTF-8 JSON. On Windows the
# default stdin/stdout encoding is cp1252, which mangles Vietnamese
# (and any non-Latin) characters in the user's prompt. Re-wrap both
# streams as UTF-8 before any read/print.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# At install time the toolkit substitutes these two placeholders. If you
# edit this file in-place, keep them spelled exactly as below — toolkit
# update re-templates only `{{...}}` tokens.
STACK = "{{STACK_FRAMEWORK}}-{{STACK_FRAMEWORK_VERSION}}"  # e.g. "odoo-12"
STACK_BARE = "{{STACK_FRAMEWORK}}"                          # e.g. "odoo"

# (regex_pattern, [skill_names]) — patterns matched case-insensitive on
# the raw prompt text. Skill names are emitted verbatim into the
# reminder, so they must match the on-disk skill folder names.
INTENT_MAP: List[Tuple[str, List[str]]] = [
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
        ["code-review", f"{STACK_BARE}-code-review", "doubt-driven-review"],
    ),
    (
        r"\b(double[-\s]?check|are\s*you\s*sure|chắc.*không|chắc.*chưa|sure\?)\b",
        ["doubt-driven-review"],
    ),

    # ---------- Discovery / lookup ----------
    (
        r"\b(how\s*do\s*we|convention|recurring|canonical|làm\s*sao.*project|chuẩn.*project|theo\s*chuẩn)\b",
        [f"{STACK}-deterministic-answers"],
    ),
    (
        r"\b(where\s*is|tìm\s*file|find.*file|trace.*call|locate|định\s*nghĩa.*ở\s*đâu|đọc\s*hiểu\s*module)\b",
        [f"{STACK}-codebase-discovery"],
    ),

    # ---------- Verify against real data ----------
    (
        r"\b(real\s*db|prod\s*data|verify.*real|kiểm\s*tra.*dữ\s*liệu|live\s*verify|thật\s*hay\s*không)\b",
        [f"{STACK}-data-verification"],
    ),

    # ---------- Debug ----------
    (
        r"\b(bug|lỗi|error|exception|traceback|không\s*chạy|crash|stuck|treo|hang|fail.*test)\b",
        [f"{STACK}-debug-troubleshoot"],
    ),

    # ---------- Feature / module ----------
    (
        r"\b(tạo\s*module|scaffold|new\s*module|module\s*mới)\b",
        ["spec-driven-feature", f"{STACK}-module-scaffold"],
    ),
    (
        r"\b(feature\s*mới|implement|refactor|new\s*feature|tính\s*năng\s*mới|thêm.*tính\s*năng|add.*feature)\b",
        ["spec-driven-feature"],
    ),

    # ---------- TDD ----------
    (
        r"\b(tdd|test\s*driven|viết\s*test\s*trước|test\s*first|red.*green.*refactor)\b",
        [f"{STACK}-tdd"],
    ),

    # ---------- Patterns / Jira ----------
    (
        r"\b(theo\s*pattern|follow.*style|tuân.*chuẩn|project\s*style|code\s*style)\b",
        [f"{STACK}-code-patterns"],
    ),
    (
        r"\b(jira|nkv[-\s]?\d+|ticket|sprint)\b",
        [f"{STACK}-jira-workflow"],
    ),
]


def _normalize(text: str) -> str:
    """Collapse whitespace + lowercase for regex matching."""
    return re.sub(r"\s+", " ", text).lower()


def _matched_skills(prompt: str) -> List[str]:
    """Return ordered, deduplicated list of skill names suggested by the prompt.

    Priority rule: when an action-verb prompt triggers
    `clarification-gate`, that skill is returned EXCLUSIVELY — the
    follow-up skills (debug-troubleshoot, spec-driven-feature, etc.)
    are suppressed for this turn so the agent doesn't load ~1500 lines
    of SKILL.md content at once and lose focus on the user's prompt.
    Those skills re-emerge on the next turn ("go" / answers to the
    gate's questions), which typically won't contain action verbs and
    won't re-trigger the gate.
    """
    norm = _normalize(prompt)
    seen = set()
    out: List[str] = []
    for pattern, skills in INTENT_MAP:
        if re.search(pattern, norm, flags=re.IGNORECASE | re.UNICODE):
            for s in skills:
                if s not in seen:
                    seen.add(s)
                    out.append(s)

    # Priority: if the clarification-gate is on the list, return ONLY
    # it. The gate must complete before downstream action skills load.
    if "clarification-gate" in seen:
        return ["clarification-gate"]
    return out


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
        "paraphrase) + ASSUMPTIONS (2-5 items) + QUESTIONS (max 3, "
        "each with 2-3 labelled options (a)/(b)/(c) and EXACTLY ONE "
        "marked **Recommended** + one-line rationale). STOP — do not "
        "call Edit/Write/Bash until the user replies 'go' or answers "
        "the questions."
    ),
    "code-review": (
        "Count table (BLOCKER/MEDIUM/LOW) + per-finding Proof line "
        "tracing trigger → observable failure."
    ),
    "doubt-driven-review": (
        "Each finding adds a `Doubt-pass:` line stating the strongest "
        "doubt + how it was refuted (or 'unknown — user question')."
    ),
    "spec-driven-feature": (
        "6-field spec (Objective / Commands / Project Structure / "
        "Code Style / Testing / Boundaries) then STOP for approval."
    ),
}


def _format_reminder(skills: List[str]) -> str:
    """Render the system reminder; tailor expectations per matched skill."""
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
    return (
        f"[intent-router] Detected intent in user prompt. Open these "
        f"skills BEFORE answering: {skill_list}. Apply each skill's "
        f"STOP checkpoints." + format_note +
        " Suppress this reminder by referencing the skill name "
        "explicitly in your next turn."
    )


def main() -> int:
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

    # Heuristic skip for very short replies (yes/no/ok), questions about
    # earlier output, or empty prompts.
    if len(prompt) < 12:
        return 0

    skills = _matched_skills(prompt)
    if not skills:
        return 0

    if _already_referenced(prompt, skills):
        return 0

    reminder = _format_reminder(skills)

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
    sys.exit(main())
