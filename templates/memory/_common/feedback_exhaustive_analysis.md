---
name: Exhaustive analysis in one pass
description: User wants a single deep audit that finds ALL issues, not iterative discovery across sessions where each pass surfaces new findings.
type: feedback
---
When the user asks "phân tích sâu" or "review module/codebase":
- Do ONE exhaustive pass across ALL angles before reporting back; do not drip-feed findings across sessions.
- Required audit dimensions for a deep review (use this as a checklist, not a menu): persisted JSON schema, all SQL touchpoints, gzip/compression transparency, cron + background workers, HTTP controllers, ORM hooks/monkey-patches, view XML field references, JS dashboard consumers, test coverage gaps, config/security/data files, edge cases (empty/huge/concurrent/error paths), unit-mismatch (ms vs s vs ns), naming consistency across surfaces, double-counting in aggregations, drift formulas.

**Why:** User explicitly complained on 2026-05-08 that each session uncovers new issues that should have been caught the first time — feels inconsistent and erodes trust. Their words: "sao cứ mỗi lần lại ra 1 cái mới thế Nghiên cứu 1 lần nghiên cứu sâu chứ."

**How to apply:** Before reporting findings on any deep review, run through the audit checklist above and confirm each dimension was probed. If a dimension was skipped (e.g. could not run due to missing data), say so explicitly in the report — do not silently leave gaps that re-surface later as "newly discovered" issues.
