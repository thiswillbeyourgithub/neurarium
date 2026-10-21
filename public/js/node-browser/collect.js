// Data browser enumeration: every graded knowledge node in the dataset as one flat
// row list (the pure half of js/node-browser.js; the UI is node-browser/view.js).
// Shared with the Sources popup (js/about/sourcing.js), so the browser's rows and
// the popup's bars are the very same nodes. No DOM, no three.js.

import {
  approvalLabel, formatApproval, formatHolder, formatOriginator, formatWithdrawal,
} from "../drug-history.js";
import { formatAlert, formatRange } from "../tdm.js";
import { formatBbb, formatLogP, formatTpsa } from "../physchem.js";
import { formatWorkup } from "../workup.js";
import { transmitterVars } from "../release-modulation.js";
import { stripSide } from "../util.js";
import { shownGrade } from "../grades.js";


/**
 * Enumerate every graded knowledge node in the dataset as a flat row list.
 *
 * A row is `{kind, name, notion, grade, uncertain, go, sources, uncertainty, ki}`:
 * `kind` is the provenance-tally key (so it labels through the very i18n strings the
 * Sources popup's bars use), `name` names the node's owner, `notion` states the claim,
 * and `grade` is the DISPLAY grade a pill would show ("verified" / "sourced" / "llm" /
 * "nosource", or "uncertain" when the node carries uncertainty bullets, which is
 * what the panel's orange badge does). `go` navigates to the owning panel, or is
 * null for a node whose owner has nothing to focus (an unlocated target, an
 * unbindable drug), which renders the row inert. The last three carry the node's
 * BACKING (its quote-level sources, its reasons to doubt, its measured Ki) so the
 * row's pill shows the concrete source rather than the grade alone: the row's shape
 * is deliberately the one `ui.pill` (the panel's own source-backed pill) consumes,
 * so a row is handed straight to it.
 *
 * Wikipedia references are deliberately absent: a reference points *at* a node, it
 * is not itself one (same rule as the popup's bars). The per-kind counts otherwise
 * match `meta.provenance_stats.by_kind` exactly, so a drift between the two is a
 * bug; `twins: false` is the one deliberate departure (see `structures` below).
 *
 * @param {import("../data.js").BrainData} data normalized dataset
 * @param {{t: Function, formatHalfLife: Function, nav: object}} deps
 * @param {{twins?: boolean}} [opts] `twins` (default true) lists both hemispheres of
 *   a mirrored region; false collapses each pair to one side-less row
 * @returns {Array<{kind: string, name: string, notion: string, grade: string,
 *                  uncertain: boolean, go: (() => void)|null, sources: object[],
 *                  uncertainty: object[], ki: object|null}>}
 */
