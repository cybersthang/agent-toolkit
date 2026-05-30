"""evidence_audit sub-package — split for maintainability.

The Stop hook is the single entry: `.claude/hooks/evidence_audit.py`.
That script delegates to modules here:

- `strip`           — context-aware text stripping (code blocks, inline
                      code, blockquotes, markdown links, tables)
- `transcript`      — JSONL transcript parsing + turn-split + tool_use/
                      tool_result extraction + TodoWrite state walk
- `claim_audit`     — original generic claim audit (CLAIM_PATTERNS +
                      DISCLAIMER_MARKERS + EVIDENCE_TOOLS)
- `pass_contract`   — PASS-claim contract (acceptance probes registry +
                      probe match + evidence-tool requirement)
- `progress_checks` — 5 cross-checks A-E (action_ghost,
                      tool_result_fabrication, phantom_citation,
                      todo_inconsistency, overcount)
- `reasons`         — block-reason formatters
- `telemetry`       — append every hook invocation to
                      `.codex/logs/hook_events.jsonl`
"""
