# Security policy

## Supported versions

agent-toolkit follows semver. Security fixes target the latest minor release line; older minors receive fixes only for issues rated **High** or **Critical**.

| Version | Supported |
|---------|-----------|
| 0.12.x | ✓ active |
| 0.11.x | ✓ critical fixes only |
| ≤ 0.10.x | ✗ — upgrade |

## Reporting a vulnerability

**Please do not open a public issue for security reports.**

Send an email to the maintainer address listed in `README.md` with the subject line `[agent-toolkit security]`. Include:

1. A description of the issue and its impact.
2. Reproduction steps — a minimal script or sequence is ideal.
3. Affected version(s) (`python setup.py --version`).
4. Your suggested fix or workaround, if any.

You should receive an acknowledgement within **5 working days**. If you don't, please follow up — the email may have been filtered.

After triage:

- **Critical / High** (RCE, credential exfiltration, hook-chain bypass that disarms `invariant_guard` blocker rules silently): patch released within 14 days where feasible. CVE filed.
- **Medium** (information disclosure, denial-of-service in a hook that propagates to the agent loop): patch released in the next minor.
- **Low** (cosmetic, defence-in-depth): folded into the next minor; credited in CHANGELOG.

## Disclosure

We follow coordinated disclosure: please give us reasonable time (default 90 days, longer if the fix needs upstream coordination with Claude Code or Cursor) to patch before public disclosure. We'll credit you in the CHANGELOG unless you ask otherwise.

## Threat model — what's in scope

The toolkit installs Python hooks that run with the user's local privileges inside Claude Code / Cursor / Codex agent sessions. Concretely, in-scope concerns include:

- **Hook bypass that defeats `severity: blocker` invariants** — e.g. a crafted envelope that crashes `invariant_guard.py` and falls open instead of fail-closed. (`run_main_safe` + G4 corrupt-state-deny in v0.10.0 + AGENT_TOOLKIT_STRICT=1 are the defences here; report regressions.)
- **Credential leak through a hook output / log** — anything that writes `password=`, API tokens, or session cookies into `.agent-toolkit/.hook_*_log.json` ring buffers. Hooks should never log envelope `tool_input` verbatim.
- **Path traversal / arbitrary file write** in installer (`setup.py init` / `update`).
- **Pickle / yaml.unsafe_load** anywhere in the toolkit. The toolkit uses `yaml.safe_load` only; `json.loads` for everything else. Regressions here are CRITICAL.
- **Telemetry export that exfiltrates beyond the workspace** — `hook_telemetry_export.py` (v0.11.0 G6) is append-only to a local file; any change that ships data over the network without explicit opt-in is a security issue.

## Out of scope

- The behaviour of an underlying model (Claude, Cursor) refusing to follow a hook's `additionalContext`. That's a model-layer concern, not a toolkit concern.
- Bugs in third-party MCP servers wired into a consumer project. Report those to their upstream.
- Issues that require the attacker to already have local code-execution on the developer's machine.

## Hardening recommendations for consumers

1. Set `AGENT_TOOLKIT_STRICT=1` in CI environments where hook crashes must propagate (default is fail-open).
2. Keep `.codex/mcp.local.env` permissions to `600` on POSIX; don't commit it.
3. Rotate any token mistakenly pasted into a hook log — the local ring buffers are not encrypted.
4. Review `.agent-toolkit/invariants.json` and `decision-log.md` in code review; they are the project's enforcement contract.
