---
name: No AI commit
description: AGENT (any Claude model — Opus, Sonnet, Haiku) MUST NOT run git commit/push/add unless DEV explicitly authorizes it in the current turn. DEV is the sole gatekeeper for git state changes.
type: feedback
---
**AGENT (any Claude model — Opus / Sonnet / Haiku) MUST NOT execute `git commit`, `git push`, or `git add` through the Bash tool unless DEV explicitly says so in the current turn.** "Explicit" means a direct imperative like "commit cái này" / "push lên đi" / "commit this" — NOT implied by "ship feature", "fix toàn bộ", "/implement", "/verify", or any task-completion phrase.

**Why:** Cross-model drift is real — one Claude variant can honor the rule while another variant in a parallel session ignores it. Recorded incident: a separate Claude session committed feature work to a feature branch with `Co-Authored-By: Claude <model>` in the body, even though `CLAUDE.md` already documented "AGENT ko được commit hay push code. DEV sẽ là người quyết định". Prose rules in `CLAUDE.md` alone are not load-bearing across all models — memory + cross-link reinforcement is needed so every session loads the rule on first turn via `MEMORY.md`.

**How to apply:**
1. Default stance: read-only on git. Edit/Write files freely. Run `git status` / `git log` / `git diff` / `git reflog` for inspection. NEVER `git commit` / `git push` / `git add`.
2. If a task naturally seems to end in "and commit", STOP and ask DEV: *"Tôi đã ship xong. Bạn muốn commit gì không, hay tự commit?"* — wait for explicit authorization in the next DEV reply.
3. If DEV authorizes commit, follow the Bash-tool guide commit format and include `Co-Authored-By: Claude <model> <noreply@anthropic.com>` in the body so the commit is auditable as AI-made.
4. NEVER push regardless — even if commit is authorized, `git push` is a separate explicit step requiring separate explicit authorization.
5. NEVER use `--no-verify`, `--no-gpg-sign`, or `git push --force` under any circumstance unless DEV explicitly types those flags themselves.
6. If DEV asks "did AGENT commit?", search the session transcript JSONL for `"command":\s*"[^"]*git[^"]*(commit|push|add)` before answering — give evidence-based answer, not memory-based.

**Related memories:** [[credentials-policy]] (other "DEV decides, AGENT acts on explicit auth only" rules).
