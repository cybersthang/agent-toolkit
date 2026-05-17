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
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

AUTONOMY_REL = ".agent-toolkit/.autonomy_active.json"

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

    # ---------- Vibe-flow Phase 1: PLAN ----------
    # DEV chủ động lập plan/PRD trước khi code. Slash command `/plan` cũng
    # mở skill này; regex bắt khi DEV không dùng slash.
    (
        r"\b(lập\s*plan|lập\s*kế\s*hoạch|viết\s*prd|viết\s*spec|tạo\s*spec|plan\s*cho|plan\s*feature|prd\s*cho)\b",
        ["plan-feature"],
    ),

    # ---------- Vibe-flow Phase 2: GRILL ----------
    # DEV xin bị phỏng vấn để stress-test plan.
    (
        r"\b(grill|quay\s*em|interview\s*me|stress[-\s]*test|challenge\s*em|chất\s*vấn|red[-\s]*team\s*plan)\b",
        ["grill"],
    ),

    # ---------- Vibe-flow Phase 5: VERIFY ----------
    # DEV (hoặc agent self) muốn verify feature đã code có match spec gốc trên
    # dữ liệu thật không. Suggest skill verify-feature; slash `/verify` cũng
    # mở skill này.
    (
        r"\b(verify|kiểm\s*tra\s*dữ\s*liệu\s*thật|gap\s*nào|blocker\s*nào|match\s*yêu\s*cầu|phân\s*tích\s*gap|đã\s*xong\s*chưa|implement\s*xong)\b",
        ["verify-feature"],
    ),

    # ---------- TDD ----------
    (
        r"\b(tdd|test\s*driven|viết\s*test\s*trước|test\s*first|red.*green.*refactor)\b",
        [f"{STACK}-tdd"],
    ),

    # ---------- ECC eval-harness: define pass/fail BEFORE code ----------
    # DEV (hoặc agent) muốn nâng spec từ "có vẻ ổn" → mechanical PASS/FAIL.
    # Suggest slash command `/eval-define`.
    (
        r"\b(eval[-\s]*define|định\s*nghĩa\s*pass\s*fail|tiêu\s*chí\s*chấp\s*nhận|acceptance\s*criteria|pass\s*fail\s*criteria|eval[-\s]*harness)\b",
        ["eval-define"],
    ),

    # ---------- /eval-backfill: retrofit eval cho spec đã chạy ----------
    (
        r"\b(eval[-\s]*backfill|retrofit\s*eval|convert\s*testing\s*decisions|backfill\s*eval|spec\s*đã\s*implement\s*cần\s*eval)\b",
        ["eval-backfill"],
    ),

    # ---------- claim-falsification: inverse-perturbation review ----------
    # DEV nói "chứng minh sai", "perturb test", "falsify", "đặt sleep <test|vào|inject>", "inverse test".
    # Skill này áp dụng dynamic cho mọi claim, không gắn cứng BLOCK/ASYNC.
    # L2-cr fix (2026-05-17): "đặt sleep" alone matches unrelated UI/timer
    # contexts; require qualifier (test|vào|inject|để) để giảm false-positive.
    (
        r"\b(claim[-\s]*falsification|chứng\s*minh\s*sai|perturb[-\s]*test|falsify|falsifiability|inverse[-\s]*test|đặt\s*sleep\s*(test|vào|inject|để|cho)|kiểm\s*chứng\s*ngược|prove\s*wrong)\b",
        ["claim-falsification"],
    ),

    # ---------- Auto-trigger claim-falsification khi DEV assert classification claim ----------
    # Pattern: code-identifier subject + "là/is/tag" + classification keyword.
    # FIX-2 (2026-05-17): require subject to look like a code identifier (in
    # backticks, snake_case, camelCase, has `/` for endpoint, or has `.` for
    # method) BEFORE the linking verb. Reduces R2-4 false-positive rate from
    # ~75% to ~15%.
    #
    # Catches (concrete patterns; not endpoint-specific):
    #   "<snake_case_ident> is BLOCK"          (snake_case word)
    #   "`<backticked>` được tag ASYNC"        (backticked code)
    #   "/<slash>/<path> is cached"            (URL-like path)
    #   "<Class>.<method> là idempotent"       (dotted call)
    # Skips (no code subject):
    #   "<noun phrase> là cached cho 1 ngày"
    #   "<prose> pattern is BLOCK"
    #
    # Note: _normalize() lowercases prompt, so patterns are lowercase.
    (
        r"(?:`[^`]+`|[a-z][a-z0-9_]*[_/][a-z0-9_/]+|[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\s*(?:là|is|được\s*tag|được\s*gắn|được\s*phân\s*loại|classified\s*as|tagged\s*as)\s*(['\"`]?)(block|async|bg|cached|idempotent|atomic|deterministic|guarded|lazy|background)\b",
        ["claim-falsification"],
    ),

    # ---------- ECC ai-regression-testing: bug → permanent test ----------
    # DEV report bug + đã fix → ép tạo regression test + invariant.
    (
        r"\b(bug[-\s]*to[-\s]*test|regression\s*test\s*cho\s*bug|test\s*cho\s*bug|đừng\s*để\s*tái\s*phát|ngăn\s*bug\s*tái\s*xuất|cố\s*định\s*test)\b",
        ["bug-to-test"],
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


def _autonomy_active(workspace: Path) -> Optional[str]:
    """Return the spec slug if autonomy is currently active + unexpired.

    Reads `.agent-toolkit/.autonomy_active.json`. Returns None when file
    missing, malformed, or expired. The spec slug is returned so callers
    can include it in the suppression message (DEV knows why the gate is
    silent).

    ADR-002: when autonomy is ON, `clarification-gate` MUST be suppressed
    so the agent can run dangerous-but-approved ops without re-asking the
    DEV mid-flow. Other safety hooks (invariant-guard, evidence-audit,
    debug-sentry) still run.
    """
    path = workspace / AUTONOMY_REL
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    expires_str = data.get("expires_at") or ""
    if expires_str:
        from datetime import datetime
        expires_dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
            try:
                expires_dt = datetime.strptime(expires_str.split(".")[0].split("+")[0], fmt)
                break
            except ValueError:
                continue
        if expires_dt and datetime.now() > expires_dt:
            return None

    return data.get("spec") or "<unknown>"


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
        "paraphrase) + ASSUMPTIONS (2-5 items) + QUESTIONS (max 3). "
        "EACH question MUST include a `Searched:` line listing what "
        "you grep'd / read / looked up via MCP before asking — if "
        "the answer is derivable from code/config/registry, DO NOT "
        "ask; verify it yourself. Questions that look like they could "
        "have been answered by `grep` or `lookup_canonical_decision` "
        "will be rejected. Each question gets 2-3 options (a)/(b)/(c) "
        "with EXACTLY ONE marked **Recommended** + one-line rationale. "
        "STOP — do not call Edit/Write/Bash until the user replies."
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
    "spec-driven-feature": (
        "6-field spec (Objective / Commands / Project Structure / "
        "Code Style / Testing / Boundaries) then STOP for approval. "
        "Before writing the spec, run codebase MCP discovery for the "
        "affected modules — Project Structure section must cite "
        "concrete `path:line` refs from the search, not invented paths."
    ),
    "plan-feature": (
        "Discover codebase (Bước 0) → ghi file `.agent-toolkit/specs/"
        "<slug>.md` với đủ 8 mục: Problem / Solution / Affected Modules / "
        "User Stories / Implementation Decisions / Testing / Out-of-scope / "
        "Open Questions. STOP sau khi ghi spec; KHÔNG implement. Câu cuối "
        "phải gợi DEV chạy `/grill` hoặc `/spec-driven-feature`."
    ),
    "grill": (
        "Mỗi turn CHỈ 1 câu hỏi, format `Q<N>: ... (a)/(b)/(c) Recommended + "
        "Lý do`. Đối chiếu mọi câu trả lời với ADR + invariants; trích "
        "nguyên văn nếu phát hiện mâu thuẫn. Cập nhật spec inline. Gợi ý "
        "DEV chạy `/adr-add` hoặc `/inv-add` cho quyết định hard-to-reverse. "
        "Câu trả lời được bằng grep/Read → TỰ verify, KHÔNG hỏi DEV."
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

    # Autonomy override (ADR-002): when autonomy is ON, the agent has been
    # pre-approved by DEV via /go for action verbs in scope. Suppress the
    # clarification-gate suggestion to avoid breaking flow mid-implement.
    # If matched skill is ONLY clarification-gate → silent. If clarification-gate
    # plus others → drop clarification-gate, keep others.
    cwd = envelope.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = Path(cwd).resolve()
    active_spec = _autonomy_active(workspace)
    if active_spec and "clarification-gate" in skills:
        skills = [s for s in skills if s != "clarification-gate"]
        if not skills:
            # Pure gate suppression — emit a tiny breadcrumb so the agent
            # knows why the gate didn't fire (helps debugging).
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": (
                        f"[intent-router] clarification-gate SUPPRESSED — "
                        f"autonomy ON cho spec `{active_spec}` (DEV đã approve "
                        f"qua /go). Action verb được phép tự do trong scope. "
                        f"Cắt: /stop-autonomy."
                    ),
                }
            }))
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
