// The drugs map page (drugs-map.html, booted by js/drugs-map-main.js): every drug placed by 2-component PCA of its
// feature vector (js/drug-map/model.js: receptor affinities, net transmitter tone, or
// both), recomputed for whatever the filters leave on screen; pick one or two features
// and they are plotted directly instead. The control boxes live in controls.js, the
// camera gestures (zoom, pan, rotate) in gestures.js, name placement in layout.js, the
// overlap nudge in spread.js. A re-render yields between its steps behind a busy
// indicator (with a "suspiciously slow" hint past SLOW_MS), then slides the dots that
// stay and fades the ones that come or go. Clicking a point or its name opens that drug
// in the 3D viewer in a new browser tab, right-click (long-press) hides it. The whole
// view is mirrored into the URL (`dm*` keys).
//
// It is a page of its own rather than a popup of the viewer so it can be shown alone
// (also served as drugsmap.olicorne.org, see docs/drugs-map/README.md) without loading
// three.js, the meshes or the panels.

import {
  buildProfiles, colorize, COLOR_MODES, DEFAULT_VIEW, directPoints,
  EFFECT_PREFIX, filterDrugs, mappableDrugs, parseSources, pca, TONE_PREFIX,
} from "./model.js";
import { placeLabels, sizesFor } from "./layout.js";
import { spreadPoints } from "./spread.js";
import { button, el, foldBox, H, rotate, svgEl, W } from "./dom.js";
import { wireGestures } from "./gestures.js";
import { createFocus } from "./focus.js";
import { plotTitle } from "./title.js";
import { ARCH_HIGH, archScore, axisCaption, axisTooltip } from "./axis.js";
import { createExtras } from "./extras.js";
import { copyPng, plotPng } from "./snapshot.js";
import { createControls } from "./controls.js";
import { LIST_SEP } from "../url-state.js";
import { viewerUrl } from "./site.js";

const { t } = window.__I18N__;
const PAD = 30;
// Room on the right for the names of the rightmost points.
const PAD_RIGHT = 130;
const GRID_PX = 60;
// Kept free under the plot title: about one name line, so a name above a dot clears it.
const TITLE_GAP_PX = 30;
// Transition length, and how long a re-render may run before the busy spinner shows
// (a fast one never flashes it) and before the "suspiciously slow" hint joins it.
const ANIM_MS = 450;
const BUSY_MS = 150;
const SLOW_MS = 5000;

/**
 * Build the map into #drugmap-body. Nothing is drawn until the first `render()`, so the
 * caller can apply the URL's view first and the map opens on it without a transition.
 * @param {{data: object, onChange: () => void}} o
 *   onChange runs after any view change (URL sync)
 * @returns {{render: () => Promise<void>, registerUrl: (urlState: object) => void}}
 */
