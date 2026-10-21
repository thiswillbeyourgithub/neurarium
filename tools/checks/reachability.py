"""Family 2: referential integrity (every cross-reference resolves).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

from lib.structure_ids import base_id


def check_reachability(report, meta, structures, projections, circuits,
                       projection_groups, receptors, drugs, addons, metabolites=()):
    report.header("2. Reachability (dangling references)")
    structure_ids = {s.get("id") for s in structures}
    base_ids = {base_id(sid) for sid in structure_ids}
    receptor_ids = {r.get("id") for r in receptors}
    targets = meta.get("drug_targets", {})
    before = report.errors

    def require(value, pool, context):
        if value not in pool:
            report.error(context)

    def check_density(ctx, owner, own_regions):
        """A density profile ranks the owner's OWN regions and nothing else: a stray base
        would draw an expression site the owner never claims. Shared by receptors and
        non-receptor targets (identical shape)."""
        density = owner.get("density")
        if not density:
            return
        for base in density.get("profile", {}):
            if base not in own_regions:
                report.error(f"{ctx}: density profile ranks {base!r}, which is not one "
                             f"of its regions (would imply an unclaimed expression site)")
        if not -1.0 <= density.get("reliability", 0) <= 1.0:
            report.error(f"{ctx}: density reliability {density.get('reliability')!r} "
                         f"is not a correlation in [-1, 1]")

    for structure in structures:
        require(structure.get("group"), meta.get("group_labels", {}),
                f"structure {structure.get('id')}: group {structure.get('group')!r} "
                f"is not in group_labels")

    for proj in projections:
        ctx = f"projection {proj.get('from')}->{proj.get('to')}"
        for endpoint in (proj.get("from"), proj.get("to")):
            if endpoint not in structure_ids:
                report.error(f"{ctx}: endpoint {endpoint!r} is not a structure id")
        require(proj.get("kind"), meta.get("projection_colors", {}),
                f"{ctx}: kind {proj.get('kind')!r} is not in projection_colors")

    for circuit in circuits:
        for sid in circuit.get("structures", []):
            if sid not in structure_ids:
                report.error(f"circuit {circuit.get('id')}: structure {sid!r} "
                             f"is not a structure id")

    # Projection groups: each names a colour-mode + a kind/sign key the viewer
    # groups arrows by; an unknown key would make the group's member-pathway list
    # (derived in the viewer) empty, so its detail panel would be unreachable.
    for group in projection_groups:
        gid, mode, key = group.get("id"), group.get("mode"), group.get("key")
        if mode == "kind":
            require(key, meta.get("projection_colors", {}),
                    f"projection group {gid}: kind {key!r} is not in projection_colors")
        elif mode == "sign":
            require(key, meta.get("sign_colors", {}),
                    f"projection group {gid}: sign {key!r} is not in sign_colors")
        else:
            report.error(f"projection group {gid}: unknown mode {mode!r} "
                         f"(expected 'kind' or 'sign')")

    for receptor in receptors:
        rid = receptor.get("id")
        for field, pool in (("family", "receptor_family_labels"),
                            ("receptor_class", "receptor_class_labels"),
                            ("synaptic", "synaptic_labels"),
                            ("sign", "sign_colors")):
            require(receptor.get(field), meta.get(pool, {}),
                    f"receptor {rid}: {field} {receptor.get(field)!r} is not in {pool}")
        for loc in receptor.get("locations", []):
            if loc not in base_ids:
                report.error(f"receptor {rid}: location {loc!r} is not a structure "
                             f"base (not in the atlas, so its panel 'Regional distribution' row "
                             f"would not be clickable)")
        # A per-region expression source must grade one of the receptor's own
        # locations (the "ALL" sentinel is the ubiquitous receptor's one claim).
        own = set(receptor.get("locations", []))
        for base in (receptor.get("location_sources") or {}):
            if base != "ALL" and base not in own:
                report.error(f"receptor {rid}: location_sources key {base!r} is not "
                             f"one of its locations (grades a region it doesn't claim)")
            if base == "ALL" and not receptor.get("ubiquitous"):
                report.error(f"receptor {rid}: location_sources 'ALL' but the "
                             f"receptor is not ubiquitous")
        check_density(f"receptor {rid}", receptor, own)
        # The merged Receptors & targets browse list expects every receptor to
        # also be a drug_targets key (a binding can target it directly).
        if rid not in targets:
            report.error(f"receptor {rid}: missing from drug_targets (unbrowsable)")

    for key, target in targets.items():
        require(target.get("type"), meta.get("target_type_labels", {}),
                f"target {key}: type {target.get('type')!r} is not in target_type_labels")
        for region in target.get("regions", []):
            if region not in base_ids:
                report.error(f"target {key}: region {region!r} is not a structure "
                             f"base (not in the atlas, so its panel 'Regional distribution' row "
                             f"would not be clickable)")
        # A per-region expression source must grade one of the target's own regions
        # (mirror of the receptor location_sources key check above).
        own_regions = set(target.get("regions", []))
        for base in (target.get("location_sources") or {}):
            if base not in own_regions:
                report.error(f"target {key}: location_sources key {base!r} is not "
                             f"one of its regions (grades a region it doesn't claim)")
        check_density(f"target {key}", target, own_regions)
        linked = target.get("receptor")
        if linked is not None and linked not in receptor_ids:
            report.error(f"target {key}: linked receptor {linked!r} is not a receptor id")

    # Action <-> target-type compatibility. A pharmacological action only makes sense
    # on certain target kinds; a mismatch means the direction (boost/block/tone) was
    # almost certainly mis-assigned. This is the guard that catches a VMAT2 (vesicular)
    # inhibitor mislabeled `reuptake_inhibitor` (which would read as a boost, not the
    # depletion it is). `modulator` is deliberately unconstrained (context-dependent).
    # A peptide receptor takes every action a receptor does: the type exists to say
    # which legend heading it belongs under, not to restrict its pharmacology.
    receptorish = {"receptor", "receptor_group", "peptide_receptor"}
    action_target_types = {
        "reuptake_inhibitor": {"transporter"},
        "releaser": {"transporter"},
        "vesicular_inhibitor": {"transporter", "vesicle_protein"},
        "vesicular_releaser": {"transporter"},
        "enzyme_inhibitor": {"enzyme"},
        "agonist": receptorish,
        "partial_agonist": receptorish,
        "antagonist": receptorish | {"ion_channel"},
        "inverse_agonist": receptorish,
        "pam": receptorish,
        "nam": receptorish,
        # A cotransporter (NKCC1) moves ions rather than a transmitter, so it is
        # blocked, never "reuptake-inhibited"; its own type keeps `blocker` legal
        # here without loosening it on a reuptake pump, where it would silently
        # mean no tone at all.
        "blocker": {"ion_channel", "vesicle_protein", "cotransporter"},
    }
    compat_errors = 0
    drug_ids = {d.get("id") for d in drugs}

    for drug in drugs:
        did = drug.get("id")
        for category in drug.get("categories", []):
            require(category, meta.get("drug_category_labels", {}),
                    f"drug {did}: category {category!r} is not in drug_category_labels")
        for binding in drug.get("bindings", []):
            target = binding.get("target")
            if target not in targets:
                report.error(f"drug {did}: binding target {target!r} is not a known "
                             f"target (the binding can never be focused)")
            # An affinity_only binding (PDSP Ki with no known direction) carries no
            # action/effect; every other binding must name a known action.
            if binding.get("affinity_only"):
                if not binding.get("ki"):
                    report.error(f"drug {did}: affinity_only binding {target!r} has "
                                 f"no ki (it would show nothing)")
            else:
                require(binding.get("action"), meta.get("drug_actions", {}),
                        f"drug {did}: binding action {binding.get('action')!r} is not "
                        f"in drug_actions")
                if "effect" in binding:
                    require(binding["effect"], meta.get("drug_effect_colors", {}),
                            f"drug {did}: binding effect {binding['effect']!r} is not "
                            f"in drug_effect_colors")
                # The action must be pharmacologically compatible with the target's
                # kind, else the derived direction (boost/block/tone) is mis-assigned.
                tgt = targets.get(target) or {}
                ttype = tgt.get("type")
                action = binding.get("action")
                allowed = action_target_types.get(action)
                if allowed is not None and ttype is not None and ttype not in allowed:
                    compat_errors += 1
                    report.error(f"drug {did}: action {action!r} is not valid on a "
                                 f"{ttype!r} target ({target!r}); its boost/block/tone "
                                 f"direction is almost certainly mis-assigned")
                elif tgt.get("vesicular") and action in ("reuptake_inhibitor", "releaser"):
                    compat_errors += 1
                    report.error(f"drug {did}: vesicular target {target!r} uses the "
                                 f"plasma-membrane action {action!r}; say which vesicular "
                                 f"direction it is -> vesicular_inhibitor (blocks loading, "
                                 f"depletes, tone down) or vesicular_releaser (a substrate "
                                 f"dumping the stores, tone up)")
            # The Ki annotation's source corpus must resolve (its verbatim-presence
            # in the CSV is confirmed in check_sources).
            ki = binding.get("ki")
            if ki:
                corpus = (ki.get("source") or {}).get("corpus")
                if corpus not in (meta.get("source_corpora", {}) or {}):
                    report.error(f"drug {did}: binding {target!r} ki source corpus "
                                 f"{corpus!r} is not in source_corpora")
    # Active metabolites: one record per molecule (metabolites.jsonl), referenced by
    # id from each parent's metabolites[]. Every ref must resolve, every record must be
    # referenced (an orphan is a molecule no panel reaches), a linked drug_id must be a
    # real drug, and a metabolite binding target must be a known target (so it can be
    # attributed in the receptor 'Ligands (drugs)' list).
    metab_ids = {m.get("id") for m in metabolites}
    referenced_metabs = set()
    for drug in drugs:
        for ref in drug.get("metabolites", []) or []:
            referenced_metabs.add(ref.get("id"))
            if ref.get("id") not in metab_ids:
                report.error(f"drug {drug.get('id')}: metabolite ref {ref.get('id')!r} "
                             f"is not a metabolites.jsonl id")
    for m in metabolites:
        mid = m.get("id")
        if mid not in referenced_metabs:
            report.error(f"metabolite {mid!r} is listed by no drug")
        link = m.get("drug_id")
        if link and link not in drug_ids:
            report.error(f"metabolite {mid!r} links drug_id {link!r} which is not a "
                         f"modeled drug")
        for binding in m.get("bindings", []) or []:
            if binding.get("target") not in targets:
                report.error(f"metabolite {mid!r} binding target "
                             f"{binding.get('target')!r} is not a known target")

    # Addon nodes carry their own insertion point, so "does it resolve?" is two
    # questions: does the anchored node exist, and is the slot one the viewer offers.
    # A wrong answer to either is a node that ships and is never drawn, which no other
    # check can see (it is well-formed, graded, and counted in the tally).
    addon_before = report.errors
    slots = meta.get("addon_slots") or {}
    displays = set(meta.get("addon_displays") or ())
    tones = set(meta.get("addon_tones") or {})
    addon_pools = {"drug": {d.get("id") for d in drugs},
                   "receptor": receptor_ids,
                   "target": set(targets),
                   "structure": base_ids,
                   # A section addon annotates a whole browse view rather than a
                   # node, so the "does the anchor exist" question is asked against
                   # the emitted section vocabulary itself.
                   "section": set(meta.get("addon_sections") or {})}
    for addon in addons:
        aid = addon.get("id")
        slot, kind = addon.get("slot"), addon.get("owner_kind")
        if slot not in slots:
            report.error(f"addon {aid!r}: slot {slot!r} is not in meta.addon_slots "
                         f"({sorted(slots)}); nothing would ever draw it")
        elif slots[slot] != kind:
            report.error(f"addon {aid!r}: anchors a {kind!r} node in slot {slot!r}, "
                         f"which is a {slots[slot]!r} panel slot")
        if addon.get("display") not in displays:
            report.error(f"addon {aid!r}: display {addon.get('display')!r} is not in "
                         f"meta.addon_displays ({sorted(displays)})")
        if addon.get("tone") not in tones:
            report.error(f"addon {aid!r}: tone {addon.get('tone')!r} is not in "
                         f"meta.addon_tones ({sorted(tones)})")
        pool = addon_pools.get(kind)
        if pool is None:
            report.error(f"addon {aid!r}: unknown owner_kind {kind!r}")
        elif addon.get("owner") not in pool:
            report.error(f"addon {aid!r}: anchors {kind} {addon.get('owner')!r}, "
                         f"which is not a known {kind} id")
        bases = meta.get("addon_bases") or ("claim",)
        basis = addon.get("basis", "claim")
        if basis not in bases:
            report.error(f"addon {aid!r}: basis {basis!r} is not in meta.addon_bases "
                         f"({list(bases)})")
        elif basis == "dataset" and addon.get("sources"):
            # A statement about the dataset itself cannot be sourced (and is kept out
            # of the tally on that ground), so a citation means it was misfiled.
            report.error(f"addon {aid!r}: a dataset statement carries sources")
        if not addon.get("text"):
            report.error(f"addon {aid!r}: no text (an addon IS its claim)")
    if addons and report.errors == addon_before:
        report.ok(f"all {len(addons)} addon nodes anchor a real node in a slot the "
                  f"viewer offers")

    if report.errors == before:
        report.ok("every cross-reference (drug -> target/action/category, projection "
                  "-> structure/kind, circuit/receptor/target -> structure) resolves; "
                  "every receptor/target region is in the atlas (its panel 'Regional distribution' "
                  "row is clickable)")

    if compat_errors == 0:
        report.ok("every binding action is compatible with its target's kind "
                  "(no mis-assigned boost/block/tone direction)")
