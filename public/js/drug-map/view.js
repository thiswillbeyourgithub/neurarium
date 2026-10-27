// The drug map popup (#drugmap-modal): every drug placed by 2-component PCA of its
// feature vector (js/drug-map/model.js: receptor affinities, net transmitter tone, or
// both), recomputed for whatever the filters leave on screen; pick one or two features
// and they are plotted directly instead. Controls: feature source, colour mode, names
// on/off, normalization, signed (agonist vs antagonist), year range, a target picker
// grouped by transmitter system, per-category chips (collapsed past the first few); in
// both lists a click picks, shift-click or long-press drops. Right-click (long-press)
// hides a drug; wheel or pinch zooms, one-finger drag pans. Clicking a point
// opens that drug in a new browser tab. The whole view is mirrored into the URL
// (`dm*` keys).

import {
  buildProfiles, categoryColor, colorize, COLOR_MODES, DEFAULT_VIEW, directPoints,
  FEATURE_SOURCES, filterDrugs, pca, pickSet, primaryCategory, TONE_PREFIX,
} from "./model.js";
import { groupTargetsBySystem } from "../legend/targets.js";
import { placeLabels, sizesFor } from "./layout.js";
import { setDrugMapOpener } from "./link.js";
import { LIST_SEP } from "../url-state.js";