export function createDrugMap({ data, onChange }) {
  const body = document.getElementById("drugmap-body");
  // Each drug carries its possible body effects (the build-time effect index, BETA), the
  // "effects" feature source (see buildProfiles).
  const effectsOf = data.possibleEffectsByDrug || new Map();
  const drugs = mappableDrugs(data.drugs || []).map((d) => ({ ...d, possibleEffects: effectsOf.get(d.id) || [] }));
  const catLabels = data.meta.drugCategoryLabels || {};
  // Every feature key -> its display name: targets, `tone:<kind>` systems, `effect:<id>`.
  const featureName = new Map();
  for (const d of drugs) for (const b of d.bindings || []) featureName.set(b.target, b.targetName || b.target);
  for (const d of drugs) {
    for (const kind of Object.keys(d.flowSystems || {})) {
      featureName.set(TONE_PREFIX + kind, t("drugmap.toneOf", { kind: (data.meta.kindLabels || {})[kind] || kind }));
    }
  }
  for (const d of drugs) for (const e of d.possibleEffects) featureName.set(EFFECT_PREFIX + e.effect, e.label);
  const nameOf = (key) => featureName.get(key) || key;
  let view = { ...DEFAULT_VIEW, hidden: new Set() };
  // The camera: viewBox once zoomed / panned (null = fit) and the rotation (radians).
  let cam = { box: null, angle: 0 };
  if (!body) return { render: async () => {}, registerUrl() {} };

  // A view change refits the frame but keeps the rotation the reader chose.
  const setView = (patch) => {
    view = { ...view, ...patch };
    cam = { ...cam, box: null };
    render();
    onChange();
  };

  // ---- Static chrome, built once: control boxes, plot, then the legend and axes boxes.
  const controls = createControls({
    data, drugs, nameOf, featureKeys: [...featureName.keys()], getView: () => view, setView,
  });
  const svg = svgEl("svg", { class: "dm-plot", role: "img" });
  svg.setAttribute("aria-label", t("drugmap.title"));
  const plotWrap = el("div", "dm-plot-wrap");
  // Fullscreen: the browser's own where it exists, else (iPhone Safari) a fixed overlay.
  const toggleFullscreen = () => {
    const on = !plotWrap.classList.contains("dm-fs");
    plotWrap.classList.toggle("dm-fs", on);
    if (on && plotWrap.requestFullscreen) plotWrap.requestFullscreen().catch(() => {});
    else if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {});
  };
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) plotWrap.classList.remove("dm-fs");
  });
  // The kebab menu (top right of the plot): fullscreen, reset rotation, copy the image.
  // Each item's label / disabled state is refreshed when the menu opens.
  const menu = el("div", "dm-menu");
  menu.hidden = true;
  menu.setAttribute("role", "menu");
  const kebab = button("dm-plot-btn dm-kebab", "⋮", (e) => {
    e.stopPropagation();
    if (menu.hidden) openMenu(); else menu.hidden = true;
  });
  kebab.title = t("drugmap.menu");
  kebab.setAttribute("aria-label", t("drugmap.menu"));
  kebab.setAttribute("aria-haspopup", "menu");
  const item = (onPick) => {
    const b = button("dm-menu-item", "", () => { menu.hidden = true; onPick(b); });
    b.setAttribute("role", "menuitem");
    return b;
  };
  const fsItem = item(toggleFullscreen);
  const rotItem = item(() => setCam({ ...cam, angle: 0 }));
  const copyItem = item(async () => {
    const res = await copyPng(() => plotPng(svg, {
      overlays: [{ node: plotTitleEl, align: "center" }, { node: watermark, align: "right" }],
      legend: { keys: legend, head: axesHead, axes },
    }), "drugsmap.png").catch(() => "failed");
    flashKebab(t(`drugmap.image.${res}`));
  });
  menu.append(fsItem, rotItem, copyItem);
  function openMenu() {
    fsItem.textContent = t(plotWrap.classList.contains("dm-fs") ? "drugmap.exitFullscreen" : "drugmap.fullscreen");
    rotItem.textContent = t("drugmap.resetRotation");
    rotItem.disabled = !cam.angle;
    copyItem.textContent = t("drugmap.copyImage");
    menu.hidden = false;
  }
  // The outcome of "Copy image", shown on the kebab itself for a moment.
  const flashKebab = (text) => {
    kebab.textContent = text;
    kebab.classList.add("dm-kebab-note");
    setTimeout(() => { kebab.textContent = "⋮"; kebab.classList.remove("dm-kebab-note"); }, 1500);
  };
  document.addEventListener("click", (e) => { if (!menu.contains(e.target)) menu.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") menu.hidden = true; });
  // Shown only once rotated: the angle, and a click turns the map back upright.
  const unrotate = button("dm-plot-btn dm-unrotate", "", () => setCam({ ...cam, angle: 0 }));
  unrotate.title = t("drugmap.unrotate");
  const busy = el("div", "dm-busy");
  const busyText = el("p", "dm-busy-text", t("drugmap.slow"));
  busy.append(el("span", "dm-spinner"), busyText);
  busy.hidden = true;
  // What is on screen, in one sentence (title.js), over the top of the plot; fitPoints
  // keeps the points below it, however many lines it wraps to.
  const plotTitleEl = el("div", "dm-plot-title");
  const watermark = el("span", "dm-watermark", `${t("drugmap.watermark")} v${window.__APP_VERSION__} · ${location.host}`);
  plotWrap.append(svg, plotTitleEl, kebab, menu, unrotate, busy, watermark);
  // The Legend folds as a whole; inside it the colour keys, then the axis meaning (always
  // shown with the legend), then the numbers behind the map in their own fold (extras.js).
  const legendBox = foldBox(t("drugmap.sec.legend"));
  const legend = el("div", "dm-legend");
  const axesHead = el("div", "dm-sub-head");
  const axes = el("div", "dm-axes");
  const extras = createExtras(t);
  legendBox.body.append(legend, axesHead, axes, extras.box);
  const note = el("p", "dm-note info-desc");
  body.replaceChildren(...controls.boxes, plotWrap, legendBox.box, note);

  const setCam = (next) => { cam = next; anim = null; drawPoints(); };
  // Which drug the pointer means + its name on top (focus.js): opens / hides it too.
  const focus = createFocus({
    svg,
    onOpen: (drug) => window.open(drugUrl(drug), "_blank", "noopener"),
    onHide: (drug) => setView({ hidden: new Set([...view.hidden, drug.id]) }),
  });
  wireGestures(svg, () => cam, setCam, () => fitFrame());
  // Names are sized in screen px, so a resized window re-lays them out.
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => {
      if (!placed.length) return;
      // A narrower plot can wrap the title onto another line: refit below it.
      if (titlePad() !== fitTop) fitPoints(placed);
      drawPoints();
    }).observe(plotWrap);
  }

  // ---- Render: filter, project, colour, then transition to the new placement. Async:
  // each step yields so a slow device paints the busy indicator; a newer render
  // started meanwhile (`gen`) makes the older one stop.
  let placed = []; // [{drug, x, y, px, py, color}]: data coordinates + fitted frame px
  let gen = 0;
  const yieldFrame = () => new Promise((resolve) => setTimeout(resolve, 0));
  async function render() {
    const my = ++gen;
    controls.render();
    const timers = [
      setTimeout(() => { busy.hidden = false; }, BUSY_MS),
      setTimeout(() => { busyText.hidden = false; }, SLOW_MS),
    ];
    busyText.hidden = true;
    try {
      await yieldFrame();
      if (my !== gen) return;
      // One or two picked features are the axes themselves: raw values, since unit
      // length over two numbers would put every drug on a circle.
      const direct = view.only && view.only.length > 0 && view.only.length <= 2;
      const prof = buildProfiles(drugs, { ...view, normalize: view.normalize && !direct });
      const kept = filterDrugs(drugs, view);
      const shown = kept.filter((d) => prof.has(d.id));
      const ids = shown.map((d) => d.id);
      await yieldFrame();
      if (my !== gen) return;
      const { points, axes: pcs } = !shown.length ? { points: new Map(), axes: [] }
        : direct ? { points: directPoints(ids, prof, view.only), axes: null } : pca(ids, prof);
      const { colorOf, legend: keyRows, ramp } = colorize(shown, view.color,
        { catLabels, unknown: t("drugmap.unknown"), t });
      await yieldFrame();
      if (my !== gen) return;
      const next = shown.map((d) => ({ drug: d, ...points.get(d.id), color: colorOf.get(d.id) }));
      plotTitleEl.textContent = plotTitle(view, {
        t, families: controls.families, systems: controls.groupsFor(view.sources),
        catName: (c) => (data.meta.drugCategoryPlurals || {})[c] || catLabels[c] || c, nameOf,
      });
      fitPoints(next);
      const prev = placed;
      placed = next;
      transition(prev, next);
      renderCaptions({ pcs, direct, keyRows, ramp, arch: pcs && pcs.length > 1 ? archScore(points.values()) : null, shown: shown.length, unplaced: kept.length - shown.length });
      const names = new Map(shown.map((d) => [d.id, d.displayName]));
      extras.update({
        view, t, nameOf, ids, profiles: prof, pcs, direct: direct ? view.only : null,
        drugName: (id) => names.get(id) || id,
        raw: () => buildProfiles(drugs, { ...view, normalize: false }),
      });
    } finally {
      // Always cancel this render's own timers, even when a newer one superseded it:
      // left armed, a stale timer would show the spinner after the newer render had
      // already hidden it, for good. Only the newest render hides the spinner.
      timers.forEach(clearTimeout);
      if (my === gen) busy.hidden = true;
    }
  }

  // Fit the data into the W x H frame, y up (a PCA has no preferred orientation, but a
  // plot reads with "more of PC2" upward), at ONE scale for both axes and centred, so a
  // distance on screen (and the grid's squares) means the same either way.
  // The top band is left to the plot title: its rendered height, plus one name line (a
  // name may sit above its dot, layout.js), turned into viewBox units (the svg
  // letterboxes the W x H frame, hence the larger of the two ratios).
  let fitTop = 0;
  function titlePad() {
    const w = svg.clientWidth, h = svg.clientHeight;
    if (!w || !h || !plotTitleEl.textContent) return 0;
    return Math.ceil((plotTitleEl.offsetHeight + TITLE_GAP_PX) * Math.max(W / w, H / h));
  }
  function fitPoints(pts) {
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    fitTop = titlePad();
    const aw = W - PAD - PAD_RIGHT, ah = H - 2 * PAD - fitTop;
    const s = Math.min(aw / (x1 - x0 || 1), ah / (y1 - y0 || 1));
    const ox = PAD + (aw - (x1 - x0) * s) / 2, oy = H - PAD - (ah - (y1 - y0) * s) / 2;
    for (const p of pts) {
      p.px = ox + (p.x - x0) * s;
      p.py = oy - (p.y - y0) * s;
    }
  }
  // The frame a null `box` shows: the whole W x H, or once rotated, the rotated points'
  // bounds grown to the plot's aspect ratio (so nothing turns out of view).
  function fitFrame() {
    if (!cam.angle || !placed.length) return { x: 0, y: 0, w: W, h: H };
    const q = placed.map((p) => rotate({ x: p.px, y: p.py }, cam.angle));
    const xs = q.map((p) => p.x), ys = q.map((p) => p.y);
    let [x0, x1, y0, y1] = [Math.min(...xs) - PAD, Math.max(...xs) + PAD_RIGHT, Math.min(...ys) - PAD, Math.max(...ys) + PAD];
    const w = Math.max(x1 - x0, (y1 - y0) * (W / H)), h = w * (H / W);
    return { x: (x0 + x1 - w) / 2, y: (y0 + y1 - h) / 2, w, h };
  }

  // ---- Transition: dots in both renders slide from their old place, new ones fade in,
  // gone ones fade out where they were. Names and the overlap nudge wait for the end.
  let anim = null;
  const reduceMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  function transition(prev, next) {
    const before = new Map(prev.map((p) => [p.drug.id, p]));
    const stays = new Set(next.map((p) => p.drug.id));
    if (!prev.length || reduceMotion()) { anim = null; drawPoints(); return; }
    for (const p of next) {
      const o = before.get(p.drug.id);
      p.from = o ? { px: o.px, py: o.py } : null;
    }
    anim = { t0: performance.now(), e: 0, ghosts: prev.filter((p) => !stays.has(p.drug.id)) };
    const step = (now) => {
      if (!anim) return;
      const k = Math.min(1, (now - anim.t0) / ANIM_MS);
      anim.e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2; // ease in-out
      if (k < 1) { drawPoints(); requestAnimationFrame(step); } else { anim = null; drawPoints(); }
    };
    requestAnimationFrame(step);
  }

  function renderCaptions({ pcs, direct, keyRows, ramp, arch, shown, unplaced }) {
    axes.replaceChildren(...(pcs
      ? pcs.map((ax, i) => {
        const ctx = { signed: view.signed, nameOf, t };
        const span = el("span", "dm-axis", axisCaption(ax, i, ctx));
        span.title = axisTooltip(ax, i, ctx);
        return span;
      })
      : direct ? view.only.map((key, i) => el("span", "dm-axis", t("drugmap.axisDirect", { axis: ["x →", "y ↑"][i], name: nameOf(key) })))
      : []));
    // Under the axes, the arch score (axis.js archScore): how far PC2 merely bends PC1.
    if (arch !== null) {
      const pct = Math.round(arch * 100);
      const span = el("span", "dm-axis dm-arch", t(pct >= ARCH_HIGH ? "drugmap.archHigh" : "drugmap.arch", { pct }));
      span.title = t("drugmap.archTip");
      axes.appendChild(span);
    }
    axesHead.textContent = pcs ? `${t("drugmap.sec.axes")}: ${t("drugmap.axesPca")}`
      : direct ? `${t("drugmap.sec.axes")}: ${t("drugmap.axesDirect")}` : "";
    legend.replaceChildren(...legendRows(keyRows, ramp));
    legendBox.setValue(ramp ? `${ramp.from}–${ramp.to}` : t("drugmap.keysN", { n: keyRows.length }));
    note.textContent = [
      t("drugmap.count", { n: shown }),
      unplaced ? t("drugmap.unplaced", { n: unplaced }) : "",
      t("drugmap.help"),
    ].filter(Boolean).join(" ");
  }

  // A dot and its name carry the same tooltip and name their drug (`data-drug`), which
  // focus.js reads to open it (click) or hide it (right-click, long-press).
  function linkDrug(node, p) {
    const title = svgEl("title");
    const yr = p.drug.firstApproval && p.drug.firstApproval.year;
    title.textContent = [p.drug.displayName, p.drug.categoryLabels.join(" · "), yr,
      p.drug.originator && p.drug.originator.name].filter(Boolean).join("\n");
    node.appendChild(title);
    node.dataset.drug = p.drug.id;
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

  // Points + names, laid out in screen pixels: the dot and name sizes follow how crowded
  // the visible points are (layout.js), touching dots are nudged apart (spread.js, with a
  // faint line back to the true place), and a name never covers a dot or another name.
  // Recomputed on every zoom / pan / turn; mid-transition only the moving dots are drawn.
  const measureCtx = document.createElement("canvas").getContext("2d");
  function drawPoints() {
    const b = cam.box || fitFrame();
    svg.setAttribute("viewBox", `${b.x} ${b.y} ${b.w} ${b.h}`);
    unrotate.hidden = !cam.angle;
    unrotate.textContent = `↻ ${Math.round(((cam.angle * 180 / Math.PI) % 360 + 540) % 360 - 180)}°`;
    const width = svg.clientWidth || W, height = svg.clientHeight || H;
    const k = b.w / width; // viewBox units per screen px
    const lerp = (p) => {
      if (!anim || !p.from) return { x: p.px, y: p.py };
      return { x: p.from.px + (p.px - p.from.px) * anim.e, y: p.from.py + (p.py - p.from.py) * anim.e };
    };
    const screen = placed.map((p) => {
      const q = rotate(lerp(p), cam.angle);
      return { id: p.drug.id, text: p.drug.name, p, vx: q.x, vy: q.y, x: (q.x - b.x) / k, y: (q.y - b.y) / k };
    });
    const inView = screen.filter((q) => q.x >= 0 && q.x <= width && q.y >= 0 && q.y <= height);
    const { font, r } = sizesFor(inView);
    const settled = !anim;
    const moved = settled && view.spread ? spreadPoints(inView, r) : new Map();
    const at = (q) => {
      const m = moved.get(q.id);
      return m ? { x: b.x + m.x * k, y: b.y + m.y * k } : { x: q.vx, y: q.vy };
    };
    const g = svgEl("g");
    g.appendChild(gridLines(b, k, cam.angle));
    for (const q of screen) {
      if (!moved.has(q.id)) continue;
      const m = at(q);
      g.appendChild(svgEl("line", { x1: q.vx, y1: q.vy, x2: m.x, y2: m.y, class: "dm-leader", "stroke-width": k }));
    }
    for (const q of screen) {
      const m = at(q);
      const c = svgEl("circle", { cx: m.x, cy: m.y, r: r * k, fill: q.p.color, class: "dm-point" });
      if (anim && !q.p.from) c.setAttribute("opacity", anim.e);
      linkDrug(c, q.p);
      g.appendChild(c);
    }
    for (const p of anim ? anim.ghosts : []) {
      const q = rotate({ x: p.px, y: p.py }, cam.angle);
      g.appendChild(svgEl("circle", { cx: q.x, cy: q.y, r: r * k, fill: p.color, class: "dm-ghost", opacity: 1 - anim.e }));
    }
    if (settled && view.labels) {
      measureCtx.font = `${font}px ${getComputedStyle(svg).fontFamily}`;
      const shifted = inView.map((q) => (moved.has(q.id) ? { ...q, ...moved.get(q.id) } : q));
      // The watermark sits over the plot's corner: names keep clear of it.
      const sr = svg.getBoundingClientRect(), wr = watermark.getBoundingClientRect();
      const avoid = wr.width ? [{ x: wr.left - sr.left, y: wr.top - sr.top, w: wr.width, h: wr.height }] : [];
      const names = placeLabels(shifted, { font, r, width, height, avoid, measure: (s) => measureCtx.measureText(s).width });
      for (const q of shifted) {
        const pos = names.get(q.id);
        if (!pos) continue;
        // A name floated away from a crowded dot (layout.js rings > 0) keeps a thin line back to it.
        if (pos.leader) {
          const L = pos.leader;
          const line = svgEl("line", { x1: b.x + L.x1 * k, y1: b.y + L.y1 * k, x2: b.x + L.x2 * k, y2: b.y + L.y2 * k,
            class: "dm-name-leader", "stroke-width": k });
          line.dataset.drug = q.id;
          g.appendChild(line);
        }
        const txt = svgEl("text", { x: b.x + pos.x * k, y: b.y + pos.y * k, class: "dm-label", "font-size": font * k });
        txt.textContent = q.text;
        linkDrug(txt, q.p);
        g.appendChild(txt);
      }
    }
    svg.replaceChildren(g);
    focus.draw({
      k, r, font, b,
      dots: screen.map((q) => {
        const m = at(q);
        return { id: q.id, p: q.p, x: m.x, y: m.y, sx: (m.x - b.x) / k, sy: (m.y - b.y) / k };
      }),
    });
  }

  return {
    render,
    /** Mirror the view into the URL, one key per control, absent at its default. */
    registerUrl(urlState) {
      const reg = (key, read, write) => urlState.register(key, {
        read,
        write: (v) => setView(write(v)),
        reset: () => setView({ ...DEFAULT_VIEW, hidden: new Set() }),
      });
      // An "on by default" switch is written only when off ("0"), the others when on.
      const flag = (key, field) => (DEFAULT_VIEW[field]
        ? reg(key, () => (view[field] ? null : "0"), (v) => ({ [field]: v !== "0" }))
        : reg(key, () => (view[field] ? "1" : null), (v) => ({ [field]: v === "1" })));
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
      flag("dmlabels", "labels");
      flag("dmspread", "spread");
      flag("dmnorm", "normalize");
      flag("dmsign", "signed");
      flag("dmmkt", "marketed");
      flag("dmki", "measuredKi");
      reg("dmsrc", () => (view.sources.join(LIST_SEP) !== DEFAULT_VIEW.sources.join(LIST_SEP) ? view.sources.join(LIST_SEP) : null),
        (v) => ({ sources: parseSources(v) }));
      // "-" = none picked (an empty value would read back as "every target").
      reg("dmtgt", () => (!view.only ? null : view.only.length ? view.only.join(LIST_SEP) : "-"),
        (v) => ({ only: !v ? null : v === "-" ? [] : v.split(LIST_SEP) }));
    },
  };
}

