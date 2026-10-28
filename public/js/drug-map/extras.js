// The Legend's "Extra details": the numbers behind the map as JSON Lines, in tabs, so a
// reader can check or reuse what the plot shows. Four tabs, each one record per line:
//   input coordinates      {"drug":"Haloperidol","D2":3.6,"5-HT2A":-2.1,...}   raw profile
//   normalized coordinates {"drug":"Haloperidol","D2":0.71,...}   what the PCA actually got
//                          (disabled when Normalize is off, or with one or two picked
//                          features, which are plotted raw, see view.js `direct`)
//   axis weights           {"feature":"D2","PC1":0.45,"PC2":-0.1,"mean":0.12}   each input
//                          axis' weight on each map axis, and the mean the PCA centred on
//   PCA formula            {"step":3,"name":"center","formula":"c[f] = u[f] - mean[f]",...}
// The text builders are DOM-free (node tests, tools/tests/drug_map_extras.test.mjs); the
// tabs are built once and fill lazily: a tab's text is only computed while the box is open
// and that tab is shown, since the coordinates of every drug run to hundreds of lines.

import { button, el, foldBox } from "./dom.js";
import { EFFECT_SIGN, PKI_FLOOR } from "./model.js";

export const TABS = ["input", "normalized", "weights", "formula"];

// 4 decimals: enough to recompute a position, short enough to read.
const round = (x) => Math.round(x * 1e4) / 1e4;
const line = (obj) => JSON.stringify(obj);

/**
 * One line per drug, its features largest first, keyed by display name.
 * @param {string[]} ids  drugs in plot order
 * @param {Map<string, Map<string, number>>} profiles
 * @param {{nameOf: (key: string) => string, drugName: (id: string) => string}} names
 * @returns {string}
 */
export function coordinatesText(ids, profiles, { nameOf, drugName }) {
  return ids.filter((id) => profiles.has(id)).map((id) => {
    const row = { drug: drugName(id) };
    const feats = [...profiles.get(id)].sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    for (const [k, w] of feats) row[nameOf(k)] = round(w);
    return line(row);
  }).join("\n");
}

/**
 * One line per input axis: its weight on each map axis. A PCA gives `PC1` / `PC2` plus
 * the `mean` it subtracted; one or two picked features are the axes themselves (x / y).
 * @param {{loadings: {target: string, w: number, mean: number}[]}[]|null} pcs
 * @param {string[]|null} direct  the picked keys when plotted directly, else null
 * @param {(key: string) => string} nameOf
 * @returns {string}
 */
export function weightsText(pcs, direct, nameOf) {
  if (direct) {
    return direct.map((k, i) => line({ feature: nameOf(k), x: i ? 0 : 1, y: i ? 1 : 0 })).join("\n");
  }
  if (!pcs || !pcs.length) return "";
  const rows = new Map();
  pcs.forEach((ax, i) => {
    for (const l of ax.loadings) {
      const r = rows.get(l.target) || { feature: nameOf(l.target), PC1: 0, PC2: 0, mean: round(l.mean) };
      r[`PC${i + 1}`] = round(l.w);
      rows.set(l.target, r);
    }
  });
  return [...rows.values()].sort((a, b) => Math.abs(b.PC1) - Math.abs(a.PC1)).map(line).join("\n");
}

/**
 * The transform from a drug's bindings to its dot, step by step, with this view's
 * settings and counts filled in. `formula` is maths (language-neutral), `what` the words.
 * @param {{view: object, direct: string[]|null, pcs: object[]|null, n: number, features: number,
 *   nameOf: (key: string) => string, t: Function}} ctx
 * @returns {string}
 */
