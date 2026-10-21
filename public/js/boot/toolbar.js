// The panel toolbar: reset view, and the search box (data + the panel's own
// controls, ranked by search-rank.js).

import { foldText, parseSearchQuery } from "../search/query.js";
import { buildSearchItems } from "../search/index.js";
import { loadSearchNames } from "../data.js";
import { rankMatch } from "../search-rank.js";

const { t } = window.__I18N__;

// How long a continuously-changing control (a text box being typed into) must be
// still before its value is written to the URL, so one edit costs one history write.
export const TYPING_SETTLE_MS = 400;

/**
 * Wire the panel's reset + search buttons (the row just above the sliders): a
 * reset button that recenters the view (handy after panning has slid the brain
 * off-center), and a magnifier that swaps a search box in place of the panel's
 * normal controls. Typing filters structures (by name), connections (by pathway
 * label) and receptors (by name / neurotransmitter / system); clicking a result
 * (or pressing Enter to take the first one) frames the camera on it. A structure
 * result opens its structure panel, a connection result the connection panel, a
 * receptor/target result focuses it (dim + dots + panel). All go through the
 * shared selectStructure / selectConnection / selectTarget helpers.
 * @param {{focus:ReturnType<typeof createCameraFocus>, meshes:THREE.Mesh[],
 *   arrows:import("./arrows.js").ProjectionArrow[],
 *   data:import("./data.js").BrainData,
 *   selection:ReturnType<typeof createSelection>,
 *   selectStructure:Function, selectConnection:Function,
 *   selectTarget:Function}} deps
 */
