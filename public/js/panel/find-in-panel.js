// Shift+F: find a row inside the open detail panel ("lab" -> the Originator row),
// open its folded section and flash it. Searches what the panel shows right now,
// so it needs no knowledge of any view: section headings, subheadings and the
// label / value fact rows are read off the DOM when the box opens.
//
// A label also matches in the other language and through its own tooltip text,
// both found by reverse lookup in the i18n catalogue (the label "Originator" is
// the value of "drug.originator", whose French "Laboratoire d'origine" and whose
// "drug.originatorTip" ("The company or lab that discovered...") ride along).
import { flashRow } from "./dom.js";

const MAX_RESULTS = 12;
// Chrome inside a heading or row that is not its text: icons, subtitles, grade
// pills, help "?" tips, beta badges.
const NOISE = "svg, .section-sub, .src-pill, .src-details-cue, .help-icon, .help-tip, .beta-tag";

/** Lowercase, accents folded, so "demi vie" finds "Demi-vie". */
export const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "")
  .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** A node's own visible text, chrome stripped, counts like "(12)" dropped. */
function ownText(node) {
  const c = node.cloneNode(true);
  for (const n of c.querySelectorAll(NOISE)) n.remove();
  return c.textContent.replace(/\(\d+\)/g, "").replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ")
    .replace(/[\s:]+$/, "").trim();
}

/**
 * Reverse index of the i18n catalogue: folded label in the current language ->
 * its folded label in the other languages (`alt`) and every language's tooltip
 * (`tip`), so "lab" finds "Originator" through "Laboratoire d'origine".
 * @returns {Map<string, {alt:string, tip:string}>}
 */
function catalogueAliases() {
  const messages = window.__I18N_MESSAGES__ || {};
  const lang = window.__I18N__?.lang || "en";
  const own = messages[lang] || {};
  const map = new Map();
  for (const [key, value] of Object.entries(own)) {
    if (typeof value !== "string" || key.endsWith("Tip") || value.length > 60) continue;
    const alt = [];
    const tip = [];
    for (const table of Object.values(messages)) {
      if (table !== own && typeof table[key] === "string") alt.push(table[key]);
      if (typeof table[`${key}Tip`] === "string") tip.push(table[`${key}Tip`]);
    }
    const k = fold(value);
    const prev = map.get(k) || { alt: "", tip: "" };
    map.set(k, { alt: fold(`${prev.alt} ${alt.join(" ")}`), tip: fold(`${prev.tip} ${tip.join(" ")}`) });
  }
  return map;
}

/**
 * Every findable entry of a panel body, in reading order.
 * @param {HTMLElement} root
 * @param {Map<string,{alt:string, tip:string}>} aliases
 * @returns {{label:string, detail:string, section:string, target:HTMLElement, text:string, alt:string, tip:string}[]}
 */
export function indexPanel(root, aliases = new Map()) {
  const out = [];
  const sectionOf = (node) => {
    const sec = node.closest("details.panel-sec, .panel-sec-empty");
    const head = sec?.querySelector(":scope > summary, :scope > .panel-sec-head");
    return head && !head.contains(node) ? ownText(head) : "";
  };
  const add = (node, target, label, detail = "") => {
    if (!label) return;
    out.push({
      label, detail, section: sectionOf(node), target,
      text: fold(`${label} ${detail}`), ...(aliases.get(fold(label)) || { alt: "", tip: "" }),
    });
  };
  for (const node of root.querySelectorAll("summary, .panel-sec-head, h3, h4, .info-fact, .hl-chip")) {
    if (node.matches(".info-fact, .hl-chip")) {
      // A label / value row (a fact row, a half-life or Tmax chip).
      const label = node.querySelector(".fact-label, .hl-label");
      const all = ownText(node);
      const own = label ? ownText(label) : all;
      add(node, node, own, all.startsWith(own) ? all.slice(own.length).trim() : all);
    } else if (node.tagName === "SUMMARY") {
      add(node, node.parentElement, ownText(node));
    } else if (!node.closest("summary")) {
      add(node, node, ownText(node));
    }
  }
  return out;
}

