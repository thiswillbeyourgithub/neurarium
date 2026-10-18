// The search box's index: one row per searchable thing (structures, connections,
// receptors / targets, drugs + their metabolites, enzymes, effects, circuits,
// projection groups, and the panel's own `data-search` controls), each carrying the
// action to run when picked. The popup UI that filters and ranks it is
// js/boot/toolbar.js.

import { controlName, foldText } from "./query.js";
import { flashRow } from "../panel/dom.js";
import { stripSide } from "../util.js";

const { t } = window.__I18N__;

/**
 * Hemisphere tag for a connection, derived from its endpoint ids, so the two
 * mirrored copies of a pathway (and the cross-midline commissures) are
 * distinguishable in the search list (which matches on the bare label).
 * @param {object} proj
 * @returns {string} "R", "L", "L↔R", or "" (purely midline).
 */
function connectionSideTag(proj) {
  const right = proj.from.endsWith("_R") || proj.to.endsWith("_R");
  const left = proj.from.endsWith("_L") || proj.to.endsWith("_L");
  if (left && right) return "L↔R";
  if (right) return "R";
  if (left) return "L";
  return "";
}

/**
 * Build the search rows. Called once by wireToolbar (the item set is static).
 * @returns {Array<{type:string, label:string, names?:string[], keywords?:string,
 *   fields?:object, select:Function, preview?:Function}>}
 */
