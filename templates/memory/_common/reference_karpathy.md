---
name: Karpathy reference
description: Upstream Karpathy guidelines repo we mirror locally; canonical source for the four behavioural principles.
type: reference
---
Upstream: https://github.com/forrestchang/andrej-karpathy-skills

- `CLAUDE.md` and `skills/karpathy-guidelines/SKILL.md` carry the four principles: Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution.
- License: MIT.
- Local mirrors: `.cursor/rules/karpathy-guidelines.mdc` (always-apply rule) and `.cursor/skills/karpathy-guidelines/SKILL.md` (focused skill).

**Why:** When we expand the local rule set, the upstream is the canonical source for behavioural wording. Diverging silently leads to drift between projects that share the Karpathy convention.

**How to apply:** Before editing the local Karpathy files, fetch the upstream `SKILL.md` to confirm wording is still in sync. Do not paraphrase — copy the principle wording verbatim and add project-specific addenda separately.
