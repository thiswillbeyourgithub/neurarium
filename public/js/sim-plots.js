/**
 * The two inline-SVG plots of the Simulation tab, split from `js/simulation.js` so
 * that file stays the controller (state, sections, wiring) and this one stays the
 * drawing: given already-computed rows it returns an `<svg>` plus the few readers the
 * controller needs to answer a pointer (which time, which column). Nothing here reads
 * the dataset, the model or `localStorage`, so a plot can be reasoned about from its
 * arguments alone.
 *
 * Both plots are `viewBox` + `width: 100%`, so they scale with the panel instead of
 * being re-laid-out on every resize, and both take their ink from the `--sem-*` /
 * `--ink` / `--muted` tokens through CSS classes (see the `.sim-*` rules in
 * index.html); only the per-drug swatch colours arrive as values, since they are a
 * palette the controller cycles rather than a theme decision.
 *
 * Built with the help of Claude Code.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

/** One SVG element with its attributes, the shorthand the whole module is written in. */
export function svg(tag, attrs = {}, text = null) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v != null) n.setAttribute(k, String(v));
  }
  if (text != null) n.textContent = text;
  return n;
}

/**
 * A dissociation constant as the reader meets it in the panels: nM up to a micromolar,
 * then µM, then mM. Two significant digits, because the third would claim a precision
 * a median over a handful of assays does not have.
 */
export function formatKi(nM) {
  if (!(nM > 0) || !Number.isFinite(nM)) return "-";
  if (nM >= 1e6) return `${Number((nM / 1e6).toPrecision(2))} mM`;
  if (nM >= 1e3) return `${Number((nM / 1e3).toPrecision(2))} µM`;
  return `${Number(nM.toPrecision(2))} nM`;
}

/**
 * A tick step that keeps at most ~8 labels on the time axis. The candidates are the
 * durations a reader already thinks in (hours, then half-days, then days and weeks),
 * so a 10-day range is labelled every 2 days rather than every 38.4 hours.
 */
function timeStep(span) {
  for (const c of [1, 2, 3, 6, 12, 24, 48, 72, 120, 168, 336, 720]) {
    if (span / c <= 8) return c;
  }
  return span / 8;
}

/** A time label in hours below half a week, in days above it. */
export function formatTime(hours, t) {
  if (hours >= 48) return t("sim.pkDays", { n: Number((hours / 24).toPrecision(3)) });
  return t("sim.pkHours", { n: Number(hours.toPrecision(3)) });
}

/**
 * The plasma plot: one line per ligand over a shared single dose at t = 0.
 *
 * @param {object} opts
 * @param {Array<{key: string, name: string, color: string, dashed: boolean,
 *   at: (h: number) => number}>} opts.lines already ratio-scaled and normalized to
 *   the tallest peak, so the y domain is a flat 0..1
 * @param {number} opts.tEnd the right edge, in hours
 * @param {Function} opts.t the i18n lookup
 * @returns {{svg: SVGElement, timeAt: (clientX: number) => number|null,
 *   setCursor: (h: number|null) => void}}
 */
export function buildPkPlot({ lines, tEnd, t }) {
  const W = 520, H = 210;
  const M = { left: 34, right: 12, top: 10, bottom: 30 };
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  const root = svg("svg", {
    class: "sim-plot sim-pk", viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: "xMidYMid meet", role: "img",
    "aria-label": t("sim.pkTitle"),
  });
  const xOf = (h) => M.left + (tEnd > 0 ? (h / tEnd) * plotW : 0);
  const yOf = (v) => M.top + plotH * (1 - Math.max(0, Math.min(1, v)));

  // Horizontal guides at 0 / 50 / 100 %, the only y reading that means anything here
  // (the curves are relative, there is no concentration unit in the data).
  for (const frac of [0, 0.5, 1]) {
    root.appendChild(svg("line", {
      class: "sim-grid", x1: M.left, x2: W - M.right, y1: yOf(frac), y2: yOf(frac),
    }));
    root.appendChild(svg("text", {
      class: "sim-tick", x: M.left - 6, y: yOf(frac) + 3, "text-anchor": "end",
    }, `${Math.round(frac * 100)}%`));
  }
  const step = timeStep(tEnd);
  for (let h = 0; h <= tEnd + 1e-6; h += step) {
    root.appendChild(svg("line", {
      class: "sim-axis-tick", x1: xOf(h), x2: xOf(h), y1: yOf(0), y2: yOf(0) + 4,
    }));
    root.appendChild(svg("text", {
      class: "sim-tick", x: xOf(h), y: yOf(0) + 15, "text-anchor": "middle",
    }, step >= 24 ? String(Math.round(h / 24)) : String(Math.round(h))));
  }
  root.appendChild(svg("text", {
    class: "sim-tick sim-axis-name", x: W - M.right, y: H - 4, "text-anchor": "end",
  }, step >= 24 ? t("sim.pkAxisDays") : t("sim.pkAxisHours")));

  // 240 samples across the range: enough that an absorption peak two hours into a
  // thirty-day window is still a corner rather than a straight cut.
  const N = 240;
  for (const line of lines) {
    const pts = [];
    for (let i = 0; i <= N; i++) {
      const h = (i / N) * tEnd;
      pts.push(`${xOf(h).toFixed(2)},${yOf(line.at(h)).toFixed(2)}`);
    }
    const el = svg("polyline", {
      class: "sim-line", points: pts.join(" "), stroke: line.color,
      "stroke-dasharray": line.dashed ? "5 3" : null,
    });
    el.appendChild(svg("title", {}, line.name));
    root.appendChild(el);
  }

  const cursor = svg("line", {
    class: "sim-cursor", x1: 0, x2: 0, y1: M.top, y2: M.top + plotH,
  });
  cursor.setAttribute("visibility", "hidden");
  root.appendChild(cursor);

  return {
    svg: root,
    timeAt(clientX) {
      const r = root.getBoundingClientRect();
      if (!r.width) return null;
      const vx = ((clientX - r.left) / r.width) * W;
      const frac = (vx - M.left) / plotW;
      return Math.max(0, Math.min(1, frac)) * tEnd;
    },
    setCursor(h) {
      if (h == null) { cursor.setAttribute("visibility", "hidden"); return; }
      cursor.setAttribute("visibility", "visible");
      cursor.setAttribute("x1", String(xOf(h)));
      cursor.setAttribute("x2", String(xOf(h)));
    },
  };
}

