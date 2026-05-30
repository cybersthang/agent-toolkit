---
name: odoo-jira-workflow
description: The Jira-integrated dev workflow — read a ticket through the jira_production / jira_preproduction MCP, map it into a `/plan` spec, drive it through the Spec-Kit flow (/plan → /clarify → /tasks → /implement → /verify), and link the branch/commits/status back to the ticket. Use when the user mentions a ticket key (e.g. NK-123), asks for sprint/standup context, or wants a ticket turned into a working change. Version-agnostic — the Jira workflow is independent of the Odoo major version.
---

# Odoo — Jira → Spec-Kit Workflow (version-agnostic)

Two Jira profiles are wired up. **Pick the right one.** This body is 100%
version-agnostic — the same Jira tools work whether the project runs Odoo
12, 17, or any future version.

| Profile        | MCP server name      | When                                                         |
|----------------|----------------------|--------------------------------------------------------------|
| Production     | `jira_production`    | Live tickets, sprint/standup queries, post-merge bug triage. |
| Pre-Production | `jira_preproduction` | UAT verification, regression tickets, release rehearsal.     |

Base URLs and credentials live ONLY in `.codex/mcp.local.env` under
`{{ENV_PREFIX}}_JIRA_PRODUCTION_*` and `{{ENV_PREFIX}}_JIRA_PREPRODUCTION_*`.
The MCP starter wrappers map the profile-prefixed vars onto the generic
`{{ENV_PREFIX}}_JIRA_*` vars at launch. To see the URL the current session
resolved to, call `env_status` on the corresponding server. Never hard-code
URLs or credentials anywhere else.

> If the project preset doesn't ship Jira MCP, neither tool is available.
> Check `.mcp.json`; add Jira via `agent-toolkit.config.json` if needed.

## 0. The MCP surface (verified tool names)

Tool names below are **verified against
`templates/codex/mcp_servers/jira_server.py`** — the same tool set exists on
BOTH `jira_production` and `jira_preproduction`. Do not invent others.

| Tool | Required args | Purpose |
|------|---------------|---------|
| `env_status` | — | Confirm profile, base URL, username; check password is loaded. |
| `get_issue` | `key` | Normalised issue: summary, status, type, priority, assignee, labels, components, description, comments, attachments, issueLinks. |
| `get_issue_raw` | `key` | Same issue, full REST payload — use when you need a custom field not in the normaliser. |
| `search_issues` | `jql` | JQL search; `maxResults` default 20, max 100. |
| `list_projects` | (opt) `name_contains` | Browse projects by name substring. |
| `my_assigned_issues` | (opt) `maxResults`, `status_not` | Open issues assigned to the configured user (defaults exclude Done/Closed/Resolved). |

**HONEST, LOAD-BEARING LIMITATION — this MCP is READ-ONLY.**
There is **NO** `transition_issue`, `add_comment`, `update_status`,
`assign_issue`, or any write tool in `jira_server.py`. So:
- You **cannot** move a ticket's status (To Do → In Progress → Done) from here.
- You **cannot** post a comment or link a branch/commit to the ticket from here.
- "Update status / link branch / link commits" steps are done by the **DEV
  in the Jira UI or via git**, OR by a separate git/CI integration outside
  this MCP. This skill's job is to *read* intent in and *prepare* the text
  the DEV pastes back — not to write to Jira. Say this plainly when the user
  asks you to "set it to In Progress".

## 1. The flow: Jira (intent) → Spec-Kit (build) → Jira (close-out)

```
get_issue(KEY)  ──►  /plan  ──►  /clarify  ──►  /tasks  ──►  /implement ──► /verify
   (read intent)     (spec)     (close gaps)   (task list)   (code+/analyze)  (probe)
                                                                                  │
                                  draft close-out text (DEV pastes to Jira) ◄─────┘
```

The verified Spec-Kit chain (commands live in `.claude/commands/`):
`/plan` (writes spec to `.agent-toolkit/specs/<branch>/<slug>.md`) →
`/clarify` (auto-fires `/tasks` on completion) → `/tasks` (STOPs for DEV
review) → `/implement` (auto-fires `/analyze` first, then executes
`tasks.md`, then auto-fires `/verify`) → `/verify` (runs MCP probes).
The task brief's shorthand "/plan → /clarify → /implement → /verify"
collapses `/tasks` and `/analyze`, which are auto-chained — name them so the
DEV isn't surprised by the STOP gate after `/clarify`.

## 2. Concrete recipes

