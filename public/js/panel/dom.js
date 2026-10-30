// Panel DOM helpers: element / button / external-link builders, fold a panel's headed
// sections into <details>, and flash a row a jump landed on (unfolding the section
// holding it).

import { isWebUrl } from "../web-url.js";
import { sectionIcon, sectionIconKey } from "./section-icons.js";

/**
 * `document.createElement(tag)` with an optional class name and text. The one
 * builder every panel, tab and popup uses, so text always goes in through
 * `textContent` (never markup) the same way everywhere.
 * @param {string} tag
 * @param {?string} [cls]
 * @param {?string} [text] omitted / null / undefined leaves the node empty
 * @returns {HTMLElement}
 */
export function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

/**
 * A `<button type="button">` (never a form submit) with an optional class and text.
 * @param {?string} [cls]
 * @param {?string} [text]
 * @returns {HTMLButtonElement}
 */
/**
 * A stable key for one folded panel section (a `details.panel-sec`), the same on
 * every render of that panel: its tour anchor, else its heading text with the counts
 * stripped ("Pharmacokinetic interactions (12)" -> "Pharmacokinetic interactions").
 * @param {HTMLDetailsElement} det
 * @returns {string}
 */
export function panelSectionKey(det) {
  if (det.dataset.tourSec) return det.dataset.tourSec;
  const summary = det.querySelector(":scope > summary");
  // The subtitle (see withSubtitle) is not part of the key: only the heading's own text.
  const own = summary ? [...summary.childNodes]
    .filter((n) => !n.classList?.contains("section-sub"))
    .map((n) => n.textContent).join("") : "";
  return own.replace(/[\d()]/g, "").trim();
}

/**
 * Append a section's plain-language subtitle (small, muted `span.section-sub`) to
 * its heading, the one way every panel heading carries one. It rides INSIDE the
 * heading, so foldSections moves it into the `<summary>` with the title and it stays
 * visible while the section is folded (it says what the folded section holds);
 * panelSectionKey ignores it. A falsy `sub` adds nothing.
 * @param {HTMLElement} head
 * @param {?string} [sub]
 * @returns {HTMLElement} `head`
 */
export function withSubtitle(head, sub) {
  if (sub) head.appendChild(el("span", "section-sub", sub));
  return head;
}

/**
 * A panel heading (`<h3>` for a foldable section, `<h4>` inside one) with an
 * optional subtitle (see withSubtitle).
 * @param {string} tag
 * @param {string} title  the localized heading
 * @param {?string} [sub]  the localized subtitle
 * @param {?string} [cls]
 * @returns {HTMLElement}
 */
export function heading(tag, title, sub, cls) {
  return withSubtitle(el(tag, cls, title), sub);
}

/**
 * A titled subsection inside a panel section (CNS penetration under Pharmacokinetics,
 * Active metabolites under Metabolism): a `div.panel-subsec` headed by an `<h4>`.
 * An `<h4>`, not an `<h3>`, so foldSections never folds it into a section of its own.
 * @param {string} title  the localized heading
 * @param {string} [cls]  extra classes for the wrapper
 * @param {?string} [sub]  the localized subtitle (see withSubtitle)
 * @returns {HTMLDivElement}
 */
export function subSection(title, cls = "", sub = null) {
  const sec = el("div", `panel-subsec ${cls}`.trim());
  sec.appendChild(heading("h4", title, sub, "panel-subsec-title"));
  return sec;
}

/**
 * A heading's text lowered for use mid-sentence ("Age and sex differences" ->
 * "age and sex differences"), its first letter only, and never an acronym's ("CNS
 * penetration" stays). Twin of tools/api_sections.py lower_first (same rule, so the
 * /api placeholder reads exactly like the panel's).
 * @param {string} s
 * @returns {string}
 */
export function lowerFirst(s) {
  if (!s || (s.length > 1 && s[1] !== s[1].toLowerCase())) return s;
  return s[0].toLowerCase() + s.slice(1);
}

/**
 * The one "nothing recorded yet" sentence of an empty panel section (i18n
 * `info.noData`): "No information about <section> for this <kind> yet.", so a reader
 * of one panel still learns the dataset tracks that section for other nodes.
 * @param {string} title  the section's localized heading
 * @param {string} kind   the panel's node kind (`info.kindThis.<kind>`)
 * @returns {string}
 */
export function noDataText(title, kind) {
  const { t } = window.__I18N__;
  return t("info.noData", { what: lowerFirst(title), kind: t(`info.kindThis.${kind}`) });
}

/**
 * An empty panel section: its heading (+ subtitle, + beta tag) then one muted
 * placeholder line, never an accordion with nothing inside. An `<h3>` head is turned
 * into a `div.panel-sec-head` so foldSections leaves the section open (no caret to
 * click into emptiness); an `<h4>` head makes it an empty subsection. Every panel
 * section skipped for lack of data goes through here (flags, such as the prodrug or
 * combo notes and addon slots, simply stay hidden).
 * @param {HTMLElement} head  built by heading() / betaHeading()
 * @param {string} kind  the panel's node kind (see noDataText)
 * @param {{tourSec?: ?string, icon?: ?string, cls?: string, text?: ?string, extra?: ?Node}} [opts]
 *   `icon` names the heading's section-icons.js key where `tourSec` does not; `text`
 *   replaces the generic sentence where a section has its own (Regional distribution's
 *   "no significant role" note); `extra` follows it (other-forms.js's link to the
 *   stereo form that fills the section)
 * @returns {HTMLDivElement}
 */