export function collectNodes(data, deps, opts = {}) {
  const { t, formatHalfLife, nav } = deps;
  const twins = opts.twins !== false;
  const rows = [];
  // `grade` is already defaulted by each caller (the per-kind default differs: an
  // unsourced classification is authored, hence "llm", while an unsourced binding
  // never had a source at all, hence "nosource"), so only the uncertainty override
  // lives here. `src` is the node's backing, `{sources, uncertainty, ki}` (any of
  // them optional); a binding object already has exactly those keys, so it is passed
  // through whole.
  // `owner` is the id of the record whose rows are being pushed (set by each loop
  // below), so a caller can pick a row by owner (kinds.js exampleRow).
  let owner = null;
  const push = (kind, name, notion, grade, go, src) => {
    const uncertainty = (src && src.uncertainty) || [];
    rows.push({
      kind,
      owner,
      name: name || "",
      notion: notion || "",
      grade: shownGrade(grade || "nosource", uncertainty),
      uncertain: shownGrade(grade, uncertainty) === "uncertain",
      go: go || null,
      sources: (src && src.sources) || [],
      uncertainty,
      ki: (src && src.ki) || null,
    });
  };

  const byId = data.byId || new Map();
  const meta = data.meta || {};
  const regionName = (id) => {
    const s = id && byId.get(id);
    return s ? (s.base_name || s.name) : null;
  };
  // A density profile is keyed by structure *base*, which is only a key in byId for
  // a midline region, so a lateralized one resolves through its right-hand member.
  const baseLabel = (base) => regionName(base) || regionName(`${base}_R`) || base;
  // A density node ranks its owner's regions against each other, so its claim is the
  // peak of that ranking: the region the profile puts first (they are emitted in
  // descending order) AND how far above this gene's brain-wide average it sits. The
  // region alone would name the claim without stating it. Signed to two decimals, the
  // same way a panel's "Regional distribution" row writes the z beside its bar.
  const topRegion = (info) => {
    const entries = info && info.profile ? Object.entries(info.profile) : [];
    if (!entries.length) return "";
    const [base, z] = entries[0];
    return `${baseLabel(base)} ${z > 0 ? "+" : ""}${z.toFixed(2)}`;
  };
  // A binding with a measured Ki but no established direction has no action label,
  // so it reads as its target plus the panel's own "affinity only" caveat.
  const bindingNotion = (b) => (b.affinityOnly
    ? `${b.targetName} (${t("drug.affinityOnly")})`
    : `${b.actionLabel}, ${b.targetName}`);

  // The DIRECTION claim, split out of the binding: backed by the binding's quote
  // sources ALONE (never its Ki, which attests that the ligand binds and nothing about
  // whether it activates or blocks), so the row's tooltip can never offer a measured
  // affinity as evidence for a direction. Same kind for a drug's and a metabolite's
  // bindings: it is a ligand's binding direction either way.
  const actionNotion = (b) => `${b.targetName}: ${b.affinityOnly
    ? t("drug.affinityOnly") : b.actionLabel}`;
  const actionBacking = (b) => ({ sources: b.sources, uncertainty: b.uncertainty,
    unknown: b.unknown });

  // Structures. A symmetric region is authored once and mirrored, so the `_L` twin
  // repeats its twin's group and grade verbatim, differing only in the side its name
  // carries. Collapsing the pair (the default) is the better *read*, since it says one
  // thing twice, and the collapsed row then drops the side from its name; listing both
  // is what makes the browser's count match the coverage tally, which counts each
  // emitted record (57 rows against 32 collapsed).
  for (const s of data.structures || []) {
    const twin = /_L$/.test(s.id) && byId.has(`${stripSide(s.id)}_R`);
    if (twin && !twins) continue;
    owner = s.id;
    push("structures", twins ? s.name : (s.base_name || s.name),
      (meta.groupLabels || {})[s.group] || s.group,
      s.classification_provenance || "llm",
      () => nav.structure(s.id), s);
  }

  // Projections. The loader pushes a flipped copy of every `mirror: true` pathway,
  // so the two hemispheres arrive as separate records for one node; collapse them
  // on the side-stripped route.
  const seenProjection = new Set();
  for (const p of data.projections || []) {
    const key = `${stripSide(p.from)}|${stripSide(p.to)}|${p.label}`;
    if (seenProjection.has(key)) continue;
    seenProjection.add(key);
    owner = p.from;
    push("projections", p.label, p.neurotransmitter || p.kind,
      p.provenance, () => nav.connection(p), p);
    // The two sub-claims split out of that arrow, each its own row with its own pill:
    // a sentence that states a pathway rarely also names what it releases, and rarer
    // still its sign (see the generator's quotes/attestation.py).
    const claims = p.claims || {};
    if (claims.transmitter) {
      push("projection_transmitter", p.label, p.neurotransmitter || p.kind,
        claims.transmitter.grade || "llm", () => nav.connection(p), claims.transmitter);
    }
    if (claims.sign) {
      push("projection_sign", p.label, (meta.signLabels || {})[p.sign] || p.sign,
        claims.sign.grade || "llm", () => nav.connection(p), claims.sign);
    }
  }

  for (const c of data.circuits || []) {
    owner = c.id;
    push("circuits", c.name, "", c.provenance, () => nav.circuit(c), c);
  }
  for (const g of data.projectionGroups || []) {
    owner = g.id;
    push("projection_groups", g.name, "", g.provenance, () => nav.group(g), g);
  }

  // A receptor's panel is its entry in the merged browse list (`data.targets`), not
  // the raw record, so index the two together once and reuse it for all six receptor
  // kinds below.
  const targetByReceptor = new Map();
  for (const tg of data.targets || []) {
    if (tg.kind === "receptor" && tg.receptor) targetByReceptor.set(tg.receptor.id, tg);
  }
  // Each of the four classification attributes is its own graded sub-claim (a quote
  // that backs the sign lends nothing to the GPCR claim), so each gets a row.
  const RECEPTOR_ATTRS = [
    ["receptors", "family", "familyLabel"],
    ["receptor_class", "receptor_class", "classLabel"],
    ["receptor_sign", "sign", "signLabel"],
    ["receptor_synaptic", "synaptic", "synapticLabel"],
  ];
  for (const r of data.receptors || []) {
    owner = r.id;
    const entry = targetByReceptor.get(r.id);
    const go = entry && entry.focusable ? () => nav.target(entry) : null;
    // A pure stub (a receptor with no CNS role: no locations, not ubiquitous, no
    // description) states nothing, so it is not a classification node and gets no
    // rows. Same predicate as the tally's `scored_receptors`, or the browser would
    // list six claims the coverage bars do not count.
    if (r.ubiquitous || (r.locations || []).length || r.description) {
      for (const [kind, attr, labelField] of RECEPTOR_ATTRS) {
        const claim = (r.classification || {})[attr] || {};
        push(kind, r.name, r[labelField], claim.grade || "llm", go, claim);
      }
    }
    for (const e of r.locationInfo || []) {
      push("receptor_locations", r.name, e.name, e.provenance || "llm", go, e);
    }
    // A ubiquitous receptor has one expression node covering the whole brain rather
    // than a row per region.
    if (r.ubiquitousInfo) {
      push("receptor_locations", r.name, t("receptor.ubiquitous"),
        r.ubiquitousInfo.provenance || "llm", go, r.ubiquitousInfo);
    }
    // ONE node for the whole profile, not one per region: it is a single measurement
    // ranking the receptor's regions against each other, so it is named by the region
    // it ranks highest (a bare receptor name would not state the claim).
    if (r.densityInfo) {
      push("receptor_density", r.name, topRegion(r.densityInfo),
        r.densityInfo.provenance || "llm", go, r.densityInfo);
    }
  }

  for (const tg of data.targets || []) {
    if (tg.kind === "receptor") continue; // covered above, from the raw record
    owner = tg.id;
    const go = tg.focusable ? () => nav.target(tg) : null;
    push("targets", tg.name, tg.typeLabel, tg.classificationProvenance || "llm", go, tg);
    // The direction-flipping polarity flag is its own node, distinct from the
    // classification grade, because it flips the drug-flow overlay's sign.
    if (tg.polarityProvenance) {
      push("target_polarity", tg.name, t("target.polarity"), tg.polarityProvenance, go,
        { sources: tg.polaritySources });
    }
    for (const e of tg.locationInfo || []) {
      push("target_locations", tg.name, e.name, e.provenance || "llm", go, e);
    }
    if (tg.densityInfo) {
      push("target_density", tg.name, topRegion(tg.densityInfo),
        tg.densityInfo.provenance || "llm", go, tg.densityInfo);
    }
  }
  // The per-target node kinds, receptors and non-receptor targets alike (data.js
  // resolves each onto the target list): receptor_effect (BETA, one row per (owner,
  // mode, effect)), receptor_release_modulation (BETA, one per (receptor, kind, site,
  // transmitter, direction)), receptor_demographic (BETA, one per (owner, factor,
  // direction, structure)) and receptor_variant (one per ClinPGx clinical annotation
  // on the owner's gene).
  for (const tg of data.targets || []) {
    owner = tg.id;
    const go = tg.focusable ? () => nav.target(tg) : null;
    for (const e of tg.effectInfo || []) {
      push("receptor_effect", tg.name, `${e.label} (${e.modeLabel})`, e.provenance, go, e);
    }
    for (const n of tg.modulationInfo || []) {
      push("receptor_release_modulation", tg.name,
        `${t(`relmod.activation.${n.effect}`,
          transmitterVars(n.transmitterLabel, window.__I18N__.ofNoun))} `
          + `(${n.kindLabel}, ${n.cellLabel})`, n.provenance, go, n);
    }
    for (const n of tg.demographicInfo || []) {
      push("receptor_demographic", tg.name,
        `${n.glyph} ${t(n.textKey, { where: n.structure ? ` (${n.structure})` : "" })}`,
        n.provenance, go, n);
    }
    for (const n of tg.variantInfo || []) {
      push("receptor_variant", tg.name,
        `${n.variant} (${[n.level, ...n.categories].join(", ")})`, n.provenance, go, n);
    }
  }

  // A metabolite's receptor BINDINGS are a property of the molecule, so a metabolite
  // shared by two parents contributes them once (one metabolites.jsonl record, keyed by
  // id). Its identity and its formation are not: "X is a metabolite of A"
  // and "X is a metabolite of B" are two separately sourced claims, and two parents
  // make it by two reactions, so both stay per parent. Matches the tally's own split.
  const seenMetaboliteBinding = new Set();
  for (const d of data.drugs || []) {
    owner = d.id;
    const go = d.focusable ? () => nav.drug(d) : null;
    for (const b of d.bindings || []) {
      if (b.viaMetabolite) continue;  // a prodrug's borrowed binding: the metabolite's node
      push("drug_bindings", d.name, bindingNotion(b), b.provenance, go, b);
      push("drug_binding_action", d.name, actionNotion(b), b.actionProvenance, go,
        actionBacking(b));
    }
    if (d.nbn) push("drug_nbn", d.name, d.nbn, d.nbnProvenance, go,
      { sources: d.nbnSources });
    for (const br of d.brandsOrdered || []) {
      const src = (br.sources || [])[0];
      push("drug_brands", d.name, br.name, src && src.provenance, go, br);
    }
    if ((d.categoryLabels || []).length) {
      push("drug_categories", d.name, d.categoryLabels.join(", "),
        d.categoryProvenance || "llm", go, { sources: d.categorySources });
    }
    if (d.halfLife) {
      push("drug_half_life", d.name, `T½ ${formatHalfLife(d.halfLife)}`,
        d.halfLifeProvenance, go, { sources: d.halfLifeSources });
    }
    if (d.tmax) {
      push("drug_tmax", d.name, `${t("drug.tmax")} ${formatHalfLife(d.tmax)}`,
        d.tmaxProvenance, go, { sources: d.tmaxSources });
    }
    // Each formulation is its own node (the release type), and its T½ / Tmax are
    // counted under the same kinds as the molecule's (its brands already ride
    // brandsOrdered above), exactly as the tally does.
    for (const f of d.formulations || []) {
      push("drug_formulations", d.name, f.label, f.releaseProvenance, go,
        { sources: f.releaseSources });
      if (f.halfLife) {
        push("drug_half_life", `${d.name} (${f.label})`,
          `T½ ${formatHalfLife(f.halfLife)}`, f.halfLifeProvenance, go,
          { sources: f.halfLifeSources });
      }
      if (f.tmax) {
        push("drug_tmax", `${d.name} (${f.label})`,
          `${t("drug.tmax")} ${formatHalfLife(f.tmax)}`, f.tmaxProvenance, go,
          { sources: f.tmaxSources });
      }
    }
    if (d.firstApproval) {
      push("drug_first_approval", d.name,
        `${approvalLabel(d.firstApproval, t)} ${formatApproval(d.firstApproval)}`,
        d.firstApproval.provenance, go, { sources: d.firstApproval.sources });
    }
    if (d.prodrug) {
      push("drug_prodrug", d.name, t("drug.prodrug"), d.prodrug.provenance, go,
        { sources: d.prodrug.sources });
    }
    if (d.constituentsClaim) {
      push("drug_constituents", d.name,
        t("drug.constituentsOf", { parts: d.constituents.join(" + ") }),
        d.constituentsClaim.provenance, go, { sources: d.constituentsClaim.sources });
    }
    if (d.therapeuticRange) {
      push("drug_therapeutic_range", d.name, `${t("drug.therapeuticRange")} `
        + formatRange(d.therapeuticRange, window.__I18N__.lang),
        d.therapeuticRange.provenance, go, { sources: d.therapeuticRange.sources });
    }
    if (d.alertLevel) {
      push("drug_alert_level", d.name, `${t("drug.alertLevel")} `
        + formatAlert(d.alertLevel, window.__I18N__.lang),
        d.alertLevel.provenance, go, { sources: d.alertLevel.sources });
    }
    const lang = window.__I18N__.lang;
    for (const [kind, node, key, text] of [
      ["drug_lipophilicity", d.xlogp, "drug.xlogp", (n) => formatLogP(n.value, lang)],
      ["drug_polar_surface", d.tpsa, "drug.tpsa", (n) => formatTpsa(n.value, lang)],
      ["drug_bbb", d.bbb, "drug.bbb", (n) => formatBbb(n, t, lang)],
    ]) {
      if (node) push(kind, d.name, `${t(key)} ${text(node)}`, node.provenance, go,
        { sources: node.sources });
    }
    for (const n of d.workup || []) {
      push("drug_workup", d.name, `${t("drug.workupShort")} ${formatWorkup(n, t("drug.workupOnlyIf"))}`,
        n.provenance, go, n);
    }
    if (d.originator) {
      push("drug_originator", d.name, `${t("drug.originator")} ${formatOriginator(d.originator, t)}`,
        d.originator.provenance, go, { sources: d.originator.sources });
      const c = d.originator.country;
      if (c) {
        push("drug_originator_country", d.name, `${t("drug.originator")} ${c.label}`,
          c.provenance, go, { sources: c.sources });
      }
    }
    for (const h of d.holders || []) {
      push("drug_holders", d.name, `${t("drug.holders")} ${formatHolder(h)}`, h.provenance,
        go, { sources: h.sources });
    }
    for (const w of d.withdrawals || []) {
      push("drug_withdrawals", d.name, `${t("drug.withdrawn")} ${formatWithdrawal(w)}`,
        w.provenance, go, { sources: w.sources });
    }
    for (const e of d.enzymes || []) {
      push("drug_enzymes", d.name, `${e.label}: ${e.roleLabel}`, e.provenance, go, e);
      // HOW MUCH of the clearing that isoform does: its own node, since the CYP quote
      // gate only ever checked that the quote names the isoform, never the tier.
      const strength = (e.claims || {}).strength;
      if (e.strengthLabel) {
        push("drug_enzyme_strength", d.name, `${e.label}: ${e.strengthLabel}`,
          (strength && strength.grade) || "llm", go, strength);
      }
    }
    // CPIC's prescribing guidance: one node per (gene, phenotype) row, two citations
    // (implication, recommendation) on one row (data/pk.js resolves the label).
    for (const block of d.pgx || []) {
      for (const r of block.rows || []) {
        push("drug_pgx", d.name, `${block.label}: ${r.label}`, r.provenance, go, r);
      }
    }
    for (const m of d.metabolites || []) {
      const mKey = m.id || (m.name || "").toLowerCase();
      // A metabolite has no panel of its own, so its nodes open the PARENT drug. Say
      // which metabolite was asked for, or the reader picks "6-Monoacetylmorphine"
      // and lands on a Heroin panel with nothing pointing at what they clicked.
      const goMetab = d.focusable
        ? () => nav.drug(d, { highlightMetabolite: m.name })
        : null;
      push("drug_metabolites", d.name, m.name, m.provenance, goMetab, m);
      for (const f of m.formedBy || []) {
        push("drug_metabolite_enzyme", d.name,
          `${m.name}: ${t("drug.formedBy")} ${f.label}`, f.provenance, goMetab, f);
      }
      for (const b of m.ownBindings || []) {
        const bKey = `${mKey}|${b.target}`;
        if (seenMetaboliteBinding.has(bKey)) continue;
        seenMetaboliteBinding.add(bKey);
        push("drug_metabolite_bindings", d.name, `${m.name}: ${bindingNotion(b)}`,
          b.provenance, goMetab, b);
        push("drug_binding_action", d.name, `${m.name}: ${actionNotion(b)}`,
          b.actionProvenance, goMetab, actionBacking(b));
      }
    }
  }

  // Addon nodes: a sourced annotation that carries its own panel slot. The row names
  // the node it annotates (so it reads like every other row: subject, then claim) and
  // navigates to that node's panel, where the annotation is spliced in.
  for (const a of data.addons || []) {
    // A statement about the dataset itself is not knowledge, so it is no node of the
    // tally (provenance.py) and no row here either: the counts must agree.
    if (a.basis === "dataset") continue;
    owner = a.owner;
    const go = a.focus ? () => nav[a.focus.nav](a.focus.arg) : null;
    push("addons", a.ownerName, a.title || a.text, a.provenance, go, a);
  }

  return rows;
}
