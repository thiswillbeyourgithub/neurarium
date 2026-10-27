// The drug map popup (#drugmap-modal): every drug placed by 2-component PCA of its
// feature vector (js/drug-map/model.js: receptor affinities, net transmitter tone, or
// both), recomputed for whatever the filters leave on screen; pick one or two features
// and they are plotted directly instead. Controls: feature source, colour mode, names
// on/off, normalization, signed (agonist vs antagonist), year range, feature picker,
// per-category chips, and right-click (long-press) to hide a drug. Clicking a point
// opens that drug in a new browser tab. The whole view is mirrored into the URL
// (`dm*` keys).

import {
  buildProfiles, categoryColor, colorize, COLOR_MODES, DEFAULT_VIEW, directPoints,
  FEATURE_SOURCES, filterDrugs, pca, primaryCategory, TONE_PREFIX,
} from "./model.js";
import { setDrugMapOpener } from "./link.js";
import { LIST_SEP } from "../url-state.js";

const { t } = window.__I18N__;
const SVG = "http://www.w3.org/2000/svg";
const W = 1000, H = 640, PAD = 30;
// Room on the right for the names of the rightmost points.
const PAD_RIGHT = 130;
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const svgEl = (tag, attrs) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  return e;
};

/**
 * @param {{data: object, wireModal: Function, onChange: () => void}} o
 *   onChange runs after any view change (URL sync)
 * @returns {{open: (patch?: object) => void, close: () => void, isOpen: boolean,
 *   registerUrl: (urlState: object) => void}}
 */
