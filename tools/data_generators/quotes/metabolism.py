"""Which enzyme *forms* each active metabolite (the ``drug_metabolite_enzyme`` nodes).

The mirror image of ``drug_enzymes``. There, the drug is the thing acted on ("olanzapine
is a substrate of CYP1A2"); here the *metabolite* is the product ("CYP2D6 turns venlafaxine
into O-desmethylvenlafaxine"). Same pharmacokinetic axis, no anatomy, nothing lit in the 3D
scene; what it buys is the prodrug story, the reason a CYP2D6 poor metabolizer gets little
from codeine or tramadol and why a CYP2D6 inhibitor changes what a venlafaxine dose actually
delivers.

**Hand-curated on purpose, unlike every other enzyme row.** ``fetch_cyp.py`` and
``fetch_cyp_wikipedia.py`` grep their claims because the source sentence has a fixed shape.
This claim does not: the corpora state it as prose, in a dozen shapes, and the near misses
are all *wrong in the same direction*. Three traps a pattern would fall into, all met while
surveying the 36 metabolite rows:

* an enzyme that **clears** the metabolite rather than making it (clobazam's own article
  states both in adjacent sentences; selegiline's poor-metabolizer paragraph is entirely
  about clearance);
* an enzyme named on the metabolite's own article with **no parent in the sentence** ("It is
  formed by dealkylation via CYP3A4" on the mCPP page: from trazodone, not nefazodone);
* an enzyme handling a **different** metabolite of the same drug (valbenazine's CYP3A4/5
  oxidation makes monooxidized valbenazine, not the dihydrotetrabenazine we list).

So each row below was read in context and written by hand, and the quote gate
(``check_data.py``) still confirms it verbatim on the cited page. 14 of the 36 metabolites
are covered; the other 22 stay honestly ``NOSOURCE`` rather than carry a guess. Primidone is
the instructive one: its article says outright that the responsible P450s are *still
unknown*, which is a real answer, not a gap to fill.

Shape: ``(drug_id, metabolite name) -> [{enzyme, reaction?, corpus, page, quote}]``. The
metabolite name must match ``drugs_data.jsonl`` exactly (``generate_data.py`` raises if a key
names a metabolite no drug has, so a rename cannot silently drop the node). Several enzymes
per metabolite is normal and not a conflict: a demethylation usually runs through more than
one isoform, and two corpora naming different ones are two separately graded claims, both
kept.
"""
from __future__ import annotations

from typing import Any


def _stahl(page: int, quote: str, enzyme: str, reaction: str | None = None
           ) -> dict[str, Any]:
    row: dict[str, Any] = {"enzyme": enzyme, "corpus": "stahl", "page": page,
                           "quote": quote}
    if reaction:
        row["reaction"] = reaction
    return row


def _wiki(slug: str, quote: str, enzyme: str, reaction: str | None = None
          ) -> dict[str, Any]:
    row: dict[str, Any] = {"enzyme": enzyme, "corpus": "wikipedia_pharm", "page": slug,
                           "quote": quote}
    if reaction:
        row["reaction"] = reaction
    return row


