// Data browser UI: the filter box, kind / grade / sort selects, mirrored-twins
// checkbox, count line and chunked row list over collectNodes' rows (see
// js/node-browser.js for the section's purpose).

import { loadFlag, saveFlag } from "../prefs.js";
import { el, btn } from "../panel/dom.js";
import { KIND_ORDER } from "../kinds.js";
import { DISPLAY_GRADE_ORDER } from "../grades.js";
import { collectNodes } from "./collect.js";


// How many rows render at once. The full list is several thousand nodes, so the
// first paint is capped and each "show more" appends a bigger chunk (by then the
// reader has decided the filter is the one they want).
const PAGE_FIRST = 150;
const PAGE_MORE = 300;
// localStorage key for the browser's "show mirrored twins" checkbox. Default OFF:
// a left/right pair says one thing twice, so reading each region once is the useful
// default; ticking it restores the reading that matches the coverage tally (which
// counts each emitted record). See js/prefs.js.
const TWINS_KEY = "neurarium.nodeTwins";

// The row keys the header names, in render order. These ARE the field names of a row
// out of collectNodes (and, one step back, of a node in the emitted data), shown
// verbatim rather than prettified: the whole point of the header is to make the node
// structure visible, so a reader can tell that every line here is one owner (`name`)
// stating one thing (`notion`) of one `kind` at one `grade`. Each carries a localized
// explanation as its tooltip.
const COLUMNS = [
  ["grade", "nodes.colGrade"],
  ["name", "nodes.colName"],
  ["notion", "nodes.colNotion"],
  ["kind", "nodes.colKind"],
];

/**
 * Build the Data browser into a section body: a filter box, kind / grade / sort
 * selects, a mirrored-twins checkbox, a count line and the chunked row list.
 *
 * The node list is collected LAZILY, on the first `open()`, because enumerating
 * every node walks the whole dataset and a visitor who never opens the section
 * should not pay for it at boot.
 *
 * @param {object} opts
 * @param {HTMLElement} opts.body the section body element to fill (#nodes-body)
 * @param {import("../data.js").BrainData} opts.data
 * @param {{t: Function, formatHalfLife: Function, nav: object}} opts.deps
 * @param {{pill: Function, fold: Function, kindLabel: Function,
 *          gradeLabel: Function, openDataFiles: Function}} opts.ui viewer helpers
 *   reused verbatim (the source-backed provenance pill builder, the search box's
 *   accent/Greek folding, the Sources popup's own kind + grade labels so the two
 *   views can't name things differently, and the About popup's data-file list so
 *   "the same nodes as files" is one list, not a copy of it)
 * @returns {{open: () => void}}
 */