export function createDrugMap({ data, wireModal, onChange }) {
  const body = document.getElementById("drugmap-body");
  const drugs = data.drugs || [];
  const catLabels = data.meta.drugCategoryLabels || {};
  // Every feature key -> its display name: targets, then `tone:<kind>` systems.
  const featureName = new Map();
  for (const d of drugs) for (const b of d.bindings || []) featureName.set(b.target, b.targetName || b.target);
  for (const d of drugs) {
    for (const kind of Object.keys(d.flowSystems || {})) {
      featureName.set(TONE_PREFIX + kind, t("drugmap.toneOf", { kind: (data.meta.kindLabels || {})[kind] || kind }));
    }
  }
  const nameOf = (key) => featureName.get(key) || key;
  let view = { ...DEFAULT_VIEW, hidden: new Set() };
  let box = null; // the SVG viewBox once zoomed / panned, null = fit
  const ctrl = wireModal({
    modalId: "drugmap-modal", toggleId: "drugs-map", closeId: "drugmap-close",
    onOpen: () => render(),
  });
  if (!body) return { ...ctrl, registerUrl() {} };

  const setView = (patch) => {
    view = { ...view, ...patch };
    box = null;
    if (ctrl.isOpen) render();
    onChange();
  };

  // ---- Static chrome, built once: controls row, chips, plot, captions, legend.
  const controls = el("div", "dm-controls");
  const colorSwitch = el("div", "seg-switch");
  colorSwitch.setAttribute("role", "group");
  colorSwitch.setAttribute("aria-label", t("drugmap.colorBy"));
  for (const m of COLOR_MODES) {
    const b = el("button", "seg-btn", t(`drugmap.color.${m}`));
    b.type = "button";
    b.dataset.mode = m;
    b.addEventListener("click", () => setView({ color: m }));
    colorSwitch.appendChild(b);
  }
  const toggle = (key, label) => {
    const lab = el("label", "list-toggle");
    const input = el("input");
    input.type = "checkbox";
    input.addEventListener("change", () => setView({ [key]: input.checked }));
    lab.append(input, el("span", null, label));
    return { lab, input };
  };
  const sourceSwitch = el("div", "seg-switch");
  sourceSwitch.setAttribute("role", "group");
  sourceSwitch.setAttribute("aria-label", t("drugmap.source"));
  for (const m of FEATURE_SOURCES) {
    const b = el("button", "seg-btn", t(`drugmap.source.${m}`));
    b.type = "button";
    b.dataset.mode = m;
    b.title = t(`drugmap.sourceTip.${m}`);
    b.addEventListener("click", () => setView({ source: m }));
    sourceSwitch.appendChild(b);
  }
  const labelsT = toggle("labels", t("drugmap.labels"));
  const normT = toggle("normalize", t("drugmap.normalize"));
  normT.lab.title = t("drugmap.normalizeTip");
  const signT = toggle("signed", t("drugmap.signed"));
  signT.lab.title = t("drugmap.signedTip");
  // Feature picker: type a target / system name, Enter or pick adds it; each chosen
  // feature is a removable chip. One or two = direct axes, more = PCA on that subset.
  const picker = el("div", "dm-features");
  const pickInput = el("input", "drugs-filter dm-feature-input");
  pickInput.type = "search";
  pickInput.placeholder = t("drugmap.pick");
  pickInput.title = t("drugmap.pickTip");
  pickInput.setAttribute("list", "dm-feature-list");
  const datalist = el("datalist");
  datalist.id = "dm-feature-list";
  const keyByName = new Map([...featureName].map(([k, n]) => [n.toLowerCase(), k]));
  for (const n of [...featureName.values()].sort((a, b) => a.localeCompare(b))) {
    const o = el("option");
    o.value = n;
    datalist.appendChild(o);
  }
  const pickedBox = el("span", "dm-picked");
  const addPicked = () => {
    const key = keyByName.get(pickInput.value.trim().toLowerCase());
    if (!key) return;
    pickInput.value = "";
    if (!(view.only || []).includes(key)) setView({ only: [...(view.only || []), key] });
  };
  pickInput.addEventListener("change", addPicked);
  pickInput.addEventListener("keydown", (ev) => { if (ev.key === "Enter") addPicked(); });
  picker.append(pickInput, datalist, pickedBox);
  const yearBox = el("span", "dm-years");
  const yearInput = (ph) => {
    const i = el("input", "drugs-filter dm-year");
    i.type = "number";
    i.placeholder = ph;
    i.addEventListener("change", () => {
      const [a, b] = [yearFrom.value, yearTo.value].map((v) => (v ? Number(v) : null));
      setView({ years: a || b ? [a || 0, b || 9999] : null });
    });
    return i;
  };
  const yearFrom = yearInput(t("drugmap.from"));
  const yearTo = yearInput(t("drugmap.to"));
  yearBox.append(el("span", null, t("drugmap.years")), yearFrom, el("span", null, "–"), yearTo);
  const unhide = el("button", "dm-unhide");
  unhide.type = "button";
  unhide.addEventListener("click", () => setView({ hidden: new Set() }));
  controls.append(sourceSwitch, colorSwitch, labelsT.lab, normT.lab, signT.lab, yearBox, unhide);

  const chips = el("div", "dm-chips");
  const presentCats = [...new Set([...Object.keys(catLabels), ...drugs.map(primaryCategory)])]
    .filter((c) => drugs.some((d) => primaryCategory(d) === c));
  const chipAll = el("button", "dm-chip dm-chip-all", t("drugmap.all"));
  chipAll.type = "button";
  chipAll.addEventListener("click", () => setView({ cats: null }));
  chips.appendChild(chipAll);
  for (const c of presentCats) {
    const chip = el("button", "dm-chip");
    chip.type = "button";
    chip.dataset.cat = c;
    const dot = el("span", "dm-dot");
    dot.style.background = categoryColor(c, catLabels);
    chip.append(dot, document.createTextNode(catLabels[c] || c));
    // A click narrows to that class alone (from "all") or toggles it in the set;
    // emptying the set returns to "all".
    chip.addEventListener("click", () => {
      const cats = new Set(view.cats || []);
      if (!view.cats) cats.add(c);
      else if (cats.has(c)) cats.delete(c);
      else cats.add(c);
      setView({ cats: cats.size ? cats : null });
    });
    chips.appendChild(chip);
  }

  const svg = svgEl("svg", { class: "dm-plot", role: "img" });
  svg.setAttribute("aria-label", t("drugmap.title"));
  const axes = el("p", "dm-axes info-desc");
  const legend = el("div", "dm-legend");
  const note = el("p", "dm-note info-desc");
  const plotWrap = el("div", "dm-plot-wrap");
  plotWrap.append(svg, el("span", "dm-watermark", `${t("drugmap.watermark")} · ${location.host}`));
  body.replaceChildren(controls, picker, chips, plotWrap, axes, legend, note);
  wireZoom(svg, () => box, (b) => { box = b; drawPoints(); });

  // ---- Render: filter, project, colour, draw.
  let placed = []; // [{drug, x, y, color}] in data coordinates
  let fit = { x: 0, y: 0, w: W, h: H };
  function render() {
    for (const b of colorSwitch.children) b.classList.toggle("active", b.dataset.mode === view.color);
    for (const b of sourceSwitch.children) b.classList.toggle("active", b.dataset.mode === view.source);
    labelsT.input.checked = view.labels;
    normT.input.checked = view.normalize;
    signT.input.checked = view.signed;
    pickedBox.replaceChildren(...(view.only || []).map((key, i) => {
      const chip = el("button", "dm-chip active", `${view.only.length <= 2 ? `${"xy"[i]}: ` : ""}${nameOf(key)} ×`);
      chip.type = "button";
      chip.addEventListener("click", () => {
        const only = view.only.filter((k) => k !== key);
        setView({ only: only.length ? only : null });
      });
      return chip;
    }));
    yearFrom.value = view.years && view.years[0] ? view.years[0] : "";
    yearTo.value = view.years && view.years[1] < 9999 ? view.years[1] : "";
    unhide.hidden = !view.hidden.size;
    unhide.textContent = t("drugmap.unhide", { n: view.hidden.size });
    chipAll.classList.toggle("active", !view.cats);
    for (const chip of chips.querySelectorAll("[data-cat]")) {
      chip.classList.toggle("active", !!view.cats && view.cats.has(chip.dataset.cat));
    }

    // One or two picked features are the axes themselves: raw values, since unit
    // length over two numbers would put every drug on a circle.
    const direct = view.only && view.only.length <= 2;
    const prof = buildProfiles(drugs, { ...view, normalize: view.normalize && !direct });
    const kept = filterDrugs(drugs, view);
    const shown = kept.filter((d) => prof.has(d.id));
    const unplaced = kept.length - shown.length;
    const ids = shown.map((d) => d.id);
    const { points, axes: pcs } = !shown.length ? { points: new Map(), axes: [] }
      : direct ? { points: directPoints(ids, prof, view.only), axes: null } : pca(ids, prof);
    const { colorOf, legend: keyRows, ramp } = colorize(shown, view.color,
      { catLabels, unknown: t("drugmap.unknown"), t });
    placed = shown.map((d) => ({ drug: d, ...points.get(d.id), color: colorOf.get(d.id) }));
    const xs = placed.map((p) => p.x), ys = placed.map((p) => p.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    // Fit the data into the W x H frame, y up (a PCA has no preferred orientation, but
    // a plot reads with "more of PC2" upward).
    const sx = (W - PAD - PAD_RIGHT) / (x1 - x0 || 1), sy = (H - 2 * PAD) / (y1 - y0 || 1);
    for (const p of placed) {
      p.px = PAD + (p.x - x0) * sx;
      p.py = H - PAD - (p.y - y0) * sy;
    }
    fit = { x: 0, y: 0, w: W, h: H };
    drawPoints();

    axes.replaceChildren(...(pcs
      ? pcs.map((ax, i) => el("span", "dm-axis", axisText(ax, i)))
      : view.only.map((key, i) => el("span", "dm-axis", t("drugmap.axisDirect", { axis: ["x →", "y ↑"][i], name: nameOf(key) })))));
    legend.replaceChildren(...legendRows(keyRows, ramp));
    note.textContent = [
      t("drugmap.count", { n: shown.length }),
      unplaced ? t("drugmap.unplaced", { n: unplaced }) : "",
      t("drugmap.help"),
    ].filter(Boolean).join(" ");
  }

  // "PC1 (34%): D2, 5-HT2A, H1 vs SERT, NET": the targets that pull each way most.
  function axisText(ax, i) {
    const name = (l) => nameOf(l.target);
    const pos = ax.loadings.filter((l) => l.w > 0).slice(0, 3).map(name);
    const neg = ax.loadings.filter((l) => l.w < 0).slice(0, 3).map(name);
    return t("drugmap.axis", {
      n: i + 1, share: Math.round(ax.share * 100),
      pos: pos.join(", ") || "-", neg: neg.join(", ") || "-",
    });
  }

  function legendRows(rows, ramp) {
    if (ramp) {
      const bar = el("span", "dm-ramp");
      return [el("span", "dm-key", String(ramp.from)), bar, el("span", "dm-key", String(ramp.to))];
    }
    return rows.map((r) => {
      const row = el("span", "dm-key");
      const dot = el("span", "dm-dot");
      dot.style.background = r.color;
      row.append(dot, document.createTextNode(`${r.label} (${r.count})`));
      return row;
    });
  }

  // Points + names, sized to the current zoom so they stay the same on screen. A name
  // that would overlap one already drawn is skipped (greedy, in list order), so a dense
  // cluster stays readable; zooming in frees the room to show it.
  function drawPoints() {
    const b = box || fit;
    svg.setAttribute("viewBox", `${b.x} ${b.y} ${b.w} ${b.h}`);
    const k = b.w / W;
    const g = svgEl("g");
    const taken = [];
    const free = (r) => !taken.some((o) =>
      r.x < o.x + o.w && o.x < r.x + r.w && r.y < o.y + o.h && o.y < r.y + r.h);
    for (const p of placed) {
      const c = svgEl("circle", { cx: p.px, cy: p.py, r: 6 * k, fill: p.color, class: "dm-point" });
      const yr = p.drug.firstApproval && p.drug.firstApproval.year;
      const title = svgEl("title");
      title.textContent = [p.drug.displayName, p.drug.categoryLabels.join(" · "), yr,
        p.drug.originator && p.drug.originator.name].filter(Boolean).join("\n");
      c.appendChild(title);
      c.addEventListener("click", () => window.open(drugUrl(p.drug), "_blank", "noopener"));
      c.addEventListener("contextmenu", (ev) => {
        ev.preventDefault();
        setView({ hidden: new Set([...view.hidden, p.drug.id]) });
      });
      g.appendChild(c);
      const rect = { x: p.px + 8 * k, y: p.py - 6 * k, w: p.drug.name.length * 6.4 * k, h: 12 * k };
      if (view.labels && free(rect)) {
        taken.push(rect);
        const txt = svgEl("text", { x: p.px + 8 * k, y: p.py + 4 * k, class: "dm-label", "font-size": 12 * k });
        txt.textContent = p.drug.name;
        g.appendChild(txt);
      }
    }
    svg.replaceChildren(g);
  }

  setDrugMapOpener((patch) => {
    view = { ...DEFAULT_VIEW, hidden: new Set(), ...patch };
    box = null;
    ctrl.open();
  });

  return {
    ...ctrl,
    get isOpen() { return ctrl.isOpen; },
    /** Mirror the view into the URL, one key per control, absent at its default. */
    registerUrl(urlState) {
      const reg = (key, read, write) => urlState.register(key, {
        read: () => (ctrl.isOpen ? read() : null),
        write: (v) => setView(write(v)),
        reset: () => setView({ ...DEFAULT_VIEW, hidden: new Set() }),
      });
      reg("dmcat", () => (view.cats ? [...view.cats].join(LIST_SEP) : null),
        (v) => ({ cats: v ? new Set(v.split(LIST_SEP)) : null }));
      reg("dmyear", () => (view.years ? `${view.years[0] || ""}-${view.years[1] < 9999 ? view.years[1] : ""}` : null),
        (v) => {
          const [a, b] = v.split("-").map((s) => (s ? Number(s) : null));
          return { years: a || b ? [a || 0, b || 9999] : null };
        });
      reg("dmhide", () => (view.hidden.size ? [...view.hidden].join(LIST_SEP) : null),
        (v) => ({ hidden: new Set(v ? v.split(LIST_SEP) : []) }));
      reg("dmcolor", () => (view.color !== DEFAULT_VIEW.color ? view.color : null),
        (v) => ({ color: COLOR_MODES.includes(v) ? v : DEFAULT_VIEW.color }));
      reg("dmlabels", () => (view.labels ? "1" : null), (v) => ({ labels: v === "1" }));
      reg("dmnorm", () => (view.normalize ? null : "0"), (v) => ({ normalize: v !== "0" }));
      reg("dmsign", () => (view.signed ? "1" : null), (v) => ({ signed: v === "1" }));
      reg("dmsrc", () => (view.source !== DEFAULT_VIEW.source ? view.source : null),
        (v) => ({ source: FEATURE_SOURCES.includes(v) ? v : DEFAULT_VIEW.source }));
      reg("dmtgt", () => (view.only ? view.only.join(LIST_SEP) : null),
        (v) => ({ only: v ? v.split(LIST_SEP) : null }));
    },
  };
}

// This page, opened on one drug's tab (the `tabs` deep link, js/url-state.js).
const drugUrl = (drug) => `${location.origin}${location.pathname}${location.search}#tabs=drug:${encodeURIComponent(drug.id)}`;

// Wheel to zoom about the pointer, drag to pan, double-click to refit: all by moving
// the SVG viewBox (`get` null = the fitted frame).
function wireZoom(svg, get, set) {
  const current = () => get() || { x: 0, y: 0, w: W, h: H };
  const toSvg = (ev) => {
    const r = svg.getBoundingClientRect(), b = current();
    return { x: b.x + ((ev.clientX - r.left) / r.width) * b.w, y: b.y + ((ev.clientY - r.top) / r.height) * b.h };
  };
  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const b = current(), at = toSvg(ev);
    const f = Math.min(Math.max(ev.deltaY > 0 ? 1.15 : 1 / 1.15, 0), 4);
    const w = Math.min(W * 2, Math.max(W / 40, b.w * f)), h = w * (H / W);
    set({ x: at.x - ((at.x - b.x) * w) / b.w, y: at.y - ((at.y - b.y) * h) / b.h, w, h });
  }, { passive: false });
  let drag = null;
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0 || ev.target.closest(".dm-point")) return;
    drag = { start: toSvg(ev), b: current() };
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    const r = svg.getBoundingClientRect();
    const dx = ((ev.clientX - r.left) / r.width) * drag.b.w + drag.b.x - drag.start.x;
    const dy = ((ev.clientY - r.top) / r.height) * drag.b.h + drag.b.y - drag.start.y;
    set({ ...drag.b, x: drag.b.x - dx, y: drag.b.y - dy });
  });
  const end = () => { drag = null; };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("dblclick", () => set(null));
}