METABOLITE_ENZYME_QUOTES: dict[tuple[str, str], list[dict[str, Any]]] = {
    # Two corpora naming different isoforms for the same demethylation. Not a
    # contradiction to resolve: several isoforms share the reaction, and each source
    # is graded on its own, so both rows ship.
    ("amitriptyline", "Nortriptyline"): [
        _stahl(41, "Metabolized to an active metabolite, nortriptyline, which is "
                   "predominantly a norepinephrine reuptake inhibitor, by demethylation "
                   "via CYP1A2",
               "cyp1a2", "demethylation"),
        _wiki("amitriptyline",
              "Amitriptyline is metabolized mostly by CYP2C19 into nortriptyline",
              "cyp2c19"),
    ],
    # The article says "hydroxybupropion"; the row is named for the position (6-).
    ("bupropion", "6-Hydroxybupropion"): [
        _wiki("bupropion",
              "Since bupropion is metabolized to hydroxybupropion by the enzyme CYP2B6",
              "cyp2b6"),
    ],
    # "activated ... to" is the formation claim; the mEH sentence right after it is the
    # opposite direction (it destroys the epoxide) and is deliberately not used.
    ("carbamazepine", "Carbamazepine-10,11-epoxide"): [
        _wiki("carbamazepine",
              "It is activated, mainly by CYP3A4, to carbamazepine-10,11- epoxide",
              "cyp3a4"),
    ],
    # Stahl names the enzyme and the count but not which metabolite is which; both of
    # the two are CYP3A4 products, and didesmethyl cariprazine is the one we list.
    ("cariprazine", "Didesmethyl cariprazine"): [
        _stahl(157, "Metabolized by CYP3A4 into two longlasting active metabolites",
               "cyp3a4"),
    ],
    # One sentence, three isoforms, three nodes. The NEXT sentence on that page
    # ("further metabolized and cleared through hydroxylation by the enzyme CYP2C19")
    # is about clearing this metabolite, not making it, so it is not a row here.
    ("clobazam", "N-desmethylclobazam"): [
        _wiki("clobazam", "The demethylation is facilitated by CYP2C19 , CYP3A4 , and "
                          "CYP2B6", "cyp2c19", "demethylation"),
        _wiki("clobazam", "The demethylation is facilitated by CYP2C19 , CYP3A4 , and "
                          "CYP2B6", "cyp3a4", "demethylation"),
        _wiki("clobazam", "The demethylation is facilitated by CYP2C19 , CYP3A4 , and "
                          "CYP2B6", "cyp2b6", "demethylation"),
    ],
    ("clomipramine", "Desmethylclomipramine"): [
        _stahl(181, "Metabolized to an active metabolite, desmethyl-clomipramine, a "
                    "predominantly norepinephrine reuptake inhibitor, by demethylation "
                    "via CYP1A2",
               "cyp1a2", "demethylation"),
    ],
    ("fluoxetine", "Norfluoxetine"): [
        _wiki("fluoxetine", "CYP2D6 is responsible for converting fluoxetine to its only "
                            "active metabolite, norfluoxetine", "cyp2d6"),
    ],
    ("imipramine", "Desipramine"): [
        _stahl(397, "Metabolized to an active metabolite, desipramine, a predominantly "
                    "norepinephrine reuptake inhibitor, by demethylation via CYP1A2",
               "cyp1a2", "demethylation"),
    ],
    # Kept with its hedge inside the quote ("is thought to be"), which is the honest
    # state: Stahl's own line calls mCPP a CYP2D6 *substrate*, the other direction.
    ("nefazodone", "Meta-chlorophenylpiperazine"): [
        _wiki("nefazodone",
              "mCPP is thought to be formed from nefazodone specifically by CYP2D6",
              "cyp2d6"),
    ],
    # The infobox names the reaction as sulfoxidation, which is the route to quetiapine
    # sulfoxide rather than to norquetiapine, so no `reaction` is recorded: the enzyme
    # is what the source pins down, and the quote shows the reader the rest.
    ("quetiapine", "Norquetiapine"): [
        _wiki("quetiapine", "Metabolism | Liver via CYP3A4-catalysed sulfoxidation to "
                            "its active metabolite norquetiapine", "cyp3a4"),
    ],
    # Two sentences, quoted together because the first names the enzyme and the second
    # names M-II among the products; either alone would not carry the claim.
    ("ramelteon", "M-II"): [
        _wiki("ramelteon", "Ramelteon is metabolized mainly by CYP1A2 while CYP2C "
                           "enzymes and CYP3A4 are involved to a minor extent. The "
                           "metabolites of ramelteon include M-I, M-II, M-III, and M-IV.",
              "cyp1a2"),
    ],
    # 9-hydroxyrisperidone IS paliperidone (the row links to that modeled drug).
    ("risperidone", "Paliperidone"): [
        _wiki("risperidone", "Metabolism | Liver ( CYP2D6 mediated to "
                             "9-hydroxyrisperidone )", "cyp2d6", "hydroxylation"),
    ],
    ("venlafaxine", "O-desmethylvenlafaxine"): [
        _stahl(889, "O-desmethylvenlafaxine (ODV), which is formed as the result of "
                    "CYP2D6", "cyp2d6", "demethylation"),
    ],
    # The one non-CYP route in the set, and the reason the field is named `enzyme`.
    ("chloral_hydrate", "Trichloroethanol"): [
        _wiki("chloral_hydrate", "Chloral hydrate is metabolized to both "
                                 "2,2,2-trichloroethanol (TCE) and trichloroacetic acid "
                                 "(TCA) by alcohol dehydrogenase", "adh"),
    ],
}