export function emptySection(head, kind,
  { tourSec = null, icon = null, cls = "", text = null, extra = null } = {}) {
  const title = [...head.childNodes].filter((n) => n.nodeType === 3)
    .map((n) => n.textContent).join("").trim();
  const sub = head.tagName === "H4";
  const sec = el("div", `${sub ? "panel-subsec" : "panel-sec"} panel-sec-empty ${cls}`.trim());
  if (tourSec) sec.dataset.tourSec = tourSec;
  if (icon) sec.dataset.icon = icon;
  let top = head;
  if (!sub) {
    top = el("div", "panel-sec-head");
    top.append(...[sectionIcon(sectionIconKey(sec))].filter(Boolean), ...head.childNodes);
  }
  sec.append(top, el("p", "panel-sec-none", text || noDataText(title, kind)));
  if (extra) sec.appendChild(extra);
  return sec;
}

/**
 * The CSS selector finding a section by the same `{tourSec, cls}` options emptySection
 * takes, so a section's empty and filled renderings answer to one selector.
 * @param {{tourSec?: ?string, cls?: string}} opts
 * @returns {?string}
 */
export function sectionSelector({ tourSec = null, cls = "" } = {}) {
  if (tourSec) return `[data-tour-sec="${tourSec}"]`;
  const classes = cls.split(/\s+/).filter(Boolean);
  return classes.length ? classes.map((c) => `.${c}`).join("") : null;
}

export function btn(cls, text) {
  const b = el("button", cls, text);
  b.type = "button";
  return b;
}

/**
 * An external link opening in a new tab (`rel="noopener noreferrer"`), or a plain
 * `<span>` with the same text when `url` is not an absolute http(s) URL, so a stray
 * `javascript:` / `data:` value can never become clickable (see isWebUrl).
 * @param {string} text
 * @param {?string} url
 * @param {?string} [cls]
 * @returns {HTMLAnchorElement|HTMLSpanElement}
 */
export function extLink(text, url, cls) {
  if (!isWebUrl(url)) return el("span", cls, text);
  const a = el("a", cls, text);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

/**
 * Scroll an element into view and flash it, for an action that lands the reader
 * somewhere they did not choose to scroll to: a click that navigates to another node
 * *because of* one row (arriving on the target's panel, the row that explains the jump
 * is under the eye instead of hunted for), or a search pick that flips a setting (the
 * changed toggle says so itself). Deferred a frame because the caller usually shows
 * the host pane right AFTER this runs (see focusDrug -> openDetailTab, and the search
 * pick, which closes the search box only after the item's select()), and
 * scrollIntoView on a hidden box is a no-op.
 * @param {?HTMLElement} elm
 */
export function flashRow(elm) {
  if (!elm) return;
  requestAnimationFrame(() => {
    // A row folded inside a collapsed section (see foldSections) is opened first, or
    // the jump would land on nothing visible. Inside the rAF: the fold pass runs
    // after a panel's rows are built, so the <details> only exists by now.
    if (elm.tagName === "DETAILS") elm.open = true;
    for (let d = elm.parentElement?.closest("details"); d;
      d = d.parentElement?.closest("details")) d.open = true;
    elm.scrollIntoView({ block: "center", behavior: "smooth" });
    elm.classList.add("node-flash");
    elm.addEventListener("animationend",
      () => elm.classList.remove("node-flash"), { once: true });
  });
}

/**
 * Fold every headed section directly under `host` into a collapsed `<details>`: a
 * section whose first child is an `<h3>` becomes `details.disclosure.panel-sec` with
 * that heading as its `<summary>` and the rest in an indented `.panel-sec-body`; one
 * that already is a `<details>` just gets the same classes and body. Classes and `data-tour-*` hooks carry over, so a tour step
 * or flashRow still finds the section (and flashRow opens it). Unheaded blocks (the
 * title, intro, facts) stay as they are.
 * @param {HTMLElement} host
 */
export function foldSections(host) {
  for (const sec of [...host.children]) {
    const isDetails = sec.tagName === "DETAILS";
    const head = sec.firstElementChild;
    if (!head || (!isDetails && head.tagName !== "H3")) continue;
    let det = sec;
    let summary = head;
    if (!isDetails) {
      det = document.createElement("details");
      det.className = sec.className;
      Object.assign(det.dataset, sec.dataset);
      summary = document.createElement("summary");
      summary.append(...head.childNodes);
      head.remove();
    }
    det.classList.add("disclosure", "panel-sec");
    const icon = !summary.querySelector(":scope > .sec-icon") && sectionIcon(sectionIconKey(det));
    if (icon) summary.prepend(icon);
    const inner = document.createElement("div");
    inner.className = "panel-sec-body";
    inner.append(...[...sec.childNodes].filter((n) => n !== summary));
    if (!isDetails) sec.replaceWith(det);
    det.replaceChildren(summary, inner);
  }
}
