// The Drugs browse section: drug rows grouped by class or pharmacokinetics, with the
// metabolite toggle and the drug filter.

import { addLegendItem, reflectRows } from "./item.js";
import { foldText } from "../search/query.js";
import { formatHalfLife } from "../panel/format.js";
import { loadFlag, loadString, saveFlag, saveString } from "../prefs.js";

const { t } = window.__I18N__;

/**
 * The drug's representative swatch colour: the net effect (boost/block/modulate)
 * most of its bindings share, so an SSRI reads green-ish and an antagonist-heavy
 * antipsychotic rose-ish at a glance. Falls back to a neutral grey.
 * @param {object} drug
 * @param {Object<string,string>} effectColors
 * @returns {string} hex colour
 */
function drugSwatchColor(drug, effectColors) {
  const counts = {};
  for (const b of drug.bindings || []) counts[b.effect] = (counts[b.effect] || 0) + 1;
  let best = null, bestN = -1;
  for (const [e, n] of Object.entries(counts)) if (n > bestN) { best = e; bestN = n; }
  return (best && effectColors[best]) || "#9aa0a6";
}

/**
 * Build the Drugs legend section (#drugs-list) from the live dataset, grouped by
 * coarse category (in the meta category-label order, drugs sorted A->Z within
 * each). Each row is coloured by the drug's dominant net effect and clickable to
 * focus it (dim the brain to the regions it acts on + animate its targets, via
 * the caller's `onPick`); a drug with no recorded bindings renders muted + inert.
 * The #drugs-filter box narrows the visible rows live (matching name + class +
 * targets), hiding emptied category headings and showing a "no match" note.
 * Returns a `reflect(activeId)` callback that lights the active drug's row.
 * @param {import("./data.js").BrainData} data
 * @param {(drug: object) => void} onPick
 * @returns {(activeId: string|null) => void}
 */
// localStorage key for the drug panel's Interactions grouping ("drug" | "enzyme").
// A reading preference rather than a per-drug state, so it persists and applies to
// every drug panel, like the metabolites toggle below.
const PK_GROUP_KEY = "neurarium.pkGroup";

export function loadPkGrouping() {
  return loadString(PK_GROUP_KEY) === "enzyme" ? "enzyme" : "drug";
}

export function savePkGrouping(mode) {
  saveString(PK_GROUP_KEY, mode);
}

// localStorage key for the Drugs list's "show active metabolites" toggle (default
// on). Persisted so the choice survives reloads (see js/prefs.js).
const METAB_TOGGLE_KEY = "neurarium.metabolites";

