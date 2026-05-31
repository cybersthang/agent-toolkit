"""v0.33 ⑤ — the Odoo 19 mail-framework claim must match source reality.

Adversarial review (2026-05-31) found the v19 rules asserted the mail
framework "was refactored to v2 in v19" — but the OWL mail/Discuss store
rewrite landed at the v16→17 boundary (the toolkit's own
`odoo-mail-v2-migration` skill says the triad is stable v17→v19). Regression
guard: no v19 rule may state the rewrite happened *in v19*, and the corrected
v16→17 attribution must be present.
"""
from __future__ import annotations

from pathlib import Path

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
V19_RULES = TOOLKIT_ROOT / "templates" / "cursor" / "rules" / "odoo-19"

# Overstated phrasings that wrongly pin the mail-v2 rewrite to v19.
_BANNED = (
    "mail framework was refactored to v2",
    "refactored to v2",
    "mail framework v2 is the #1",
)


def test_no_overstated_v19_mail_v2_claim():
    offenders = []
    for mdc in V19_RULES.glob("*.mdc"):
        text = mdc.read_text(encoding="utf-8").lower()
        for phrase in _BANNED:
            if phrase.lower() in text:
                offenders.append(f"{mdc.name}: {phrase!r}")
    assert not offenders, "v19 mail-v2 overstatement still present:\n" + "\n".join(offenders)


def test_corrected_v16_17_attribution_present():
    generic = (V19_RULES / "odoo-19-generic.mdc").read_text(encoding="utf-8")
    assert "v16→17" in generic, "corrected v16→17 mail-rewrite attribution missing"
    # the valuable 'verify installed source' guidance must survive the edit
    assert "installed Odoo 19 source" in generic
