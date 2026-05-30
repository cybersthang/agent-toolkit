# Credits & References

This toolkit is original work but stands on the shoulders of several
upstream projects + academic ideas. Adopting / extending any of these
in your own toolkit is encouraged — check each license.

## Upstream skill repos

- **[github/spec-kit](https://github.com/github/spec-kit)** — the
  5-phase Spec Kit workflow (`SPECIFY → CLARIFY → TASKS → ANALYZE →
  IMPLEMENT`) that this toolkit's slash-command surface mirrors.
  We added a 6th phase (`/verify` real-data probes via MCP) and renamed
  the entry point from `/specify` → `/plan` to match the DEV mental model.

- **[mattpocock/skills](https://github.com/mattpocock/skills) (MIT)** —
  Matt Pocock's open skill library. We adopted the structural ideas
  from these specific skills (cite paths kept in each SKILL.md
  "Reference" section):
  - [`engineering/to-prd`](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-prd/SKILL.md)
    — basis for `plan-feature/SKILL.md`.
  - [`engineering/zoom-out`](https://github.com/mattpocock/skills/tree/main/skills/engineering/zoom-out)
    — feeds the `plan-feature` discovery loop.
  - [`productivity/grill-me`](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me)
    + [`engineering/grill-with-docs`](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs)
    — basis for `clarify/SKILL.md` (1-Q-per-turn interview loop).

- **[forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)**
  — local mirror of Andrej Karpathy's behavioural guidelines (think
  before coding, smallest change, surgical edits, goal-driven
  verification). Sourced verbatim into `karpathy-guidelines/SKILL.md`
  and `templates/memory/_common/reference_karpathy.md`.

## Academic / methodology references

- **[Karl Popper](https://en.wikipedia.org/wiki/Falsifiability)
  *Logic of Scientific Discovery* (1959)** — "a claim that cannot be
  shown false also cannot be shown true". Backbone of
  `claim-falsification/SKILL.md` and `real-data-proof/SKILL.md` —
  every property claim must come with a perturbation that *could*
  refute it on real data.

- **Property-based testing tradition** —
  [Hypothesis](https://hypothesis.readthedocs.io/) (Python) +
  [QuickCheck](https://hackage.haskell.org/package/QuickCheck) (Haskell).
  The "perturb input → invariant must hold" frame in
  `claim-falsification` is the runtime analogue.

- **[Andrej Karpathy](https://karpathy.ai/)** — the
  *Think Before Coding / Simplicity / Surgical Changes / Goal-Driven*
  formulation that the toolkit treats as a hard invariant for every
  skill body and every agent turn.

## Runtime platforms the toolkit installs into

- **[Claude Code](https://docs.claude.com/en/docs/claude-code)** (Anthropic)
  — primary target; hooks (`templates/claude/hooks/*.py`), slash commands
  (`templates/claude/commands/*.md`), and `settings.json` are all Claude
  Code-shaped.

- **[Cursor IDE](https://cursor.com/)** — secondary target; the
  toolkit ships always-apply rules under `.cursor/rules/` and on-demand
  skills under `.cursor/skills/`.

- **[Codex CLI](https://github.com/openai/codex)** — supported via the
  same MCP servers (codebase, postgres, realdata_test, jira) +
  `.codex/` directory layout.

- **[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)**
  (Anthropic) — the protocol every shipped MCP server speaks
  (`codebase_server.py`, `postgres_server.py`, `jira_server.py`,
  `realdata_test_server.py`).

## Author + maintenance

- **Author / maintainer**: **Thang Vo** — Senior Developer (Odoo & Agent AI)
  - Contact: [ducthangict.dhtn@gmail.com](mailto:ducthangict.dhtn@gmail.com)
  - Zalo: [0989 464 344](tel:+84989464344) (`ictlucky.dhtn`)
  - Original work; toolkit is in active use on production Odoo 12 + 17
    Enterprise workspaces.
- **Issues / contributions**: open an issue on the toolkit repo or
  reach out via the maintainer contact above.
- **License**: toolkit is **MIT** — see [`LICENSE`](../LICENSE) at root.
  Third-party MIT attribution (mattpocock/skills, github/spec-kit,
  affaan-m/everything-claude-code, andrej-karpathy-skills) is
  consolidated in [`NOTICE`](../NOTICE). Original Python code in `lib/`,
  `setup.py` carries `# SPDX-License-Identifier: MIT` at file top;
  skills/hooks/templates inherit the toolkit LICENSE unless an in-file
  `license:` frontmatter states otherwise.