export function buildDrugLegend(data, onPick) {
  const container = document.getElementById("drugs-list");
  const filterInput = document.getElementById("drugs-filter");
  const metabToggle = document.getElementById("drugs-show-metabolites");
  // Drug id -> drug. NOT data.byId, which is the *structure* index: looking a drug up
  // there always missed, so a metabolite bullet that should link to its own drug row
  // silently rendered inert.
  const drugById = new Map(data.drugs.map((d) => [d.id, d]));
  if (!container) return () => {};
  container.replaceChildren();
  const rows = [];   // { row, id } for the focusable drugs (for reflect)
  const groups = []; // { heading, rows:[row,...] } for the live filter
  // Filter state per legend row: { haystack, isMetab, ancestors } (see applyFilter).
  const rowInfo = new WeakMap();
  const effectColors = data.meta.drugEffectColors || {};
  const cats = data.meta.drugCategoryLabels || {};

  // Active metabolites as discreet indented bullets under the parent drug, each
  // showing its own T½; a metabolite that is itself a modeled drug jumps to it.
  // Toggled by #drugs-show-metabolites; marked isMetab (rowInfo) so applyFilter can gate them,
  // and given a haystack (own + parent name) so filtering behaves.
  //
  // Recursive: a metabolite that IS a modeled drug has metabolites of its own
  // (loxapine -> amoxapine -> 7-/8-hydroxyamoxapine), and flattening those onto one
  // level lost which molecule made which. `depth` drives the indent, `ancestors` is
  // the chain applyFilter must reveal when a deep bullet matches, and `seen` guards a
  // metabolic cycle in the data from spinning here forever.
  const MAX_METAB_DEPTH = 3;
  function addMetabRows(owner, ancestors, depth, seen, groupRows) {
    if (depth > MAX_METAB_DEPTH) return;
    for (const m of owner.metabolites || []) {
      const mrow = document.createElement("div");
      mrow.className = "legend-item metab-item";
      if (depth > 1) mrow.style.setProperty("--metab-depth", String(depth));
      const nameSpan = document.createElement("span");
      nameSpan.className = "metab-name";
      nameSpan.textContent = m.name;
      mrow.appendChild(nameSpan);
      const hlStr = formatHalfLife(m.halfLife);
      if (hlStr) {
        const hlSpan = document.createElement("span");
        hlSpan.className = "metab-item-hl";
        hlSpan.textContent = hlStr;
        mrow.appendChild(hlSpan);
      }
      const linked = m.drugId ? drugById.get(m.drugId) : null;
      if (linked && m.linkFocusable) {
        mrow.classList.add("clickable");
        mrow.title = t("drug.metaboliteOf", { prodrug: owner.displayName });
        mrow.addEventListener("click", () => onPick(linked));
      }
      // The whole chain up to the drug row, so a match on a grandchild pulls every
      // level above it back into view rather than orphaning the bullet.
      rowInfo.set(mrow, { haystack: foldText(`${m.name} ${owner.name}`), isMetab: true, ancestors });
      container.appendChild(mrow);
      groupRows.push(mrow);
      if (linked && !seen.has(linked.id)) {
        addMetabRows(linked, [...ancestors, mrow], depth + 1,
          new Set([...seen, linked.id]), groupRows);
      }
    }
  }

  // Group drugs by their primary (first) category.
  const byCat = new Map();
  for (const drug of data.drugs || []) {
    const cat = (drug.categories && drug.categories[0]) || "other";
    if (!byCat.has(cat)) byCat.set(cat, []);
    byCat.get(cat).push(drug);
  }
  // Category order = the meta order first, then any leftover keys.
  const order = [...Object.keys(cats),
                 ...[...byCat.keys()].filter((c) => !(c in cats))];
  const done = new Set();
  for (const cat of order) {
    if (done.has(cat)) continue;
    done.add(cat);
    const list = byCat.get(cat);
    if (!list || !list.length) continue;
    list.sort((a, b) => a.name.localeCompare(b.name));
    const h = document.createElement("h2");
    h.textContent = cats[cat] || cat;
    container.appendChild(h);
    const groupRows = [];
    for (const drug of list) {
      const row = addLegendItem(
        container, drugSwatchColor(drug, effectColors), drug.displayName, true);
      row.classList.add("drug-item");
      rowInfo.set(row, { haystack: foldText(`${drug.name} ${drug.keywords}`), isMetab: false, ancestors: [] });
      row.dataset.tourId = `drug:${drug.id}`; // guided-tour target hook
      // Every drug opens its panel, even one with nothing to light (see js/data.js).
      row.classList.add("clickable");
      row.title = drug.categoryLabels.join(" · ");
      row.addEventListener("click", () => onPick(drug));
      rows.push({ row, id: drug.id });
      groupRows.push(row);
      addMetabRows(drug, [row], 1, new Set([drug.id]), groupRows);
    }
    groups.push({ heading: h, rows: groupRows });
  }

  // "No match" note for the filter (hidden unless every row is filtered out).
  const empty = document.createElement("p");
  empty.className = "drugs-empty info-desc";
  empty.textContent = t("drugs.none");
  empty.hidden = true;
  container.appendChild(empty);

  const applyFilter = () => {
    const q = foldText((filterInput?.value || "").trim());
    const showMetab = metabToggle ? metabToggle.checked : true;
    let anyVisible = false;
    for (const g of groups) {
      for (const row of g.rows) {
        // A metabolite bullet is visible only when the toggle is on AND it matches.
        const info = rowInfo.get(row);
        const match = (!q || info.haystack.includes(q)) &&
          (!info.isMetab || showMetab);
        row.hidden = !match;
      }
      // A matched metabolite pulls its whole chain back into view even when no name
      // above it matches (searching "norf" shows fluoxetine so the Norfluoxetine
      // bullet is never orphaned; "hydroxyamoxapine" shows loxapine AND the amoxapine
      // bullet between them, so the two-step route stays readable).
      for (const row of g.rows) {
        const info = rowInfo.get(row);
        if (info.isMetab && !row.hidden) {
          for (const up of info.ancestors) up.hidden = false;
        }
      }
      const groupVisible = g.rows.some((row) => !row.hidden);
      g.heading.hidden = !groupVisible;
      if (groupVisible) anyVisible = true;
    }
    empty.hidden = anyVisible;
  };
  if (filterInput) {
    filterInput.value = "";
    filterInput.addEventListener("input", applyFilter);
  }
  if (metabToggle) {
    metabToggle.checked = loadFlag(METAB_TOGGLE_KEY);
    metabToggle.addEventListener("change", () => {
      saveFlag(METAB_TOGGLE_KEY, metabToggle.checked);
      applyFilter();
    });
  }
  applyFilter(); // apply the persisted toggle state on first build

  return reflectRows(rows);
}
