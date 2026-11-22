// The Functional area view (BETA): one Brodmann area, its Wikipedia picture and lead,
// and the modeled structures it lies in.

import { stripSide } from "../../util.js";

const { t } = window.__I18N__;

/**
 * Populate the panel for a functional area (a Functional areas legend row / search):
 * its name with the beta tag and the book quote's grade on the heading line, the
 * Wikipedia illustration + lead (the same appendWikiImages / appendReference a circuit
 * uses), then the structures it lies in, each clickable. Until the area has its own
 * drawn shape (`own_shape`) a note says the whole lobe is lit instead.
 */
export function showArea(P, area) {
  const {
    appendReference, appendSourcedHeading, appendWikiImages, body, clearBody, data, el,
    finishBody, locationList,
  } = P;
  clearBody("area");
  const title = el("h2", "info-title", area.name);
  title.appendChild(el("span", "beta-tag", t("sim.beta")));
  body.appendChild(title);
  appendSourcedHeading(t("area.heading", { n: area.number }), area.provenance,
    area.sources, true);
  appendWikiImages(area.structureImage, area.structureImageGallery, area.name, "wiki");
  appendReference({ url: area.wikipedia, description: "", descriptionProvenance: null });

  const seen = new Set();
  const names = [];
  const bases = [];
  for (const id of area.structures) {
    const base = stripSide(id);
    if (seen.has(base)) continue;
    seen.add(base);
    const s = data.byId.get(id);
    names.push(s ? s.base_name : base);
    bases.push(base);
  }
  const where = el("div", "info-locations");
  where.dataset.tourSec = "structures";
  where.appendChild(el("h3", null, t("area.structures")));
  if (!area.own_shape) where.appendChild(el("p", "area-coarse", t("area.coarse")));
  where.appendChild(locationList(names, bases));
  body.appendChild(where);
  finishBody();
}
