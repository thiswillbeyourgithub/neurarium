/**
 * The Simulation (beta) tab: pick a few drugs, see what their combination does to
 * the modeled receptors and how that changes over the hours after a dose, then ask
 * the reverse question ("which drugs would give me this profile?").
 *
 * Everything quantitative lives in `js/sim-model.js`, whose header lists every
 * shortcut the maths takes; this file is the controller (state, sections, wiring)
 * and `js/sim-plots.js` the drawing. The split matters here more than elsewhere:
 * the tab is the one place in the app that computes a claim rather than reporting a
 * sourced one, so the assumptions have to stay readable in one file, and they are
 * repeated to the visitor in the warnings box at the top rather than buried in a
 * tooltip.
 *
 * No three.js and nothing outside `body` except the floating tooltip, which lives on
 * `<body>` while shown for the same reason `attachTip` does it (the panel scrolls and
 * clips).
 *
 * Built with the help of Claude Code.
 */

import { loadFlag, saveFlag } from "./prefs.js";
import {
  receptorProfile, ligandsOf, pkFlags, solveCombination,
  toAxis, fromAxis, TMAX_HOURS, P_FLOOR, ASSUMED_PKI,
} from "./sim-model.js";
import { buildPkPlot, buildRxPlot, formatKi, formatTime } from "./sim-plots.js";

/** "Include active metabolites", persisted like the Drugs section's own twin. */
const METAB_KEY = "neurarium.simMetabolites";

/**
 * The per-drug swatch palette. These are identity colours for up to six picked drugs,
 * not semantics, so they live here rather than in the theme tokens: they must stay
 * apart from each other (and from the effect colours the rest of the app uses) in
 * both themes, which is a property of the SET, not of either background.
 */
const DRUG_COLORS = [
  "#6aa9ff", "#ff9d5c", "#5fd0a6", "#e879c7", "#f2c14e", "#9b8cff",
  "#4fd0e0", "#ff7d7d",
];

/** How far a curve must fall before the time axis stops (5% of its own peak). */
const TAIL_FRACTION = 0.05;
const MIN_HOURS = 24;
const MAX_HOURS = 30 * 24;

/** Where a curve has decayed to `TAIL_FRACTION`, by doubling then bisecting. */
function tailEnd(curve) {
  if (!curve) return 0;
  let hi = Math.max(curve.tmax * 2, 1);
  let guard = 0;
  while (curve.at(hi) > TAIL_FRACTION && guard++ < 64) hi *= 1.6;
  let lo = curve.tmax;
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2;
    if (curve.at(mid) > TAIL_FRACTION) lo = mid; else hi = mid;
  }
  return hi;
}

/**
 * Build the Simulation tab into a (detached) container.
 *
 * @param {object} opts
 * @param {HTMLElement} opts.body the container to fill (#simulation-body)
 * @param {import("./data.js").BrainData} opts.data
 * @param {{t: Function, nav: {drug: Function}}} opts.deps
 * @param {{fold: Function}} opts.ui the search box's accent/Greek folding, reused so
 *   the pickers here match what the panel's own search box accepts
 * @returns {{open: () => void, setDrugs: (list: object[]) => void,
 *   getDrugs: () => Array<{id: string, ratio: number}>}}
 */
