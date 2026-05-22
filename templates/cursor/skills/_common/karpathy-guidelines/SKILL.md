---
name: karpathy-guidelines
description: Behavioral guidelines (Karpathy) to reduce common LLM coding mistakes. Use when writing, reviewing, or refactoring code to avoid overcomplication, make surgical changes, surface assumptions, and define verifiable success criteria.
license: MIT
---

# Karpathy Guidelines

**Tradeoff:** these guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Self-test: "Would a senior engineer call this overcomplicated?" If yes, simplify.

## 2a. Grep Before Write (anti-duplication probe)

Before adding any new function, class, or non-trivial helper:

```
1. Grep workspace for the identifier (or 1-2 close variants).
2. Cite results in response (path:line if hit, "Searched: <pattern> → 0 hits" if not).
3. Decide one of: reuse / extend / rewrite — with one-line reason.
```

Duplicate logic under different names is the #1 AI-coding bloat pattern. The 3 lines above cost 5 seconds and eliminate 90% of it. See sibling skill `reuse-first-then-write` for the full 3-step workflow with examples.

## 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.
- Remove imports/variables/functions that YOUR change made unused; do not delete pre-existing dead code unless asked.

The test: every changed line traces directly to the user's request.

## 4. Goal-Driven Execution

Define success criteria. Loop until verified.

- "Add validation" => "Write tests for invalid inputs, then make them pass."
- "Fix the bug" => "Write a test that reproduces it, then make it pass."
- "Refactor X" => "Ensure tests pass before and after."

For multi-step tasks, state a brief plan:

```
1. [Step] => verify: [check]
2. [Step] => verify: [check]
3. [Step] => verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
