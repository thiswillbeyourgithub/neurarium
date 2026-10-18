"""Family 5 walks over the anatomy nodes and the addons: projections, structures.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""


def walk_addons(gate, addons):
    for addon in addons:
        for i, src in enumerate(addon.get("sources", []) or []):
            gate.check_one(f"addon {addon.get('id')} sources[{i}]", src)


def walk_projections(gate, meta, projections):
    for proj in projections:
        pid = f"{proj.get('from')}->{proj.get('to')}"
        for i, src in enumerate(proj.get("sources", []) or []):
            gate.check_one(f"projection {pid} sources[{i}]", src)
        # The per-claim split (transmitter / sign): gated by the shared gate helper.
        gate.check_claims(f"projection {pid}", proj, {
            "transmitter": proj.get("neurotransmitter"),
            "sign": (meta.get("kind_signs") or {}).get(proj.get("kind")),
        })
        # A pathway the book only states as a blanket sweep wears the same orange badge
        # a binding does, and its bullets are gated the same way.
        gate.check_uncertainty(f"projection {pid}", proj)


def walk_structures(gate, structures):
    for s in structures:
        for i, src in enumerate(s.get("sources", []) or []):
            gate.check_one(f"structure {s.get('id')} sources[{i}]", src)
