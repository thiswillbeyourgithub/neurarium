// The panel toolbar: reset view, and the search box (data + the panel's own
// controls, ranked by search-rank.js).

import { controlName, foldText, parseSearchQuery } from "../search/query.js";
import { flashRow } from "../panel/dom.js";
import { loadSearchNames } from "../data.js";
import { rankMatch } from "../search-rank.js";
import { stripSide } from "../util.js";

const { t } = window.__I18N__;

// How long a continuously-changing control (a text box being typed into) must be
// still before its value is written to the URL, so one edit costs one history write.
export const TYPING_SETTLE_MS = 400;

/**
 * Hemisphere tag for a connection, derived from its endpoint ids, so the two
 * mirrored copies of a pathway (and the cross-midline commissures) are
 * distinguishable in the search list (which matches on the bare label).
 * @param {object} proj
 * @returns {string} "R", "L", "L↔R", or "" (purely midline).
 */
function connectionSideTag(proj) {
  const right = proj.from.endsWith("_R") || proj.to.endsWith("_R");
  const left = proj.from.endsWith("_L") || proj.to.endsWith("_L");
  if (left && right) return "L↔R";
  if (right) return "R";
  if (left) return "L";
  return "";
}

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

  // One searchable index over structures + connections + receptors, each carrying
  // the action to run when it is picked. Built once. Mirrored L/R twins are
  // collapsed to a single row (a brain is symmetric, so "frontal lobe" and
  // "corticothalamic" each list once and a pick focuses *both* hemispheres, not one);
  // receptors show their neurotransmitter as a tag (and carry extra `keywords` so the
  // system / mechanism also match). The match runs over `label` + `keywords`; only
  // `label` is shown.
  // Group meshes / arrows by their side-stripped base so each pair yields one row.
  const meshesByBase = new Map();
  for (const mesh of meshes) {
    const base = stripSide(mesh.userData.structure.id);
    (meshesByBase.get(base) || meshesByBase.set(base, []).get(base)).push(mesh);
  }
  const arrowsByBase = new Map();
  for (const arrow of arrows) {
    const p = arrow.projection;
    const key = `${stripSide(p.from)}->${stripSide(p.to)}`;
    (arrowsByBase.get(key) || arrowsByBase.set(key, []).get(key)).push(arrow);
  }
  // Everything the panel can DO, listed beside everything it can show: the popups
  // (About, the Legend, Sources & provenance, the keyboard shortcuts, What's new),
  // the Data browser and the other browse sections, the view toggles and options, and
  // the guided tour. A control joins this index by carrying `data-search` in the
  // markup and is named by its own visible label, so a new option is findable the day
  // it lands and can never drift from what the panel calls it: search owns no second
  // copy of what a control is or does, and a pick just clicks it. The search box
  // itself deliberately carries no mark, since a result that opens the search you are
  // already inside is a loop rather than a result.
  const commandRows = [...document.querySelectorAll("[data-search]")].map((elm) => {
    const box = elm.type === "checkbox" ? elm : null;
    // A checkbox is named by the <label> wrapping it; everything else by itself. Both
    // go through controlName, the one definition of what a control is called.
    const labelEl = box ? box.closest("label") : null;
    return {
      type: "command",
      // Derived on read, never stored alongside the control it describes: an option
      // has to say what it is set to *now*, and the theme + panel-only buttons rename
      // themselves on each click (they name the state a click would give you, not the
      // one showing). A getter is live by construction, so no render path can read a
      // stale one.
      get label() {
        const name = controlName(labelEl || elm);
        return box ? `${name} · ${t(box.checked ? "search.on" : "search.off")}` : name;
      },
      // The attribute's value, when it has one, is a list of aliases: the words a
      // visitor is likely to type for a control whose visible name does not contain
      // them ("tour" for Start the tutorial, "citations" for Sources & provenance).
      // Never a second name, always extra ways in to the one the panel shows. Spelled
      // once each: the matcher folds accents on both sides (see foldText), so the
      // unaccented twin of an accented alias would be dead weight.
      keywords: elm.dataset.search || "",
      // Picked is done: this clicks the real control, so its handler stays the one
      // definition of what it means. An option additionally flashes itself, since
      // what it changed may be nowhere near the panel; a button opens something
      // visible and needs no pointing at. flashRow defers a frame, which lands after
      // the pick has closed the search box and put the controls back on screen.
      //
      // An option inside a collapsed accordion body (Show active metabolites lives in
      // the Drugs section) has to have that section opened first, or the pick flips a
      // persisted preference with nothing at all to show for it: scrollIntoView and
      // the flash are both no-ops on a `hidden` subtree. Opening is the section's own
      // header click, for the same reason the pick itself is the control's own.
      select: () => {
        if (box) {
          tabs.showSettings(); // the flashed option lives in the Settings pane
          const head = elm.closest("[hidden]")?.previousElementSibling;
          if (head?.classList.contains("collapse-header")) head.click();
        }
        elm.click();
        if (box) flashRow(labelEl || box);
      },
    };
  });

  const items = [
    ...[...meshesByBase.values()].map((group) => {
      // Frame a representative (prefer the midline / right member); the isolate
      // already spans both sides via isolateGroupFor, so both hemispheres dim in.
      const rep = group.find((m) => !/_[LR]$/.test(m.userData.structure.id)) || group[0];
      const s = rep.userData.structure;
      return {
        type: "structure",
        // base_name is the hemisphere-stripped name ("frontal lobe"); fall back to
        // the full name for a genuine singleton.
        label: s.base_name || s.name,
        names: [s.base_name || s.name],
        keywords: (s.aliases || []).join(" "),
        select: () => selectStructure(rep, { frame: true, isolate: true }),
        preview: () => selectStructure(rep, { isolate: true, preview: true }),
      };
    }),
    ...[...arrowsByBase.values()].map((group) => {
      const rep = group[0];
      const proj = rep.projection;
      const siblings = group.slice(1);
      // A clean L/R pair needs no side tag; a lone / crossing pathway keeps its tag.
      const tag = siblings.length ? "" : connectionSideTag(proj);
      return {
        type: "connection",
        label: proj.label + (tag ? ` · ${tag}` : ""),
        names: [proj.label],
        // Frame + isolate both twins, so a connection search pick dims the rest of the
        // brain and lights both hemispheres, not just the picked side.
        select: () => selectConnection(rep, { frame: true, isolate: true, siblings }),
        preview: () => selectConnection(rep, { isolate: true, preview: true, siblings }),
      };
    }),
    // Focusable receptors + non-receptor targets (a stub / unlocated target has no
    // anatomy to show, so it stays a legend-only listing). A receptor shows its
    // neurotransmitter as the tag, a target its type; keywords carry the system /
    // mechanism so they match too without cluttering the row.
    ...(data.targets || []).filter((tgt) => tgt.focusable).map((tgt) => {
      const tag = tgt.kind === "receptor"
        ? (tgt.receptor && tgt.receptor.neurotransmitter)
        : tgt.typeLabel;
      return {
        type: "target",
        label: tgt.name + (tag ? ` · ${tag}` : ""),
        names: [tgt.name],
        keywords: tgt.keywords || "",
        select: () => focusTarget(tgt, { frame: true }),
        preview: () => focusTarget(tgt, { preview: true }),
      };
    }),
    // Focusable drugs (those with a binding profile). The row shows the primary
    // class as a tag; keywords carry the full class list + nomenclature + targets.
    // `fields` feeds the structured `class:"..."` / `nbn:"..."` filters (the panel's
    // clickable Class / Nomenclature values), pre-folded for matching.
    ...(data.drugs || []).filter((d) => d.focusable).map((drug) => ({
      type: "drug",
      label: drug.displayName + (drug.category ? ` · ${drug.category}` : ""),
      names: [drug.name, ...drug.categoryLabels],
      keywords: drug.keywords || "",
      fields: {
        class: foldText(drug.categoryLabels.join(" ")),
        nbn: foldText(drug.nbn || ""),
      },
      select: () => focusDrug(drug, { frame: true }),
      preview: () => focusDrug(drug, { preview: true }),
    })),
    // Active metabolites that are not themselves a focusable drug (a metabolite that
    // IS a modeled drug is already searchable as its own drug row, so it is skipped
    // here to avoid a duplicate). A pick focuses the parent drug, whose panel lists
    // the metabolite under "Active metabolites"; the label carries the "metab. of X"
    // tag and keywords match on both the metabolite and the parent name. A metabolite
    // produced by several parents (e.g. mCPP) collapses to ONE entry keyed by its
    // metabolite id, listing every parent, so search never shows the same molecule twice.
    ...(() => {
      const byKey = new Map();
      for (const drug of (data.drugs || []).filter((d) => d.focusable)) {
        for (const m of (drug.metabolites || []).filter((x) => !x.linkFocusable)) {
          const key = m.id;
          const existing = byKey.get(key);
          if (existing) {
            if (!existing.prodrugs.includes(drug.displayName)) existing.prodrugs.push(drug.displayName);
            existing.keywords += ` ${drug.name} ${drug.displayName} ${drug.keywords || ""}`;
            continue;
          }
          // The first parent seen owns the focus target; every parent's panel lists this
          // metabolite identically, so which one we open does not matter.
          byKey.set(key, {
            name: m.name,
            drug,
            prodrugs: [drug.displayName],
            keywords: `${drug.name} ${drug.displayName} ${drug.keywords || ""}`,
          });
        }
      }
      // A metabolite has no panel of its own, so the pick opens its parent drug and
      // hands over the name it was searched under: the parent's panel then scrolls to
      // that metabolite's row and flashes it. Without it, searching 6-Monoacetylmorphine
      // simply opened a Heroin tab, with nothing on screen tying the two together.
      return [...byKey.values()].map((e) => ({
        type: "drug",
        label: `${e.name} · ${t("drug.metaboliteOf", { prodrug: e.prodrugs.join(", ") })}`,
        names: [e.name],
        keywords: e.keywords,
        select: () => focusDrug(e.drug, { frame: true, highlightMetabolite: e.name }),
        preview: () => focusDrug(e.drug, { preview: true }),
      }));
    })(),
    // Drug-metabolising enzymes (the Enzymes section). Pharmacokinetics, so a pick
    // changes nothing in the 3D scene; it opens the isoform's panel exactly like its
    // legend row, which is the whole point: an enzyme is a graded node with drugs on
    // both sides of it, and it was reachable only by scrolling its section.
    ...(data.enzymes || []).map((enz) => ({
      type: "enzyme",
      label: `${enz.label} · ${t("search.tagEnzyme")}`,
      names: [enz.label],
      keywords: enz.keywords || "",
      select: () => focusEnzyme(enz),
      // No preview: an enzyme focus is a panel, not a scene state, so there is
      // nothing for a hover to show and nothing for it to restore.
    })),
    // Clinical effects (the Effects section, BETA): a pick opens the effect's panel,
    // like its legend row; no scene state, so no preview (as for an enzyme).
    ...(data.effects || []).map((effect) => ({
      type: "effect",
      label: `${effect.label} · ${t("search.tagEffect")}`,
      names: [effect.label],
      keywords: effect.keywords || "",
      select: () => focusEffect(effect),
    })),
    // Named circuits (the loops in the Projections section): a pick isolates the
    // loop, plays its traveling pulse and opens its panel, exactly like its legend
    // row, so search reaches them too (part of "anything from search == the panel").
    ...(data.circuits || []).map((circuit) => ({
      type: "circuit",
      label: `${circuit.name} · ${t("search.tagCircuit")}`,
      names: [circuit.name],
      keywords: circuit.description || "",
      select: () => focusCircuit(circuit, { frame: true }),
      preview: () => focusCircuit(circuit, { preview: true }),
    })),
    // Projection groups (the per-transmitter / per-sign rows of the Projections
    // legend): a pick pins that whole pathway group + dims the rest + opens its
    // panel, like its legend row. Both colour modes' records are listed; their
    // names don't collide (transmitters vs excitatory/inhibitory/modulatory).
    ...(data.projectionGroups || []).map((group) => ({
      type: "group",
      label: `${group.name} · ${t("search.tagPathways")}`,
      names: [group.name],
      keywords: group.description || "",
      select: () => focusProjectionGroup(group, { frame: true }),
      preview: () => focusProjectionGroup(group, { preview: true }),
    })),
    ...commandRows,
  ];

  // Type-filter chips above the results: scope the search to one kind of thing
  // (a structure, a drug, ...). The label reuses each section's own heading so the
  // chip can't drift from the panel. Only types actually present become chips, plus
  // an "All" reset; `activeType` (null = all) persists for the session like the
  // query text does. Built once (the item set is static).
  const searchFilters = document.getElementById("search-filters");
  const FILTER_LABELS = {
    structure: "panel.structures", connection: "info.connections",
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
