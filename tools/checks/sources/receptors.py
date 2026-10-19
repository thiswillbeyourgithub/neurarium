"""Family 5 walks over the receptors and the non-receptor drug targets.

Both carry the same expression / effect / demographic / variant nodes, so they share
the per-node helpers below; only release modulation is receptor-only.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from data_generators import demographics as DEMOG
from data_generators import release_modulation as RELMOD
from lib.quote_match import normalize_for_match
from lib.structure_ids import bases_of


def check_effects(gate, meta, ctx, owner, is_receptor):
    """receptor_effect nodes (BETA): closed vocabularies, one quote at least, each
    quote gated like any other. ``inhibition`` is a non-receptor target's mode."""
    report = gate.report
    effect_modes = meta.get("receptor_effect_modes") or {}
    effect_labels = meta.get("receptor_effect_labels") or {}
    for e in owner.get("effects") or []:
        where = f"{ctx} effects[{e.get('mode')}:{e.get('effect')}]"
        if e.get("mode") not in effect_modes or e.get("effect") not in effect_labels:
            report.error(f"{where}: mode/effect not in meta.receptor_effect_*")
        if is_receptor and e.get("mode") == "inhibition":
            report.error(f"{where}: 'inhibition' on a receptor")
        if not e.get("sources"):
            report.error(f"{where}: an effect node with no source")
        for i, src in enumerate(e.get("sources") or []):
            gate.check_one(f"{where} sources[{i}]", src)


def check_release_modulation(gate, r, bases):
    """receptor_release_modulation nodes (BETA): the same closed-vocabulary rules
    the applier and the emitter enforce (``release_modulation.vocab_error``), one
    quote at least, each quote gated like any other."""
    report = gate.report
    for n in r.get("release_modulation") or []:
        site = n.get("site") or {}
        f = {"kind": n.get("kind"), "structure": site.get("structure"),
             "cell": site.get("cell"), "modulates": n.get("modulates"),
             "effect": n.get("effect_of_activation")}
        where = f"receptor {r.get('id')} release_modulation[{RELMOD.node_key(**f)}]"
        neuro = r.get("neurotransmitter")
        why = RELMOD.vocab_error(f, neuro.get("en") if isinstance(neuro, dict) else neuro,
                                 bases)
        if why:
            report.error(f"{where}: {why}")
        if not n.get("sources"):
            report.error(f"{where}: a release-modulation node with no source")
        for i, src in enumerate(n.get("sources") or []):
            gate.check_one(f"{where} sources[{i}]", src)


def check_demographics(gate, ctx, owner, bases):
    """receptor_demographic nodes (BETA): the closed vocabulary the applier and the
    emitter enforce (``demographics.vocab_error``), a magnitude verbatim in one of
    its own quotes, one quote at least, each quote gated like any other."""
    report = gate.report
    for n in owner.get("demographics") or []:
        f = {k: n.get(k) for k in ("factor", "direction", "structure")}
        where = f"{ctx} demographics[{DEMOG.node_key(**f)}]"
        why = DEMOG.vocab_error(f, bases)
        if why:
            report.error(f"{where}: {why}")
        if not n.get("sources"):
            report.error(f"{where}: a demographic node with no source")
        mag = n.get("magnitude")
        if mag and not any(normalize_for_match(mag) in normalize_for_match(s.get("quote") or "")
                           for s in n.get("sources") or []):
            report.error(f"{where}: magnitude {mag!r} is in none of its quotes")
        for i, src in enumerate(n.get("sources") or []):
            gate.check_one(f"{where} sources[{i}]", src)


def check_variants(gate, ctx, owner):
    for n in owner.get("variants") or []:
        for i, src in enumerate(n.get("sources") or []):
            gate.check_one(f"{ctx} variants[{n.get('annotation')}] sources[{i}]", src)


def walk_receptors(gate, meta, receptors, structures):
    check_one = gate.check_one
    bases = bases_of(structures)
    for r in receptors:
        for attr, entry in (r.get("classification") or {}).items():
            for i, src in enumerate(entry.get("sources") or []):
                check_one(f"receptor {r.get('id')} classification[{attr}] sources[{i}]", src)
            gate.check_uncertainty(f"receptor {r.get('id')} classification[{attr}]", entry)
        # Per-region expression sources are quote-checked like any other (the gate
        # that keeps a future "5-HT2A is dense in the PFC" citation honest).
        for base, srcs in (r.get("location_sources") or {}).items():
            for i, src in enumerate(srcs or []):
                # One tissue line of the receptor's own gene page ("CNS: pons.").
                check_one(f"receptor {r.get('id')} location_sources[{base}][{i}]", src,
                          short_ok=True)
        gate.check_location_uncertainty(f"receptor {r.get('id')}", r)
        # The density profile's quote carries the z per region and the cross-donor
        # agreement, so gating it verbatim is what keeps those numbers honest.
        for i, src in enumerate((r.get("density") or {}).get("sources") or []):
            check_one(f"receptor {r.get('id')} density sources[{i}]", src)
        check_effects(gate, meta, f"receptor {r.get('id')}", r, is_receptor=True)
        check_release_modulation(gate, r, bases)
        check_demographics(gate, f"receptor {r.get('id')}", r, bases)
        check_variants(gate, f"receptor {r.get('id')}", r)


def walk_targets(gate, meta, structures):
    check_one = gate.check_one
    bases = bases_of(structures)
    for tid, tinfo in (meta.get("drug_targets", {}) or {}).items():
        if isinstance(tinfo, dict):
            for i, src in enumerate(tinfo.get("sources", []) or []):
                check_one(f"target {tid} sources[{i}]", src)
            # A non-receptor target's per-region expression sources, quote-checked
            # like the receptor ones (same honesty gate for a future citation).
            for base, srcs in (tinfo.get("location_sources") or {}).items():
                for i, src in enumerate(srcs or []):
                    check_one(f"target {tid} location_sources[{base}][{i}]", src,
                              short_ok=True)  # one line of its gene page, as above
            gate.check_location_uncertainty(f"target {tid}", tinfo)
            for i, src in enumerate((tinfo.get("density") or {}).get("sources") or []):
                check_one(f"target {tid} density sources[{i}]", src)
            check_effects(gate, meta, f"target {tid}", tinfo, is_receptor=False)
            check_demographics(gate, f"target {tid}", tinfo, bases)
            check_variants(gate, f"target {tid}", tinfo)
