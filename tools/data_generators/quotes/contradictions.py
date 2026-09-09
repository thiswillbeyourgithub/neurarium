"""Where one corpus **denies** what another states (the ``contradicted`` badge).

Every other doubt this package records is about a quote's *reach*: the sentence is on
the page, but it may not be about this node (see ``uncertainty.py``). This one is about
a quote's *truth*, and it is the only kind the dataset cannot settle: two graded,
quote-gated sources say opposite things, and picking a winner would mean asserting a
judgement neither corpus makes.

The recurring shape, and the reason this file exists at all, is **in vitro vs in vivo**.
A prescriber's manual states an interaction as a bare fact ("Inhibits CYP3A4"); the
pharmacology literature qualifies it ("in vivo, ... do not significantly affect the
activity of ... CYP3A4"). Both sentences are real. The laboratory effect exists and the
bedside effect does not, and a terse bullet has no room to say so. Dropping the row would
hide what the manual prints; keeping it silently would let the reader believe something
the better-evidenced source contradicts. So the row ships, flagged, with the denial
quoted underneath it.

**Hand-curated, unlike the three derived flags in** ``uncertainty.py``. A scan for
"negation sentence naming an isoform this drug modulates" over the stored articles
returns six pairs, of which three are not contradictions at all:

* a caveat scoped to two named substrates ("bupropion does not seem to affect the
  concentrations of CYP2D6 substrates fluoxetine and paroxetine") is a *detail of* the
  inhibition, not a denial of it;
* an exception clause ("interactions are considered unlikely ... **with possible
  exceptions such as** CYP2A6 substrates") actually affirms the interaction while its
  words read as a negation.

At a 50% false-positive rate the derivation would encode its own errors as doubt, which
is worse than the silence it replaces. So each entry below was read in context and
written by hand, and the ordinary quote gate (``check_data.py`` family 5) still confirms
it verbatim on the cited page, exactly like the claim it doubts.

Shape: ``(drug_id, enzyme, role) -> source``. ``generate_data.py`` raises if a key names
no emitted enzyme row, so a re-run of either CYP fetcher cannot silently strip the flag
and leave the contradiction unmarked.
"""
from __future__ import annotations

from typing import Any


def _wiki(slug: str, quote: str) -> dict[str, Any]:
    """A denial read off the stored English article (corpus #9), graded like any quote."""
    return {"corpus": "wikipedia_pharm", "page": slug, "quote": quote,
            "provenance": "verified", "llm": "opus"}


ENZYME_CONTRADICTIONS: dict[tuple[str, str, str], dict[str, Any]] = {
    # Stahl's fluoxetine monograph (p.331) prints a bare "Inhibits CYP3A4". Wikipedia
    # cites Sager et al. 2014 (Clin Pharmacol Ther 95:653), whose whole subject is the
    # in vitro -> in vivo correlation for exactly these isoforms: the inhibition is real
    # in the dish and not at the bedside.
    ("fluoxetine", "cyp3a4", "inhibitor"): _wiki(
        "fluoxetine",
        "In vivo, fluoxetine and norfluoxetine do not significantly affect the "
        "activity of CYP1A2 and CYP3A4"),
    # Stahl p.83 states "Induces CYP3A4 (and slightly CYP1A2)" for armodafinil, carrying
    # its own hedge. The article denies the CYP1A2 half outright, and pointedly: the
    # induction is modafinil's, not its R-enantiomer's.
    ("armodafinil", "cyp1a2", "inducer"): _wiki(
        "armodafinil",
        "In contrast to modafinil, however, armodafinil does not induce CYP1A2"),
    # Stahl p.553 already hedges ("Inhibits CYP2C19 (and perhaps CYP2C9)"), so this one
    # is a disagreement the weaker source half-anticipates. Kept flagged rather than
    # dropped: the hedge is Stahl's, the denial is the article's, and neither is ours.
    ("modafinil", "cyp2c9", "inhibitor"): _wiki(
        "modafinil",
        "However, other in-vitro studies find no significant inhibition of CYP2C9"),
}