export function buildSearchItems({ meshes, arrows, data, tabs, selectStructure, selectConnection, focusTarget, focusDrug, focusEnzyme, focusEffect, focusCircuit, focusProjectionGroup }) {
  // One searchable index over structures + connections + receptors, each carrying
  // the action to run when it is picked. Built once. Mirrored L/R twins are
  // collapsed to a single row (a brain is symmetric, so "frontal lobe" and
  // "corticothalamic" each list once and a pick focuses *both* hemispheres, not one);
  // receptors show their neurotransmitter as a tag (and carry extra `keywords` so the
  // system / mechanism also match). The match runs over `label` + `keywords`; only
  // `label` is shown.
  // Group meshes / arrows by their side-stripped base so each pair yields one row.
  const meshesByBase = new Map();
  for (const mesh of meshes) {
    const base = stripSide(mesh.userData.structure.id);
    (meshesByBase.get(base) || meshesByBase.set(base, []).get(base)).push(mesh);
  }
  const arrowsByBase = new Map();
  for (const arrow of arrows) {
    const p = arrow.projection;
    const key = `${stripSide(p.from)}->${stripSide(p.to)}`;
    (arrowsByBase.get(key) || arrowsByBase.set(key, []).get(key)).push(arrow);
  }
  // Everything the panel can DO, listed beside everything it can show: the popups
  // (About, the Legend, Sources & provenance, the keyboard shortcuts, What's new),
  // the Data browser and the other browse sections, the view toggles and options, and
  // the guided tour. A control joins this index by carrying `data-search` in the
  // markup and is named by its own visible label, so a new option is findable the day
  // it lands and can never drift from what the panel calls it: search owns no second
  // copy of what a control is or does, and a pick just clicks it. The search box
  // itself deliberately carries no mark, since a result that opens the search you are
  // already inside is a loop rather than a result.
  const commandRows = [...document.querySelectorAll("[data-search]")].map((elm) => {
    const box = elm.type === "checkbox" ? elm : null;
    // A checkbox is named by the <label> wrapping it; everything else by itself. Both
    // go through controlName, the one definition of what a control is called.
    const labelEl = box ? box.closest("label") : null;
    return {
      type: "command",
      // Derived on read, never stored alongside the control it describes: an option
      // has to say what it is set to *now*, and the theme + panel-only buttons rename
      // themselves on each click (they name the state a click would give you, not the
      // one showing). A getter is live by construction, so no render path can read a
      // stale one.
      get label() {
        const name = controlName(labelEl || elm);
        return box ? `${name} · ${t(box.checked ? "search.on" : "search.off")}` : name;
      },
      // The attribute's value, when it has one, is a list of aliases: the words a
      // visitor is likely to type for a control whose visible name does not contain
      // them ("tour" for Start the tutorial, "citations" for Sources & provenance).
      // Never a second name, always extra ways in to the one the panel shows. Spelled
      // once each: the matcher folds accents on both sides (see foldText), so the
      // unaccented twin of an accented alias would be dead weight.
      keywords: elm.dataset.search || "",
      // Picked is done: this clicks the real control, so its handler stays the one
      // definition of what it means. An option additionally flashes itself, since
      // what it changed may be nowhere near the panel; a button opens something
      // visible and needs no pointing at. flashRow defers a frame, which lands after
      // the pick has closed the search box and put the controls back on screen.
      //
      // An option inside a collapsed accordion body (Show active metabolites lives in
      // the Drugs section) has to have that section opened first, or the pick flips a
      // persisted preference with nothing at all to show for it: scrollIntoView and
      // the flash are both no-ops on a `hidden` subtree. Opening is the section's own
      // header click, for the same reason the pick itself is the control's own.
      select: () => {
        if (box) {
          tabs.showSettings(); // the flashed option lives in the Settings pane
          const head = elm.closest("[hidden]")?.previousElementSibling;
          if (head?.classList.contains("collapse-header")) head.click();
        }
        elm.click();
        if (box) flashRow(labelEl || box);
      },
    };
  });

  const items = [
    ...[...meshesByBase.values()].map((group) => {
      // Frame a representative (prefer the midline / right member); the isolate
      // already spans both sides via isolateGroupFor, so both hemispheres dim in.
      const rep = group.find((m) => !/_[LR]$/.test(m.userData.structure.id)) || group[0];
      const s = rep.userData.structure;
      return {
        type: "structure",
        // base_name is the hemisphere-stripped name ("frontal lobe"); fall back to
        // the full name for a genuine singleton.
        label: s.base_name || s.name,
        names: [s.base_name || s.name],
        keywords: (s.aliases || []).join(" "),
        select: () => selectStructure(rep, { frame: true, isolate: true }),
        preview: () => selectStructure(rep, { isolate: true, preview: true }),
      };
    }),
    ...[...arrowsByBase.values()].map((group) => {
      const rep = group[0];
      const proj = rep.projection;
      const siblings = group.slice(1);
      // A clean L/R pair needs no side tag; a lone / crossing pathway keeps its tag.
      const tag = siblings.length ? "" : connectionSideTag(proj);
      return {
        type: "connection",
        label: proj.label + (tag ? ` · ${tag}` : ""),
        names: [proj.label],
        // Frame + isolate both twins, so a connection search pick dims the rest of the
        // brain and lights both hemispheres, not just the picked side.
        select: () => selectConnection(rep, { frame: true, isolate: true, siblings }),
        preview: () => selectConnection(rep, { isolate: true, preview: true, siblings }),
      };
    }),
    // Focusable receptors + non-receptor targets (a stub / unlocated target has no
    // anatomy to show, so it stays a legend-only listing). A receptor shows its
    // neurotransmitter as the tag, a target its type; keywords carry the system /
    // mechanism so they match too without cluttering the row.
    ...(data.targets || []).filter((tgt) => tgt.focusable).map((tgt) => {
      const tag = tgt.kind === "receptor"
        ? (tgt.receptor && tgt.receptor.neurotransmitter)
        : tgt.typeLabel;
      return {
        type: "target",
        label: tgt.name + (tag ? ` · ${tag}` : ""),
        names: [tgt.name],
        keywords: tgt.keywords || "",
        select: () => focusTarget(tgt, { frame: true }),
        preview: () => focusTarget(tgt, { preview: true }),
      };
    }),
    // Focusable drugs (those with a binding profile). The row shows the primary
    // class as a tag; keywords carry the full class list + nomenclature + targets.
    // `fields` feeds the structured `class:"..."` / `nbn:"..."` filters (the panel's
    // clickable Class / Nomenclature values), pre-folded for matching.
    ...(data.drugs || []).filter((d) => d.focusable).map((drug) => ({
      type: "drug",
      label: drug.displayName + (drug.category ? ` · ${drug.category}` : ""),
      names: [drug.name, ...drug.categoryLabels],
      keywords: drug.keywords || "",
      fields: {
        class: foldText(drug.categoryLabels.join(" ")),
        nbn: foldText(drug.nbn || ""),
      },
      select: () => focusDrug(drug, { frame: true }),
      preview: () => focusDrug(drug, { preview: true }),
    })),
    // Active metabolites that are not themselves a focusable drug (a metabolite that
    // IS a modeled drug is already searchable as its own drug row, so it is skipped
    // here to avoid a duplicate). A pick focuses the parent drug, whose panel lists
    // the metabolite under "Active metabolites"; the label carries the "metab. of X"
    // tag and keywords match on both the metabolite and the parent name. A metabolite
    // produced by several parents (e.g. mCPP) collapses to ONE entry keyed by its
    // metabolite id, listing every parent, so search never shows the same molecule twice.
    ...(() => {
      const byKey = new Map();
      for (const drug of (data.drugs || []).filter((d) => d.focusable)) {
        for (const m of (drug.metabolites || []).filter((x) => !x.linkFocusable)) {
          const key = m.id;
          const existing = byKey.get(key);
          if (existing) {
            if (!existing.prodrugs.includes(drug.displayName)) existing.prodrugs.push(drug.displayName);
            existing.keywords += ` ${drug.name} ${drug.displayName} ${drug.keywords || ""}`;
            continue;
          }
          // The first parent seen owns the focus target; every parent's panel lists this
          // metabolite identically, so which one we open does not matter.
          byKey.set(key, {
            name: m.name,
            drug,
            prodrugs: [drug.displayName],
            keywords: `${drug.name} ${drug.displayName} ${drug.keywords || ""}`,
          });
        }
      }
      // A metabolite has no panel of its own, so the pick opens its parent drug and
      // hands over the name it was searched under: the parent's panel then scrolls to
      // that metabolite's row and flashes it. Without it, searching 6-Monoacetylmorphine
      // simply opened a Heroin tab, with nothing on screen tying the two together.
      return [...byKey.values()].map((e) => ({
        type: "drug",
        label: `${e.name} · ${t("drug.metaboliteOf", { prodrug: e.prodrugs.join(", ") })}`,
        names: [e.name],
        keywords: e.keywords,
        select: () => focusDrug(e.drug, { frame: true, highlightMetabolite: e.name }),
        preview: () => focusDrug(e.drug, { preview: true }),
      }));
    })(),
    // Drug-metabolising enzymes (the Enzymes section). Pharmacokinetics, so a pick
    // changes nothing in the 3D scene; it opens the isoform's panel exactly like its
    // legend row, which is the whole point: an enzyme is a graded node with drugs on
    // both sides of it, and it was reachable only by scrolling its section.
    ...(data.enzymes || []).map((enz) => ({
      type: "enzyme",
      label: `${enz.label} · ${t("search.tagEnzyme")}`,
      names: [enz.label],
      keywords: enz.keywords || "",
      select: () => focusEnzyme(enz),
      // No preview: an enzyme focus is a panel, not a scene state, so there is
      // nothing for a hover to show and nothing for it to restore.
    })),
    // Clinical effects (the Effects section, BETA): a pick opens the effect's panel,
    // like its legend row; no scene state, so no preview (as for an enzyme).
    ...(data.effects || []).map((effect) => ({
      type: "effect",
      label: `${effect.label} · ${t("search.tagEffect")}`,
      names: [effect.label],
      keywords: effect.keywords || "",
      select: () => focusEffect(effect),
    })),
    // Named circuits (the loops in the Projections section): a pick isolates the
    // loop, plays its traveling pulse and opens its panel, exactly like its legend
    // row, so search reaches them too (part of "anything from search == the panel").
    ...(data.circuits || []).map((circuit) => ({
      type: "circuit",
      label: `${circuit.name} · ${t("search.tagCircuit")}`,
      names: [circuit.name],
      keywords: circuit.description || "",
      select: () => focusCircuit(circuit, { frame: true }),
      preview: () => focusCircuit(circuit, { preview: true }),
    })),
    // Projection groups (the per-transmitter / per-sign rows of the Projections
    // legend): a pick pins that whole pathway group + dims the rest + opens its
    // panel, like its legend row. Both colour modes' records are listed; their
    // names don't collide (transmitters vs excitatory/inhibitory/modulatory).
    ...(data.projectionGroups || []).map((group) => ({
      type: "group",
      label: `${group.name} · ${t("search.tagPathways")}`,
      names: [group.name],
      keywords: group.description || "",
      select: () => focusProjectionGroup(group, { frame: true }),
      preview: () => focusProjectionGroup(group, { preview: true }),
    })),
    ...commandRows,
  ];
  return items;
}
