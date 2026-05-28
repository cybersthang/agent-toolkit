# v0.23 C1 (two-source)
"""Two-source verification for critical claims.

Why this exists
---------------
`evidence_audit.py`'s PASS-claim contract trusts a single MCP server's
output without question. If a verification probe reads from Postgres and
that node is a read-replica suffering replication lag, the query can
return STALE data — the probe "passes" against data that no longer
reflects reality (a false-positive verification). Reviewer R1 flagged
this for financial / data-integrity claims where a stale read is
indistinguishable from a correct one.

The mitigation: for claims a probe explicitly marks `critical`, require
corroborating evidence from a SECOND distinct MCP source. A real value
that agrees across two independent backends (e.g. `mcp__postgres__` AND
`mcp__codebase__`, or `mcp__realdata_test__` AND a second confirm) is far
harder to fake via replica lag than a single-source read.

Design — conservative rollout
------------------------------
This layer is deliberately:

  * **Opt-in (default OFF).** A probe is subject to cross-source checking
    ONLY when it declares ``cross_source_required: true`` (and is marked
    ``severity: blocker``). Existing probes are untouched.
  * **Warn-only (first version).** When the requirement is NOT met the
    caller emits a non-blocking warning rather than blocking the Stop.
    This avoids false-blocking established workflows during rollout. A
    future version can promote the warning to a block once the signal is
    trusted in the field.

How to enable on a probe
------------------------
Add the flag to the probe entry in
``.agent-toolkit/acceptance-probes.json``::

    {
      "id": "ledger-balance-integrity",
      "severity": "blocker",
      "cross_source_required": true,          <-- opt in here
      "evidence": {
        "required_tools": ["mcp__postgres__query_readonly"],
        "min_calls": 1
      }
    }

With the flag set, the turn must also call a tool from a DIFFERENT MCP
server prefix (e.g. ``mcp__codebase__search_text`` or
``mcp__realdata_test__eval_orm_expression``) so the critical value is
corroborated by two independent backends. With it absent/false, this
module is a no-op for that probe.

Public API
----------
  * ``requires_cross_source(claim_text, probe) -> bool``
  * ``cross_source_satisfied(tool_calls) -> bool``
  * ``cross_source_warning(...)`` — convenience reason-string builder.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# v0.23 C1 (two-source) — minimum distinct MCP server prefixes required to
# consider a critical claim corroborated. Two independent backends defeat a
# single-node replica-lag false positive.
MIN_DISTINCT_SOURCES = 2

# v0.23 C1 (two-source) — claim phrases that mark a turn as making a
# critical (data-integrity / financial) assertion. Used as a secondary
# signal when a probe opts in but we also want to confirm the response
# actually claims something critical (vs. an incidental match).
_CRITICAL_CLAIM_RE = re.compile(
    r"\b(balance|ledger|reconcil\w*|integrity|financial|amount|total|"
    r"khớp\s*sổ|đối\s*soát|toàn\s*vẹn|số\s*dư|chính\s*xác)\b",
    re.IGNORECASE | re.UNICODE,
)

# v0.23 C1 (two-source) — matches an MCP tool name's server prefix:
# `mcp__<server>__<tool>` → captures `mcp__<server>__`.
_MCP_PREFIX_RE = re.compile(r"^(mcp__[A-Za-z0-9_\-]+?__)")


def _is_truthy(value: Any) -> bool:
    """Tolerant truthiness for JSON-config booleans (bool / "true" / 1)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return False


def requires_cross_source(claim_text: str, probe: Dict[str, Any]) -> bool:
    """Return True if `probe` opts into two-source verification for this turn.

    A probe is subject to cross-source checking only when ALL hold:

      * it declares ``cross_source_required: true`` (opt-in — default OFF),
      * its severity is ``blocker`` (we never gate soft/warn probes), and
      * the turn's text actually makes a critical-class claim (financial /
        data-integrity), OR the probe sets ``cross_source_force: true`` to
        skip the text heuristic.

    The text gate prevents a generically-tagged probe from demanding two
    sources on an unrelated, non-critical statement. Set
    ``cross_source_force`` when the probe's mere activation is itself the
    critical signal.
    """
    if not isinstance(probe, dict):
        return False
    if not _is_truthy(probe.get("cross_source_required")):
        return False
    severity = str(probe.get("severity") or "blocker").lower()
    if severity != "blocker":
        return False
    if _is_truthy(probe.get("cross_source_force")):
        return True
    return bool(_CRITICAL_CLAIM_RE.search(claim_text or ""))


def distinct_mcp_sources(tool_calls: List[Dict[str, Any]]) -> List[str]:
    """Return the sorted set of distinct `mcp__<server>__` prefixes used.

    Non-MCP tools (Read/Grep/Bash/…) contribute nothing here — only
    independent MCP backends count toward corroboration.
    """
    seen = set()
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        name = call.get("name") or ""
        m = _MCP_PREFIX_RE.match(name)
        if m:
            seen.add(m.group(1))
    return sorted(seen)


def cross_source_satisfied(
    tool_calls: List[Dict[str, Any]],
    min_sources: int = MIN_DISTINCT_SOURCES,
) -> bool:
    """Return True if the turn used ≥`min_sources` distinct MCP prefixes.

    This is the corroboration check: a critical value confirmed by two
    independent MCP backends is robust against a single replica-lag
    false-positive. A single source — no matter how many calls — does not
    satisfy it.
    """
    return len(distinct_mcp_sources(tool_calls)) >= int(min_sources)


def cross_source_warning(
    matched_probes: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
) -> Optional[str]:
    """Build a non-blocking warning string when ≥1 opted-in critical probe
    lacks two-source corroboration. Returns None when nothing to warn.

    Warn-only by design (v0.23 C1): the caller routes this through the
    `additionalContext` envelope, not a `block`, so existing workflows are
    never false-blocked during rollout.
    """
    sources = distinct_mcp_sources(tool_calls)
    if len(sources) >= MIN_DISTINCT_SOURCES:
        return None
    ids = [p.get("id", "?") for p in matched_probes if isinstance(p, dict)]
    if not ids:
        return None
    return (
        "[evidence-audit][cross-source][WARN] Critical probe(s) "
        f"{', '.join(ids)} declared `cross_source_required: true` but this "
        f"turn's verification used only {len(sources)} MCP source"
        f"{'' if len(sources) == 1 else 's'} "
        f"({', '.join(sources) or 'none'}). A single-source read can be a "
        "replica-lag false positive on data-integrity / financial claims. "
        f"Recommend corroborating with a SECOND distinct MCP backend "
        f"(≥{MIN_DISTINCT_SOURCES} of e.g. mcp__postgres__, mcp__codebase__, "
        "mcp__realdata_test__) before chốt. "
        "[warn-only — not blocking this Stop in v0.23]"
    )
