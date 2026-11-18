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

One table, :data:`CONTRADICTIONS`, keyed by the doubted node's **citation site** (the
grammar of ``tools/sourcing/citation_site.py``, the same address a judge verdict names),
each mapping to the denying source(s). Any node-shaped site of any kind can be doubted
with a data-only edit, at the precision the site gives: the metabolism row
(``drug:<id>/enzymes[<enzyme>:<role>]``) or only its tier sub-claim (``.../strength``), one
receptor classification attribute (``receptor:<id>/classification[<attr>]``), one binding
of several on a target (``drug:<id>/bindings[<target>:<action>]``), a per-parent metabolite
link (``drug:<id>/metabolites[<metabolite>]``), a receptor effect, a workup row, and so on.
A drug's ``half_life`` / ``tmax`` (``drug:<id>/half_life``, ``.../formulations[<release>]/tmax``)
can be named too: the value dict stands for the node and carries the bullet. Any other flat
facet stored as ``*_sources`` on its owner is not a node dict and cannot be named
(``citation_site.node_index``).

``generate_data.py`` raises if a site names no emitted node (or two), and ``check_data.py``
fails on the same, so a re-run of a fetcher cannot silently strip the flag and leave the
contradiction unmarked.
"""
from __future__ import annotations

from typing import Any


def _wiki(slug: str, quote: str) -> dict[str, Any]:
    """A denial read off the stored English article (corpus #9), graded like any quote."""
    return {"corpus": "wikipedia_pharm", "page": slug, "quote": quote,
            "provenance": "verified", "llm": "opus"}


def _book(corpus: str, page: int, quote: str) -> dict[str, Any]:
    """A denial read off a book corpus page, judged like any LLM-picked quote."""
    return {"corpus": corpus, "page": page, "quote": quote,
            "provenance": "verified", "llm": "opus"}


def _dailymed(setid: str, quote: str) -> dict[str, Any]:
    """A denial read off a stored US label (corpus #14, ``page`` = set id), judged like
    any LLM-picked quote. The label is stored by ``fetch_dailymed.QUOTE_LABELS``."""
    return {"corpus": "dailymed", "page": setid, "quote": quote,
            "provenance": "verified", "llm": "opus"}


def _gtopdb_class(target_id: int, quote: str) -> dict[str, Any]:
    """A transduction row read off the GtoPdb classification page (corpus #12): a table
    row copied by code, so it needs no judge (the corpus is ``machine``)."""
    return {"corpus": "gtopdb_class", "page": target_id, "quote": quote,
            "provenance": "verified"}


def _gtopdb_ki(ligand: str, quote: str) -> dict[str, Any]:
    """A ligand-target interaction row read off the GtoPdb ki page (corpus #11, ``page`` =
    ligand slug): copied by code, so no judge (the corpus is ``machine``)."""
    return {"corpus": "gtopdb_ki", "page": ligand, "quote": quote, "species": "Human",
            "provenance": "verified"}


def _pdsp(ki_id: int, radioligand: str, reference: str) -> dict[str, Any]:
    """A measurement read off the PDSP Ki CSV (corpus #5, cited by row like a binding's
    own Ki and gated by check_data family 8): here an inactive ceiling, "> 10000 nM"."""
    return {"corpus": "pdsp_ki", "ki_id": ki_id, "value_nm": 10000,
            "species": "HUMAN", "preparation": "CLONED", "radioligand": radioligand,
            "reference": reference, "note": ">", "provenance": "verified"}


def _europepmc(pmid: str, quote: str) -> dict[str, Any]:
    """A sentence read off a stored Europe PMC abstract (corpus #17, ``page`` = PMID),
    judged like any LLM-picked quote."""
    return {"corpus": "europepmc", "page": pmid, "quote": quote,
            "provenance": "verified", "llm": "opus"}


# Each value is one denying source, or a list of them (one denial may need two sentences,
# or two corpora deny the same claim): one bullet either way, citing them all. Grouped by
# doubted node kind for the reader only; the site says it all.
# Stahl's d-methylphenidate T½ line (p.513), the denial of two other values below.
_D_MPH_HALF_LIFE = _book("stahl", 513, "Mean plasma elimination half-life approximately "
                         "2.2 hours (same as d,lmethylphenidate)")

CONTRADICTIONS: dict[str, dict[str, Any] | list[dict[str, Any]]] = {
    # --- metabolism rows (the isoform touches the drug at all) ---
    # Stahl's fluoxetine monograph (p.331) prints a bare "Inhibits CYP3A4". Wikipedia
    # cites Sager et al. 2014 (Clin Pharmacol Ther 95:653), whose whole subject is the
    # in vitro -> in vivo correlation for exactly these isoforms: the inhibition is real
    # in the dish and not at the bedside.
    "drug:fluoxetine/enzymes[cyp3a4:inhibitor]": _wiki(
        "fluoxetine",
        "In vivo, fluoxetine and norfluoxetine do not significantly affect the "
        "activity of CYP1A2 and CYP3A4"),
    # Stahl p.83 states "Induces CYP3A4 (and slightly CYP1A2)" for armodafinil, carrying
    # its own hedge. The article denies the CYP1A2 half outright, and pointedly: the
    # induction is modafinil's, not its R-enantiomer's.
    "drug:armodafinil/enzymes[cyp1a2:inducer]": _wiki(
        "armodafinil",
        "In contrast to modafinil, however, armodafinil does not induce CYP1A2"),
    # Stahl p.553 already hedges ("Inhibits CYP2C19 (and perhaps CYP2C9)"), so this one
    # is a disagreement the weaker source half-anticipates. Kept flagged rather than
    # dropped: the hedge is Stahl's, the denial is the article's, and neither is ours.
    "drug:modafinil/enzymes[cyp2c9:inhibitor]": _wiki(
        "modafinil",
        "However, other in-vitro work has shown no significant inhibition of CYP2C9"),

    # --- metabolism tiers: Stahl and the CYP pass agree each isoform clears / is
    # inhibited by the drug, they disagree on the tier. The row's isoform claim stays
    # green, only the tier goes orange. ---
    # Stahl p.210: "to a lesser extent by CYP2D6". The article's drugbox says the
    # opposite, though its own pharmacokinetics prose names CYP1A2 as primary: the
    # article disagrees with itself, which is exactly why neither side is picked.
    "drug:clozapine/enzymes[cyp2d6:substrate]/strength": _wiki(
        "clozapine", "Liver , by several CYP isozymes mainly via CYP2D6"),
    "drug:fluvoxamine/enzymes[cyp1a2:substrate]/strength": _wiki(
        "fluvoxamine",
        "fluvoxamine is metabolized primarily by CYP2D6 and to a minor extent by "
        "CYP1A2"),
    # Stahl p.770 "weakly at low doses"; the article's "moderate" is in vitro, but the
    # sentences after it report a dose-dependent rise of CYP2D6 substrates in humans.
    "drug:sertraline/enzymes[cyp2d6:inhibitor]/strength": _wiki(
        "sertraline", "Sertraline is a moderate inhibitor of CYP2D6 and CYP2B6 in vitro"),

    # --- receptor classification attributes a corpus states otherwise. The sourcing
    # pass never rewrites data to match a source, so these were reported as conflicts
    # and kept. ---
    # We say postsynaptic; the article gives it a presynaptic autoreceptor role.
    "receptor:5ht5a/classification[synaptic]": _wiki(
        "5_ht5a_receptor", "It also appears to serve as a presynaptic serotonin autoreceptor"),
    # mGluR6 (we say postsynaptic) was read and left out: the only candidate is a
    # group-level sentence ("groups II and III are mostly located on presynaptic
    # elements") that never names mGluR6 and goes on to say both sites occur.
    # We say modulatory; Gs coupling (adenylyl cyclase up) points excitatory, the same
    # transduction-to-sign reading corpus #12 uses.
    "receptor:a2a/classification[sign]": _wiki(
        "adenosine_a2a_receptor",
        "The A 2A receptor binds with the G s protein at the intracellular site of the "
        "receptor"),
    # We say modulatory; Stahl Essential reads MT1 as inhibiting SCN neurons.
    "receptor:mt1/classification[sign]": _book(
        "stahl_essential", 455,
        "MT1-mediated inhibition of neurons in the suprachiasmatic nucleus (SCN)"),
    # We say modulatory; GtoPdb lists one primary transducer, Gi/Go, which the corpus #12
    # transduction-to-sign reading maps to inhibitory (the a2a reading, mirrored).
    "receptor:h4/classification[sign]": _gtopdb_class(
        265, "H4 receptor (HRH4), GtoPdb target 265 | transduction: Gi/Go family | "
             "effectors: Phospholipase C stimulation"),
    "receptor:mt2/classification[sign]": _gtopdb_class(
        288, "MT2 receptor (MTNR1B), GtoPdb target 288 | transduction: Gi/Go family | "
             "effectors: Adenylyl cyclase inhibition, Phospholipase C stimulation"),
    # cb1 is read and left out: GtoPdb's Gi/Go row is a brake on transmitter release,
    # and its own sources say it brakes excitatory and inhibitory release alike, which
    # is what modulatory means here (docs/SOURCING_GAPS.md, receptor_sign).

    # --- drug bindings another corpus describes otherwise. The binding's own note and
    # sources stay as they are; the bullet quotes the other corpus underneath. ---
    # The note (Wikipedia, verified) puts etomidate at the beta+/alpha- transmembrane
    # site of beta2/beta3-containing GABA-A receptors; Stahl Essential p338 groups it with
    # the general anesthetics binding at the neuroactive-steroid sites. Neither is edited.
    "drug:etomidate/bindings[gaba_a:modulator]": _book(
        "stahl_essential", 338,
        "Certain general anesthetics (e.g., propofol, etomidate, alphaxolone, alfadalone) "
        "also bind at the same sites as neuroactive steroids"),

    # Stahl p.31 hedges a D2 partial agonism ("May be a partial agonist at dopamine 2
    # receptors ...") beside the D2 blockade it also states: two bindings on one target,
    # and only the partial agonism is denied. Tadori 2012 ran exactly the assay that
    # separates the two (cAMP in cells expressing human D2, beside aripiprazole and the
    # partial agonists) and amisulpride came out an antagonist; GtoPdb's curated rows and
    # the article's pharmacology lead say antagonist and nothing else.
    "drug:amisulpride/bindings[d2:partial_agonist]": [
        _europepmc(
            "22568121",
            "Antipsychotics (risperidone, olanzapine, amisulpride, sulpiride and "
            "perphenazine) which displayed antidepressive effects in schizophrenia "
            "patients behaved as preferential antagonists in cells expressing D2 "
            "receptors compared to cells expressing D3 receptors."),
        _gtopdb_ki(
            "amisulpride",
            "amisulpride at D2 receptor (DRD2, Human): Antagonist / Antagonist, pKi 7.8 "
            "[PMID 1975644]"),
        _wiki(
            "amisulpride",
            "Amisulpride functions primarily as a dopamine D 2 and D 3 receptor "
            "antagonist"),
    ],

    # --- active-metabolite links another corpus denies. The link and its own sources
    # stay; the bullet quotes the denial underneath it. ---
    # Stahl p.604 lists both samidorphan metabolites as active ("function as a mu opioid
    # receptor" agonist / antagonist); the Lybalvi label grants the same binding but
    # denies either one contributes at the bedside: the in vitro vs in vivo shape again.
    "drug:olanzapinesamidorphan/metabolites[n_dealkylated_samidorphan]": _dailymed(
        "32ffddd1-4e2b-45d9-9b36-bb730167ec80",
        "Neither metabolite contributes to the pharmacological effects of samidorphan"),
    "drug:olanzapinesamidorphan/metabolites[samidorphan_n_oxide]": _dailymed(
        "32ffddd1-4e2b-45d9-9b36-bb730167ec80",
        "Neither metabolite contributes to the pharmacological effects of samidorphan"),
    # Wikipedia (citing Seeman 2009, a D2High assay) states salvinorin A D2 partial
    # agonism. Roth 2002 ran the PDSP screen, D2 included (PDSP row 22214, same paper:
    # D2 at the 10000 nM inactive ceiling), and found nothing outside the kappa receptor.
    # The abstract names the screen, not D2 itself; the full text is not open access.
    "drug:salvinorin_a/bindings[d2:partial_agonist]": _europepmc(
        "12192085",
        "Salvinorin A had no significant activity against a battery of 50 receptors, "
        "transporters, and ion channels and showed a distinctive profile compared with the "
        "prototypic hallucinogen lysergic acid diethylamide."),
    # Wikipedia's lead lists 5-HT1B and 5-HT1D among MDMA's partial-agonist targets.
    # PDSP holds two independent human cloned-receptor screens, Setola 2003 and Ray
    # 2010, and both found MDMA inactive at each up to 10000 nM: a measured "does not
    # bind" against an uncited summary sentence.
    "drug:mdma/bindings[5ht1b:partial_agonist]": [
        _pdsp(50642, "3H-GR-125743", "Setola V, et al., 2003"),
        _pdsp(78899, "3H-5-CT", "Ray TS 2010"),
    ],
    "drug:mdma/bindings[5ht1d:partial_agonist]": [
        _pdsp(50641, "3H-GR-125743", "Setola V, et al., 2003"),
        _pdsp(78930, "3H-5-CT", "Ray TS 2010"),
    ],
    # --- pharmacokinetic durations (the value dict is the node) ---
    # Stahl prints d-methylphenidate's mean T½ as 2.2 h "same as d,l-methylphenidate"
    # (p.513), yet its own d,l monograph gives 3.5 h (p.521); and the serdexmethylphenidate
    # monograph (p.757) gives d-methylphenidate 11.7 h (formed slowly from the prodrug,
    # so its apparent T½ tracks the conversion, which the bullet cannot say). Three
    # numbers for one molecule in one book: each value is flagged with the others quoted.
    "drug:methylphenidate_d/half_life": [
        _book("stahl", 521, "Average half-life of methylphenidate in adults is 3.5 hours "
              "(1.3–7.7 hours)"),
        _book("stahl", 757, "Mean plasma elimination halflife approximately 5.7 hours "
              "(serdexmethylphenidate) and 11.7 hours (d-methylphenidate)"),
    ],
    "drug:methylphenidate_dl/half_life": _D_MPH_HALF_LIFE,
    "drug:serdexmethylphenidate/half_life": _D_MPH_HALF_LIFE,
    # Dimenhydrinate's T½ is its diphenhydramine component's, 5-6 h per its article;
    # Stahl gives diphenhydramine itself about 8 h (p.264). One molecule, two values.
    "drug:diphenhydramine/half_life": _wiki(
        "dimenhydrinate", "The diphenhydramine component requires about 2 hours to reach "
        "peak concentration after either oral or sublingual administration of "
        "dimen\u00adhydrinate, and has a half-life of 5 \u2013 6 hours in healthy adults."),
    "drug:dimenhydrinate/half_life": _book(
        "stahl", 264, "Plasma half-life approximately 8 hours; may be longer in children "
        "and in the elderly"),
}
