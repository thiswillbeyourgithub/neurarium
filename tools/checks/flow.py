"""Family 8: drug flow vs. binding consistency (warns, never errors).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import math
from collections import defaultdict

from lib.drugs_io import is_combination

from .common import base_id


def _affinity_weight(ki):
    """Ki (nM) -> a 0.35..1 engagement weight, a faithful port of js/data.js
    ``affinityWeightOf`` (a pKi ramp, 1 uM..0.1 nM -> 0.35..1). A binding with no
    measured Ki gets the same neutral mid weight the viewer uses, so the check
    reasons about the exact numbers the flow overlay animates."""
    median = ki.get("median") if isinstance(ki, dict) else None
    if not (isinstance(median, (int, float)) and median > 0):
        return 0.55
    pki = 9 - math.log10(median)
    t = max(0.0, min(1.0, (pki - 6) / 4))
    return 0.35 + 0.65 * t


def _tone_bucket_of(target, rec_meta):
    """Which ``meta.tone_rules`` bucket a binding falls in, or None for no tone.

    The one part of the flow model that is not in the rule table, because it is a
    join rather than a rule: the target's ``type`` (plus its ``vesicular`` flag)
    picks the first four buckets, and the autoreceptor bucket needs the RECEPTOR
    record behind the binding, since a receptor only feeds back on release when it
    is presynaptic AND inhibitory. Mirrors ``toneBucketOf`` in js/data.js.
    """
    ttype = target.get("type", "")
    if ttype == "transporter":
        return "vesicular_transporter" if target.get("vesicular") else "transporter"
    if ttype in ("enzyme", "vesicle_protein"):
        return ttype
    if ttype in ("receptor", "receptor_group"):
        # sign/synaptic from the specific receptor record (a modeled 5-HT1x / D2/D3),
        # else the group's own flag (the alpha2 family, in meta.drug_targets).
        rm = rec_meta.get(target.get("receptor")) if target.get("receptor") else target
        presyn = bool(rm) and rm.get("synaptic") in ("presynaptic", "both")
        if presyn and rm.get("sign") == "inhibitory":
            return "autoreceptor"
    return None


def _tone_of(target, action, rec_meta, tone_rules):
    """Signed tone contribution of one binding + the *label* of the mechanism that
    set it: ``(+1|-1|0, driver|None)``. +1 raises the transmitter's tone, -1 lowers
    it, 0 = not a tone-setter (a postsynaptic receptor -> dots only, never flow). The
    label lets the check say *why* a system's flow points the way it does (a reuptake
    block vs. an autoreceptor block).

    ``tone_rules`` is ``meta.tone_rules``, the SAME table js/data.js animates: the
    rule used to be transcribed by hand in each language, which is how the VMAT2
    direction bug survived in one copy. Now only the bucket join above is per-language
    and the directions themselves have one author (TONE_RULES in
    tools/data_generators/drugs.py)."""
    bucket = _tone_bucket_of(target, rec_meta)
    rule = (tone_rules.get(bucket) or {}).get(action) if bucket else None
    if not rule:
        return (0, None)
    tone, mechanism = rule[0], rule[1]
    return (tone, mechanism.replace("_", " "))


def _target_regions(target, rec_meta):
    """Base regions where a drug target is expressed: a receptor-linked target
    reuses its receptor's ``locations``, a bare DRUG_TARGETS entry its ``regions``."""
    rid = target.get("receptor")
    if rid and rid in rec_meta:
        return set(rec_meta[rid].get("locations", []))
    return set(target.get("regions", []))


