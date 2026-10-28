// The Legend's "Extra details": the numbers behind the map as JSON Lines, in tabs, so a
// reader can check or reuse what the plot shows. Four tabs, each one record per line:
//   input coordinates      {"drug":"Haloperidol","D2":3.6,"5-HT2A":-2.1,...}   raw profile
//   normalized coordinates {"drug":"Haloperidol","D2":0.71,...}   what the PCA actually got
//                          (disabled when no normalization applies: off, or "shape" with
//                          one or two picked features, plotted raw, see view.js `norm`)
//   axis weights           {"feature":"D2","PC1":0.45,"PC2":-0.1,"mean":0.12}   each input
//                          axis' weight on each map axis, and the mean the PCA centred on
// The text builders are DOM-free (node tests, tools/tests/drug_map_extras.test.mjs); the
// tabs are built once and fill lazily: a tab's text is only computed while the box is open
// and that tab is shown, since the coordinates of every drug run to hundreds of lines.

import { button, el, foldBox } from "./dom.js";

export const TABS = ["input", "normalized", "weights"];

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
  const disabled = (k) => k === "normalized" && !!state && state.norm === "off";
  const textOf = (k) => {
    if (!state) return "";
    if (!cache.has(k)) {
      const s = state;
      cache.set(k, k === "input" ? coordinatesText(s.ids, s.raw(), s)
        : k === "normalized" ? coordinatesText(s.ids, s.profiles, s)
          : weightsText(s.pcs, s.direct, s.nameOf));
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
