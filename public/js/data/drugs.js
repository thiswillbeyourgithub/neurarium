// Drug stage: per-drug facts + metabolism (delegated), then the resolved bindings
// with their animation fields, the tone flow, brands and search keywords.

import { affinityWeightOf, toneWeightOf, toneBySystem } from "./tone.js";
import { resolveDrugFacts } from "./drug-facts.js";
import { resolveDrugMetabolism, makeVariabilityEntry } from "./pk.js";

// A brand name can carry a parenthetical note from the source's own list, and two
// very different things hide in there. A FORMULATION note ("Saphris (sublingual)")
// is the same molecule delivered another way. A COMPOSITION note ("Suboxone (with
// naloxone)") is a DIFFERENT product, so letting it headline the drug misnames it:
// buprenorphine is not Suboxone. See the primaryBrand pick below.
const BRAND_NOTE = /\s*\([^()]*\)\s*$/;
const BRAND_COMBO = /\((?:with|in combination|\+)/i;

export function resolveDrugs({ drugs, receptors, byId, allIds, metaRecord, v },
                             { toneSignOf, toneRuleOf, toneFactorOf }, bindingDisplayFields) {
  const { systemFlowKinds } = v;
  const variabilityEntry = makeVariabilityEntry(metaRecord);
  // Resolve each drug for the viewer. A binding's `target` indexes the merged
  // drug_targets map; resolve its display name, the action label + net effect (and
  // the effect's swatch colour, driving the per-drug animation), and the concrete
  // structure ids it lights: a receptor-linked target reuses that receptor's
  // already-expanded structureIds, a ubiquitous one lights every structure, and a
  // non-receptor target expands its region bases to both hemispheres (like a
  // receptor's locations). The union over all bindings is the drug's affected set
  // (what the focus dims the brain down to). `keywords` feeds the search box.
  const receptorStructureIds = new Map(receptors.map((r) => [r.id, r.structureIds]));
  for (const d of drugs) {
    resolveDrugFacts(d, v);
    resolveDrugMetabolism(d, v, metaRecord, variabilityEntry);
    const affected = new Set();
    // `lit`: the structure ids this binding lights get added to (the drug's own
    // bindings feed `affected`; a metabolite's lit set is discarded, see below).
    const resolveBinding = (b, lit) => {
      // Display + provenance fields come from the shared resolver; the drug loop
      // then layers on the animation-only fields (structureIds/flow/weights). See
      // bindingDisplayFields. `tgt` is reused, `disp.tgt` is not returned to callers.
      const disp = bindingDisplayFields(b);
      const { tgt, affinityOnly, peripheral, effect } = disp;
      // Neither an affinity-only nor a peripheral binding touches the scene: the
      // first states no direction, the second states one that happens elsewhere.
      const inert = affinityOnly || peripheral;
      // An affinity_only binding has a measured Ki but no known direction (neither
      // PDSP nor GtoPdb states one): it is listed in the panel with its Ki but has no
      // action/effect, so it never animates and contributes nothing to the lit-region
      // union or the flow. Every binding that DOES state a direction animates,
      // whichever corpus sourced it.
      let structureIds = [];
      if (inert) {
        structureIds = [];
      } else if (tgt.ubiquitous) {
        structureIds = allIds.slice();
      } else if (tgt.receptor && receptorStructureIds.has(tgt.receptor)) {
        structureIds = receptorStructureIds.get(tgt.receptor).slice();
      } else {
        structureIds = (tgt.regions || []).flatMap((bse) =>
          [bse, `${bse}_R`, `${bse}_L`].filter((id) => byId.has(id)),
        );
      }
      if (!inert) for (const id of structureIds) lit.add(id);
      return {
        target: disp.target,
        targetName: disp.targetName,
        system: disp.system,
        // The projection kind this binding's target system feeds (meta.system_flow_
        // kinds), null when the system has no modeled ascending pathway or the
        // binding is affinity-only. Lets a panel list the "neurotransmitter tone" per
        // binding and lets d.flowKinds below dedupe from a single field.
        flowKind: inert ? null : systemFlowKinds[tgt.system] || null,
        receptor: disp.receptor,
        affinityOnly,
        peripheral,
        action: disp.action,
        actionLabel: disp.actionLabel,
        effect,
        effectColor: disp.effectColor,
        effectLabel: disp.effectLabel,
        note: disp.note,
        tentative: disp.tentative,
        structureIds,
        // Relative engagement from the measured Ki (0.35..1), NOT effect size.
        // Scales the dot cloud in drug-anim; also weights this binding's system
        // tone below. Neutral mid-value when no Ki.
        affinityWeight: inert ? 0 : affinityWeightOf(b.ki),
        // Signed tone-setter contribution to its system's ascending flow (+1 raises
        // the transmitter's tone, -1 lowers, 0 = not a tone-setter -> dots only).
        toneSign: inert ? 0 : toneSignOf(tgt, b.action),
        // Why it sets that tone (meta.tone_rules driver, e.g. "reuptake_block"), shown
        // in the drug panel's tone breakdown; null when it sets none.
        toneRule: inert ? null : toneRuleOf(tgt, b.action),
        // Its share of that tone: the bucket factor (an autoreceptor counts half a
        // reuptake block) times the floor-free Ki weight (see toneBySystem).
        toneFactor: inert ? 1 : toneFactorOf(tgt),
        toneWeight: inert ? 0 : toneWeightOf(b.ki),
        // Per-claim sources ({corpus, page, quote, provenance}); `provenance` is the
        // strongest grade among the quote sources AND the measured Ki. See
        // bindingDisplayFields / _binding_grade in generate_data.py.
        sources: disp.sources,
        provenance: disp.provenance,
        // The direction's own grade (node kind `drug_binding_action`), from the quote
        // sources alone. null = affinity_only, i.e. no direction claim to grade.
        actionProvenance: disp.actionProvenance,
        unknown: disp.unknown,
        // Non-empty -> the badge reads "uncertain" instead of the green check.
        uncertainty: disp.uncertainty,
        // The measured PDSP Ki (own verified badge), null when absent.
        ki: disp.ki,
        // The molecule this binding is lent from (a prodrug's or a salt's borrowing,
        // or an active metabolite's binding, see borrowBindings); null on the drug's
        // own bindings.
        viaMetabolite: b.via_metabolite || null,
      };
    };
    d.bindings = (d.bindings || []).map((b) => resolveBinding(b, affected));
    d.structureIds = [...affected];
    // Its active metabolites' bindings (borrowBindings `metabolite_bindings`, empty for
    // a prodrug, which already took them as its own), resolved the same way and
    // flagged `fromMetabolite`. They stay out of the lit regions (those are the parent
    // molecule's), but every panel readout of bindings reads `allBindings`: the
    // "Direct molecular targets" rows, the tone and its flow overlay below, the inferred
    // effects and the release changes, each row naming the compound (`viaMetabolite`).
    const scratch = new Set();
    d.metaboliteBindings = (d.metabolite_bindings || [])
      .map((b) => ({ ...resolveBinding(b, scratch), fromMetabolite: true }));
    d.allBindings = d.metaboliteBindings.length
      ? [...d.bindings, ...d.metaboliteBindings] : d.bindings;
    // By-mechanism flow, split from the dots (approach 3): a projection kind gets a
    // flow overlay ONLY from *tone-setter* bindings (transporters, enzymes, vesicle
    // proteins, presynaptic inhibitory autoreceptors), never from a postsynaptic
    // receptor (those stay dots). Per engaged kind we sum toneSign*toneFactor*toneWeight so
    // combos and opposing autoreceptors resolve to a net signed tone; the sign is the
    // flow direction (boost vs damp) and the clamped magnitude its intensity.
    d.flowSystems = toneBySystem(d.allBindings);
    // Normalize to a per-drug *relative* intensity (`rel`, 0..1): the drug's strongest
    // engaged system streams at 1, the rest in proportion. Dosage is highly variable,
    // so what the flow overlay should show is the relative "dirtiness" across systems,
    // not an absolute magnitude. `weight` (absolute affinity) is kept for the panel's
    // strongest-binding pill; `rel` drives the animation's density/speed.
    const maxFlowWeight = Math.max(0, ...Object.values(d.flowSystems).map((f) => f.weight));
    for (const f of Object.values(d.flowSystems)) {
      f.rel = maxFlowWeight ? f.weight / maxFlowWeight : 1;
    }
    // Drives the flowing-beads overlay (main.js filters arrows by these kinds, then
    // js/circuit-anim.js animates them with the per-kind direction/weight above) and
    // the panel's "Neurotransmitter tone" list. Empty for a drug that sets no tone (a
    // purely postsynaptic agent gets just dots + wash).
    d.flowKinds = Object.keys(d.flowSystems);
    // Static "context" pathways (viewer-side, split from the flow): the ascending
    // systems the drug acts *within* through a POSTSYNAPTIC receptor (a flow-mapped
    // system carrying no tone-setter binding) e.g. an H1 / 5-HT2 / postsynaptic-D2
    // blocker. Blocking a postsynaptic receptor does NOT change the transmitter's
    // release/tone, so these earn no beads and no direction: main.js pins them at a
    // dimmed *static* opacity so a purely postsynaptic agent (an antihistamine) still
    // visibly engages its system's pathways, without falsely claiming a tone shift. A
    // kind already flowing (in flowSystems) is excluded, the beads already cover it.
    const ctxKinds = new Set();
    for (const b of d.allBindings) {
      if (b.flowKind && !b.toneSign && !d.flowSystems[b.flowKind]) ctxKinds.add(b.flowKind);
    }
    d.contextKinds = [...ctxKinds];
    // Every drug is focusable, bindings or not: its panel (brands, kinetics,
    // metabolism, addons) is worth opening even when there is nothing to light in 3D
    // (lithium), so search + the drug list reach it like any other.
    d.focusable = d.focusable !== false;
    // Commercial brand names, ordered for THIS locale (the `region` tag orders only,
    // it is never shown): a French reader sees fr -> eu -> na, everyone else
    // na -> eu -> fr; within a region the authored order is kept (first = most iconic).
    // `brandsOrdered` are the graded brand nodes in that order (deduped by name so a
    // name shared across regions shows once, keeping its first/top-region source);
    // `primaryBrand` is the single most-iconic name shown after the drug name
    // everywhere (see drugDisplayName), `brandNames` the full list, `displayName` the
    // name + primary. All brand names also feed search. See docs/DRUGS.md "Drugs".
    const brandRank = window.__I18N__.lang === "fr"
      ? { fr: 0, eu: 1, na: 2 }
      : { na: 0, eu: 1, fr: 2 };
    const brandSeen = new Set();
    // Formulation brands join after the molecule's own (tagged with their `release`),
    // so search and the primary brand see every name while the panel's Brands row can
    // keep to the molecule's.
    d.brandsOrdered = [...(d.brands || []), ...d.formulations.flatMap((f) => f.brands)]
      // `region` is one tag, or a list when one name is sold in several regions.
      .map((b, i) => ({ b, r: Math.min(...[].concat(b.region).map((g) => brandRank[g] ?? 9)), i }))
      .sort((x, y) => x.r - y.r || x.i - y.i)
      .map((x) => x.b)
      .filter((b) => {
        const k = (b.name || "").toLowerCase();
        if (!k || brandSeen.has(k)) return false;
        brandSeen.add(k);
        return true;
      });
    d.brandNames = d.brandsOrdered.map((b) => b.name);
    // Locale-ordered brand *stems*, the note dropped: a brand listed both plainly and
    // with a note (naltrexone's "Revia (oral)" in the NA list, "Revia" in the FR one)
    // is ONE brand, and counts as plainly named wherever it first appeared.
    const stems = [];
    const stemAt = new Map();
    for (const n of d.brandNames) {
      const stem = n.replace(BRAND_NOTE, "");
      const k = stem.toLowerCase();
      let e = stemAt.get(k);
      if (!e) { e = { stem, plain: false, combo: false }; stemAt.set(k, e); stems.push(e); }
      if (!BRAND_NOTE.test(n)) e.plain = true;
      else if (BRAND_COMBO.test(n)) e.combo = true;
    }
    // The headline brand is the first plainly-named one, else the first whose only
    // note is a formulation, so a combination product never quietly stands in for the
    // single molecule: Stahl lists nothing but the naloxone combos and the depots for
    // buprenorphine, whose plain brand (Subutex here, Temgésic in French) is the one
    // to show. A drug that IS a combination keeps its own, since it is already named.
    const selfCombo = /[+/]/.test(d.name || "");
    d.primaryBrand = (stems.find((e) => e.plain)
      || stems.find((e) => selfCombo || !e.combo)
      || {}).stem || d.brandNames[0] || null;
    // `label` = the name plus its display-only chemical synonym when the generator
    // emits one (DRUG_NAME_QUALIFIERS: "Paliperidone (9-OH-risperidone)"); `name`
    // itself stays the INN, which the external lookup links search by.
    d.label = d.name_qualifier ? `${d.name} (${d.name_qualifier})` : d.name;
    d.displayName = d.primaryBrand ? `${d.label} (${d.primaryBrand})` : d.label;
    // `aliases` are the search-only alternate names (GHB for sodium oxybate, ecstasy
    // for MDMA, ...). They join the haystack and are never rendered: a drug is always
    // shown under its own name, so an alias only ever helps someone find it.
    d.keywords = [...d.categoryLabels, d.nbn, ...d.brandNames, ...(d.aliases || []),
                  d.name_qualifier,
                  ...d.bindings.map((b) => b.targetName)]
      .filter(Boolean)
      .join(" ");
  }
}