def check_flow_consistency(report, meta, drugs, projections, receptors):
    """Cross-check each drug's by-mechanism flow overlay against its own receptor
    bindings, as an **informational** eyeball list (warnings, never errors, like the
    connectivity family): where the modeled flow direction and the drug's receptor
    actions tell opposite stories, so a human can confirm the picture is intended.

    Two views (the user asked for both), each collapsed to one line per drug+system:

    * **system-level** (8a): the flow overlay drives a transmitter's tone one way
      while the drug's *postsynaptic* receptor bindings on that same system net the
      other way (e.g. an SSRI raising serotonergic tone via SERT while antagonising
      5-HT2 postsynaptically). The driver tag says which mechanism set the flow.
    * **region-level** (8b): the drug boosts a system's ascending flow *into* a
      region while strongly blocking that system's receptors expressed *there*, so
      the streamed beads overstate the downstream effect (the user's own example).

    Most flags are the **intended** presynaptic-tone-vs-postsynaptic-block split, the
    documented autoreceptor caveat (a D2-antagonist antipsychotic reads dopamine-up
    because it blocks the D2 autoreceptor, while its postsynaptic blockade shows in
    the block-coloured dots). This is a review aid, not a gate: it cannot tell an
    intended dual action from a mis-entered ``action``, only surface the mismatch.
    The flow model (``_affinity_weight`` / ``_tone_of``) is the same one js/data.js
    animates, ported here so the check reasons about the very numbers the user sees."""
    report.header("8. Drug flow vs. binding consistency")
    drug_targets = meta.get("drug_targets", {})
    drug_actions = meta.get("drug_actions", {})
    system_flow_kinds = meta.get("system_flow_kinds", {})
    tone_rules = meta.get("tone_rules", {})
    rec_meta = {r.get("id"): r for r in receptors}
    effect_sign = {"boost": 1, "block": -1, "modulate": 0}

    # Base target-regions per projection kind: where increased flow of a kind would
    # arrive, so its postsynaptic receptors are the ones the region-level check cares
    # about. (Projections are already mirror-expanded by the caller.)
    arrives_in = defaultdict(set)
    for proj in projections:
        kind, dst = proj.get("kind"), base_id(proj.get("to"))
        if kind and dst:
            arrives_in[kind].add(dst)

    STRONG = 0.6   # per-binding engagement weight that counts as a "strong" block
    NET = 0.4      # net postsynaptic magnitude that counts as a real opposite lean

    a_flags, b_flags = [], []
    for drug in drugs:
        if is_combination(drug):
            continue  # a combo "A + B" has no unified flow (handled in the viewer)
        tone = defaultdict(float)          # system -> summed toneSign * affinity
        tone_drivers = defaultdict(list)   # system -> [(sign, driver_label)]
        postsyn = defaultdict(float)       # system -> summed effectSign * affinity
        postsyn_targets = defaultdict(set)  # system -> {receptor ids with an effect}
        strong_blocks = []                 # (system, target_id, base-region set)
        for b in drug.get("bindings", []):
            if b.get("affinity_only"):
                continue  # measured affinity, no direction -> never animates
            target = drug_targets.get(b.get("target"), {})
            system = target.get("system")
            if not system:
                continue
            action = b.get("action")
            aff = _affinity_weight(b.get("ki"))
            sign, driver = _tone_of(target, action, rec_meta, tone_rules)
            if sign:
                tone[system] += sign * aff
                tone_drivers[system].append((sign, driver))
                continue
            effect = drug_actions.get(action, {}).get("effect")
            es = effect_sign.get(effect, 0)
            if es:
                postsyn[system] += es * aff
                postsyn_targets[system].add(b["target"])
            if (effect == "block" and aff >= STRONG
                    and target.get("type") in ("receptor", "receptor_group")):
                strong_blocks.append(
                    (system, b["target"], _target_regions(target, rec_meta)))

        # 8a: flow direction opposes the net postsynaptic lean on the same system.
        for system, tsum in tone.items():
            if system not in system_flow_kinds or abs(tsum) < 1e-9:
                continue
            flow_dir = 1 if tsum > 0 else -1
            pnet = postsyn.get(system, 0.0)
            if (flow_dir > 0 and pnet <= -NET) or (flow_dir < 0 and pnet >= NET):
                drivers = sorted({drv for sgn, drv in tone_drivers[system]
                                  if sgn == flow_dir and drv})
                a_flags.append((
                    drug["id"], system, "up" if flow_dir > 0 else "down",
                    "; ".join(drivers) or "?",
                    "block" if pnet < 0 else "boost",
                    sorted(postsyn_targets[system])))

        # 8b: boosts a system's flow into regions whose receptors it strongly blocks.
        up_systems = {s for s, v in tone.items()
                      if s in system_flow_kinds and v > 0}
        by_system = defaultdict(lambda: (set(), set()))  # system -> (recs, regions)
        for system, tid, regions in strong_blocks:
            if system not in up_systems:
                continue
            hit = regions & arrives_in.get(system_flow_kinds[system], set())
            if hit:
                recs, regs = by_system[system]
                recs.add(tid)
                regs |= hit
        for system, (recs, regs) in by_system.items():
            b_flags.append((drug["id"], system, sorted(recs), sorted(regs)))

    for did, system, direction, drivers, lean, blocked in sorted(a_flags):
        report.review(
            f"drug {did!r}: {system} flow modeled {direction} ({drivers}) but its "
            f"postsynaptic {system} bindings net-{lean} ({', '.join(blocked)})")
    for did, system, recs, regs in sorted(b_flags):
        report.review(
            f"drug {did!r}: boosts {system} flow into {', '.join(regs)} yet blocks "
            f"{system} receptor(s) expressed there ({', '.join(recs)})")
    report.ok(
        f"{len(a_flags)} flow/postsynaptic + {len(b_flags)} flow-into-blocked-region "
        f"mismatches flagged (mostly the intended presynaptic-tone vs. postsynaptic-"
        f"block split; review, not a gate)")
