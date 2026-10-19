#!/usr/bin/env python
"""The claim walk: every citation in the emitted data, with its site and the claim it backs.

One walk, two readers. ``recheck_quotes.py build`` shows a judge each quote beside the
claim(s) it backs, each prefixed by its citation site (see ``citation_site.py``).
``generate_data.py`` runs the same walk over the records it is about to write, so each
citation's ``pipeline`` reads the judge stamp recorded for THAT site
(``quote_llm.json`` is ``{quote id: {site: model}}``): a quote judged for one claim and
later reused by a new claim leaves the new citation unjudged rather than inheriting a
verdict about a different sentence-claim pairing. A citation the walk cannot place gets
the site ``*`` (:data:`UNPLACED`), matching the generic claim a judge is shown for it.

Made with the help of Claude Code.
"""
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "public", "data")

sys.path.insert(0, os.path.join(ROOT, "tools"))
from data_generators import history as HIST  # noqa: E402
from data_generators import workup as WORKUP  # noqa: E402
from data_generators import formulations as FORM  # noqa: E402
from data_generators import provenance as PROV  # noqa: E402
from data_generators import release_modulation as RELMOD  # noqa: E402
from data_generators import demographics as DEMOG  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import citation_site as CS  # noqa: E402

# Allen AHBA is intentionally absent from the judging: its quotes are deterministic.
EXCLUDE_CORPUS = {"allen_ahba"}

# The site of a citation the walk cannot place (it is judged under the generic claim).
UNPLACED = "*"

# The emitted collections the walk reads, as ``data`` keys (``meta`` is one object).
COLLECTIONS = ("structures", "projections", "circuits", "projection_groups",
               "receptors", "drugs", "metabolites", "addons")