export function formulaText({ view, direct, pcs, n, features, nameOf, t }) {
  const steps = [];
  const add = (name, formula, extra = {}) => steps.push({ step: steps.length + 1, name, formula, ...extra });
  const src = view.sources;
  if (src.includes("receptors")) {
    add("receptor affinity", `a[f] = max(0, pKi - ${PKI_FLOOR}), pKi = 9 - log10(Ki nM)`
      + (view.signed ? ` ; v[f] = a[f] * sign(effect), ${Object.entries(EFFECT_SIGN).map(([k, s]) => `${k} ${s > 0 ? "+" : ""}${s}`).join(", ")}` : " ; v[f] = a[f]"),
    { what: t(view.measuredKi ? "drugmap.fx.receptorsMeasured" : "drugmap.fx.receptors"), signed: view.signed });
  }
  if (src.includes("tone")) add("neurotransmitter tone", "v[tone:k] = net tone sum of system k", { what: t("drugmap.fx.tone") });
  if (src.includes("effects")) add("body effects", "v[effect:e] = max a[f] over the bindings behind e", { what: t("drugmap.fx.effects") });
  if (direct) {
    add("axes", `x = v[${nameOf(direct[0])}]` + (direct[1] ? `, y = v[${nameOf(direct[1])}]` : ", y = 0"),
      { what: t("drugmap.fx.direct") });
  } else {
    add("normalize", view.normalize ? "u[f] = v[f] / sqrt(sum over g in block(f) of v[g]^2)" : "u[f] = v[f]",
      { what: t(view.normalize ? "drugmap.fx.normalize" : "drugmap.fx.noNormalize"), applied: view.normalize });
    add("center", "c[f] = u[f] - mean[f]", { what: t("drugmap.fx.center"), drugs: n });
    add("covariance", "C = sum over drugs of c c^T", { what: t("drugmap.fx.covariance"), features });
    add("axes", "w1, w2 = top two eigenvectors of C",
      { what: t("drugmap.fx.eigen"), PC1_share: pcs ? round(pcs[0].share) : 0, PC2_share: pcs && pcs[1] ? round(pcs[1].share) : 0 });
    add("project", "x = sum_f c[f] * w1[f], y = sum_f c[f] * w2[f]", { what: t("drugmap.fx.project") });
  }
  add("screen", "one scale for x and y, y up", { what: t(view.spread ? "drugmap.fx.screenSpread" : "drugmap.fx.screen") });
  return steps.map(line).join("\n");
}

// JSON tokens -> classed spans: a string followed by ":" is a key.
const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}[\],:])/g;

/**
 * Colour JSON Lines as DOM nodes (never innerHTML: names come from the data).
 * @param {string} text
 * @returns {Node[]}
 */
function highlight(text) {
  const out = [];
  let at = 0;
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > at) out.push(document.createTextNode(text.slice(at, m.index)));
    const [cls, s] = m[1] ? [m[2] ? "dm-j-key" : "dm-j-str", m[1]] : m[3] ? ["dm-j-num", m[3]]
      : m[4] ? ["dm-j-lit", m[4]] : ["dm-j-punct", m[5]];
    out.push(el("span", cls, s));
    if (m[2]) out.push(el("span", "dm-j-punct", m[2]));
    at = m.index + m[0].length;
  }
  if (at < text.length) out.push(document.createTextNode(text.slice(at)));
  return out;
}

async function copyText(text, btn, t) {
  try {
    await navigator.clipboard.writeText(text);
    const was = btn.textContent;
    btn.textContent = t("drugmap.copied");
    setTimeout(() => { btn.textContent = was; }, 1200);
  } catch {
    btn.textContent = t("drugmap.copyFailed");
  }
}

/**
 * The "Extra details" box. `update(state)` hands it the latest render; the text is built
 * from it only when shown.
 * @param {Function} t
 * @returns {{box: HTMLElement, update: (state: object) => void}}
 */
export function createExtras(t) {
  const fold = foldBox(t("drugmap.sec.extras"), "dm-extras");
  const tabBar = el("div", "dm-tabs");
  const pre = el("pre", "dm-jsonl");
  const copy = button("dm-copy", t("drugmap.copy"), () => copyText(textOf(active), copy, t));
  const copyAll = button("dm-copy-all", t("drugmap.copyAll"), () => copyText(
    TABS.filter((k) => !disabled(k)).map((k) => `# ${t(`drugmap.tab.${k}`)}\n${textOf(k)}`).join("\n\n"), copyAll, t));
  const field = el("div", "dm-jsonl-wrap");
  field.append(pre, copy);
  fold.body.append(tabBar, field, copyAll);

  let state = null;
  let active = "input";
  const cache = new Map();
  const disabled = (k) => k === "normalized" && !!state && (!state.view.normalize || !!state.direct);
  const textOf = (k) => {
    if (!state) return "";
    if (!cache.has(k)) {
      const s = state;
      cache.set(k, k === "input" ? coordinatesText(s.ids, s.raw(), s)
        : k === "normalized" ? coordinatesText(s.ids, s.profiles, s)
          : k === "weights" ? weightsText(s.pcs, s.direct, s.nameOf)
            : formulaText({ ...s, n: s.ids.length, features: s.featureCount }));
    }
    return cache.get(k);
  };
  const tabs = new Map(TABS.map((k) => [k, button("dm-tab", t(`drugmap.tab.${k}`), () => { active = k; paint(); })]));
  tabBar.append(...tabs.values());

  function paint() {
    if (active !== "input" && disabled(active)) active = "input";
    for (const [k, b] of tabs) {
      b.disabled = disabled(k);
      b.title = b.disabled ? t("drugmap.tab.normalizedOff") : "";
      b.classList.toggle("on", k === active);
      b.setAttribute("aria-pressed", String(k === active));
    }
    if (!fold.box.open) return;
    pre.replaceChildren(...highlight(textOf(active)));
  }
  fold.box.addEventListener("toggle", paint);

  return {
    box: fold.box,
    update(next) {
      state = next;
      cache.clear();
      paint();
    },
  };
}