export function createSimulation({ body, data, deps, ui }) {
  const { t, nav } = deps;
  const { fold } = ui;

  // ---- state -------------------------------------------------------------
  /** `[{drug, ratio, hidden, color}]`, the picked list in display order. */
  let entries = [];
  let metabOn = loadFlag(METAB_KEY, true);
  let threshold = 0.3;
  let showUnknown = true;
  /** Hours since the shared dose the receptor plot is read at; null = each peak. */
  let scrubT = null;
  /** The solver's wish list: `[{id, name, axis}]`. */
  let wanted = [];
  let onlyListed = true;
  let maxDrugs = 3;
  let built = false;
  let onChange = () => {};

  const drugById = new Map((data.drugs || []).map((d) => [d.id, d]));
  const targetById = new Map((data.targets || []).map((tg) => [tg.id, tg]));
  const enzymeLabel = new Map((data.enzymes || []).map((e) => [e.id, e.label]));
  const meta = data.meta || {};
  const candidates = (data.drugs || []).filter((d) => d.focusable && !d.combo);

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const button = (cls, text, title) => {
    const b = el("button", cls, text);
    b.type = "button";
    if (title) b.title = title;
    return b;
  };

  // ---- the floating tooltip ---------------------------------------------
  // One bubble reused by both plots. It follows the pointer, which `attachTip` does
  // not do, so it is built here rather than borrowed; it wears `.help-tip` so it is
  // the same bubble a source pill shows.
  const tip = el("div", "help-tip sim-tip");
  const showTip = (text, clientX, clientY) => {
    tip.textContent = text;
    if (!tip.isConnected) document.body.appendChild(tip);
    tip.classList.add("show");
    const w = tip.offsetWidth, h = tip.offsetHeight;
    const left = Math.max(6, Math.min(clientX + 12, window.innerWidth - w - 6));
    const top = Math.max(6, Math.min(clientY - h - 12, window.innerHeight - h - 6));
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  };
  const hideTip = () => {
    tip.classList.remove("show");
    if (tip.isConnected) tip.remove();
  };

  // ---- helpers over the data --------------------------------------------
  const visibleEntries = () => entries.filter((e) => !e.hidden);
  const modelEntries = () => visibleEntries().map((e) => ({ drug: e.drug, ratio: e.ratio }));

  const systemLabel = (system) => (system
    ? (meta.receptorFamilyLabels || {})[system] || system
    : t("sim.systemOther"));
  /** A system's bar colour: the transmitter's own colour (meta.receptorFamilyColors,
   *  authored beside the arrow palette), so a serotonergic column reads the same here
   *  as its pathways do in the 3D scene and glutamate stays the excitatory red. A
   *  system with no entry returns null and the plot falls back to its neutral token. */
  const systemColor = (system) => (meta.receptorFamilyColors || {})[system] || null;
  const targetName = (id) => {
    const tg = targetById.get(id);
    return tg ? tg.name : id;
  };
  const targetSystem = (id) => {
    const tg = targetById.get(id);
    return tg ? tg.system : null;
  };

  /** Every ligand the visible list puts in circulation, keyed as the model keys it. */
  const ligandIndex = () => {
    const out = new Map();
    for (const e of visibleEntries()) {
      for (const lig of ligandsOf(e.drug, { metabolites: metabOn })) {
        out.set(lig.key, {
          name: lig.name, color: e.color, dim: !!lig.metabolite, curve: lig.curve,
          ratio: e.ratio,
        });
      }
    }
    return out;
  };

  // ---- section 1: the warnings box ---------------------------------------
  const warnBox = el("div", "sim-warn");
  const warnDyn = el("div", "sim-warn-dyn");

  const buildWarnStatic = () => {
    const head = el("div", "sim-warn-head");
    head.appendChild(el("span", "sim-warn-glyph", "⚠"));
    head.appendChild(el("span", "sim-warn-title", t("sim.warnTitle")));
    warnBox.appendChild(head);
    // Said before the bullets, not after them: a reader who stops at the first line
    // has to have been told that the list below is the known shortcuts and not the
    // complete set of them.
    warnBox.appendChild(el("p", "sim-warn-note", t("sim.warnNotExhaustive")));
    const list = el("ul", "sim-warn-list");
    const assumedKi = formatKi(Math.pow(10, 9 - ASSUMED_PKI));
    const bullets = [
      t("sim.warn.interactions"),
      t("sim.warn.halfLife"),
      t("sim.warn.plasma"),
      t("sim.warn.dose", { h: TMAX_HOURS }),
      t("sim.warn.endogenous"),
      t("sim.warn.additive"),
      t("sim.warn.unknown"),
      t("sim.warn.assumedKi", { ki: assumedKi }),
      t("sim.warn.metabolite"),
    ];
    for (const text of bullets) list.appendChild(el("li", null, text));
    warnBox.appendChild(list);
    warnBox.appendChild(warnDyn);
  };

  const renderWarnDynamic = (flags) => {
    warnDyn.textContent = "";
    const rows = [];
    const seen = new Set();
    for (const f of pkFlags(modelEntries())) {
      const key = `${f.kind}|${f.a}|${f.b}|${f.enzyme}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(t(`sim.flag.${f.kind}`, {
        a: f.a, b: f.b, enzyme: enzymeLabel.get(f.enzyme) || f.enzyme,
      }));
    }
    // The profile's own two flags, deduplicated: the model pushes one per ligand pass,
    // so a drug seen at two time points would otherwise be counted twice.
    const assumed = new Set(), unknown = new Set();
    for (const f of flags || []) {
      (f.kind === "assumedKi" ? assumed : unknown).add(`${f.ligand} · ${f.target}`);
    }
    if (!rows.length && !assumed.size && !unknown.size) return;
    warnDyn.appendChild(el("div", "sim-warn-sub", t("sim.warnBetween")));
    const list = el("ul", "sim-warn-list");
    for (const text of rows) list.appendChild(el("li", null, text));
    if (assumed.size || unknown.size) {
      const li = el("li", null, t("sim.flag.profile", {
        assumed: assumed.size, unknown: unknown.size,
      }));
      if (unknown.size) {
        const det = el("details", "sim-details");
        det.appendChild(el("summary", null, t("sim.flag.unknownList")));
        const sub = el("ul", "sim-warn-list");
        for (const line of [...unknown].sort()) sub.appendChild(el("li", null, line));
        det.appendChild(sub);
        li.appendChild(det);
      }
      list.appendChild(li);
    }
    warnDyn.appendChild(list);
  };

  // ---- a reusable inline search picker -----------------------------------
  /**
   * The "Add drug" / "Add receptor" affordance: a button that swaps itself for a
   * text input with up to `MAX_HITS` matching buttons under it. One implementation so
   * the two lists behave identically (same folding, same Escape, same re-collapse).
   */
  const MAX_HITS = 12;
  const makePicker = ({ label, placeholder, items, onPick }) => {
    const wrap = el("div", "sim-picker");
    const open = button("sim-add", label);
    const boxWrap = el("div", "sim-picker-box");
    boxWrap.hidden = true;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "drugs-filter";
    input.autocomplete = "off";
    input.placeholder = placeholder;
    const hits = el("div", "sim-hits");
    boxWrap.appendChild(input);
    boxWrap.appendChild(hits);
    wrap.appendChild(open);
    wrap.appendChild(boxWrap);

    const close = () => {
      boxWrap.hidden = true;
      open.hidden = false;
      input.value = "";
      hits.textContent = "";
    };
    const refresh = () => {
      const q = fold(input.value.trim());
      hits.textContent = "";
      const pool = items();
      const found = (q ? pool.filter((it) => it.folded.includes(q)) : pool)
        .slice(0, MAX_HITS);
      if (!found.length) {
        hits.appendChild(el("div", "sim-nohit", t("sim.noMatch")));
        return;
      }
      for (const it of found) {
        const b = button("sim-hit", it.label);
        b.addEventListener("click", () => { onPick(it); close(); });
        hits.appendChild(b);
      }
    };
    open.addEventListener("click", () => {
      open.hidden = true;
      boxWrap.hidden = false;
      refresh();
      input.focus();
    });
    input.addEventListener("input", refresh);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") { ev.stopPropagation(); close(); }
    });
    return wrap;
  };

  // ---- section 2: the drug list ------------------------------------------
  const drugSec = el("section", "sim-sec");
  const drugList = el("div", "sim-list");
  const emptyNote = el("p", "sim-empty", t("sim.empty"));

  const freeColor = () => {
    const used = new Set(entries.map((e) => e.color));
    return DRUG_COLORS.find((c) => !used.has(c)) || DRUG_COLORS[entries.length % DRUG_COLORS.length];
  };

  const addDrug = (drug, ratio = 1) => {
    if (!drug || entries.some((e) => e.drug.id === drug.id)) return;
    entries.push({ drug, ratio: Math.max(0.1, ratio), hidden: false, color: freeColor() });
    renderAll();
  };

  const renderDrugRows = () => {
    drugList.textContent = "";
    emptyNote.hidden = entries.length > 0;
    for (const e of entries) {
      const row = el("div", e.hidden ? "sim-row muted" : "sim-row");
      const sw = button("sim-swatch", null, t("sim.toggleVisible"));
      sw.style.background = e.color;
      sw.setAttribute("aria-pressed", String(!e.hidden));
      sw.addEventListener("click", () => { e.hidden = !e.hidden; renderAll(); });
      row.appendChild(sw);

      const name = button("sim-name", e.drug.displayName || e.drug.name, t("sim.openPanel"));
      name.addEventListener("click", () => nav.drug(e.drug));
      row.appendChild(name);

      const stepper = el("div", "sim-ratio");
      const minus = button("sim-step", "−", t("sim.less"));
      const num = document.createElement("input");
      num.type = "number";
      num.step = "0.1";
      num.min = "0.1";
      num.className = "sim-ratio-input";
      num.value = String(Number(e.ratio.toFixed(2)));
      num.title = t("sim.ratioHint");
      num.setAttribute("aria-label", t("sim.ratio"));
      const plus = button("sim-step", "+", t("sim.more"));
      const setRatio = (v) => {
        e.ratio = Math.max(0.1, Math.round(v * 10) / 10);
        num.value = String(Number(e.ratio.toFixed(2)));
        renderAll();
      };
      minus.addEventListener("click", () => setRatio(e.ratio - 0.1));
      plus.addEventListener("click", () => setRatio(e.ratio + 0.1));
      num.addEventListener("change", () => setRatio(Number(num.value) || 0.1));
      stepper.appendChild(minus);
      stepper.appendChild(num);
      stepper.appendChild(plus);
      row.appendChild(stepper);

      const rm = button("sim-remove", "×", t("sim.remove"));
      rm.addEventListener("click", () => {
        entries = entries.filter((o) => o !== e);
        renderAll();
      });
      row.appendChild(rm);
      drugList.appendChild(row);
    }
  };

  const buildDrugSection = () => {
    drugSec.appendChild(el("h3", "sim-h", t("sim.drugs")));
    drugSec.appendChild(emptyNote);
    drugSec.appendChild(drugList);
    drugSec.appendChild(makePicker({
      label: t("sim.addDrug"),
      placeholder: t("sim.searchDrug"),
      items: () => candidates
        .filter((d) => !entries.some((e) => e.drug.id === d.id))
        .map((d) => ({
          drug: d,
          label: d.displayName || d.name,
          folded: fold(`${d.name} ${d.displayName || ""} ${d.keywords || ""}`),
        })),
      onPick: (it) => addDrug(it.drug),
    }));
    const metabLabel = el("label", "list-toggle");
    const metabBox = document.createElement("input");
    metabBox.type = "checkbox";
    metabBox.id = "sim-metabolites";
    metabBox.checked = metabOn;
    metabBox.addEventListener("change", () => {
      metabOn = metabBox.checked;
      saveFlag(METAB_KEY, metabOn);
      renderAll();
    });
    metabLabel.appendChild(metabBox);
    metabLabel.appendChild(el("span", null, t("sim.metabolites")));
    drugSec.appendChild(metabLabel);
  };

  // ---- section 3: the plasma plot ----------------------------------------
  const pkSec = el("section", "sim-sec");
  const pkHost = el("div", "sim-plot-host");
  const pkLegend = el("div", "sim-legend");
  const pkRead = el("div", "sim-readout");
  let pkPlot = null;
  let pkLines = [];

  const buildPkSection = () => {
    pkSec.appendChild(el("h3", "sim-h", t("sim.pkTitle")));
    pkSec.appendChild(el("p", "sim-caption", t("sim.pkCaption", { h: TMAX_HOURS })));
    pkSec.appendChild(pkHost);
    pkSec.appendChild(pkRead);
    pkSec.appendChild(pkLegend);
  };

  let scrubPending = null;
  let scrubFrame = 0;
  const flushScrub = () => {
    scrubFrame = 0;
    scrubT = scrubPending;
    pkPlot?.setCursor(scrubT);
    renderReadout();
    renderRx();
  };
  const queueScrub = (h) => {
    scrubPending = h;
    if (!scrubFrame) scrubFrame = requestAnimationFrame(flushScrub);
  };

  const renderReadout = () => {
    if (scrubT == null) { pkRead.textContent = t("sim.pkAtPeak"); return; }
    const parts = pkLines.map((l) => `${l.name} ${Math.round(l.at(scrubT) * 100)}%`);
    pkRead.textContent = `${formatTime(scrubT, t)} · ${parts.join(" · ")}`;
  };

  const renderPk = () => {
    pkHost.textContent = "";
    pkLegend.textContent = "";
    pkPlot = null;
    pkLines = [];
    const raw = [];
    for (const e of visibleEntries()) {
      for (const lig of ligandsOf(e.drug, { metabolites: metabOn })) {
        if (!lig.curve) continue;
        raw.push({ name: lig.name, color: e.color, dashed: !!lig.metabolite,
          curve: lig.curve, ratio: e.ratio });
      }
    }
    if (!raw.length) {
      pkHost.appendChild(el("p", "sim-empty", t("sim.pkNone")));
      pkRead.textContent = "";
      return;
    }
    const norm = Math.max(...raw.map((l) => l.ratio)) || 1;
    pkLines = raw.map((l) => ({
      name: l.name, color: l.color, dashed: l.dashed,
      at: (h) => (l.ratio * l.curve.at(h)) / norm,
    }));
    const tEnd = Math.min(MAX_HOURS, Math.max(MIN_HOURS, ...raw.map((l) => tailEnd(l.curve))));
    pkPlot = buildPkPlot({ lines: pkLines, tEnd, t });
    pkHost.appendChild(pkPlot.svg);
    pkPlot.setCursor(scrubT);
    for (const l of raw) {
      const item = el("span", "sim-legend-item");
      const dot = el("span", l.dashed ? "sim-legend-dot dashed" : "sim-legend-dot");
      // A dashed key draws its stroke as a border, which reads `currentcolor`; a
      // solid one is a filled block. Setting both leaves one rule to pick between.
      dot.style.background = l.color;
      dot.style.color = l.color;
      item.appendChild(dot);
      item.appendChild(el("span", null, l.name));
      pkLegend.appendChild(item);
    }
    // Pointer, not mouse: one path covers hover, drag and touch, and `touch-action:
    // none` on the svg (index.html) keeps a scrub from scrolling the panel instead.
    const onMove = (ev) => {
      const h = pkPlot.timeAt(ev.clientX);
      if (h == null) return;
      queueScrub(h);
      const lines = pkLines.map((l) => `${l.name}: ${Math.round(l.at(h) * 100)}%`);
      showTip(`${formatTime(h, t)}\n${lines.join("\n")}`, ev.clientX, ev.clientY);
    };
    pkPlot.svg.addEventListener("pointermove", onMove);
    pkPlot.svg.addEventListener("pointerdown", onMove);
    pkPlot.svg.addEventListener("pointerleave", () => { queueScrub(null); hideTip(); });
    pkPlot.svg.addEventListener("pointercancel", () => { queueScrub(null); hideTip(); });
  };

  // ---- section 4: the receptor plot --------------------------------------
  const rxSec = el("section", "sim-sec");
  const rxHost = el("div", "sim-plot-host sim-scroll");
  const rxControls = el("div", "sim-controls");
  let rxCols = [];

  const axisScaleLine = () => {
    const parts = [];
    for (let k = 1; k <= 5; k++) parts.push(`${k} = ${formatKi(1 / fromAxis(k))}`);
    return parts.join(", ");
  };

  const buildRxSection = () => {
    rxSec.appendChild(el("h3", "sim-h", t("sim.rxTitle")));
    const thrWrap = el("label", "sim-slider");
    thrWrap.appendChild(el("span", null, t("sim.rxThreshold")));
    const thr = document.createElement("input");
    thr.type = "range";
    thr.min = "0";
    thr.max = "4";
    thr.step = "0.1";
    thr.value = String(threshold);
    thr.id = "sim-threshold";
    const thrVal = el("span", "sim-slider-val", threshold.toFixed(1));
    thr.addEventListener("input", () => {
      threshold = Number(thr.value);
      thrVal.textContent = threshold.toFixed(1);
      renderRx();
    });
    thrWrap.appendChild(thr);
    thrWrap.appendChild(thrVal);
    rxControls.appendChild(thrWrap);
    const unkLabel = el("label", "list-toggle");
    const unkBox = document.createElement("input");
    unkBox.type = "checkbox";
    unkBox.id = "sim-show-unknown";
    unkBox.checked = showUnknown;
    unkBox.addEventListener("change", () => { showUnknown = unkBox.checked; renderRx(); });
    unkLabel.appendChild(unkBox);
    unkLabel.appendChild(el("span", null, t("sim.rxUnknownToggle")));
    rxControls.appendChild(unkLabel);
    rxSec.appendChild(rxControls);
    rxSec.appendChild(rxHost);
    rxSec.appendChild(el("p", "sim-caption", t("sim.rxCaption", {
      floor: formatKi(1 / P_FLOOR), scale: axisScaleLine(),
    })));
  };

  /** One column's tooltip: what is engaged, how hard, and by whom. */
  const colTipText = (col) => {
    const lines = [`${col.name} · ${col.systemLabel}`];
    const say = (key, axis, linear) => {
      if (!axis) return;
      lines.push(`${t(key)}: ${Math.abs(axis).toFixed(2)} (${formatKi(1 / Math.abs(linear))})`);
    };
    say("sim.rxBoost", col.boostAxis, col.boost);
    say("sim.rxBlock", col.blockAxis, col.block);
    say("sim.rxUnknown", col.unknownAxis, col.unknown);
    lines.push(`${t("sim.rxNet")}: ${col.netAxis >= 0 ? "+" : ""}${col.netAxis.toFixed(2)}`);
    lines.push(t("sim.rxWhich"));
    for (const seg of [...col.up, ...col.down]) {
      lines.push(`  ${seg.name}: ${formatKi(1 / Math.abs(seg.value))}`);
    }
    return lines.join("\n");
  };

  const renderRx = () => {
    rxHost.textContent = "";
    const list = modelEntries();
    if (!list.length) {
      rxHost.appendChild(el("p", "sim-empty", t("sim.rxNone")));
      rxCols = [];
      renderWarnDynamic([]);
      return;
    }
    const prof = receptorProfile(list, { t: scrubT, metabolites: metabOn });
    renderWarnDynamic(prof.flags);
    const ligs = ligandIndex();
    const segsOf = (perLigand, positive) => {
      const raw = [...perLigand.entries()]
        .filter(([, v]) => (positive ? v > 0 : v < 0))
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
      const sum = raw.reduce((s, [, v]) => s + Math.abs(v), 0) || 1;
      return raw.map(([key, v], i) => {
        const info = ligs.get(key) || {};
        // `color` is the drug's own swatch, kept for the tooltip and the picked list;
        // the bar itself is painted in its receptor's transmitter colour, so a stack of
        // two drugs is told apart by `shade` (see buildRxPlot) rather than by hue.
        return { key, name: info.name || key, color: info.color || DRUG_COLORS[0],
          shade: i, dim: !!info.dim, frac: Math.abs(v) / sum, value: v };
      });
    };
    rxCols = prof.rows.map((row) => {
      const boostAxis = toAxis(row.boost);
      const blockAxis = toAxis(row.block);
      const unknownAxis = toAxis(row.unknown);
      const system = targetSystem(row.target);
      return {
        target: row.target, name: targetName(row.target), system,
        systemLabel: systemLabel(system), systemColor: systemColor(system),
        boost: row.boost, block: row.block, unknown: row.unknown,
        boostAxis, blockAxis, unknownAxis,
        netAxis: toAxis(row.boost + row.block),
        up: segsOf(row.perLigand, true), down: segsOf(row.perLigand, false),
      };
    }).filter((c) => Math.max(
      Math.abs(c.boostAxis), Math.abs(c.blockAxis),
      showUnknown ? c.unknownAxis : 0) >= threshold);

    if (!rxCols.length) {
      rxHost.appendChild(el("p", "sim-empty", t("sim.rxNone")));
      return;
    }
    // Systems lead with the one the combination hits hardest, so the reason a drug
    // was picked is the first group read; the system-less bucket is pinned last.
    const groups = new Map();
    for (const c of rxCols) {
      const key = c.system || "";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(c);
    }
    const order = [...groups.keys()].sort((a, b) => {
      if (!a !== !b) return a ? -1 : 1;
      const peak = (k) => Math.max(...groups.get(k).map((c) => Math.abs(c.netAxis)));
      return peak(b) - peak(a);
    });
    rxCols = [];
    for (const key of order) {
      const members = groups.get(key)
        .sort((a, b) => Math.abs(b.netAxis) - Math.abs(a.netAxis));
      members.forEach((c, i) => { c.groupStart = i === 0; });
      rxCols.push(...members);
    }
    const plot = buildRxPlot({
      cols: rxCols, showUnknown, t,
      segTitle: (col, seg) => `${seg.name} · ${col.name}: ${formatKi(1 / Math.abs(seg.value))}`,
    });
    rxHost.appendChild(plot.svg);
    const onMove = (ev) => {
      const col = plot.colAt(ev.clientX);
      plot.setHover(col);
      if (col) showTip(colTipText(col), ev.clientX, ev.clientY);
      else hideTip();
    };
    plot.svg.addEventListener("pointermove", onMove);
    plot.svg.addEventListener("pointerdown", onMove);
    plot.svg.addEventListener("pointerleave", () => { plot.setHover(null); hideTip(); });
    plot.svg.addEventListener("pointercancel", () => { plot.setHover(null); hideTip(); });
  };

  // ---- section 5: the target profile + solver -----------------------------
  const solveSec = el("section", "sim-sec");
  const wantList = el("div", "sim-list");
  const solveOut = el("div", "sim-solve-out");
  let solveBtn = null;

  const renderWanted = () => {
    wantList.textContent = "";
    for (const w of wanted) {
      const row = el("div", "sim-row sim-want");
      row.appendChild(el("span", "sim-name-static", w.name));
      const range = document.createElement("input");
      range.type = "range";
      range.min = "-4";
      range.max = "4";
      range.step = "0.1";
      range.value = String(w.axis);
      range.setAttribute("aria-label", w.name);
      const val = el("span", "sim-slider-val");
      const paint = () => {
        const dir = w.axis === 0 ? "" : t(w.axis > 0 ? "sim.boostLabel" : "sim.blockLabel");
        val.textContent = `${w.axis > 0 ? "+" : ""}${w.axis.toFixed(1)} ${dir}`.trim();
      };
      paint();
      range.addEventListener("input", () => {
        w.axis = Number(range.value);
        paint();
      });
      row.appendChild(range);
      row.appendChild(val);
      const rm = button("sim-remove", "×", t("sim.remove"));
      rm.addEventListener("click", () => {
        wanted = wanted.filter((o) => o !== w);
        renderWanted();
      });
      row.appendChild(rm);
      wantList.appendChild(row);
    }
  };

  const runSolver = () => {
    solveOut.textContent = "";
    if (!wanted.length) {
      solveOut.appendChild(el("p", "sim-empty", t("sim.solveEmpty")));
      return;
    }
    solveBtn.disabled = true;
    solveBtn.textContent = t("sim.solving");
    // The solve is synchronous and takes a few hundred ms; yielding once lets the
    // disabled state paint, so the button does not look inert while it works.
    setTimeout(() => {
      let res;
      try {
        res = solveCombination(
          new Map(wanted.map((w) => [w.id, fromAxis(w.axis)])),
          candidates,
          { fixed: entries.map((e) => ({ drug: e.drug, ratio: e.ratio })),
            onlyListed, maxDrugs, metabolites: metabOn });
      } finally {
        solveBtn.disabled = false;
        solveBtn.textContent = t("sim.solve");
      }
      solveOut.textContent = "";
      solveOut.appendChild(el("p", "sim-fit",
        t("sim.fit", { pct: Math.round(res.fit * 100), n: res.rows })));
      if (!res.picks.length) {
        solveOut.appendChild(el("p", "sim-empty", t("sim.noPicks")));
        return;
      }
      const picks = res.picks.map((p) => ({
        drug: p.drug, ratio: Math.max(0.1, Math.round(p.ratio * 10) / 10), opposes: p.opposes,
      }));
      for (const p of picks) {
        const row = el("div", "sim-row");
        row.appendChild(el("span", "sim-name-static",
          `${p.drug.displayName || p.drug.name} × ${p.ratio.toFixed(1)}`));
        // A pick pulling against a wish only makes sense as a correction of what
        // the listed drugs overshoot; say so, or the pick reads as a wrong answer.
        if (p.opposes && p.opposes.length) {
          const names = p.opposes.map((id) => (targetById.get(id) || { name: id }).name).join(", ");
          row.appendChild(el("span", "sim-caption", t("sim.pickOpposes", { targets: names })));
        }
        const add = button("sim-add small", t("sim.addPick"));
        add.addEventListener("click", () => addDrug(p.drug, p.ratio));
        row.appendChild(add);
        solveOut.appendChild(row);
      }
      const all = button("sim-add", t("sim.addAll"));
      all.addEventListener("click", () => {
        for (const p of picks) addDrug(p.drug, p.ratio);
      });
      solveOut.appendChild(all);
      solveOut.appendChild(el("p", "sim-caption", t("sim.solveNote")));
    }, 0);
  };

  const buildSolveSection = () => {
    solveSec.appendChild(el("h3", "sim-h", t("sim.solveTitle")));
    solveSec.appendChild(el("p", "sim-caption", t("sim.solveCaption")));
    solveSec.appendChild(wantList);
    const picker = makePicker({
      label: t("sim.addReceptor"),
      placeholder: t("sim.searchReceptor"),
      items: () => (data.targets || [])
        .filter((tg) => !wanted.some((w) => w.id === tg.id))
        .map((tg) => ({ id: tg.id, name: tg.name, label: tg.name,
          folded: fold(`${tg.name} ${tg.keywords || ""}`) })),
      onPick: (it) => { wanted.push({ id: it.id, name: it.name, axis: 0 }); renderWanted(); },
    });
    solveSec.appendChild(picker);
    const useCur = button("sim-add", t("sim.useCurrent"), t("sim.useCurrentHint"));
    useCur.addEventListener("click", () => {
      wanted = rxCols
        .filter((c) => Math.abs(c.netAxis) >= 0.05)
        .map((c) => ({ id: c.target, name: c.name,
          axis: Math.max(-4, Math.min(4, Math.round(c.netAxis * 10) / 10)) }));
      renderWanted();
    });
    solveSec.appendChild(useCur);

    const opts = el("div", "sim-controls");
    const onlyLabel = el("label", "list-toggle");
    const onlyBox = document.createElement("input");
    onlyBox.type = "checkbox";
    onlyBox.id = "sim-only-listed";
    onlyBox.checked = onlyListed;
    onlyBox.addEventListener("change", () => { onlyListed = onlyBox.checked; });
    onlyLabel.appendChild(onlyBox);
    onlyLabel.appendChild(el("span", null, t("sim.onlyListed")));
    onlyLabel.title = t("sim.onlyListedHint");
    opts.appendChild(onlyLabel);
    const maxLabel = el("label", "sim-slider");
    maxLabel.appendChild(el("span", null, t("sim.maxDrugs")));
    const maxIn = document.createElement("input");
    maxIn.type = "number";
    maxIn.min = "1";
    maxIn.max = "6";
    maxIn.step = "1";
    maxIn.value = String(maxDrugs);
    maxIn.className = "sim-ratio-input";
    maxIn.id = "sim-max-drugs";
    maxIn.addEventListener("change", () => {
      maxDrugs = Math.max(1, Math.min(6, Number(maxIn.value) || 3));
      maxIn.value = String(maxDrugs);
    });
    maxLabel.appendChild(maxIn);
    opts.appendChild(maxLabel);
    solveSec.appendChild(opts);
    solveSec.appendChild(el("p", "sim-caption", t("sim.onlyListedHint")));
    solveBtn = button("sim-solve", t("sim.solve"));
    solveBtn.addEventListener("click", runSolver);
    solveSec.appendChild(solveBtn);
    solveSec.appendChild(solveOut);
  };

  // ---- assembly -----------------------------------------------------------
  function renderAll() {
    if (!built) return;
    renderDrugRows();
    renderPk();
    renderRx();
    renderReadout();
    onChange();
  }

  const build = () => {
    if (built) return;
    built = true;
    buildWarnStatic();
    buildDrugSection();
    buildPkSection();
    buildRxSection();
    buildSolveSection();
    // The lead states the question the tab answers in both directions, and the unit
    // it answers it in, before the warnings box qualifies that answer.
    const lead = el("div", "sim-lead");
    lead.appendChild(el("p", null, t("sim.lead")));
    lead.appendChild(el("p", "sim-lead-unit", t("sim.leadUnit")));
    body.appendChild(lead);
    body.appendChild(warnBox);
    body.appendChild(drugSec);
    body.appendChild(pkSec);
    body.appendChild(rxSec);
    body.appendChild(solveSec);
    renderWanted();
    renderAll();
  };

  return {
    /** Build on first use; a no-op on every reopen. */
    open() { build(); },
    /** Called after any change to the drug list, so the URL can follow it. */
    setOnChange(fn) { onChange = fn || (() => {}); },
    /** Replace the picked list (a deep link). Unknown ids are skipped. */
    setDrugs(list) {
      entries = [];
      for (const item of list || []) {
        const drug = drugById.get(item.id);
        if (!drug || entries.some((e) => e.drug.id === drug.id)) continue;
        entries.push({
          drug, ratio: Math.max(0.1, Number(item.ratio) || 1), hidden: false,
          color: DRUG_COLORS[entries.length % DRUG_COLORS.length],
        });
      }
      renderAll();
    },
    /** The picked list as `[{id, ratio}]`, in display order. */
    getDrugs() {
      return entries.map((e) => ({ id: e.drug.id, ratio: e.ratio }));
    },
  };
}