def _jsonl(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_emitted():
    """The emitted dataset as the walk's ``data`` argument (meta + every collection)."""
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as fh:
        data = {"meta": json.load(fh)}
    for name in COLLECTIONS:
        data[name] = list(_jsonl(f"{name}.jsonl"))
    return data


def _qids(sources):
    """The citation refs in a source list (each a ``{quote_id, ...}`` dict)."""
    return [s for s in sources if isinstance(s, dict) and "quote_id" in s]


def site_of(claim: str) -> str:
    """The citation site a claim line names (``site | text``), else :data:`UNPLACED`."""
    head, sep, _ = claim.partition(" | ")
    return head if sep else UNPLACED


def _labels(data):
    """``(category id -> label, target id -> display name)``, read from the emitted data.

    The judge is asked whether a sentence supports a claim, so the claim has to be
    written in the words the dataset actually publishes, not in its internal ids. The
    difference is not cosmetic: our ``stimulant`` bucket is labelled "Stimulant /
    wake-promoting", so Stahl's "Wake-promoting agent" supports it and the id does not,
    and a judge shown the id fails a claim the data never made.
    """
    meta = data["meta"]
    cats = meta.get("drug_category_labels") or {}
    targets = {tid: (entry.get("name") or tid)
               for tid, entry in (meta.get("drug_targets") or {}).items()}
    for rec in data["receptors"]:
        targets.setdefault(rec["id"], rec.get("name") or rec["id"])
    return cats, targets


def _hours(hl):
    """A half-life record (``{hours, hours_max?}``) as a phrase the judge can weigh."""
    if not hl:
        return "an unstated duration"
    return (f"{hl['hours']}-{hl['hours_max']} hours" if hl.get("hours_max")
            else f"{hl['hours']} hours")


def _target_facet(key: str) -> str:
    """A drug target's own `sources` list is its *classification* source.

    The applier walks `classification_sources.json`, where the same quote sits under the
    target itself (a non-receptor target states one `type`, so it has no per-attribute
    level), and a site has to read the same from both ends or it addresses nothing.
    """
    return "classification" if key == "sources" else key


# Printed over a quote the claim walk could not reach (a source on a node kind the
# reconstruction does not model, e.g. an uncertainty bullet's own citation). It is a
# prompt, not a claim, so it is deliberately excluded from the co-citation tally below.
UNRECONSTRUCTED_CLAIM = ("This quote is cited as the source of a dataset claim whose "
                         "text could not be reconstructed here. Confirm it appears "
                         "verbatim on the page and states a coherent, correct fact.")


_UNCERTAIN_RE = re.compile(r'^\s*"uncertain\.([a-z_]+)":\s*"((?:[^"\\]|\\.)*)"',
                           re.MULTILINE)


def _uncertainty_reasons():
    """``kind -> the English sentence the viewer prints for that doubt``.

    Read off ``js/i18n/en.js`` rather than restated here: the judge must be shown the
    same words a reader is shown, and a second copy would drift the day a reason is
    reworded.
    """
    fn = os.path.join(ROOT, "public", "js", "i18n", "en.js")
    out = {}
    with open(fn, encoding="utf-8") as fh:
        for kind, text in _UNCERTAIN_RE.findall(fh.read()):
            out.setdefault(kind, text.replace('\\"', '"').replace("\\'", "'"))
    return out


UNCERTAINTY_REASONS = _uncertainty_reasons()


def _reason(bullet):
    """The English sentence a reader is shown for one uncertainty bullet, args filled."""
    text = UNCERTAINTY_REASONS.get(bullet.get("kind"), "")
    for k, v in (bullet.get("args") or {}).items():
        text = text.replace("{" + k + "}", ", ".join(map(str, v)) if isinstance(v, list)
                            else str(v))
    return text


def _doubts(node):
    """The already-recorded doubts about a node, as a suffix to its claim line.

    THE POINT: a judge that is not told the dataset already doubts a claim will
    re-derive the doubt from scratch and call it a rejection. That happened: a Kandel
    sentence covering a whole diffuse system was rejected for not naming one pathway,
    which is exactly the `blanket_claim` flag those arrows already carry, so the
    verdict would have demoted a citation the dataset was already honest about.

    The flag is the dataset conceding the point, so the judge is asked the question
    that is still open (is this sentence on the page, and is it about this at all?)
    rather than the one already answered.
    """
    bullets = (node or {}).get("uncertainty") or []
    if not bullets:
        return ""
    parts = [f"{b.get('kind')}: {_reason(b)}" if _reason(b) else b.get("kind")
             for b in bullets]
    return (" [ALREADY FLAGGED UNCERTAIN by the dataset, and shown to readers as such: "
            + " ".join(parts)
            + " Do not reject the citation for the reason the flag already states; "
              "judge only whether the sentence is on the page and is about this claim "
              "at all.]")


def _effect_claims(add, kind, label, owner_kind, oid, nm, owner):
    """One claim per receptor_effect node's quote (receptors and targets alike)."""
    kind["now"] = "receptor_effect"
    for e in owner.get("effects") or []:
        mode = {"both": "agonism or antagonism"}.get(e["mode"], e["mode"])
        for q in _qids(e.get("sources", [])):
            add(q, f"{label} {nm}: {mode} of it can cause (or contribute to) the "
                   f"clinical effect '{e['effect'].replace('_', ' ')}' in humans.",
                CS.site(owner_kind, oid, "effects", f"{e['mode']}:{e['effect']}"))


def _demographic_claims(add, kind, label, owner_kind, oid, nm, owner):
    """One claim per receptor_demographic node's quote (receptors and targets alike): the
    WHOLE node (factor, direction, region, magnitude), in healthy humans only."""
    kind["now"] = "receptor_demographic"
    for n in owner.get("demographics") or []:
        what = {"decrease": "DECREASES with age", "increase": "INCREASES with age",
                "higher_in_female": "is HIGHER in women than in men",
                "higher_in_male": "is HIGHER in men than in women",
                "no_difference": f"does NOT differ by {n['factor']}"}[n["direction"]]
        where = f" in the {n['structure']}" if n.get("structure") else ""
        mag = f" (by {n['magnitude']})" if n.get("magnitude") else ""
        for q in _qids(n.get("sources", [])):
            add(q, f"{label} {nm}: its brain availability / binding (PET, SPECT or "
                   f"post-mortem){where} {what}{mag}, measured in humans. Reject an "
                   f"animal-only statement, or a sentence about a different receptor / "
                   f"transporter than {nm}.",
                CS.site(owner_kind, oid, "demographics",
                        DEMOG.node_key(n["factor"], n["direction"], n.get("structure"))))


def _release_modulation_claims(add, kind, r, nm):
    """One claim per receptor_release_modulation node's quote: the WHOLE node (kind, cell,
    structure, transmitter, direction of activation), so a judge rejects a sentence that
    states only part of it. Human / clinical pharmacology only (animal-only is rejected)."""
    kind["now"] = "receptor_release_modulation"
    for n in r.get("release_modulation") or []:
        site = n.get("site") or {}
        f = {"kind": n["kind"], "structure": site.get("structure"), "cell": site.get("cell"),
             "modulates": n["modulates"], "effect": n["effect_of_activation"]}
        where = f" in the {f['structure']}" if f["structure"] else ""
        for q in _qids(n.get("sources", [])):
            add(q, f"Receptor {nm} acts as a {f['kind']} on "
                   f"{f['cell'].replace('_', ' ')}s{where}: ACTIVATING it {f['effect']}s the "
                   f"release of {f['modulates']} (a blocker therefore does the opposite). "
                   f"Reject an animal-only (rat / mouse / knockout) statement.",
                CS.site("receptor", r["id"], "release_modulation", RELMOD.node_key(**f)))


def reconstruct_claims(quotes, data=None, on_cite=None, site_kinds=None):
    """``(claims, kinds)``: per quote id, the claim(s) it backs and its node kind.

    ``data`` is the emitted dataset (default: read off ``public/data``, see
    :func:`load_emitted`); ``on_cite(site, ref)`` is called for every citation ref the
    walk places, which is how the generator keys a judge stamp to its site.
    """
    data = data if data is not None else load_emitted()
    claims = collections.defaultdict(list)
    kinds = {}
    cat_labels, target_names = _labels(data)
    # The node kind the loop below is filling, read by ``add``. A holder rather than an
    # argument on every call site, because the kinds come in runs (one loop, one kind);
    # it is what lets ``build --kinds`` narrow a rerun to the kinds a pass needs. Coarse
    # on purpose: ``receptor_classification`` covers the four per-attribute tally kinds.
    kind = {"now": None}

    def add(ref, claim, site=None, node=None):
        """Record one claim, prefixed by the citation site it is made at.

        The site is what lets a verdict name a claim rather than a sentence: a quote
        cited from three places gets three claims here, and a judge that rejects one
        answers with that one site, so the other two keep their source (see
        ``citation_site.py``, and ``demote_quotes.py --sites``). It rides in the claim
        string rather than in a field of its own so every reader of a batch, the judge
        included, sees it beside the claim it addresses instead of in a parallel list
        that has to be zipped back together.
        """
        qid = ref if isinstance(ref, str) else ref["quote_id"]
        if on_cite is not None and site and not isinstance(ref, str):
            on_cite(site, ref)
        if node is not None and site and id(node) not in bulleted:
            bulleted.add(id(node))
            _place_bullets(site, node)
        if qid in quotes and quotes[qid]["corpus"] not in EXCLUDE_CORPUS:
            kinds.setdefault(qid, kind["now"])
            if site_kinds is not None:
                site_kinds.setdefault((qid, site or UNPLACED), kind["now"])
            # `site | text`, not `[site] text`: a site carries brackets of its own
            # (`bindings[5ht2a]`), so a bracketed prefix cannot be split back off it.
            claim += _doubts(node)
            claims[qid].append(f"{site} | {claim}" if site else claim)

    bulleted: set[int] = set()

    def _place_bullets(site, node):
        """Place the citations of a node's uncertainty bullets.

        A bullet citing the node's own sentence is that same citation read for a doubt
        (the judge sees it appended to the claim, :func:`_doubts`), so it shares the
        site. A bullet citing another sentence (a contradicting source, a measured Ki)
        is a claim of its own, judged at ``<site>/uncertainty[<kind>]``.
        """
        own = {r["quote_id"] for r in _qids(node.get("sources") or [])}
        for b in node.get("uncertainty") or []:
            for r in _qids(b.get("sources") or []):
                if r["quote_id"] in own:
                    if on_cite is not None:
                        on_cite(site, r)
                else:
                    add(r, f"A reason to doubt the claim at {site}: {_reason(b) or b.get('kind')}",
                        f"{site}/uncertainty[{b.get('kind')}]")

    metab_by_id = {m["id"]: m for m in data["metabolites"]}
    parents_of: dict[str, list[str]] = {}
    for d in data["drugs"]:
        nm = d["name"]
        kind["now"] = "drug_bindings"
        for b in d.get("bindings", []):
            tag = " (tentative)" if b.get("tentative") else ""
            tname = target_names.get(b["target"], b["target"])
            for q in _qids(b.get("sources", [])):
                add(q, f"Drug {nm} acts on target '{tname}' as {b['action']}{tag}.",
                    CS.site("drug", d["id"], f"bindings[{CS.binding_key(b)}]"), b)
            # A literature Ki quoted from prose or a paper's table (corpus #17 picks it
            # by model, so it needs a judge like any picked quote). A code-copied Ki row
            # (PDSP, GtoPdb, a Wikipedia table) is stamped `page_code` and never asks.
            ki_src = (b.get("ki") or {}).get("source") or {}
            if not str(ki_src.get("pipeline", "")).startswith("page_llm"):
                ki_src = {}
            for q in _qids([ki_src]):
                param = ki_src.get("param") or "Ki"
                add(q, f"Drug {nm} binds target '{tname}' with a measured affinity "
                       f"({param}) of {ki_src.get('value_nm'):g} nM.",
                    CS.site("drug", d["id"], f"bindings[{CS.binding_key(b)}]/ki"))
        kind["now"] = "drug_categories"
        for q in _qids(d.get("category_sources", [])):
            cats = [cat_labels.get(c, c) for c in d.get("categories", [])]
            add(q, f"Drug {nm} is classified as {', '.join(cats)}.",
                CS.site("drug", d["id"], "categories"))
        kind["now"] = "drug_nbn"
        for q in _qids(d.get("nbn_sources", [])):
            add(q, f"Drug {nm} Neuroscience-based Nomenclature = '{d.get('nbn')}'.",
                CS.site("drug", d["id"], "nbn"))
        # The molecule, then each formulation (same three facets, under its release).
        rel_labels = FORM.labels()
        for h in PROV.product_holders(d):
            rel = h.get("release")
            fac = f"formulations[{rel}]/" if rel else ""
            of = f" ({rel_labels[rel]['en']} formulation)" if rel else ""
            if rel:
                kind["now"] = "drug_formulations"
                for q in _qids(h.get("release_sources", [])):
                    add(q, f"Drug {nm} is marketed as a {rel_labels[rel]['en'].lower()} "
                           f"formulation (this source names that product).",
                        CS.site("drug", d["id"], f"{fac}release"))
            kind["now"] = "drug_brands"
            for br in h.get("brands", []):
                for q in _qids(br.get("sources", [])):
                    add(q, f"Drug {nm} is sold under the brand name '{br['name']}'{of}.",
                        CS.site("drug", d["id"], f"{fac}brands[{br['name']}]"))
            kind["now"] = "drug_half_life"
            for q in _qids(h.get("half_life_sources", [])):
                add(q, f"Drug {nm}{of} has an elimination half-life of "
                       f"{_hours(h.get('half_life'))}.",
                    CS.site("drug", d["id"], f"{fac}half_life"))
            kind["now"] = "drug_tmax"
            for q in _qids(h.get("tmax_sources", [])):
                add(q, f"Drug {nm}{of} reaches its peak plasma concentration "
                       f"{_hours(h.get('tmax'))} after a dose.",
                    CS.site("drug", d["id"], f"{fac}tmax"))
        kind["now"] = "drug_first_approval"
        fa = d.get("first_approval") or {}
        for q in _qids(d.get("first_approval_sources", [])):
            where = (f" in {HIST.COUNTRIES[fa['country']]['en']}"
                     if fa.get("country") else "")
            by = f" (by the {HIST.AGENCIES[fa['agency']]['en']})" if fa.get("agency") else ""
            add(q, f"Drug {nm} was first approved or introduced for medical use"
                   f"{where}{by} in {fa.get('year')}.",
                CS.site("drug", d["id"], "first_approval"))
        kind["now"] = "drug_withdrawals"
        for w in d.get("withdrawals", []):
            why = HIST.WITHDRAWAL_REASONS[w["reason"]]["en"]
            for q in _qids(w.get("sources", [])):
                add(q, f"Drug {nm} was withdrawn from the market "
                       f"({HIST.COUNTRIES[w['country']]['en']}) in {w['year']}, "
                       f"reason: {why}.",
                    CS.site("drug", d["id"], f"withdrawals[{CS.withdrawal_key(w)}]"))
        kind["now"] = "drug_workup"
        for w in d.get("workup", []):
            test = WORKUP.TESTS[w["test"]]["en"]
            when = WORKUP.TIMINGS[w["timing"]]["en"]
            for q in _qids(w.get("sources", [])):
                only = (f", only if: {'; '.join(w['conditions'])}" if w.get("conditions")
                        else "")
                add(q, f"The French label (RCP) of drug {nm} asks for a check of {test} "
                       f"{when}{only}.", CS.site("drug", d["id"], f"workup[{CS.workup_key(w)}]"))
        kind["now"] = "drug_holders"
        for h in d.get("holders", []):
            where = HIST.COUNTRIES[h["market"]]["en"]
            for q in _qids(h.get("sources", [])):
                add(q, f"Drug {nm}'s marketing authorisation in {where} is currently "
                       f"held by one of: {', '.join(h['names'])}.",
                    CS.site("drug", d["id"], f"holders[{h['market']}]"))
        og = d.get("originator") or {}
        kind["now"] = "drug_originator"
        for q in _qids(d.get("originator_sources", [])):
            add(q, f"Drug {nm} was discovered, first synthesized or developed by "
                   f"{og.get('name')}.", CS.site("drug", d["id"], "originator"))
        for q in _qids(d.get("originator_now_sources", [])):
            add(q, f"The company {og.get('name')} is now part of, or now named, "
                   f"{og.get('now')}.", CS.site("drug", d["id"], "originator/now"))
        kind["now"] = "drug_originator_country"
        for q in _qids(d.get("originator_country_sources", [])):
            country = HIST.COUNTRIES[d["originator_country"]]["en"]
            add(q, f"The company {og.get('name')} (originator of drug {nm}) is based in "
                   f"{country}.", CS.site("drug", d["id"], "originator_country"))
        kind["now"] = "drug_prodrug"
        for q in _qids(d.get("prodrug_sources", [])):
            mets = ", ".join(metab_by_id[m["id"]]["name"] for m in d.get("metabolites", []))
            add(q, f"Drug {nm} is a prodrug: inactive itself, its effect comes from "
                   f"its active metabolite ({mets}).",
                CS.site("drug", d["id"], "prodrug"))
        kind["now"] = "drug_constituents"
        for q in _qids(d.get("constituents_sources", [])):
            add(q, f"Drug {nm} is made of {' and '.join(d.get('constituents') or [])}.",
                CS.site("drug", d["id"], "constituents"))
        kind["now"] = "drug_therapeutic_range"
        trr = d.get("therapeutic_range") or {}
        for q in _qids(d.get("therapeutic_range_sources", [])):
            add(q, f"Drug {nm} therapeutic reference range in blood is "
                   f"{trr.get('low')}-{trr.get('high')} {trr.get('unit')}.",
                CS.site("drug", d["id"], "therapeutic_range"))
        kind["now"] = "drug_alert_level"
        al = d.get("alert_level") or {}
        for q in _qids(d.get("alert_level_sources", [])):
            add(q, f"Drug {nm} laboratory alert level in blood is "
                   f"{al.get('value')} {al.get('unit')}.",
                CS.site("drug", d["id"], "alert_level"))
        kind["now"] = "drug_lipophilicity"
        for q in _qids(d.get("xlogp_sources", [])):
            add(q, f"Drug {nm}'s computed XLogP3 (octanol/water partition) is "
                   f"{d.get('xlogp')}.", CS.site("drug", d["id"], "xlogp"))
        kind["now"] = "drug_polar_surface"
        for q in _qids(d.get("tpsa_sources", [])):
            add(q, f"Drug {nm}'s computed topological polar surface area is "
                   f"{d.get('tpsa')} square angstroms.", CS.site("drug", d["id"], "tpsa"))
        kind["now"] = "drug_bbb"
        bbb = d.get("bbb") or {}
        for q in _qids(d.get("bbb_sources", [])):
            add(q, f"Drug {nm} is labelled {bbb.get('label')} (blood-brain barrier "
                   f"permeable or not) by B3DB.", CS.site("drug", d["id"], "bbb"))
        kind["now"] = "drug_enzymes"
        for e in d.get("enzymes", []):
            tier = f", {e['strength']}" if e.get("strength") else ""
            for q in _qids(e.get("sources", [])):
                add(q, f"Drug {nm} is a {e['role']} of the enzyme "
                       f"{e['enzyme'].upper()}{tier}.",
                    CS.site("drug", d["id"], f"enzymes[{CS.enzyme_key(e)}]"), e)
            kind["now"] = "drug_enzyme_strength"
            strength = (e.get("claims") or {}).get("strength") or {}
            for q in _qids(strength.get("sources", [])):
                add(q, f"Drug {nm} is a {e.get('strength')} {e['role']} of the enzyme "
                       f"{e['enzyme'].upper()} (the strength of that role is the claim).",
                    CS.site("drug", d["id"], f"enzymes[{CS.enzyme_key(e)}]/strength"),
                    strength)
            kind["now"] = "drug_enzymes"
        for m in d.get("metabolites", []):
            mn = metab_by_id[m["id"]]["name"]
            parents_of.setdefault(m["id"], []).append(nm)
            kind["now"] = "drug_metabolites"
            for q in _qids(m.get("sources", [])):
                add(q, f"Drug {nm} has an active metabolite, {mn}.",
                    CS.site("drug", d["id"], f"metabolites[{m['id']}]"))
            kind["now"] = "drug_metabolite_enzyme"
            for fb in m.get("formed_by", []):
                step = f" by {fb['reaction']}" if fb.get("reaction") else ""
                for q in _qids(fb.get("sources", [])):
                    add(q, f"The metabolite {mn} is formed from {nm} by the enzyme "
                           f"{fb['enzyme'].upper()}{step}.",
                        CS.site("drug", d["id"], f"metabolites[{m['id']}]/formed_by[{fb['enzyme']}]"))

    # A metabolite's own facts (half-life, receptor bindings) live once per molecule in
    # metabolites.jsonl, whichever drugs make it; the claim names every parent.
    for mid, m in metab_by_id.items():
        mn, of = m["name"], ", ".join(parents_of.get(mid, [])) or "a drug"
        kind["now"] = "drug_metabolites"
        for q in _qids(m.get("half_life_sources", [])):
            add(q, f"{mn}, an active metabolite of {of}, has an elimination "
                   f"half-life of {_hours(m.get('half_life'))}.",
                CS.site("metabolite", mid, "half_life"))
        kind["now"] = "drug_metabolite_bindings"
        for mb in m.get("bindings", []):
            mt = target_names.get(mb["target"], mb["target"])
            for q in _qids(mb.get("sources", [])):
                add(q, f"{mn}, an active metabolite of {of}, acts on target "
                       f"'{mt}' as {mb.get('action') or 'a binder'}.",
                    CS.site("metabolite", mid, f"bindings[{CS.binding_key(mb)}]"))

    for r in data["receptors"]:
        nm = r["name"]
        kind["now"] = "receptor_classification"
        for attr, info in (r.get("classification") or {}).items():
            for q in _qids(info.get("sources", [])):
                add(q, f"Receptor {nm}: {attr} = '{r.get(attr)}'.",
                    CS.site("receptor", r["id"], "classification", attr))
        kind["now"] = "receptor_locations"
        for region, srcs in (r.get("location_sources") or {}).items():
            for q in _qids(srcs):
                add(q, f"Receptor {nm} is expressed in brain region '{region}'.",
                    CS.site("receptor", r["id"], "locations", region))
        _effect_claims(add, kind, "Receptor", "receptor", r["id"], nm, r)
        _release_modulation_claims(add, kind, r, nm)
        _demographic_claims(add, kind, "Receptor", "receptor", r["id"], nm, r)

    kind["now"] = "projections"
    for p in data["projections"]:
        for q in _qids(p.get("sources", [])):
            add(q, f"Projection '{p['from']}'->'{p['to']}' ({p.get('kind')}, "
                   f"{p.get('neurotransmitter')}): {p.get('label', '')}. {p.get('description', '')}",
                CS.site("projection", f"{p['from']}->{p['to']}"), p)
        # The transmitter and the sign are nodes of their own (projection_transmitter /
        # projection_sign), so each is its own claim, judged on its own.
        route = f"Projection '{p['from']}'->'{p['to']}'"
        for facet, text in (("transmitter", f"{route} releases {p.get('neurotransmitter')} "
                                            f"as its neurotransmitter."),
                            ("sign", f"{route} is {p.get('kind')} on its target "
                                     f"(its transmitter {p.get('neurotransmitter')} "
                                     f"has that effect)."),):
            claim = (p.get("claims") or {}).get(facet) or {}
            kind["now"] = f"projection_{facet}"
            for q in _qids(claim.get("sources", [])):
                add(q, text, CS.site("projection", f"{p['from']}->{p['to']}", facet), claim)
        kind["now"] = "projections"

    kind["now"] = "circuits"
    for c in data["circuits"]:
        for q in _qids(c.get("sources", [])):
            add(q, f"Functional circuit '{c['name']}': {c.get('description', '')}",
                CS.site("circuit", c["id"]))

    kind["now"] = "projection_groups"
    for g in data["projection_groups"]:
        for q in _qids(g.get("sources", [])):
            add(q, f"Projection group '{g['name']}' ({g['mode']}={g['key']}): {g.get('description', '')}",
                CS.site("group", f"{g['mode']}:{g['key']}"))

    kind["now"] = "structures"
    for s in data["structures"]:
        for q in _qids(s.get("sources", [])):
            add(q, f"Brain structure '{s['name']}' ({s.get('base_name')}) anatomy/existence.",
                CS.site("structure", s["id"]))

    for tid, t in data["meta"].get("drug_targets", {}).items():
        nm = t.get("name") or tid
        kind["now"] = "target_locations"
        for region, srcs in (t.get("location_sources") or {}).items():
            for q in _qids(srcs):
                add(q, f"Molecular target {nm} is expressed in brain region '{region}'.",
                    CS.site("target", tid, "locations", region))
        _effect_claims(add, kind, "Molecular target", "target", tid, nm, t)
        _demographic_claims(add, kind, "Molecular target", "target", tid, nm, t)
        kind["now"] = "target_other"
        for k, v in t.items():
            if k in ("location_sources", "effects", "demographics"):
                continue
            if isinstance(v, dict) and "sources" in v:
                for q in _qids(v["sources"]):
                    add(q, f"Molecular target {nm}: {k}.",
                        CS.site("target", tid, _target_facet(k)))
            elif isinstance(v, list):
                for q in _qids(v):
                    add(q, f"Molecular target {nm}: {k}.",
                        CS.site("target", tid, _target_facet(k)))
    kind["now"] = "addons"
    for a in data["addons"]:
        for q in _qids(a.get("sources", [])):
            add(q, f"Annotation on {a['owner_kind']} '{a['owner']}': {a.get('text', '')}",
                CS.site("addon", f"{a['owner_kind']}:{a['owner']}"))


    # Fold any remaining (referenced but unreconstructed) non-Allen quote with a generic claim.
    kind["now"] = "other"
    for qid, q in quotes.items():
        if q["corpus"] not in EXCLUDE_CORPUS and qid not in claims:
            add(qid, UNRECONSTRUCTED_CLAIM)
    # A node backed by SEVERAL quotes is not asking each of them for the whole claim.
    # That is the dataset's own model (a compound value earns its green check only when
    # every part is attested: 5-HT1B's synaptic="both" is one presynaptic quote plus one
    # postsynaptic one, a two-category class is one sentence per category), and a judge
    # shown one quote beside the whole claim rejects the pair that is exactly right. So
    # the claim says out loud how many citations share it, and what to weigh THIS one on.
    shared = collections.Counter()
    for qid, texts in claims.items():
        for text in set(texts):
            # The unreconstructed-claim placeholder is not a claim, it is the same
            # sentence printed over every quote the walk could not reach. Counting it
            # would tell hundreds of unrelated quotes they are co-cited with each other.
            if text != UNRECONSTRUCTED_CLAIM:
                shared[text] += 1
    for texts in claims.values():
        for i, text in enumerate(texts):
            if shared[text] > 1:
                texts[i] = (f"{text} [cited here alongside {shared[text] - 1} other "
                            f"quote(s): judge whether THIS one carries its share of the "
                            f"claim, not whether it carries the whole claim alone]")
    return claims, kinds

