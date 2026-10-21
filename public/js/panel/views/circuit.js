// The Circuit view: a named circuit's member regions and the pathways between them.

import { stripSide } from "../../util.js";
import { emptySection } from "../dom.js";

const { t } = window.__I18N__;

/**
 * Populate the panel for a *circuit* (clicking a Circuits legend row / search):
 * its name (with the loop's source grade on the heading line), a sourced
 * description, the structures it loops through (deduped to bases, each clickable
 * to jump to that region) and its member pathways (the projections with both
 * endpoints in the loop, derived not stored). Mirrors the structure panel's
 * shape; the member-pathway + region rows reuse the shared pathwayRow /
 * locationList so nothing is duplicated.
 */
export function showCircuit(P, circuit) {
  const {
    appendPathwayList, appendReference, appendSourcedHeading, appendWikiImages, body,
    clearBody, data, el, foldBody, locationList,
  } = P;
  clearBody("circuit");
  body.appendChild(el("h2", "info-title", circuit.name));
  // The circuit's source grade sits on its identity line (always shown, NOSOURCE
  // when llm-only), not a "Sources" block below the member lists (which would read
  // as grading the members, not the circuit).
  appendSourcedHeading(
    t("circuit.heading"), circuit.provenance, circuit.sources, true);

  // Wikipedia illustration (hero + lazy gallery), the same hot-linked treatment a
  // brain structure gets (see appendWikiImages); no-op when unillustrated.
  appendWikiImages(circuit.structureImage, circuit.structureImageGallery,
    circuit.name, "wiki");

  // Description (baked fallback) + the Wikipedia reference below it, then the
  // live-lead refresh (upgrades to the current WP lead when reachable), via the
  // same shared appendReference every panel uses. Like a brain structure, the
  // circuit reads its text from Wikipedia; the baked copy is the offline
  // fallback and carries the loop's own citation grade until the live lead lands.
  appendReference({
    url: circuit.wikipedia, description: circuit.description,
    descriptionProvenance: circuit.provenance,
  });

  // Structures in the loop, deduped to bases (so the two hemispheres collapse
  // to one row), each rendered as a link that jumps to the region via
  // onStructurePick (locationList wires the click; the `.info-locations` class
  // gives it the clickable link styling). No per-structure source pill: a
  // structure's membership in the loop is not a separate sourced claim, it is
  // part of the circuit node itself, which is already graded on the heading
  // above (`circuit.provenance`). Each linked structure carries its own anatomy
  // grade on its own panel.
  const seen = new Set();
  const names = [];
  const bases = [];
  for (const id of circuit.structures) {
    const base = stripSide(id);
    if (seen.has(base)) continue;
    seen.add(base);
    const s = data.byId.get(id);
    names.push(s ? s.base_name : base);
    bases.push(base);
  }
  if (bases.length) {
    const where = el("div", "info-locations");
    where.dataset.tourSec = "structures"; // guided-tour section anchor
    where.appendChild(el("h3", null, t("circuit.structures")));
    where.appendChild(locationList(names, bases));
    body.appendChild(where);
  } else {
    body.appendChild(emptySection(el("h3", null, t("circuit.structures")), "circuit",
      { tourSec: "structures" }));
  }

  // Member pathways: every projection with both endpoints inside the loop (the
  // same rule the viewer uses to light a circuit's arrows), so the panel never
  // duplicates the circuit -> arrows mapping.
  const idSet = new Set(circuit.structures);
  const members = data.projections.filter(
    (p) => idSet.has(p.from) && idSet.has(p.to));
  appendPathwayList(t("circuit.pathways"), members, "circuit", "pathways");
  // Headed sections start folded, like the drug panel (see foldSections).
  foldBody();
}
