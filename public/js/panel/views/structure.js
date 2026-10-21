// The Structure view: one brain region, its pathways in and out, what is expressed
// there, and its reference material.

import { stripSide } from "../../util.js";
import { heading } from "../dom.js";

const { t } = window.__I18N__;


/**
 * Populate the panel for a *structure* (clicking a region, a double-click,
 * or a structure search result): its name, group, and the list of pathways
 * touching it. Each connection row is clickable and routes through
 * onConnectionPick so the caller can frame it + open the connection panel.
 */
export function showStructure(P, structure) {
  const {
    appendAddons, appendExpressedTargets, appendReference, appendSourcedHeading,
    appendWikiImages, baseNameOf, body, clearBody, data, el, foldBody, pathwayList,
  } = P;
  clearBody("structure");
  body.appendChild(el("h2", "info-title", structure.name));
  // The anatomy classification grade (existence / group / position) rides the
  // group line it actually grades, not a broad "Source" row at the bottom (a
  // source always sits on the specific node it backs). Omitted when the anatomy
  // grade is absent (structures are the only node kind that may be ungraded).
  appendSourcedHeading(
    data.meta.groupLabels[structure.group] || structure.group,
    structure.classification_provenance, structure.sources);
  // Addon slot: a caveat about this region as a whole (see appendAddons). A
  // structure addon anchors the hemisphere-less BASE, so it shows on both sides.
  appendAddons(body, "structure", stripSide(structure.id), "structure.top");

  // Wikipedia illustration (the lead rotating-brain GIF, else an SVG diagram or
  // an infobox image) + its lazy "show more" gallery, via the shared helper (see
  // appendWikiImages): hot-linked, spinner while loading, silent hide on failure.
  appendWikiImages(structure.structureImage, structure.structureImageGallery,
    structure.name, "wiki");

  // External reference (Wikipedia) + its live lead summary, via the shared
  // appendReference (structures carry no baked description, so the live lead,
  // when it arrives, appears above the link).
  appendReference({ url: structure.wikipedia });

  // Pathways with this structure at either end, in the data's order, with
  // left/right twins collapsed (via pathwayList): a midline source (e.g. the
  // raphe) projects to both hemispheres of each target, which would otherwise
  // list as two rows differing only by "Left"/"Right". Each row shows just the
  // other endpoint's hemisphere-stripped base name, direction relative to this
  // structure (out it projects, in it receives, both reciprocal/commissural).
  const conns = data.projections.filter(
    (p) => p.from === structure.id || p.to === structure.id);
  if (conns.length === 0) {
    body.appendChild(el("p", "info-desc", t("info.noConnections")));
  } else {
    const { ul, count } = pathwayList(conns, (proj) => {
      const outgoing = proj.from === structure.id;
      const otherId = outgoing ? proj.to : proj.from;
      return {
        dir: proj.bidirectional ? "both" : outgoing ? "out" : "in",
        label: baseNameOf(otherId),
      };
    });
    const wrap = el("div", "info-connections");
    wrap.appendChild(heading("h3", `${t("info.connections")} (${count})`,
      t("info.connectionsSub")));
    wrap.appendChild(ul);
    body.appendChild(wrap);
  }

  // What is expressed here: the receptors + non-receptor targets whose "Regional distribution"
  // list names this region. A structure with no pathway can still carry plenty of
  // them, so this section is outside the branch above.
  appendExpressedTargets(stripSide(structure.id));
  // Headed sections start folded, like the drug panel (see foldSections).
  foldBody();
}
