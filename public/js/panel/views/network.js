// The Network view (BETA): one large-scale network, its Wikipedia lead, the
// functional areas it spans and the modeled structures they lie in.

import { structureList } from "./area.js";

const { t } = window.__I18N__;

/**
 * Populate the panel for a network (a Networks legend row / search): its name with the
 * beta tag and the quotes' grade on the heading line, the Wikipedia lead, then its
 * member functional areas (each clickable, focusing that area) and the structures they
 * lie in (each clickable). Member structures are derived from the areas at build time.
 */
export function showNetwork(P, net) {
  const {
    appendReference, appendSourcedHeading, body, clearBody, data, el, finishBody, linkName,
    onAreaPick,
  } = P;
  clearBody("network");
  const title = el("h2", "info-title", net.name);
  title.appendChild(el("span", "beta-tag", t("sim.beta")));
  body.appendChild(title);
  appendSourcedHeading(t("network.heading"), net.provenance, net.sources, true);
  appendReference({ url: net.wikipedia, description: "", descriptionProvenance: null });

  const areaById = new Map((data.functionalAreas || []).map((a) => [a.id, a]));
  const areas = el("div", "info-locations");
  areas.dataset.tourSec = "areas";
  areas.appendChild(el("h3", null, t("network.areas")));
  const ul = el("ul");
  for (const id of net.areas) {
    const area = areaById.get(id);
    if (!area) continue;
    const li = el("li");
    li.appendChild(linkName(`${area.name} (BA ${area.number})`, () => onAreaPick(area)));
    ul.appendChild(li);
  }
  areas.appendChild(ul);
  body.appendChild(areas);

  const where = el("div", "info-locations");
  where.dataset.tourSec = "structures";
  where.appendChild(el("h3", null, t("network.structures")));
  where.appendChild(structureList(P, net.structures));
  body.appendChild(where);
  finishBody();
}
