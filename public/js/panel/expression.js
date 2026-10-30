// Expression rows: where a receptor or target is found (one graded row per region,
// grouped by legend group), and the targets expressed in a structure.

import { groupTargetsBySystem } from "../legend/targets.js";
import { emptySection, heading } from "./dom.js";

const { t } = window.__I18N__;

export function makeExpression(P) {
  const {
    baseResolves, body, data, el, groupOfBase, locationPill, nodePill, onStructurePick,
    onTargetPick, speciesLabel,
  } = P;

  // One "Regional distribution" region row: the name (clickable -> jump when the base resolves)
  // plus, when `meta` is given, its own per-region provenance pill (since "found in
  // region B" is graded per region, separate from the mechanism/type pill above).
  const locationRow = (name, base, meta, density) => {
    const li = el("li");
    li.appendChild(el("span", "loc-name", name));
    // A non-human expression claim (the source was checked in rat/mouse/monkey,
    // not human) is flagged with a small amber tag, the same convention as the Ki
    // chip; a human (or unsourced) row shows none. The full assay species is also
    // in the provenance pill's tooltip below.
    if (meta && meta.nonHuman) {
      const tag = el("span", "loc-species",
        t("receptor.speciesTag", { species: speciesLabel(meta.species) }));
      tag.title = t("receptor.speciesTip", { species: speciesLabel(meta.species) });
      li.appendChild(tag);
    }
    if (base && baseResolves(base)) {
      li.classList.add("clickable");
      li.addEventListener("click", () => onStructurePick(base));
    }
    if (meta) li.appendChild(locationPill(meta));
    // How much sits here, when the owner carries a measured profile: a bar scaled
    // against its own strongest region (see densityEntry) plus the signed z, since a
    // bar alone would read as an absolute quantity it is not. Last in the row so the
    // bars line up in a column at the panel edge and the pill keeps its spot by the name.
    // Ternary, not `density && ...`: that yields null (not undefined) for an owner with
    // no profile, which the `!== undefined` guard would wave through into z.toFixed().
    const z = density ? density.profile[base] : undefined;
    if (z !== undefined) {
      const signed = `${z > 0 ? "+" : ""}${z.toFixed(2)}`;
      const wrap = el("span", "loc-density");
      wrap.title = t("receptor.densityValueTip", { z: signed });
      const bar = el("span", "loc-density-bar");
      bar.style.setProperty("--fill", `${Math.round(density.rel[base] * 100)}%`);
      wrap.appendChild(bar);
      wrap.appendChild(el("span", "loc-density-z", signed));
      li.appendChild(wrap);
    }
    return li;
  };

  // The "Regional distribution" region list shared by showReceptor / showTarget: parallel arrays
  // of display names + their base ids (+ optional per-region provenance `info`).
  // Rows are grouped under anatomical-group headings in the SAME order as the
  // Structures legend (data.meta.groupLabels key order), so the list reads like that
  // panel and the extra vertical spacing keeps the provenance pills from crowding.
  // Bases that don't resolve to a group fall into a trailing "other" bucket (with a
  // heading only when there are also real groups; an all-unresolved list stays flat).
  const locationList = (names, bases, info, density) => {
    const buckets = new Map(); // group key (or null) -> [{name, base, meta}]
    names.forEach((name, i) => {
      const base = bases && bases[i];
      const g = base ? groupOfBase(base) : null;
      if (!buckets.has(g)) buckets.set(g, []);
      buckets.get(g).push({ name, base, meta: info && info[i] });
    });
    const order = [...Object.keys(data.meta.groupLabels), null]
      .filter((g) => buckets.has(g));
    const container = el("div", "loc-groups");
    // The profile is ONE claim over the whole list, so its caption + grade pill sit
    // above the rows rather than repeating on each: what varies per row is the value,
    // what is graded once is the measurement. The caption also carries how well the
    // donors agreed, so a reader can weigh the bars instead of trusting them blind.
    if (density) {
      const cap = el("p", "loc-density-caption", t("receptor.density"));
      cap.title = t("receptor.densityTip");
      const r = `${density.reliability > 0 ? "+" : ""}${density.reliability.toFixed(2)}`;
      const agree = el("span", "loc-density-agree",
        t("receptor.densityAgreement", { r }));
      agree.title = t("receptor.densityAgreementTip", {
        donors: density.donors,
        min: (data.meta.densityMinReliability ?? 0).toFixed(2),
      });
      cap.appendChild(agree);
      cap.appendChild(nodePill(density));
      container.appendChild(cap);
    }
    for (const g of order) {
      if (g !== null) {
        container.appendChild(el("h4", "loc-group-label", data.meta.groupLabels[g]));
      } else if (order.length > 1) {
        container.appendChild(el("h4", "loc-group-label", t("receptor.foundOther")));
      }
      const ul = el("ul");
      for (const { name, base, meta } of buckets.get(g)) {
        ul.appendChild(locationRow(name, base, meta, density));
      }
      container.appendChild(ul);
    }
    return container;
  };

  // "Receptor expression": the reverse of a receptor's "Regional distribution" list, read off
  // data.targetsByStructure. The expression claim belongs to the (target, region)
  // pair, so each row carries THAT region's own graded node, the same pill (and the
  // same amber non-human species tag) the receptor panel shows for this structure:
  // one node, two ends, never two gradings. Grouped by neurotransmitter system in the
  // Receptors & targets section's own order, biggest system in THIS region first.
  // Capped per system, since a cortical lobe carries a hundred of them and a global
  // cap would swallow whole systems (same reasoning as the drug-interactions groups).
  const EXPRESSED_CAP = 8;

  const appendExpressedTargets = (base) => {
    const entries = (data.targetsByStructure || new Map()).get(base) || [];
    if (!entries.length) {
      body.appendChild(emptySection(heading("h3", t("structure.expressed"),
        t("structure.expressedSub")), "structure", { tourSec: "expressed" }));
      return;
    }
    // One row per target: a target cannot be expressed twice in one region, but the
    // index is built per (target, region) so guard anyway rather than double-list.
    const byId = new Map(entries.map((e) => [e.target.id, e]));
    const families = data.meta.receptorFamilyLabels || {};
    const wrap = el("div", "info-bindings info-interactors");
    wrap.dataset.tourSec = "expressed"; // guided-tour section anchor
    wrap.appendChild(heading("h3", `${t("structure.expressed")} (${byId.size})`,
      t("structure.expressedSub")));
    wrap.appendChild(el("p", "info-caption", t("structure.expressedCaption")));
    const groups = groupTargetsBySystem([...byId.values()].map((e) => e.target),
      () => 1);
    for (const [key, list] of groups) {
      wrap.appendChild(el("div", "drug-cat",
        key === "_other" ? t("targets.otherSystem") : (families[key] || key)));
      const ul = el("ul", "pk-group-body");
      const rowOf = (tgt) => {
        const entry = byId.get(tgt.id);
        const meta = entry.info;
        const li = el("li");
        const dot = el("span", "swatch");
        dot.style.background = tgt.swatchColor;
        li.appendChild(dot);
        li.appendChild(el("span", "bind-target", tgt.name));
        if (tgt.kind !== "receptor" && tgt.typeLabel) {
          li.appendChild(el("span", "legend-tag", tgt.typeLabel));
        }
        // "everywhere": this one is a ubiquitous receptor, listed here because it is
        // listed everywhere, which is a weaker statement than a named region.
        if (entry.ubiquitous) {
          li.appendChild(el("span", "legend-tag", t("structure.expressedEverywhere")));
        }
        if (meta && meta.nonHuman) {
          const tag = el("span", "loc-species",
            t("receptor.speciesTag", { species: speciesLabel(meta.species) }));
          tag.title = t("receptor.speciesTip", { species: speciesLabel(meta.species) });
          li.appendChild(tag);
        }
        if (meta) li.appendChild(locationPill(meta));
        if (tgt.focusable) {
          li.classList.add("clickable");
          li.addEventListener("click", () => onTargetPick(tgt));
        }
        return li;
      };
      for (const tgt of list.slice(0, EXPRESSED_CAP)) ul.appendChild(rowOf(tgt));
      wrap.appendChild(ul);
      const rest = list.slice(EXPRESSED_CAP);
      if (rest.length) {
        const more = el("button", "pk-more", t("info.more", { n: rest.length }));
        more.addEventListener("click", () => {
          for (const tgt of rest) ul.appendChild(rowOf(tgt));
          more.remove();
        });
        wrap.appendChild(more);
      }
    }
    body.appendChild(wrap);
  };

  /**
   * The "Regional distribution" section a receptor and a target panel share: a heading, then the
   * graded region list, or the "no regional role" note when there is none. Only a
   * receptor can be `ubiquitous` (expressed everywhere, one sourced sentence instead
   * of a list). `P.sourcesTip` / `P.makeProvenancePill` are read at call time: the
   * pills factory is assembled onto P after this one.
   * @param {{locationNames: string[], ubiquitous?: boolean, ubiquitousInfo?: object,
   *   locationInfo: object, densityInfo: object}} owner
   * @param {string[]} bases the side-stripped base id of each location name
   * @param {?string} [tourSec] guided-tour section anchor (`data-tour-sec`)
   */
  const appendFoundIn = (owner, bases, tourSec = null) => {
    const head = heading("h3", t("receptor.foundIn"), t("receptor.foundInSub"));
    // No region and not ubiquitous: a stub with no CNS role, said in its own words.
    if (!owner.ubiquitous && !owner.locationNames.length) {
      body.appendChild(emptySection(head, owner.kind === "receptor" ? "receptor" : "target",
        { tourSec, icon: "regions", cls: "info-locations", text: t("receptor.noRole") }));
      return;
    }
    const where = el("div", "info-locations");
    where.dataset.icon = "regions";
    if (tourSec) where.dataset.tourSec = tourSec;
    where.appendChild(head);
    if (owner.ubiquitous) {
      const p = el("p", "info-desc info-desc-pilled", t("receptor.ubiquitous"));
      const u = owner.ubiquitousInfo;
      if (u) {
        const tip = u.sources && u.sources.length
          ? P.sourcesTip(u.sources) : t("receptor.locUnsourced");
        p.appendChild(P.makeProvenancePill(u.provenance, tip));
      }
      where.appendChild(p);
    } else {
      where.appendChild(locationList(owner.locationNames, bases,
        owner.locationInfo, owner.densityInfo));
    }
    body.appendChild(where);
  };

  return {
    appendExpressedTargets, appendFoundIn, EXPRESSED_CAP, locationList, locationRow,
  };
}
