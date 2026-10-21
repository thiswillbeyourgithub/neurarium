// Receptor stage: labels, concrete structure ids, per-region expression nodes.

import { localize } from "./localize.js";
import { strongestGrade } from "../grades.js";
import { locationEntry, densityEntry } from "./expression.js";

export function resolveReceptors({ receptors, byId, baseName, allIds, v }) {
  const { receptorFamilyLabels, receptorClassLabels, signColors, signLabels, synapticLabels } = v;
  // Resolve each receptor for the viewer. `locations` holds structure *base* ids
  // (like circuits, but one entry per region rather than per hemisphere); expand
  // each to the concrete structure ids actually emitted (both hemispheres, or the
  // bare id for a midline structure) so the marker layer can light them up, and
  // collect the side-stripped region names for the info panel. A `ubiquitous`
  // receptor (NMDA, GABA-A, ...) lights every structure. `focusable` is false for
  // the deliberate "stub" receptors (no CNS role, empty locations) so the legend
  // can render them as inert rows.
  for (const r of receptors) {
    r.neurotransmitter = localize(r.neurotransmitter);
    r.description = r.description ? localize(r.description) : "";
    r.familyLabel = receptorFamilyLabels[r.family] || r.family;
    r.classLabel = receptorClassLabels[r.receptor_class] || r.receptor_class;
    r.signColor = signColors[r.sign] || "#ffffff";
    r.signLabel = signLabels[r.sign] || r.sign;
    r.synapticLabel = synapticLabels[r.synaptic] || r.synaptic;
    if (r.ubiquitous) {
      r.structureIds = allIds.slice();
    } else {
      r.structureIds = r.locations.flatMap((b) =>
        [b, `${b}_R`, `${b}_L`].filter((id) => byId.has(id)),
      );
    }
    r.locationNames = r.locations.map((b) => baseName.get(b) || b);
    // Per-region expression provenance: the "Regional distribution" node "this receptor is
    // expressed in region B" is graded per region (default llm when unsourced), so
    // the panel shows a pill per row. Parallel to locations/locationNames.
    const locSrc = r.location_sources || {};
    const locDoubt = r.location_uncertainty || {};
    r.locationInfo = r.locations.map((b, i) =>
      locationEntry(b, r.locationNames[i], locSrc[b], locDoubt[b]));
    // How much of it sits in each region (one measured profile over those regions,
    // its own graded node). Null when unmeasured -> the panel just omits the bars.
    r.densityInfo = densityEntry(r.density);
    // A ubiquitous receptor is one "throughout the brain" expression node
    // (its location_sources under the "ALL" sentinel), graded like a region.
    if (r.ubiquitous) {
      r.ubiquitousInfo = {
        sources: locSrc.ALL || [],
        provenance: strongestGrade(locSrc.ALL) || "llm",
      };
    }
    r.focusable = r.ubiquitous || r.structureIds.length > 0;
  }
}
