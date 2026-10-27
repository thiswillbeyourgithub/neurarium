// The drug map's control boxes, each a rounded <details> whose summary shows its
// current value: Presets (open, one button per js/drug-map/presets.js view), Inputs (feature type + the axes picker), Filter
// points by (classes grouped into families), Color by and Advanced (the switches). Built once;
// `render()` reflects the view. In both lists a click picks, shift-click or long-press
// drops (`pickOrDrop`, `pickSet`).

import { categoryColor, COLOR_MODES, FEATURE_SOURCES, pickSet, primaryCategory, TONE_PREFIX } from "./model.js";
import { button, chipSearch, el, foldBox, pickOrDrop } from "./dom.js";
import { groupTargetsBySystem } from "../legend/targets.js";
import { matchesPreset, PRESETS, presetView } from "./presets.js";

const { t } = window.__I18N__;

/**
 * @param {{data: object, drugs: object[], nameOf: (key: string) => string,
 *   featureKeys: string[], getView: () => object, setView: (patch: object) => void}} o
 * @returns {{boxes: HTMLElement[], render: () => void}}
 */
export function createControls({ data, drugs, nameOf, featureKeys, getView, setView }) {
  const catLabels = data.meta.drugCategoryLabels || {};
  const seg = (modes, label, key, viewKey, tip) => {
    const sw = el("div", "seg-switch");
    sw.setAttribute("role", "group");
    sw.setAttribute("aria-label", label);
    for (const m of modes) {
      const b = button("seg-btn", t(`${key}.${m}`), () => setView({ [viewKey]: m }));
      b.dataset.mode = m;
      if (tip) b.title = t(`${tip}.${m}`);
      sw.appendChild(b);
    }
    return sw;
  };
  const row = (label, ...kids) => {
    const r = el("div", "dm-row");
    r.append(el("span", "dm-row-label", label), ...kids);
    return r;
  };

  // ---- Presets: a click replaces the whole view (presetView starts from the defaults).
  const presets = foldBox(t("drugmap.sec.presets"));
  presets.box.open = true;
  const presetRow = el("div", "dm-controls dm-presets");
  const presetBtns = PRESETS.map((p) => {
    const b = button("dm-chip", t(`drugmap.preset.${p.id}`), () => setView(presetView(p)));
    b.dataset.preset = p.id;
    return { p, b };
  });
  presetRow.append(...presetBtns.map((x) => x.b));
  presets.body.append(presetRow);

  // ---- Inputs: feature type, then the axes (targets grouped by transmitter system in
  // the Receptors & targets legend's order, the net-tone features as one last group).
  const inputs = foldBox(t("drugmap.sec.input"));
  const sourceSwitch = seg(FEATURE_SOURCES, t("drugmap.source"), "drugmap.source", "source", "drugmap.sourceTip");
  const families = data.meta.receptorFamilyLabels || {};
  const systemOf = new Map(), boundBy = new Map();
  for (const d of drugs) {
    for (const b of d.bindings || []) {
      if (!b.target) continue;
      systemOf.set(b.target, b.system);
      boundBy.set(b.target, (boundBy.get(b.target) || 0) + 1);
    }
  }
  const targetGroups = groupTargetsBySystem(
    [...systemOf].map(([id, system]) => ({ id, system, name: nameOf(id) })),
    (x) => boundBy.get(x.id)).map(([key, list]) => [
    key === "_other" ? t("targets.otherSystem") : families[key] || key, list.map((x) => x.id)]);
  const toneKeys = featureKeys.filter((k) => k.startsWith(TONE_PREFIX));
  const groupsFor = (source) => [
    ...(source !== "tone" ? targetGroups : []),
    ...(source !== "receptors" && toneKeys.length ? [[t("drugmap.source.tone"), toneKeys]] : []),
  ];
  const axesValue = el("span", "dm-row-value");
  const axesPanel = el("div", "dm-panel");
  axesPanel.hidden = true;
  const axesBtn = button("dm-chip dm-filter-btn", t("drugmap.filter"), () => {
    axesPanel.hidden = !axesPanel.hidden;
    if (!axesPanel.hidden) filter.box.open = false;
    render();
  });
  const axesList = el("div", "dm-tlist");
  const axesBar = el("div", "dm-tbar");
  axesBar.append(
    button("dm-chip", t("drugmap.pickAll"), () => setView({ only: null })),
    button("dm-chip", t("drugmap.pickNone"), () => setView({ only: [] })),
    el("span", "dm-hint", t("drugmap.pickTip")));
  const axesSearch = chipSearch(axesList, t("drugmap.searchTargets"));
  axesPanel.append(axesSearch.input, axesBar, axesList);
  inputs.body.append(row(t("drugmap.type"), sourceSwitch), row(t("drugmap.axes"), axesBtn, axesValue), axesPanel);

  // ---- Color by.
  const color = foldBox(t("drugmap.sec.color"));
  const colorSwitch = seg(COLOR_MODES, t("drugmap.colorBy"), "drugmap.color", "color");
  color.body.append(colorSwitch);

  // ---- Filter by: the classes, grouped into families (meta.drugCategoryGroups).
  const filter = foldBox(t("drugmap.sec.filter"));
  filter.box.addEventListener("toggle", () => {
    if (filter.box.open && !axesPanel.hidden) { axesPanel.hidden = true; render(); }
  });
  const presentCats = [...new Set([...Object.keys(catLabels), ...drugs.map(primaryCategory)])]
    .filter((c) => drugs.some((d) => primaryCategory(d) === c));
  const applyCats = (keys, mode) => {
    const view = getView();
    const cats = pickSet(view.cats && [...view.cats], keys, mode, presentCats);
    setView({ cats: cats.length && cats.length < presentCats.length ? new Set(cats) : null });
  };
  const groupOf = new Map();
  for (const [g, cats] of Object.entries(data.meta.drugCategoryGroups || {})) {
    for (const c of cats) groupOf.set(c, g);
  }
  const catGroups = new Map();
  for (const c of presentCats) {
    const g = groupOf.get(c) || "other";
    if (!catGroups.has(g)) catGroups.set(g, []);
    catGroups.get(g).push(c);
  }
  const groupLabels = data.meta.drugCategoryGroupLabels || {};
  const chipAll = button("dm-chip", t("drugmap.all"), () => setView({ cats: null }));
  // An approval-year range has no control of its own: only a decade heading's "map"
  // link sets one, shown as a removable chip.
  const yearChip = button("dm-chip active", "", () => setView({ years: null }));
  const unhide = button("dm-unhide", "", () => setView({ hidden: new Set() }));
  const filterBar = el("div", "dm-tbar");
  filterBar.append(chipAll, yearChip, unhide);
  const catList = el("div", "dm-tlist dm-cats");
  const catHeads = [], catChips = [];
  for (const [g, cats] of catGroups) {
    const box = el("div", "dm-tgroup");
    const head = button("dm-tgroup-head", groupLabels[g] || g);
    pickOrDrop(head, () => applyCats(cats, "pick"), () => applyCats(cats, "drop"));
    catHeads.push({ head, cats });
    const items = el("div", "dm-titems");
    for (const c of cats) {
      const chip = button("dm-chip");
      chip.dataset.cat = c;
      const dot = el("span", "dm-dot");
      dot.style.background = categoryColor(c, catLabels);
      chip.append(dot, document.createTextNode(catLabels[c] || c));
      pickOrDrop(chip, () => applyCats([c], "pick"), () => applyCats([c], "drop"));
      catChips.push(chip);
      items.appendChild(chip);
    }
    box.append(head, items);
    catList.appendChild(box);
  }
  const catSearch = chipSearch(catList, t("drugmap.searchClasses"));
  filter.body.append(catSearch.input, filterBar, catList);

  // ---- Advanced: the switches, all on by default.
  const advanced = foldBox(t("drugmap.sec.advanced"));
  const toggles = ["labels", "spread", "normalize", "signed", "measuredKi", "marketed"].map((key) => {
    const lab = el("label", "list-toggle");
    const input = el("input");
    input.type = "checkbox";
    input.addEventListener("change", () => setView({ [key]: input.checked }));
    lab.append(input, el("span", null, t(`drugmap.${key}`)));
    if (key !== "labels") lab.title = t(`drugmap.${key}Tip`);
    return { key, input, lab };
  });
  const advRow = el("div", "dm-controls");
  advRow.append(...toggles.map((x) => x.lab));
  advanced.body.append(advRow);

  function render() {
    const view = getView();
    for (const b of sourceSwitch.children) b.classList.toggle("active", b.dataset.mode === view.source);
    for (const b of colorSwitch.children) b.classList.toggle("active", b.dataset.mode === view.color);
    for (const x of toggles) x.input.checked = view[x.key];
    const lit = presetBtns.find(({ p }) => matchesPreset(view, p));
    for (const { b } of presetBtns) b.classList.toggle("active", b === lit?.b);
    presets.setValue(lit ? lit.b.textContent : "");

    // Axes.
    const groups = groupsFor(view.source);
    const universe = groups.flatMap(([, keys]) => keys);
    const on = (k) => !view.only || view.only.includes(k);
    const applyAxes = (keys, mode) => {
      const next = pickSet(view.only, keys, mode, universe);
      setView({ only: universe.every((k) => next.includes(k)) ? null : next });
    };
    const axis = (k) => {
      const i = view.only && view.only.length <= 2 ? view.only.indexOf(k) : -1;
      return i < 0 ? "" : `${"xy"[i]}: `;
    };
    if (!axesPanel.hidden) {
      axesList.replaceChildren(...groups.map(([label, keys]) => {
        const box = el("div", "dm-tgroup");
        const head = button("dm-tgroup-head", label);
        head.classList.toggle("active", keys.every(on));
        pickOrDrop(head, () => applyAxes(keys, "pick"), () => applyAxes(keys, "drop"));
        const items = el("div", "dm-titems");
        for (const k of keys) {
          const b = button("dm-chip", `${axis(k)}${nameOf(k)}`);
          b.classList.toggle("active", on(k));
          pickOrDrop(b, () => applyAxes([k], "pick"), () => applyAxes([k], "drop"));
          items.appendChild(b);
        }
        box.append(head, items);
        return box;
      }));
      axesSearch.apply();
    }
    axesBtn.classList.toggle("active", !axesPanel.hidden);
    const n = view.only ? view.only.filter((k) => universe.includes(k)).length : universe.length;
    axesValue.textContent = !view.only ? t("drugmap.pickSumAll", { n })
      : !n ? t("drugmap.pickSumNone")
      : view.only.length <= 2 ? view.only.map((k) => `${axis(k)}${nameOf(k)}`).join(" · ")
      : t("drugmap.pickSumSome", { k: n, n: universe.length });
    inputs.setValue(`${t(`drugmap.source.${view.source}`)} · ${axesValue.textContent}`);
    color.setValue(t(`drugmap.color.${view.color}`));

    // Filter.
    chipAll.classList.toggle("active", !view.cats);
    for (const chip of catChips) chip.classList.toggle("active", !!view.cats && view.cats.has(chip.dataset.cat));
    for (const { head, cats } of catHeads) {
      head.classList.toggle("active", !!view.cats && cats.every((c) => view.cats.has(c)));
    }
    // The chips' dots are the class colours, so they only show when points use them:
    // in another colour mode they would read as that mode's legend.
    catList.classList.toggle("dm-no-dots", view.color !== "category");
    yearChip.hidden = !view.years;
    if (view.years) {
      yearChip.textContent = t("drugmap.yearChip", {
        from: view.years[0] || "…", to: view.years[1] < 9999 ? view.years[1] : "…" });
    }
    unhide.hidden = !view.hidden.size;
    unhide.textContent = t("drugmap.unhide", { n: view.hidden.size });
    filter.setValue([
      view.cats ? t("drugmap.someClasses", { n: view.cats.size }) : t("drugmap.all"),
      view.years ? yearChip.textContent.replace(/ ×$/, "") : "",
      view.marketed ? t("drugmap.marketed") : "",
      view.hidden.size ? t("drugmap.hiddenN", { n: view.hidden.size }) : "",
    ].filter(Boolean).join(" · "));
  }

  return { boxes: [presets.box, inputs.box, filter.box, color.box, advanced.box], render };
}