// Grid lines over the visible frame `b`, about GRID_PX apart on screen at a round step
// (1, 2 or 5 x 10^n viewBox units), so zooming in subdivides it rather than sliding it,
// and squares stay square (one scale for both axes). Drawn in the points' unrotated
// space and turned with them, so it stays aligned with the axes.
function gridLines(b, k, angle) {
  const raw = GRID_PX * k, mag = 10 ** Math.floor(Math.log10(raw));
  const step = mag * ([1, 2, 5, 10].find((m) => mag * m >= raw));
  // The visible frame's corners turned back into the unrotated space, and their bounds.
  const c = [[b.x, b.y], [b.x + b.w, b.y], [b.x, b.y + b.h], [b.x + b.w, b.y + b.h]]
    .map(([x, y]) => rotate({ x, y }, -angle));
  const [x0, x1] = [Math.min(...c.map((p) => p.x)), Math.max(...c.map((p) => p.x))];
  const [y0, y1] = [Math.min(...c.map((p) => p.y)), Math.max(...c.map((p) => p.y))];
  const g = svgEl("g", { class: "dm-grid", "stroke-width": k,
    transform: `rotate(${angle * 180 / Math.PI} ${W / 2} ${H / 2})` });
  for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
    g.appendChild(svgEl("line", { x1: x, x2: x, y1: y0, y2: y1 }));
  }
  for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
    g.appendChild(svgEl("line", { x1: x0, x2: x1, y1: y, y2: y }));
  }
  return g;
}

// The 3D viewer opened on one drug's tab (the `tabs` deep link, js/url-state.js).
const drugUrl = (drug) => `${viewerUrl()}#tabs=drug:${encodeURIComponent(drug.id)}`;