/**
 * Rank entries against a query: every word must appear somewhere. A word starting
 * the row's label (in either language) beats one inside it, which beats a hit in
 * its value, then in its tooltip; ties go to the shorter label, then reading order.
 * @param {ReturnType<typeof indexPanel>} entries
 * @param {string} query
 */
export function rankEntries(entries, query) {
  const words = fold(query).split(" ").filter(Boolean);
  if (!words.length) return [];
  const scored = [];
  entries.forEach((e, i) => {
    const label = fold(e.label);
    let score = 0;
    for (const w of words) {
      const re = new RegExp(`(^| )${w}`);
      if (label.startsWith(w)) score += 6;
      else if (re.test(label) || re.test(e.alt)) score += 5;
      else if (label.includes(w) || e.alt.includes(w)) score += 4;
      else if (re.test(e.text)) score += 3;
      else if (e.text.includes(w)) score += 2;
      else if (e.tip.includes(w)) score += 1;
      else return;
    }
    scored.push({ e, score, i, len: label.length });
  });
  scored.sort((a, b) => b.score - a.score || a.len - b.len || a.i - b.i);
  return scored.slice(0, MAX_RESULTS).map((s) => s.e);
}

/**
 * Wire the find box (#panel-find) over the detail pane.
 * @returns {{open:()=>boolean, close:()=>void, readonly isOpen:boolean}}
 */
export function wireFindInPanel() {
  const box = document.getElementById("panel-find");
  const input = document.getElementById("panel-find-input");
  const list = document.getElementById("panel-find-results");
  const pane = document.getElementById("details-pane");
  const body = document.getElementById("info-body");
  const noop = { open: () => false, close() {}, get isOpen() { return false; } };
  if (!box || !input || !list || !pane || !body) return noop;

  let entries = [];
  let hits = [];
  let active = 0;
  let aliases = null;
  const t = (k) => window.__I18N__?.t(k) ?? k;

  const render = () => {
    hits = rankEntries(entries, input.value);
    active = Math.min(active, Math.max(0, hits.length - 1));
    list.replaceChildren();
    if (input.value.trim() && !hits.length) {
      const li = document.createElement("li");
      li.className = "panel-find-empty";
      li.textContent = t("find.none");
      list.appendChild(li);
    }
    hits.forEach((h, i) => {
      const li = document.createElement("li");
      li.className = "panel-find-hit" + (i === active ? " active" : "");
      li.setAttribute("role", "option");
      const main = document.createElement("span");
      main.className = "panel-find-label";
      main.textContent = h.label;
      li.appendChild(main);
      if (h.detail) {
        const d = document.createElement("span");
        d.className = "panel-find-detail";
        d.textContent = h.detail.length > 60 ? `${h.detail.slice(0, 57)}...` : h.detail;
        li.appendChild(d);
      }
      if (h.section) {
        const s = document.createElement("span");
        s.className = "panel-find-section";
        s.textContent = h.section;
        li.appendChild(s);
      }
      li.addEventListener("pointerdown", (e) => { e.preventDefault(); pick(i); });
      list.appendChild(li);
    });
  };

  const close = () => {
    box.hidden = true;
    input.value = "";
    list.replaceChildren();
  };
  const pick = (i) => {
    const h = hits[i];
    close();
    if (h) flashRow(h.target);
  };
  const open = () => {
    if (pane.hidden) return false;
    aliases ||= catalogueAliases();
    entries = indexPanel(body, aliases);
    box.hidden = false;
    active = 0;
    render();
    input.focus();
    input.select();
    return true;
  };

  input.addEventListener("input", () => { active = 0; render(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { close(); e.preventDefault(); e.stopPropagation(); }
    else if (e.key === "Enter") { pick(active); e.preventDefault(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (hits.length) active = (active + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length;
      render();
      e.preventDefault();
    }
  });
  input.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== input) close(); }, 150));

  return { open, close, get isOpen() { return !box.hidden; } };
}