export function wireToolbar({ focus, meshes, arrows, data, selection, tabs, urlState, expandPanel, selectStructure, selectConnection, focusTarget, focusDrug, focusEnzyme, focusEffect, focusCircuit, focusProjectionGroup }) {
  const resetBtn = document.getElementById("reset-view");
  const searchToggle = document.getElementById("search-toggle");
  const searchBox = document.getElementById("search");
  const searchInput = document.getElementById("search-input");
  const searchClear = document.getElementById("search-clear");
  const searchResults = document.getElementById("search-results");
  // Show the inline clear "×" only when the box holds text. Called from
  // renderResults (which runs on every value change: input, open, prefilled query).
  const syncClear = () => { if (searchClear) searchClear.hidden = !searchInput.value; };
  // The normal controls; the search box shows in their place (not as a popup),
  // while the reset/search buttons above stay put so the magnifier can toggle
  // back.

  resetBtn.addEventListener("click", () => {
    // Every Settings control back to its shipped default first (un-spreading the brain
    // among them), so the recenter below frames the assembled brain.
    urlState.resetAll();
    focus.recenter();
    // Full reset: close any open detail tabs (which clears the 3D focus and strips
    // the deep-link hash via setOnEmpty), then drop any remaining halo / isolate set,
    // restoring default opacity.
    tabs.closeAll();
    selection.clear();
  });

  // The searchable index (search/index.js), built once.
  const items = buildSearchItems({ meshes, arrows, data, tabs, selectStructure, selectConnection, focusTarget, focusDrug, focusEnzyme, focusEffect, focusCircuit, focusProjectionGroup });

  // Type-filter chips above the results: scope the search to one kind of thing
  // (a structure, a drug, ...). The label reuses each section's own heading so the
  // chip can't drift from the panel, except connections (the structure panel's
  // "Connectivity" heading names a property, not a kind, so the chip has its own key). Only types actually present become chips, plus
  // an "All" reset; `activeType` (null = all) persists for the session like the
  // query text does. Built once (the item set is static).
  const searchFilters = document.getElementById("search-filters");
  const FILTER_LABELS = {
    structure: "panel.structures", connection: "search.filterConnections",
    target: "panel.receptors", drug: "panel.drugs",
    circuit: "legend.circuits", group: "legendKey.pathways",
    enzyme: "panel.enzymes", effect: "panel.effects", command: "search.filterCommands",
  };
  let activeType = null;
  const filterChips = [];
  const presentTypes = [...new Set(items.map((it) => it.type))]
    .filter((ty) => ty in FILTER_LABELS);
  if (searchFilters && presentTypes.length > 1) {
    const addChip = (type, labelKey) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "search-filter" + (type === activeType ? " active" : "");
      b.textContent = t(labelKey);
      b.addEventListener("click", () => {
        activeType = type;
        for (const c of filterChips) c.el.classList.toggle("active", c.type === activeType);
        renderResults();
        searchInput.focus();
      });
      searchFilters.appendChild(b);
      filterChips.push({ type, el: b });
    };
    addChip(null, "search.filterAll");
    for (const ty of presentTypes) addChip(ty, FILTER_LABELS[ty]);
  }

  // Index (among the non-empty rows) of the keyboard-highlighted result, or -1
  // when there is none. Arrow keys move it; Enter activates it (the first by
  // default, since renderResults pre-highlights row 0).
  let activeIndex = -1;
  // True while a hover preview (a transient focus, see the row mouseenter) is
  // applied but not yet committed by a click. Leaving the result list restores the
  // brain to neutral; a click clears the flag so the committed focus survives.
  let previewing = false;
  searchResults.addEventListener("mouseleave", () => {
    if (previewing) { previewing = false; selection.clear(); }
  });
  const resultRows = () => [...searchResults.querySelectorAll("li:not(.empty)")];
  function highlight(index) {
    const rows = resultRows();
    if (rows.length === 0) { activeIndex = -1; return; }
    activeIndex = (index + rows.length) % rows.length; // wrap past either end
    rows.forEach((li, i) => li.classList.toggle("active", i === activeIndex));
    rows[activeIndex].scrollIntoView({ block: "nearest" });
  }

  // Rebuild the (capped) result list from the current query. An empty query
  // lists everything so the box doubles as a browsable index.
  function renderResults() {
    // Parse a leading `field:"value"` filter (else plain free text). A field filter
    // keeps only items carrying that field whose value matches; the trailing free
    // text still matches the label + keywords.
    const { field, value, rest } = parseSearchQuery(searchInput.value);
    syncClear();
    searchResults.innerHTML = "";
    // A structured filter (class:"..." / nbn:"...") is a deliberate "list the whole
    // class" query, so show more rows than the compact name-search list (the results
    // box scrolls). Plain name search stays capped short.
    const cap = field ? 40 : 8;
    // Score each surviving item so the most relevant rise to the top of the capped
    // list (rankMatch, js/search-rank.js: label prefix, then a whole-word alias or a
    // label word start, then mid-word hits). Without this, array order alone buried the
    // late entries (circuits, projection groups) under a common query like
    // "dopamine". An empty query (browse-all) and field-only filters leave `rest`
    // empty -> every item scores 0 -> the stable `idx` tiebreak keeps the original
    // order (structures first).
    const scored = [];
    items.forEach((it, idx) => {
      if (activeType && it.type !== activeType) return; // type chip scopes the list
      if (field) {
        const fv = it.fields && it.fields[field];
        if (fv === undefined) return; // only items carrying this field
        if (value && !fv.includes(value)) return;
      }
      let score = 0;
      if (rest) {
        score = rankMatch(foldText(it.label), foldText(it.keywords || ""), rest);
        if (score === null) return; // no match in label or keywords
      }
      scored.push({ it, score, idx });
    });
    scored.sort((a, b) => a.score - b.score || a.idx - b.idx);
    const matches = scored.slice(0, cap).map((s) => s.it);
    if (matches.length === 0) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = t("search.noMatch");
      searchResults.appendChild(li);
      activeIndex = -1;
      return;
    }
    matches.forEach((item, i) => {
      const li = document.createElement("li");
      li.textContent = item.label;
      li.addEventListener("click", () => {
        previewing = false; // the pick is now the committed focus, not a preview
        item.select();
        closeSearch();
      });
      // Hovering syncs the highlight (so mouse + keyboard agree on the active row)
      // AND transiently applies the row's full focus, so you can dim the brain down
      // to each result in turn to compare them without committing. Restored when the
      // pointer leaves the list (the #search-results mouseleave below).
      li.addEventListener("mouseenter", () => {
        highlight(i);
        if (item.preview) { item.preview(); previewing = true; }
      });
      searchResults.appendChild(li);
    });
    highlight(0); // pre-highlight the first match: Enter selects it straight away
  }

  // Bilingual matching: each row's `names` gain their other-language twin in
  // `keywords`, so "Hippocampe" finds the hippocampus from the English UI and
  // "Hippocampus" from the French one. The table is fetched the first time search
  // opens (never at startup) and folded in once; the open popup then re-renders.
  let bilingual = null;
  function loadBilingualNames() {
    bilingual ??= loadSearchNames().then((other) => {
      for (const item of items) {
        const alt = (item.names || []).map(other).filter(Boolean);
        if (alt.length) item.keywords = `${item.keywords || ""} ${alt.join(" ")}`;
      }
      if (!searchBox.hidden) renderResults();
    });
  }

  function openSearch() {
    loadBilingualNames();
    // Search is a popup over the scene, but a pick lands in the panel (a detail tab,
    // or a flashed control in Settings), so a collapsed panel is expanded first or
    // the pick would happen out of sight.
    expandPanel();
    searchBox.hidden = false;
    searchToggle.classList.add("active");
    // Keep whatever was last typed this session: the input retains its value while
    // hidden, and a page reload (a new session) starts it empty, so this is
    // session-scoped memory with no persistence. Re-render the matching results for
    // the remembered query and select all of it, so the next keystroke replaces it
    // while Enter / arrow-browsing the existing results still works straight away.
    renderResults();
    searchInput.focus();
    searchInput.select();
    urlState.sync(); // whether the panel is searching is part of the shareable link
  }
  function closeSearch() {
    searchBox.hidden = true;
    searchToggle.classList.remove("active");
    urlState.sync();
  }
  // The popup's own exits, besides Esc (the input's keydown below, and
  // wireShortcuts when focus sits elsewhere) and a pick: the × and a backdrop click.
  document.getElementById("search-close")?.addEventListener("click", closeSearch);
  searchBox.addEventListener("click", (event) => {
    if (event.target === searchBox) closeSearch();
  });

  // Open search pre-filled with a query (a drug panel's clickable Class /
  // Nomenclature hands back e.g. `class:"SNRI"`), so the structured filter runs
  // immediately. Works whether search was open or closed.
  function openSearchWithQuery(query) {
    if (searchBox.hidden) openSearch();
    searchInput.value = query;
    renderResults();
    searchInput.focus();
    urlState.sync();
  }

  // The "?" button toggles the search-syntax help block beneath the bar.
  const searchHelp = document.getElementById("search-help");
  const searchSyntax = document.getElementById("search-syntax");
  if (searchHelp && searchSyntax) {
    searchHelp.addEventListener("click", () => {
      const show = searchSyntax.hidden;
      searchSyntax.hidden = !show;
      searchHelp.setAttribute("aria-expanded", String(show));
    });
  }

  searchToggle.addEventListener("click", () => {
    if (searchBox.hidden) openSearch();
    else closeSearch();
  });
  searchInput.addEventListener("input", renderResults);

  // `q=<query>`: the in-panel search, which replaces the panel's normal controls, so
  // whether it is open at all is UI state. An OPEN but empty box reads as `q=` (the
  // empty string), a closed one as null, which is the difference between "searching,
  // nothing typed yet" and "not searching". Typing is continuous, so its sync waits
  // for a pause rather than writing per keystroke.
  urlState.register("q", {
    read: () => (searchBox.hidden ? null : searchInput.value),
    write: (v) => (v === "" ? openSearch() : openSearchWithQuery(v)),
  });
  searchInput.addEventListener("input", () => urlState.sync(TYPING_SETTLE_MS));
  // The inline "×": wipe the query, re-render (now empty -> the neutral list) and
  // keep focus so the user can retype immediately; syncClear (in renderResults)
  // hides the button again.
  if (searchClear) {
    searchClear.addEventListener("click", () => {
      searchInput.value = "";
      renderResults();
      searchInput.focus();
    });
  }
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      highlight(activeIndex + 1);
      event.preventDefault(); // don't move the text caret
    } else if (event.key === "ArrowUp") {
      highlight(activeIndex - 1);
      event.preventDefault();
    } else if (event.key === "Enter") {
      const rows = resultRows();
      const pick = rows[activeIndex] || rows[0]; // highlighted, else the first
      if (pick) pick.click();
    } else if (event.key === "Escape") {
      closeSearch();
    }
  });

  // Ctrl/Cmd+F opens our in-panel search instead of the browser's native find
  // (which would be useless here: the structures/connections are canvas + data,
  // not page text). If search is already open we just re-focus and select its
  // text so a second press lets the user retype straight away.
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && (event.key === "f" || event.key === "F")) {
      event.preventDefault();
      if (searchBox.hidden) {
        openSearch();
      } else {
        // Already open: refocus + select so a second press retypes straight away.
        searchInput.focus();
        searchInput.select();
      }
    }
  });

  return { openSearchWithQuery };
}
