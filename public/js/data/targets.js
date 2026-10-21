// The merged "Receptors & targets" browse list and its by-structure reverse index.

import { localize } from "./localize.js";
import { locationEntry, densityEntry } from "./expression.js";

export function buildTargets({ receptors, byId, baseName, v }) {
  const { drugTargets, targetTypeLabels, targetTypeColors, receptorFamilyLabels } = v;
  // Build the merged "Receptors & targets" browse list: one normalized entry per
  // focusable *thing a drug can act on*, so a transporter (SERT), enzyme (MAO-A) or
  // channel (Nav) can be explored on its own, not only as a line in a drug's "Acts
  // on" list. Two sources, one shape: every modeled receptor (kind "receptor",
  // keeping its sign swatch + full classification for the panel), then every
  // *non-receptor* drug_targets entry (the receptor-linked ones are already covered
  // by the receptors above). Both carry `system` (the neurotransmitter family the
  // legend groups by; null -> the "Other" heading), a swatch colour, the expanded
  // `structureIds` to light, a `focusable` flag (false when there is no modeled
  // region, like a receptor stub) and search `keywords`. A receptor entry points
  // back at its record (panel reuses showReceptor); a non-receptor one carries the
  // display fields showTarget needs.
  const targets = [];
  for (const r of receptors) {
    targets.push({
      id: r.id,
      kind: "receptor",
      name: r.name,
      system: r.family,
      swatchColor: r.signColor,
      structureIds: r.structureIds,
      ubiquitous: !!r.ubiquitous,
      focusable: r.focusable,
      receptor: r,
      keywords: [r.familyLabel, r.classLabel, r.signLabel, r.neurotransmitter]
        .filter(Boolean).join(" "),
    });
  }
  for (const [id, tgt] of Object.entries(drugTargets)) {
    if (tgt.receptor) continue; // already listed as a receptor above
    const structureIds = (tgt.regions || []).flatMap((b) =>
      [b, `${b}_R`, `${b}_L`].filter((sid) => byId.has(sid)),
    );
    const typeLabel = targetTypeLabels[tgt.type] || tgt.type || "";
    const systemLabel = tgt.system ? receptorFamilyLabels[tgt.system] || tgt.system : "";
    targets.push({
      id,
      kind: tgt.type || "target",
      name: localize(tgt.name),
      system: tgt.system || null,
      swatchColor: targetTypeColors[tgt.type] || "#9aa0a6",
      structureIds,
      ubiquitous: false,
      focusable: structureIds.length > 0,
      receptor: null,
      typeLabel,
      systemLabel,
      wikipedia: tgt.wikipedia || "",
      // Representative HGNC symbol (SERT -> SLC6A4), an identifier, not a graded
      // claim: what the gene-keyed ClinPGx lookup link searches for.
      gene: tgt.gene || "",
      // A receptor_group's modeled subtype receptor ids (α2 -> α2A/B/C/D), a
      // sourceless taxonomy (meta.drug_targets[].subtypes). The panel lists each
      // subtype's own interacting drugs in a dropdown; empty for a non-group target.
      subtypes: tgt.subtypes || [],
      // Source grade backing this target's classification (type / system / regions),
      // shown as the panel's "Source" pill (default "llm"); `sources` carries the
      // quote-level source(s) so the pill tooltip can show the verbatim quote.
      classificationProvenance: tgt.classification_provenance || "llm",
      sources: tgt.sources || [],
      // Tone-polarity sub-claim ("engaging this target raises/lowers system tone"):
      // its OWN graded node (kind target_polarity), distinct from the classification
      // grade, because the vesicular/sign/synaptic flags flip the flow-overlay sign.
      // Present only for a target that carries a polarity flag; the panel renders a
      // dedicated pilled row so a wrong direction is not hidden behind the type pill.
      vesicular: !!tgt.vesicular,
      polaritySign: tgt.sign || null,
      polaritySynaptic: tgt.synaptic || null,
      polarityProvenance: tgt.polarity_provenance || null,
      polaritySources: tgt.polarity_sources || [],
      locationNames: (tgt.regions || []).map((b) => baseName.get(b) || b),
      // The raw base ids parallel to locationNames, so the panel can make each
      // "Regional distribution" row jump to that structure (the receptor records keep their own
      // `locations` for the same purpose).
      locationBases: (tgt.regions || []).slice(),
      // Per-region expression provenance ("Regional distribution"), parallel to locationBases:
      // "target T is found in region B" is its own graded node (default llm when
      // unsourced), so the panel shows a per-row pill, exactly like a receptor's
      // locationInfo. From the emitted target.location_sources ({base: [source]}).
      locationInfo: (tgt.regions || []).map((b) =>
        locationEntry(b, baseName.get(b) || b, (tgt.location_sources || {})[b],
          (tgt.location_uncertainty || {})[b])),
      // Expression density per region, the mirror of a receptor's densityInfo.
      densityInfo: densityEntry(tgt.density),
      keywords: [typeLabel, systemLabel].filter(Boolean).join(" "),
    });
  }
  return targets;
}

export function indexTargetsByStructure({ targets, baseName }) {
  // The reverse of a receptor's "Regional distribution": region base -> the targets expressed
  // there. Same node, read from the other end (the expression claim belongs to the
  // (target, region) pair, not to the target), so each entry carries THAT region's
  // own graded `info` and the structure panel shows the very pill the receptor panel
  // shows. A ubiquitous receptor is listed in every region under its single
  // "throughout the brain" node, which is the one expression claim it has.
  const targetsByStructure = new Map();
  const pushTarget = (base, entry) => {
    if (!baseName.has(base)) return; // an expression claim on an unmodeled region
    if (!targetsByStructure.has(base)) targetsByStructure.set(base, []);
    targetsByStructure.get(base).push(entry);
  };
  for (const tgt of targets) {
    const rec = tgt.receptor;
    if (rec && rec.ubiquitous) {
      for (const base of baseName.keys()) {
        pushTarget(base, { target: tgt, info: rec.ubiquitousInfo, ubiquitous: true });
      }
      continue;
    }
    const bases = rec ? rec.locations : tgt.locationBases;
    const infos = rec ? rec.locationInfo : tgt.locationInfo;
    (bases || []).forEach((base, i) => {
      pushTarget(base, { target: tgt, info: infos && infos[i], ubiquitous: false });
    });
  }
  return targetsByStructure;
}
