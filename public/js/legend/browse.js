// The Enzymes and Effects browse sections: panel-only lists (no 3D state), each a
// buildBrowseList over its dataset slice.

import { buildBrowseList } from "./item.js";
import { buildEffectSiteSwitch, loadEffectSite, siteShown } from "../effect-site.js";

const { t } = window.__I18N__;

/**
 * Build the Enzymes section (#enzymes-body): one row per metabolic isoform some
 * drug actually touches, natural-sorted (CYP1A2 ... CYP3A5), each showing how many
 * drugs sit on it and clickable to open its panel.
 *
 * The metabolism mirror of buildTargetLegend, minus everything 3D: an enzyme has no
 * anatomy, so a row never dims the brain or scatters dots, and the section caption
 * says so rather than leaving a user waiting for the scene to react.
 * @param {import("./data.js").BrainData} data
 * @param {(enzyme: object) => void} onPick
 * @returns {(activeId: string|null) => void} reflect: lights the active row
 */
export function buildEnzymeLegend(data, onPick) {
  return buildBrowseList({ section: "enzymes", captionKey: "enzymes.hint", kind: "enzyme",
    items: data.enzymes || [], count: (enz) => enz.rows.length, onPick });
}

/**
 * Build the Effects section (#effects-body, BETA): one row per clinical effect some
 * receptor / target carries a sourced receptor_effect node for, A->Z, its tag the
 * number of drugs that could reach it. Like the Enzymes section it lights nothing in
 * the scene (the caption says so): a pick opens the effect's panel.
 * @param {import("./data.js").BrainData} data
 * @param {(effect: object) => void} onPick
 * @returns {(activeId: string|null) => void} reflect: lights the active row
 */
export function buildEffectLegend(data, onPick) {
  // No effect index (derived/effects.json failed to load, already said by a red
  // banner): hide the whole section rather than show an empty, clickable header.
  const section = document.getElementById("effects");
  if (section) section.hidden = !(data.effects || []).length;
  const items = data.effects || [];
  const reflect = buildBrowseList({ section: "effects", captionKey: "effects.legendHint", kind: "effect",
    items, count: (effect) => effect.drugs.length, tagTitle: t("effects.legendTag"), onPick });
  // The central / peripheral switch (js/effect-site.js) hides rows in place, after the caption.
  const body = document.getElementById("effects-body");
  if (body && items.length) {
    const siteById = new Map(items.map((e) => [e.id, e.site]));
    const apply = (mode) => {
      for (const row of body.querySelectorAll('[data-tour-id^="effect:"]')) {
        row.hidden = !siteShown(siteById.get(row.dataset.tourId.slice("effect:".length)), mode);
      }
    };
    body.firstElementChild.after(buildEffectSiteSwitch(apply).el);
    apply(loadEffectSite());
  }
  return reflect;
}

/**
 * Build the Functional areas section (#areas-body, BETA): one row per Brodmann area in
 * Wikipedia's order, tagged with its number. An area without its own drawn shape yet
 * lights the whole lobe it lies in, so its row is greyed (`coarse`) with a tooltip.
 * @param {import("./data.js").BrainData} data
 * @param {(area: object) => void} onPick
 * @returns {(activeId: string|null) => void} reflect: lights the active row
 */
export function buildAreaLegend(data, onPick) {
  const areas = data.functionalAreas || [];
  const reflect = buildBrowseList({ section: "areas", captionKey: "areas.legendHint",
    kind: "area", items: areas.map((a) => ({ ...a, label: a.name })),
    count: (a) => a.number, tagTitle: t("areas.legendTag"),
    onPick: (item) => onPick(areas.find((a) => a.id === item.id)) });
  for (const a of areas) {
    const row = document.querySelector(`#areas-body [data-tour-id="area:${a.id}"]`);
    if (row && !a.own_shape) {
      row.classList.add("coarse");
      row.title = t("areas.coarseTip");
    }
  }
  return reflect;
}
