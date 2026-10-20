"""Who a drug comes from: its originator lab, that lab's country, its current holders.

Three node kinds hang off a drug here (see ``docs/DRUGS.md`` "Regulatory history"),
shown in the panel's "Identification" section next to the first approval:

* ``drug_holders``: ONE node per (drug, market), ``holders[] = {market, names[],
  sources}``: the company that holds the marketing authorisation in that market TODAY,
  read by code off a regulator's own register (US: the sponsor of the drug's
  first-approval NDA on its Drugs@FDA page, corpus #18; France: the ``holder:`` line of
  the drug's brand-name product pages, BDPM corpus #16). ``names`` is a list because a
  market can carry several brand-name products held by different companies; each name
  has its own quote. A current holder is not the inventor (Seroquel's US NDA is held by
  CHEPLAPHARM today, AstraZeneca developed it), hence the separate originator.
* ``drug_originator``: ONE node per drug, ``originator = {name, now?}``: the company or
  lab the drug's English Wikipedia article says discovered / synthesized / developed it,
  worded as the sentence words it (``name`` must be a verbatim substring of the quote).
  ``now`` is that company's current name when a quote (usually the company's own
  article) says it was acquired / merged / renamed, cited apart in
  ``originator_now_sources`` (part of the same node, never graded alone).
* ``drug_originator_country``: ONE node per drug, ``originator_country`` (an id of
  :data:`history.COUNTRIES`): the originator company's country, from the company's own
  English Wikipedia article (an infobox Headquarters row or a lead sentence), attested by
  the country's pattern (``history.attests``), the same rule as a withdrawal country.

Built with the help of Claude Code.
"""

from __future__ import annotations

import re
from typing import Any

from . import history
from lib.placeholder import is_placeholder

from .provenance import _quote_sources

# The markets a holder is read for, in display order: one regulator register each.
HOLDER_MARKETS: tuple[str, ...] = ("us", "fr")

# A sentence about where a drug came from says someone discovered, synthesized,
# developed or invented it. The same pattern drives the fetcher (what is offered) and
# the applier (what passes), so "offered" and "accepted" cannot drift.
ORIGINATOR_RE = re.compile(
    r"\b(?:discover|synthesi[sz]|develop|invent|first (?:made|prepared|produced|described))",
    re.IGNORECASE)

# A company-article sentence giving a company's later name says it was acquired,
# merged, renamed or absorbed. "now" alone is too loose ("now marketed").
SUCCESSOR_RE = re.compile(
    r"\b(?:acquir|merg|renam|became (?:part|a subsidiary)|absorbed|taken over|took over|"
    r"bought|successor|now (?:part|known|a subsidiary|owned)|formerly)",
    re.IGNORECASE)


def drug_origin(drug: dict[str, Any]) -> dict[str, Any]:
    """The emitted ``holders``, ``originator`` and ``originator_country`` of one drug.

    Validates shapes and vocabularies so a hand edit with a typo fails the build rather
    than shipping a label-less id. Returns only the keys the drug carries.
    """
    did = drug["id"]
    out: dict[str, Any] = {}
    rows = []
    for h in drug.get("holders") or []:
        if h.get("market") not in HOLDER_MARKETS:
            raise KeyError(f"Drug {did!r} holder market {h.get('market')!r} unknown")
        names = h.get("names")
        if not names or any(is_placeholder(n) for n in names):
            raise ValueError(f"Drug {did!r} holder {h['market']} has no names: {h!r}")
        row: dict[str, Any] = {"market": h["market"], "names": list(names)}
        srcs = _quote_sources(h.get("sources"), f"Drug {did!r} holder {h['market']}")
        if srcs:
            row["sources"] = srcs
        rows.append(row)
    if rows:
        out["holders"] = sorted(rows, key=lambda r: HOLDER_MARKETS.index(r["market"]))
    og = drug.get("originator")
    if og:
        if is_placeholder(og.get("name")):
            raise ValueError(f"Drug {did!r} originator has no name: {og!r}")
        out["originator"] = {k: og[k] for k in ("name", "now") if og.get(k)}
        srcs = _quote_sources(drug.get("originator_sources"), f"Drug {did!r} originator")
        if srcs:
            out["originator_sources"] = srcs
        now = _quote_sources(drug.get("originator_now_sources"),
                             f"Drug {did!r} originator now")
        if bool(og.get("now")) != bool(now):
            raise ValueError(f"Drug {did!r} originator `now` needs its own sources "
                             f"(originator_now_sources), and only then")
        if now:
            out["originator_now_sources"] = now
    country = drug.get("originator_country")
    if country:
        if country not in history.COUNTRIES or country in history.SCOPES:
            raise KeyError(f"Drug {did!r} originator_country {country!r} unknown")
        if not og:
            raise ValueError(f"Drug {did!r} has an originator_country but no originator")
        out["originator_country"] = country
        srcs = _quote_sources(drug.get("originator_country_sources"),
                              f"Drug {did!r} originator_country")
        if srcs:
            out["originator_country_sources"] = srcs
    return out