const { t } = window.__I18N__;
const SVG = "http://www.w3.org/2000/svg";
const W = 1000, H = 640, PAD = 30;
// Room on the right for the names of the rightmost points.
const PAD_RIGHT = 130;
// Class chips shown before the rest fold behind the ellipsis chip.
const CHIPS_SHOWN = 8;
const LEGEND_SHOWN = 8;
const LONG_PRESS_MS = 500;
const GRID_PX = 60;
// A pointer moving less than this (px) is still a click, not a pan.
const DRAG_SLOP_PX = 5;
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const button = (cls, text, onClick) => {
  const b = el("button", cls, text);
  b.type = "button";
  if (onClick) b.addEventListener("click", onClick);
  return b;
};
// The gesture every filter row here shares: a click picks, shift-click or a long press
// (touch) drops. The long press swallows the click that follows it.
function pickOrDrop(node, pick, drop) {
  let pressed = null, longPressed = false;
  node.addEventListener("pointerdown", (ev) => {
    longPressed = false;
    if (ev.pointerType === "mouse") return;
    pressed = setTimeout(() => { longPressed = true; drop(); }, LONG_PRESS_MS);
  });
  for (const type of ["pointerup", "pointercancel", "pointerleave"]) {
    node.addEventListener(type, () => clearTimeout(pressed));
  }
  node.addEventListener("contextmenu", (ev) => ev.preventDefault());
  node.addEventListener("click", (ev) => {
    if (longPressed) return;
    if (ev.shiftKey) drop();
    else pick();
  });
}
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

  // ---- Static chrome, built once: control sections, plot, captions, legend.
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
  // Target picker: every feature of the current source, targets grouped by transmitter
  // system in the Receptors & targets legend's order (most-bound system first), the
  // net-tone features as one last group. One or two picked = direct axes, more = PCA
  // on that subset. Folded behind a summary naming the selection.
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
  const toneKeys = [...featureName.keys()].filter((k) => k.startsWith(TONE_PREFIX));
  const groupsFor = (source) => [
    ...(source !== "tone" ? targetGroups : []),
    ...(source !== "receptors" && toneKeys.length ? [[t("drugmap.source.tone"), toneKeys]] : []),
  ];
  const picker = el("details", "dm-targets");
  const pickSummary = el("summary");
  const pickList = el("div", "dm-tlist");
  const pickBar = el("div", "dm-tbar");
  pickBar.append(
    button("dm-chip", t("drugmap.pickAll"), () => setView({ only: null })),
    button("dm-chip", t("drugmap.pickNone"), () => setView({ only: [] })),
    el("span", "dm-hint", t("drugmap.pickTip")));
  picker.append(pickSummary, pickBar, pickList);
  function renderPicker() {
    const groups = groupsFor(view.source);
    const universe = groups.flatMap(([, keys]) => keys);
    const on = (k) => !view.only || view.only.includes(k);
    const apply = (keys, mode) => {
      const next = pickSet(view.only, keys, mode, universe);
      setView({ only: universe.every((k) => next.includes(k)) ? null : next });
    };
    const axis = (k) => {
      const i = view.only && view.only.length <= 2 ? view.only.indexOf(k) : -1;
      return i < 0 ? "" : `${"xy"[i]}: `;
    };
    pickList.replaceChildren(...groups.map(([label, keys]) => {
      const box = el("div", "dm-tgroup");
      const head = button("dm-tgroup-head", label);
      head.classList.toggle("active", keys.every(on));
      pickOrDrop(head, () => apply(keys, "pick"), () => apply(keys, "drop"));
      const items = el("div", "dm-titems");
      for (const k of keys) {
        const b = button("dm-chip", `${axis(k)}${nameOf(k)}`);
        b.classList.toggle("active", on(k));
        pickOrDrop(b, () => apply([k], "pick"), () => apply([k], "drop"));
        items.appendChild(b);
      }
      box.append(head, items);
      return box;
    }));
    const n = view.only ? view.only.filter((k) => universe.includes(k)).length : universe.length;
    pickSummary.textContent = !view.only ? t("drugmap.pickSumAll", { n })
      : !n ? t("drugmap.pickSumNone")
      : view.only.length <= 2 ? view.only.map((k) => `${axis(k)}${nameOf(k)}`).join(" · ")
      : t("drugmap.pickSumSome", { k: n, n: universe.length });
  }
  const marketT = toggle("marketed", t("drugmap.marketed"));
  marketT.lab.title = t("drugmap.marketedTip");
  // An approval-year range has no control of its own: only a decade heading's "map"
  // link sets one, shown as a removable chip among the filters.
  const yearChip = el("button", "dm-chip active");
  yearChip.type = "button";
  yearChip.addEventListener("click", () => setView({ years: null }));
  const unhide = el("button", "dm-unhide");
  unhide.type = "button";
  unhide.addEventListener("click", () => setView({ hidden: new Set() }));

  const chips = el("div", "dm-chips");
  chips.append(yearChip, unhide);
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
    // emptying the set returns to "all". Dropping removes it from what is shown.
    const apply = (mode) => {
      const cats = pickSet(view.cats && [...view.cats], [c], mode, presentCats);
      setView({ cats: cats.length ? new Set(cats) : null });
    };
    pickOrDrop(chip, () => apply("pick"), () => apply("drop"));
    chips.appendChild(chip);
  }
  // The class list runs to 4 rows, so past CHIPS_SHOWN it folds behind an ellipsis
  // chip (an active class always stays visible).
  let chipsOpen = false;
  const chipMore = el("button", "dm-chip dm-chip-more");
  chipMore.type = "button";
  chipMore.addEventListener("click", () => { chipsOpen = !chipsOpen; render(); });
  chips.appendChild(chipMore);

  const svg = svgEl("svg", { class: "dm-plot", role: "img" });
  svg.setAttribute("aria-label", t("drugmap.title"));
  const axes = el("p", "dm-axes info-desc");
  const legend = el("div", "dm-legend");
  const note = el("p", "dm-note info-desc");
  const plotWrap = el("div", "dm-plot-wrap");
  // Fullscreen: the browser's own where it exists, else (iPhone Safari) a fixed overlay.
  const fsBtn = el("button", "dm-fullscreen", "⛶");
  fsBtn.type = "button";
  fsBtn.title = t("drugmap.fullscreen");
  fsBtn.setAttribute("aria-label", t("drugmap.fullscreen"));
  fsBtn.addEventListener("click", () => {
    const on = !plotWrap.classList.contains("dm-fs");
    plotWrap.classList.toggle("dm-fs", on);
    if (on && plotWrap.requestFullscreen) plotWrap.requestFullscreen().catch(() => {});
    else if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {});
  });
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) plotWrap.classList.remove("dm-fs");
  });
  plotWrap.append(svg, fsBtn, el("span", "dm-watermark", `${t("drugmap.watermark")} · ${location.host}`));
  // Four labelled steps: what places the drugs, what colours them, which are shown,
  // and the advanced switches folded away.
  const section = (title, ...kids) => {
    const s = el("div", "dm-section");
    s.append(el("span", "dm-section-title", title), ...kids);
    return s;
  };
  const advanced = el("details", "dm-advanced");
  const advRow = el("div", "dm-controls");
  advRow.append(labelsT.lab, normT.lab, signT.lab, marketT.lab);
  advanced.append(el("summary", "dm-section-title", t("drugmap.sec.advanced")), advRow);
  body.replaceChildren(
    section(t("drugmap.sec.input"), sourceSwitch, picker),
    section(t("drugmap.sec.color"), colorSwitch),
    section(t("drugmap.sec.filter"), chips),
    advanced, plotWrap, axes, legend, note);
  wireZoom(svg, () => box, (b) => { box = b; drawPoints(); });
  // Names are sized in screen px, so a resized popup re-lays them out.
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => { if (ctrl.isOpen && placed.length) drawPoints(); }).observe(plotWrap);
  }

  // ---- Render: filter, project, colour, draw.
  let placed = []; // [{drug, x, y, color}] in data coordinates
  let fit = { x: 0, y: 0, w: W, h: H };
  function render() {
    for (const b of colorSwitch.children) b.classList.toggle("active", b.dataset.mode === view.color);
    for (const b of sourceSwitch.children) b.classList.toggle("active", b.dataset.mode === view.source);
    labelsT.input.checked = view.labels;
    normT.input.checked = view.normalize;
    signT.input.checked = view.signed;
    marketT.input.checked = view.marketed;
    renderPicker();
    yearChip.hidden = !view.years;
    if (view.years) {
      yearChip.textContent = t("drugmap.yearChip", {
        from: view.years[0] || "…", to: view.years[1] < 9999 ? view.years[1] : "…" });
    }
    unhide.hidden = !view.hidden.size;
    unhide.textContent = t("drugmap.unhide", { n: view.hidden.size });
    chipAll.classList.toggle("active", !view.cats);
    let folded = 0;
    chips.querySelectorAll("[data-cat]").forEach((chip, i) => {
      const active = !!view.cats && view.cats.has(chip.dataset.cat);
      chip.classList.toggle("active", active);
      chip.hidden = !chipsOpen && i >= CHIPS_SHOWN && !active;
      if (chip.hidden) folded++;
    });
    chipMore.hidden = !chipsOpen && !folded;
    // The chips' dots are the class colours, so they only show when points use them:
    // in another colour mode they would read as that mode's legend.
    chips.classList.toggle("dm-no-dots", view.color !== "category");
    chipMore.textContent = chipsOpen ? t("drugmap.fewerClasses") : t("drugmap.moreClasses", { n: folded });

    // One or two picked features are the axes themselves: raw values, since unit
    // length over two numbers would put every drug on a circle.
    const direct = view.only && view.only.length > 0 && view.only.length <= 2;
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
    // a plot reads with "more of PC2" upward), at ONE scale for both axes and centred,
    // so a distance on screen (and the grid's squares) means the same either way.
    const aw = W - PAD - PAD_RIGHT, ah = H - 2 * PAD;
    const s = Math.min(aw / (x1 - x0 || 1), ah / (y1 - y0 || 1));
    const ox = PAD + (aw - (x1 - x0) * s) / 2, oy = H - PAD - (ah - (y1 - y0) * s) / 2;
    for (const p of placed) {
      p.px = ox + (p.x - x0) * s;
      p.py = oy - (p.y - y0) * s;
    }
    fit = { x: 0, y: 0, w: W, h: H };
    drawPoints();

    axes.replaceChildren(...(pcs
      ? pcs.map((ax, i) => el("span", "dm-axis", axisText(ax, i)))
      : view.only.map((key, i) => el("span", "dm-axis", t("drugmap.axisDirect", { axis: ["x →", "y ↑"][i], name: nameOf(key) })))));
    const rows = legendRows(keyRows, ramp);
    if (rows.length > LEGEND_SHOWN + 1) {
      // A long legend (labs, routes) folds past its first rows behind a <details>.
      const more = el("details", "dm-legend-more");
      more.open = legendOpen;
      more.addEventListener("toggle", () => { legendOpen = more.open; });
      more.append(el("summary", null, t("drugmap.moreKeys", { n: rows.length - LEGEND_SHOWN })),
        ...rows.slice(LEGEND_SHOWN));
      legend.replaceChildren(...rows.slice(0, LEGEND_SHOWN), more);
    } else legend.replaceChildren(...rows);
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

  // A dot and its name both open the drug in a new tab (click) or hide it (right-click,
  // long-press), with the same tooltip.
  function linkDrug(node, p) {
    const title = svgEl("title");
    title.textContent = p.tip;
    node.appendChild(title);
    node.addEventListener("click", () => window.open(drugUrl(p.drug), "_blank", "noopener"));
    node.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      setView({ hidden: new Set([...view.hidden, p.drug.id]) });
    });
  }
  let legendOpen = false;
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

  // Points + names, laid out in screen pixels (js/drug-map/layout.js): their size follows
  // how crowded the visible points are, and a name never covers a dot or another name.
  // Recomputed on every zoom / pan, so zooming into a cluster grows and frees its names.
  const measureCtx = document.createElement("canvas").getContext("2d");
  function drawPoints() {
    const b = box || fit;
    svg.setAttribute("viewBox", `${b.x} ${b.y} ${b.w} ${b.h}`);
    const width = svg.clientWidth || W, height = svg.clientHeight || H;
    const k = b.w / width; // viewBox units per screen px
    const screen = placed
      .map((p) => ({ id: p.drug.id, text: p.drug.name, p, x: (p.px - b.x) / k, y: (p.py - b.y) / k }))
      .filter((q) => q.x >= 0 && q.x <= width && q.y >= 0 && q.y <= height);
    const { font, r } = sizesFor(screen);
    let names = new Map();
    if (view.labels) {
      measureCtx.font = `${font}px ${getComputedStyle(svg).fontFamily}`;
      names = placeLabels(screen, { font, r, width, height, measure: (s) => measureCtx.measureText(s).width });
    }
    const g = svgEl("g");
    g.appendChild(gridLines(b, k));
    for (const p of placed) {
      const c = svgEl("circle", { cx: p.px, cy: p.py, r: r * k, fill: p.color, class: "dm-point" });
      const yr = p.drug.firstApproval && p.drug.firstApproval.year;
      p.tip = [p.drug.displayName, p.drug.categoryLabels.join(" · "), yr,
        p.drug.originator && p.drug.originator.name].filter(Boolean).join("\n");
      linkDrug(c, p);
      g.appendChild(c);
    }
    for (const q of screen) {
      const at = names.get(q.id);
      if (!at) continue;
      const txt = svgEl("text", { x: b.x + at.x * k, y: b.y + at.y * k, class: "dm-label", "font-size": font * k });
      txt.textContent = q.text;
      linkDrug(txt, q.p);
      g.appendChild(txt);
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
      reg("dmlabels", () => (view.labels ? null : "0"), (v) => ({ labels: v !== "0" }));
      reg("dmnorm", () => (view.normalize ? null : "0"), (v) => ({ normalize: v !== "0" }));
      reg("dmsign", () => (view.signed ? null : "0"), (v) => ({ signed: v !== "0" }));
      reg("dmmkt", () => (view.marketed ? "1" : null), (v) => ({ marketed: v === "1" }));
      reg("dmsrc", () => (view.source !== DEFAULT_VIEW.source ? view.source : null),
        (v) => ({ source: FEATURE_SOURCES.includes(v) ? v : DEFAULT_VIEW.source }));
      // "-" = none picked (an empty value would read back as "every target").
      reg("dmtgt", () => (!view.only ? null : view.only.length ? view.only.join(LIST_SEP) : "-"),
        (v) => ({ only: !v ? null : v === "-" ? [] : v.split(LIST_SEP) }));
    },
  };
}