export function createNodeBrowser({ body, data, deps, ui }) {
  const { t } = deps;
  const { pill, fold, kindLabel, gradeLabel, openDataFiles } = ui;

  let rows = null;
  let matches = [];
  let limit = PAGE_FIRST;


  const filterInput = document.createElement("input");
  filterInput.type = "text";
  filterInput.id = "nodes-filter";
  filterInput.className = "drugs-filter";
  filterInput.autocomplete = "off";
  filterInput.placeholder = t("nodes.filter");

  const controls = el("div", "node-filters");
  const makeSelect = (label, options) => {
    const sel = document.createElement("select");
    sel.className = "node-select";
    sel.setAttribute("aria-label", label);
    sel.title = label;
    for (const [value, text] of options) {
      const o = document.createElement("option");
      o.value = value;
      o.textContent = text;
      sel.appendChild(o);
    }
    controls.appendChild(sel);
    return sel;
  };

  // A mirrored region is two emitted records saying one thing, so whether the pair
  // reads as one row or two is a preference, not a fact. It only ever changes the
  // `structures` rows, so the checkbox is shown only while some structure row is in
  // the current result (see apply): a control that cannot affect what you are looking
  // at is noise.
  const twinsLabel = el("label", "list-toggle");
  const twinsBox = document.createElement("input");
  twinsBox.type = "checkbox";
  twinsBox.id = "nodes-show-twins";
  twinsBox.checked = loadFlag(TWINS_KEY, false);
  twinsLabel.appendChild(twinsBox);
  twinsLabel.appendChild(el("span", null, t("nodes.twins")));
  twinsLabel.title = t("nodes.twinsHint");

  const countEl = el("div", "node-count");
  const list = el("div", "node-list");
  // Header + rows share one horizontal scroller so the four columns keep a readable
  // width instead of being squeezed into the panel's: the keys stay over the cells
  // they name because both scroll as one block.
  const grid = el("div", "node-grid");
  const moreBtn = btn("node-more");
  moreBtn.hidden = true;

  // What a node IS, said once above the list, because a flat list of sentences does
  // not by itself reveal that each line is a record with fields. The header below
  // then names those fields, and the "as files" link hands over the very same nodes
  // in their stored form.
  const intro = el("p", "node-intro", t("nodes.intro"));
  const filesBtn = btn("node-datafiles", t("nodes.dataFiles"));
  filesBtn.title = t("nodes.dataFilesHint");
  filesBtn.addEventListener("click", () => openDataFiles?.());
  intro.appendChild(document.createTextNode(" "));
  intro.appendChild(filesBtn);

  // The column header, built with a row's exact structure (grade cell, then a
  // three-column inner box mirroring .node-main) so the two share one grid template
  // in the stylesheet and each key really sits over the cell it names.
  const head = el("div", "node-head");
  const headMain = el("span", "node-head-main");
  const headCells = {};
  for (const [key, tip] of COLUMNS) {
    const cell = el("span", `node-head-cell node-head-${key}`, key);
    cell.title = t(tip);
    headCells[key] = cell;
    (key === "grade" ? head : headMain).appendChild(cell);
  }
  head.appendChild(headMain);
  // The two swappable columns' own names, kept so apply() can put the selected kind
  // over one of them and hand the name back when it goes.
  const nameDefault = headCells.name.textContent;
  const notionDefault = headCells.notion.textContent;

  const rowEl = (r) => {
    // A div rather than a button: the grade pill is itself a <button> (it pins its
    // tooltip on touch), and nesting one inside another is invalid, so the clickable
    // half is an inner button beside the pill.
    const wrap = el("div", "node-row");
    // The row IS the pill's `{sources, uncertainty, ki}` argument, so a browser pill
    // opens on the node's verbatim quote (or its reasons to doubt, or its measured
    // Ki), exactly like the same node's pill inside a detail panel.
    wrap.appendChild(pill(r.grade, r));
    const main = btn(r.go ? "node-main clickable" : "node-main");
    main.appendChild(el("span", "node-name", r.name));
    // Always emitted, empty or not: it is a grid cell, and skipping it would slide
    // the kind tag up into the notion column.
    main.appendChild(el("span", "node-notion", r.notion || ""));
    main.appendChild(el("span", "node-kind", kindLabel(r.kind)));
    if (r.go) main.addEventListener("click", r.go);
    else main.disabled = true;
    wrap.appendChild(main);
    return wrap;
  };

  let kindSel = null;
  let gradeSel = null;
  let sortSel = null;

  const render = () => {
    list.textContent = "";
    const frag = document.createDocumentFragment();
    const end = Math.min(limit, matches.length);
    for (let i = 0; i < end; i += 1) frag.appendChild(rowEl(matches[i]));
    list.appendChild(frag);
    head.hidden = matches.length === 0;
    countEl.textContent = t("nodes.count", { shown: end, total: matches.length });
    const rest = matches.length - end;
    moreBtn.hidden = rest <= 0;
    if (rest > 0) moreBtn.textContent = t("info.more", { n: rest });
  };

  const apply = () => {
    const q = fold((filterInput.value || "").trim());
    const kind = kindSel.value;
    const grade = gradeSel.value;
    matches = rows.filter((r) => {
      if (kind && r.kind !== kind) return false;
      if (grade && r.grade !== grade) return false;
      if (!q) return true;
      return fold(`${r.name} ${r.notion}`).includes(q);
    });
    const mode = sortSel.value;
    const byName = (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })
      || a.notion.localeCompare(b.notion, undefined, { numeric: true });
    if (mode === "name") matches.sort(byName);
    else if (mode === "kind") {
      matches.sort((a, b) =>
        KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || byName(a, b));
    } else {
      const dir = mode === "strongest" ? -1 : 1;
      matches.sort((a, b) =>
        dir * (DISPLAY_GRADE_ORDER[a.grade] - DISPLAY_GRADE_ORDER[b.grade]) || byName(a, b));
    }
    // The twins choice only ever splits or collapses `structures` rows, so offer it
    // only while the current result contains some (both readings keep the kind, so
    // the control does not hide itself the moment it is used).
    twinsLabel.hidden = !matches.some((r) => r.kind === "structures");
    // With one kind selected, every row would repeat the kind chosen right above the
    // list, so the column is dropped and its width goes to name + notion. Kept only
    // in the "all kinds" reading, where it is what tells the rows apart. The kind then
    // heads the notion column instead: "what this node states" is abstract, while
    // "Receptor expression regions" says outright what the cells under it are.
    grid.classList.toggle("no-kind", kind !== "");
    // Some kinds state their whole claim in the name (a circuit, a projection group),
    // leaving the notion cell empty on every row. Then the notion column goes too and
    // the kind heads the NAME column, rather than pairing a nameless header with a
    // column of blanks. Read off the rows, not a kind list, so a kind that later gains
    // a notion (or loses one) is handled without a second place to update.
    const noNotion = kind !== "" && !matches.some((r) => r.notion);
    grid.classList.toggle("no-notion", noNotion);
    headCells.name.textContent = noNotion ? kindLabel(kind) : nameDefault;
    headCells.notion.textContent = kind === "" ? notionDefault : kindLabel(kind);
    limit = PAGE_FIRST;
    render();
  };

  let debounce = 0;
  const applySoon = () => {
    clearTimeout(debounce);
    debounce = setTimeout(apply, 120);
  };

  const collect = () => { rows = collectNodes(data, deps, { twins: twinsBox.checked }); };

  const build = () => {
    if (rows) return;
    collect();

    const presentKinds = new Set(rows.map((r) => r.kind));
    kindSel = makeSelect(t("nodes.kindLabel"), [
      ["", t("nodes.allKinds")],
      ...KIND_ORDER.filter((k) => presentKinds.has(k)).map((k) => [k, kindLabel(k)]),
    ]);
    const presentGrades = new Set(rows.map((r) => r.grade));
    gradeSel = makeSelect(t("nodes.gradeLabel"), [
      ["", t("nodes.allGrades")],
      ...["verified", "uncertain", "sourced", "llm", "unknown", "nosource"]
        .filter((g) => presentGrades.has(g)).map((g) => [g, gradeLabel(g)]),
    ]);
    sortSel = makeSelect(t("nodes.sortLabel"), [
      ["weakest", t("nodes.sortWeakest")],
      ["strongest", t("nodes.sortStrongest")],
      ["name", t("nodes.sortName")],
      ["kind", t("nodes.sortKind")],
    ]);

    filterInput.addEventListener("input", applySoon);
    kindSel.addEventListener("change", apply);
    gradeSel.addEventListener("change", apply);
    sortSel.addEventListener("change", apply);
    twinsBox.addEventListener("change", () => {
      saveFlag(TWINS_KEY, twinsBox.checked);
      collect(); // the structure rows themselves change, so re-enumerate before filtering
      apply();
    });
    moreBtn.addEventListener("click", () => {
      limit += PAGE_MORE;
      render();
    });

    body.appendChild(intro);
    body.appendChild(filterInput);
    body.appendChild(controls);
    body.appendChild(twinsLabel);
    body.appendChild(countEl);
    grid.appendChild(head);
    grid.appendChild(list);
    body.appendChild(grid);
    body.appendChild(moreBtn);
    apply();
  };

  return {
    /** Collect + render on first use; a no-op on every reopen. */
    open() { build(); },
  };
}