const COL_W = 26;      // one target column
const GROUP_GAP = 12;  // the breathing space between two neurotransmitter systems
// How far a stack's successive ligands step down in opacity, strongest first. It stops
// at four because a fifth contributor to ONE receptor is already unreadable as a band,
// and the tooltip is what answers there; every step past the fourth reuses the last.
const SEG_SHADES = [1, 0.72, 0.52, 0.36];

/**
 * The receptor plot: one column per engaged target, grouped by neurotransmitter
 * system. Above the zero line the boost stack (plus, on top of it, the hatched band
 * for bindings nobody sourced a direction for), below it the block stack, each split
 * into one segment per ligand so a bar says WHICH drug carries it. A short horizontal
 * rule per column marks the net.
 *
 * @param {object} opts
 * @param {Array<object>} opts.cols one per target, in draw order, each
 *   `{target, name, systemLabel, systemColor, boostAxis, blockAxis, unknownAxis,
 *     netAxis, up: [{key, color, shade, frac, dim}], down: [...], groupStart: boolean}`
 *   (a segment's `shade` is its rank in the stack, which picks its opacity; `color` is
 *   the drug's own swatch, used by the caller's tooltip, not by the fill)
 *   (`systemColor` null for a system with no modeled projection kind: the strip and
 *   the group label then fall back to the neutral token in the stylesheet)
 * @param {boolean} opts.showUnknown draw the hatched direction-less band
 * @param {Function} opts.t the i18n lookup
 * @param {Function} opts.segTitle `(col, seg) => string`, a segment's `<title>`
 * @returns {{svg: SVGElement, colAt: (clientX: number) => object|null,
 *   setHover: (col: object|null) => void}}
 */