// Grid lines over the visible frame `b`, about GRID_PX apart on screen at a round
// step (1, 2 or 5 x 10^n viewBox units), so zooming in subdivides it rather than
// sliding it, and squares stay square (one scale for both axes).
function gridLines(b, k) {
  const raw = GRID_PX * k, mag = 10 ** Math.floor(Math.log10(raw));
  const step = mag * ([1, 2, 5, 10].find((m) => mag * m >= raw));
  const g = svgEl("g", { class: "dm-grid", "stroke-width": k });
  for (let x = Math.ceil(b.x / step) * step; x <= b.x + b.w; x += step) {
    g.appendChild(svgEl("line", { x1: x, x2: x, y1: b.y, y2: b.y + b.h }));
  }
  for (let y = Math.ceil(b.y / step) * step; y <= b.y + b.h; y += step) {
    g.appendChild(svgEl("line", { x1: b.x, x2: b.x + b.w, y1: y, y2: y }));
  }
  return g;
}

// This page, opened on one drug's tab (the `tabs` deep link, js/url-state.js).
const drugUrl = (drug) => `${location.origin}${location.pathname}${location.search}#tabs=drug:${encodeURIComponent(drug.id)}`;

// Wheel or pinch to zoom about the pointer / the fingers' midpoint, drag to pan,
// double-click to refit: all by moving the SVG viewBox (`get` null = the fitted frame).
function wireZoom(svg, get, set) {
  const current = () => get() || { x: 0, y: 0, w: W, h: H };
  const frac = (ev) => {
    const r = svg.getBoundingClientRect();
    return { fx: (ev.clientX - r.left) / r.width, fy: (ev.clientY - r.top) / r.height };
  };
  const toSvg = (ev, b = current()) => {
    const { fx, fy } = frac(ev);
    return { x: b.x + fx * b.w, y: b.y + fy * b.h };
  };
  // Zoom so the frame is `w` wide, keeping the svg point `at` under screen fraction (fx, fy).
  const zoomTo = (w, at, { fx, fy }) => {
    w = Math.min(W * 2, Math.max(W / 40, w));
    const h = w * (H / W);
    set({ x: at.x - fx * w, y: at.y - fy * h, w, h });
  };
  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    zoomTo(current().w * (ev.deltaY > 0 ? 1.15 : 1 / 1.15), toSvg(ev), frac(ev));
  }, { passive: false });

  // Every pointer down on the plot is tracked, a dot included (so a finger landing on
  // a dot can still start a pan or a pinch): one = drag to pan once it moves past
  // DRAG_SLOP_PX, two = pinch, and going from two back to one resumes the pan from the
  // finger left. Moves and ends are read on `window`, so a pointer released off the
  // plot never stays behind as a ghost that turns the next touch into a pinch. A
  // gesture swallows the click that ends it, so a pan never opens a drug.
  const touches = new Map(); // pointerId -> last event
  let drag = null, pinch = null, gestured = false;
  const mid = () => {
    const [a, b] = [...touches.values()];
    return { clientX: (a.clientX + b.clientX) / 2, clientY: (a.clientY + b.clientY) / 2,
      dist: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) };
  };
  const startDrag = (ev, moved) => {
    drag = { start: toSvg(ev), b: current(), x0: ev.clientX, y0: ev.clientY, moved };
  };
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    if (!touches.size) gestured = false;
    touches.set(ev.pointerId, ev);
    if (touches.size === 2) {
      const m = mid();
      drag = null;
      gestured = true;
      pinch = { dist: m.dist || 1, at: toSvg(m), b: current() };
    } else if (touches.size === 1) startDrag(ev, false);
  });
  window.addEventListener("pointermove", (ev) => {
    if (!touches.has(ev.pointerId)) return;
    touches.set(ev.pointerId, ev);
    if (pinch && touches.size === 2) {
      const m = mid();
      zoomTo(pinch.b.w * (pinch.dist / (m.dist || 1)), pinch.at, frac(m));
    } else if (drag) {
      if (!drag.moved && Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < DRAG_SLOP_PX) return;
      drag.moved = gestured = true;
      const { fx, fy } = frac(ev);
      set({ ...drag.b, x: drag.start.x - fx * drag.b.w, y: drag.start.y - fy * drag.b.h });
    }
  });
  const end = (ev) => {
    if (!touches.delete(ev.pointerId)) return;
    pinch = null;
    drag = null;
    if (touches.size === 1) startDrag([...touches.values()][0], true);
  };
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
  // Capture phase, ahead of a dot's own click (open) and contextmenu (hide) handlers.
  for (const type of ["click", "contextmenu"]) {
    svg.addEventListener(type, (ev) => {
      if (!gestured) return;
      ev.stopPropagation();
      ev.preventDefault();
    }, true);
  }
  svg.addEventListener("dblclick", () => set(null));
}