### A. Read a ticket and pull its intent into the conversation
```
env_status()                       # first call per session — confirm profile + URL reachable
get_issue({ key: "NK-123" })       # summary, description, comments, acceptance criteria
# need a custom field (e.g. "Steps to Reproduce", "Severity")?
get_issue_raw({ key: "NK-123" })   # then read fields.customfield_XXXXX
```
Cite the key as `[NK-123](<base_url>/browse/NK-123)` (base_url from `env_status`).

### B. Map the ticket → a `/plan` spec
1. Decide the slug from the ticket: kebab-case, <40 chars, ideally prefixed
   with the key so the spec is traceable — e.g. `nk-123-export-log-daily`.
2. Pass the ticket's *intent* (not the raw body) into `/plan`:
   ```
   /plan NK-123: <summary>. Acceptance: <bullet the AC from get_issue>.
   ```
3. `/plan` writes `.agent-toolkit/specs/<branch>/<slug>.md`. In the spec's
   context section, paste the ticket link + the AC verbatim so `/clarify`
   and `/verify` can check the build against the ticket, not your paraphrase.

### C. Drive the build
```
/clarify <slug>     # one question per turn until gaps closed; auto-fires /tasks
                    # → STOP here for DEV review of tasks.md
/implement <slug>   # /analyze (HALT on BLOCK) → execute tasks → /verify
```
`/verify` produces a Gap/Blocker/Pass table per User Story. The acceptance
criteria you pasted from the ticket are what each probe checks against.

### D. Branch & commit linking (DEV-side, NOT via this MCP)
The MCP cannot write to Jira. Prepare the artifacts the DEV uses:
- **Branch name** should carry the key so Jira's git integration links it
  automatically: `feature/NK-123-export-log-daily`. (Branch creation /
  commits are DEV-authorized git steps — never `git commit`/`push` without
  explicit DEV instruction; see project hard rules.)
- **Commit message** should start with the key: `NK-123 add daily export
  cron`. Most Jira git integrations index `KEY` in branch + commit and link
  them to the ticket without an API call.
- **Status transition** (In Progress / In Review / Done) is a DEV click in
  Jira (or a Smart Commit `#in-progress` if the org enabled them) — this MCP
  cannot perform it. Tell the DEV what to set; don't claim you set it.

### E. Sprint / standup context
```
my_assigned_issues({ maxResults: 25 })                 # my open work
search_issues({ jql: "project = NK AND sprint in openSprints() ORDER BY status", maxResults: 50 })
search_issues({ jql: "project = NK AND status = 'In Review' ORDER BY updated DESC" })
```
For post-merge triage on preprod, switch to `jira_preproduction` and run the
same JQL.

### F. Close-out text (DEV pastes into the ticket)
After `/verify` passes, draft the comment for the DEV to paste — don't claim
it was posted:
> NK-123 implemented in `feature/NK-123-export-log-daily`. Spec:
> `.agent-toolkit/specs/<branch>/<slug>.md`. /verify: all User Stories PASS
> (probe table attached). Touches modules: <A, B>. Ready for review.

## 3. Anti-patterns

- **Claiming you changed Jira state.** "I moved NK-123 to In Progress" /
  "I commented on the ticket" — the MCP is read-only. You can only *draft*
  the comment / *recommend* the transition for the DEV.
- **Mixing profiles in one answer** ("NK-100 in prod and NK-100 in preprod").
  Confirm with `env_status` which profile you're reading; default to
  `jira_production` for live tickets, `jira_preproduction` for UAT/staging.
- **Pasting the full issue body.** Pull the fields you need; the normaliser
  already truncates. Put the AC into the spec, not into chat.
- **Skipping `/clarify`/`/tasks` because "the ticket is clear."** The STOP
  gate after `/clarify` is a DEV review point — don't auto-`/implement`
  straight off a ticket.
- **Building from your paraphrase of the ticket** instead of the verbatim AC.
  `/verify` checks the build against what's in the spec; if you summarised
  the AC loosely, the probes verify the wrong thing.
- **Using Jira to answer code questions.** Jira is for intent; the `codebase`
  MCP (`odoo-codebase-discovery`) is for code. Don't grep a ticket for
  "where does this model live."
- **Inventing a slug unrelated to the key.** Prefix the slug + branch +
  commits with the ticket key so the trail is reconstructable later.

## Sibling skills

- `odoo-codebase-discovery` — map the code the ticket touches before `/plan`.
- `odoo-code-review` / `odoo-debug-troubleshoot` — review/fix the change.
- `odoo-data-verification` — probe real DB during `/verify`.