export function buildRxPlot({ cols, showUnknown, t, segTitle }) {
  const M = { left: 46, right: 14, top: 12 };
  const plotH = 230, labelBand = 74, systemBand = 20;
  // Each group opens with a gap, so a column's x is its index plus the groups before it.
  let x = M.left;
  for (const col of cols) {
    if (col.groupStart && col !== cols[0]) x += GROUP_GAP;
    col.x = x;
    x += COL_W;
  }
  const W = Math.max(320, x + M.right);
  const H = M.top + plotH + labelBand + systemBand;
  const root = svg("svg", {
    class: "sim-plot sim-rx", viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: "xMidYMid meet", role: "img",
    "aria-label": t("sim.rxTitle"),
  });

  const defs = svg("defs");
  const pat = svg("pattern", {
    id: "sim-unknown-hatch", width: 6, height: 6,
    patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)",
  });
  pat.appendChild(svg("rect", { class: "sim-unknown-bg", width: 6, height: 6 }));
  pat.appendChild(svg("line", { class: "sim-unknown-line", x1: 0, y1: 0, x2: 0, y2: 6 }));
  defs.appendChild(pat);
  root.appendChild(defs);

  // Asymmetric domain: the axis gives each side exactly the room its tallest stack
  // needs, so a pure antagonist does not draw half an empty plot above the zero line.
  let up = 0, down = 0;
  for (const c of cols) {
    up = Math.max(up, c.boostAxis + (showUnknown ? c.unknownAxis : 0), c.netAxis);
    down = Math.max(down, -c.blockAxis, -c.netAxis);
  }
  const total = Math.max(1, up + down);
  const zeroY = M.top + plotH * (up / total);
  const yOf = (axis) => zeroY - (axis / total) * plotH;

  // Integer ticks only, each labelled with the Ki a single binding would need to reach
  // it: the axis is a log, so the labels are what makes it readable.
  for (let k = -Math.floor(down); k <= Math.floor(up); k++) {
    const y = yOf(k);
    root.appendChild(svg("line", {
      class: k === 0 ? "sim-axis" : "sim-grid", x1: M.left - 4, x2: W - M.right, y1: y, y2: y,
    }));
    root.appendChild(svg("text", {
      class: "sim-tick", x: M.left - 7, y: y + 3, "text-anchor": "end",
    }, k === 0 ? "0" : String(Math.abs(k))));
  }

  // A column is painted in its receptor's transmitter colour (the one its pathways
  // wear in the 3D scene), so the plot reads as the brain does: a red glutamate
  // column, a blue GABA one. Which drug carries which share of a stack is then said
  // by SHADE, not by hue: the segments are the same colour stepped down in opacity,
  // strongest contributor first, and each one names its drug on hover. A system with
  // no colour of its own leaves the fill to the stylesheet's neutral token.
  const shadeOf = (seg) => SEG_SHADES[Math.min(seg.shade || 0, SEG_SHADES.length - 1)];
  let groupFrom = null;
  const flushGroup = (endCol) => {
    if (!groupFrom || !endCol) return;
    const cx = (groupFrom.x + endCol.x + COL_W) / 2;
    root.appendChild(svg("text", {
      class: "sim-group", x: cx, y: M.top + plotH + labelBand + 13,
      "text-anchor": "middle", fill: groupFrom.systemColor,
    }, groupFrom.systemLabel));
  };

  cols.forEach((col, i) => {
    if (col.groupStart) { flushGroup(cols[i - 1]); groupFrom = col; }
    const bw = COL_W - 8;
    const bx = col.x + 4;
    // Boost stack, bottom-up from the zero line.
    let acc = 0;
    for (const seg of col.up) {
      const h = seg.frac * col.boostAxis;
      if (!(h > 0)) continue;
      const r = svg("rect", {
        class: seg.dim ? "sim-seg sim-seg-metab" : "sim-seg",
        x: bx, y: yOf(acc + h), width: bw, height: Math.max(0.5, yOf(acc) - yOf(acc + h)),
        fill: col.systemColor, "fill-opacity": shadeOf(seg),
      });
      r.appendChild(svg("title", {}, segTitle(col, seg)));
      root.appendChild(r);
      acc += h;
    }
    // Block stack, top-down from the zero line (blockAxis is negative).
    acc = 0;
    for (const seg of col.down) {
      const h = seg.frac * col.blockAxis;
      if (!(h < 0)) continue;
      const r = svg("rect", {
        class: seg.dim ? "sim-seg sim-seg-metab" : "sim-seg",
        x: bx, y: yOf(acc), width: bw, height: Math.max(0.5, yOf(acc + h) - yOf(acc)),
        fill: col.systemColor, "fill-opacity": shadeOf(seg),
      });
      r.appendChild(svg("title", {}, segTitle(col, seg)));
      root.appendChild(r);
      acc += h;
    }
    if (showUnknown && col.unknownAxis > 0) {
      const top = col.boostAxis + col.unknownAxis;
      const r = svg("rect", {
        class: "sim-unknown", x: bx, y: yOf(top), width: bw,
        height: Math.max(0.5, yOf(col.boostAxis) - yOf(top)),
        fill: "url(#sim-unknown-hatch)",
      });
      r.appendChild(svg("title", {}, `${col.name}: ${t("sim.rxUnknown")}`));
      root.appendChild(r);
    }
    root.appendChild(svg("line", {
      class: "sim-net", x1: col.x + 1, x2: col.x + COL_W - 1,
      y1: yOf(col.netAxis), y2: yOf(col.netAxis),
    }));
    root.appendChild(svg("rect", {
      class: "sim-sysbar", x: col.x + 2, y: M.top + plotH + 2,
      width: COL_W - 4, height: 3, fill: col.systemColor,
    }));
    root.appendChild(svg("text", {
      class: "sim-col", "text-anchor": "end",
      transform: `rotate(-50 ${col.x + COL_W / 2} ${M.top + plotH + 12})`,
      x: col.x + COL_W / 2, y: M.top + plotH + 12,
    }, col.name));
    // One transparent full-height hit area per column: a pointer anywhere over the
    // column answers, not only over the few pixels a thin bar happens to occupy.
    const hit = svg("rect", {
      class: "sim-colhit", x: col.x, y: M.top, width: COL_W, height: plotH,
    });
    col.hit = hit;
    root.appendChild(hit);
  });
  flushGroup(cols[cols.length - 1]);

  let hovered = null;
  return {
    svg: root,
    colAt(clientX) {
      const r = root.getBoundingClientRect();
      if (!r.width) return null;
      const vx = ((clientX - r.left) / r.width) * W;
      return cols.find((c) => vx >= c.x && vx < c.x + COL_W) || null;
    },
    setHover(col) {
      if (hovered) hovered.hit.classList.remove("on");
      hovered = col;
      if (hovered) hovered.hit.classList.add("on");
    },
  };
}
