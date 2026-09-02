// Data browser: one flat, searchable list of every graded knowledge node.
//
// The Sources & provenance popup answers "how well sourced is the dataset?" with
// bars and one example node per kind; this section answers the next question the
// bars provoke, "which ones?", by listing every node behind them. Same nodes, same
// grades, same navigation callbacks: only the presentation differs, so the two must
// never drift apart (collectNodes below is the enumeration, buildKindExample in
// main.js picks one representative from the same fields).
//
// It doubles as a sourcing workbench, which is why the default sort is weakest-grade
// first: the unsourced claims surface on top rather than being buried under the
// verified majority.
//
// No three.js here: rows navigate through the `nav` callbacks main.js hands in, so
// this module never touches the scene.

import { loadFlag, saveFlag } from "./prefs.js";

// Sort rank of a display grade, weakest to strongest. `uncertain` sits between
// sourced and verified for the same reason the Sources popup's bar does: the quote
// really was checked, it just may not attribute the claim.
const GRADE_RANK = { nosource: 0, llm: 1, sourced: 2, uncertain: 3, verified: 4 };

// Enumeration order, and therefore the kind <select>'s option order. Kinds absent
// from the loaded dataset are dropped from the select, never from this list.
const KIND_ORDER = [
  "structures",
  "projections",
  "circuits",
  "projection_groups",
  "receptors",
  "receptor_class",
  "receptor_sign",
  "receptor_synaptic",
  "receptor_locations",
  "receptor_density",
  "targets",
  "target_polarity",
  "target_locations",
  "target_density",
  "drug_bindings",
  "drug_nbn",
  "drug_brands",
  "drug_categories",
  "drug_half_life",
  "drug_enzymes",
  "drug_metabolites",
  "drug_metabolite_enzyme",
  "drug_metabolite_bindings",
];

// How many rows render at once. The full list is several thousand nodes, so the
// first paint is capped and each "show more" appends a bigger chunk (by then the
// reader has decided the filter is the one they want).
const PAGE_FIRST = 150;
const PAGE_MORE = 300;

// A trailing `_R` / `_L` is a rendering detail, not part of a region's identity.
const stripSide = (id) => String(id || "").replace(/_[RL]$/, "");

/**
 * Enumerate every graded knowledge node in the dataset as a flat row list.
 *
 * A row is `{kind, name, notion, grade, uncertain, go, sources, uncertainty, ki}`:
 * `kind` is the provenance-tally key (so it labels through the very i18n strings the
 * Sources popup's bars use), `name` names the node's owner, `notion` states the claim,
 * and `grade` is the DISPLAY grade a pill would show ("verified" / "sourced" / "llm" /
 * "nosource", or "uncertain" when the node carries uncertainty bullets, which is
 * what the panel's orange badge does). `go` navigates to the owning panel, or is
 * null for a node whose owner has nothing to focus (an unlocated target, an
 * unbindable drug), which renders the row inert. The last three carry the node's
 * BACKING (its quote-level sources, its reasons to doubt, its measured Ki) so the
 * row's pill shows the concrete source rather than the grade alone: the row's shape
 * is deliberately the one `ui.pill` (the panel's own source-backed pill) consumes,
 * so a row is handed straight to it.
 *
 * Wikipedia references are deliberately absent: a reference points *at* a node, it
 * is not itself one (same rule as the popup's bars). The per-kind counts otherwise
 * match `meta.provenance_stats.by_kind` exactly, so a drift between the two is a
 * bug; `twins: false` is the one deliberate departure (see `structures` below).
 *
 * @param {import("./data.js").BrainData} data normalized dataset
 * @param {{t: Function, formatHalfLife: Function, nav: object}} deps
 * @param {{twins?: boolean}} [opts] `twins` (default true) lists both hemispheres of
 *   a mirrored region; false collapses each pair to one side-less row
 * @returns {Array<{kind: string, name: string, notion: string, grade: string,
 *                  uncertain: boolean, go: (() => void)|null, sources: object[],
 *                  uncertainty: object[], ki: object|null}>}
 */
export function collectNodes(data, deps, opts = {}) {
  const { t, formatHalfLife, nav } = deps;
  const twins = opts.twins !== false;
  const rows = [];
  // `grade` is already defaulted by each caller (the per-kind default differs: an
  // unsourced classification is authored, hence "llm", while an unsourced binding
  // never had a source at all, hence "nosource"), so only the uncertainty override
  // lives here. `src` is the node's backing, `{sources, uncertainty, ki}` (any of
  // them optional); a binding object already has exactly those keys, so it is passed
  // through whole.
  const push = (kind, name, notion, grade, go, src) => {
    const uncertainty = (src && src.uncertainty) || [];
    rows.push({
      kind,
      name: name || "",
      notion: notion || "",
      grade: uncertainty.length ? "uncertain" : (grade || "nosource"),
      uncertain: !!uncertainty.length,
      go: go || null,
      sources: (src && src.sources) || [],
      uncertainty,
      ki: (src && src.ki) || null,
    });
  };

  const byId = data.byId || new Map();
  const meta = data.meta || {};
  const regionName = (id) => {
    const s = id && byId.get(id);
    return s ? (s.base_name || s.name) : null;
  };
  // A density profile is keyed by structure *base*, which is only a key in byId for
  // a midline region, so a lateralized one resolves through its right-hand member.
  const baseLabel = (base) => regionName(base) || regionName(`${base}_R`) || base;
  const topRegion = (info) => {
    const bases = info && info.profile ? Object.keys(info.profile) : [];
    return bases.length ? baseLabel(bases[0]) : "";
  };
  // A binding with a measured Ki but no established direction has no action label,
  // so it reads as its target plus the panel's own "affinity only" caveat.
  const bindingNotion = (b) => (b.affinityOnly
    ? `${b.targetName} (${t("drug.affinityOnly")})`
    : `${b.actionLabel}, ${b.targetName}`);

  // Structures. A symmetric region is authored once and mirrored, so the `_L` twin
  // repeats its twin's group and grade verbatim, differing only in the side its name
  // carries. Collapsing the pair (the default) is the better *read*, since it says one
  // thing twice, and the collapsed row then drops the side from its name; listing both
  // is what makes the browser's count match the coverage tally, which counts each
  // emitted record (57 rows against 32 collapsed).
  for (const s of data.structures || []) {
    const twin = /_L$/.test(s.id) && byId.has(`${stripSide(s.id)}_R`);
    if (twin && !twins) continue;
    push("structures", twins ? s.name : (s.base_name || s.name),
      (meta.groupLabels || {})[s.group] || s.group,
      s.classification_provenance || "llm",
      () => nav.structure(s.id), s);
  }

  // Projections. The loader pushes a flipped copy of every `mirror: true` pathway,
  // so the two hemispheres arrive as separate records for one node; collapse them
  // on the side-stripped route.
  const seenProjection = new Set();
  for (const p of data.projections || []) {
    const key = `${stripSide(p.from)}|${stripSide(p.to)}|${p.label}`;
    if (seenProjection.has(key)) continue;
    seenProjection.add(key);
    push("projections", p.label, p.neurotransmitter || p.kind,
      p.provenance, () => nav.connection(p), p);
  }

  for (const c of data.circuits || []) {
    push("circuits", c.name, "", c.provenance, () => nav.circuit(c), c);
  }
  for (const g of data.projectionGroups || []) {
    push("projection_groups", g.name, "", g.provenance, () => nav.group(g), g);
  }

  // A receptor's panel is its entry in the merged browse list (`data.targets`), not
  // the raw record, so index the two together once and reuse it for all six receptor
  // kinds below.
  const targetByReceptor = new Map();
  for (const tg of data.targets || []) {
    if (tg.kind === "receptor" && tg.receptor) targetByReceptor.set(tg.receptor.id, tg);
  }
  // Each of the four classification attributes is its own graded sub-claim (a quote
  // that backs the sign lends nothing to the GPCR claim), so each gets a row.
  const RECEPTOR_ATTRS = [
    ["receptors", "family", "familyLabel"],
    ["receptor_class", "receptor_class", "classLabel"],
    ["receptor_sign", "sign", "signLabel"],
    ["receptor_synaptic", "synaptic", "synapticLabel"],
  ];
  for (const r of data.receptors || []) {
    const entry = targetByReceptor.get(r.id);
    const go = entry && entry.focusable ? () => nav.target(entry) : null;
    // A pure stub (a receptor with no CNS role: no locations, not ubiquitous, no
    // description) states nothing, so it is not a classification node and gets no
    // rows. Same predicate as the tally's `scored_receptors`, or the browser would
    // list six claims the coverage bars do not count.
    if (r.ubiquitous || (r.locations || []).length || r.description) {
      for (const [kind, attr, labelField] of RECEPTOR_ATTRS) {
        const claim = (r.classification || {})[attr] || {};
        push(kind, r.name, r[labelField], claim.grade || "llm", go, claim);
      }
    }
    for (const e of r.locationInfo || []) {
      push("receptor_locations", r.name, e.name, e.provenance || "llm", go, e);
    }
    // A ubiquitous receptor has one expression node covering the whole brain rather
    // than a row per region.
    if (r.ubiquitousInfo) {
      push("receptor_locations", r.name, t("receptor.ubiquitous"),
        r.ubiquitousInfo.provenance || "llm", go, r.ubiquitousInfo);
    }
    // ONE node for the whole profile, not one per region: it is a single measurement
    // ranking the receptor's regions against each other, so it is named by the region
    // it ranks highest (a bare receptor name would not state the claim).
    if (r.densityInfo) {
      push("receptor_density", r.name, topRegion(r.densityInfo),
        r.densityInfo.provenance || "llm", go, r.densityInfo);
    }
  }

  for (const tg of data.targets || []) {
    if (tg.kind === "receptor") continue; // covered above, from the raw record
    const go = tg.focusable ? () => nav.target(tg) : null;
    push("targets", tg.name, tg.typeLabel, tg.classificationProvenance || "llm", go, tg);
    // The direction-flipping polarity flag is its own node, distinct from the
    // classification grade, because it flips the drug-flow overlay's sign.
    if (tg.polarityProvenance) {
      push("target_polarity", tg.name, t("target.polarity"), tg.polarityProvenance, go,
        { sources: tg.polaritySources });
    }
    for (const e of tg.locationInfo || []) {
      push("target_locations", tg.name, e.name, e.provenance || "llm", go, e);
    }
    if (tg.densityInfo) {
      push("target_density", tg.name, topRegion(tg.densityInfo),
        tg.densityInfo.provenance || "llm", go, tg.densityInfo);
    }
  }

  // A metabolite's receptor BINDINGS are a property of the molecule, so a metabolite
  // shared by two parents contributes them once (the applier writes an identical list
  // to each parent). Its identity and its formation are not: "X is a metabolite of A"
  // and "X is a metabolite of B" are two separately sourced claims, and two parents
  // make it by two reactions, so both stay per parent. Matches the tally's own split.
  const seenMetaboliteBinding = new Set();
  for (const d of data.drugs || []) {
    const go = d.focusable ? () => nav.drug(d) : null;
    for (const b of d.bindings || []) {
      push("drug_bindings", d.name, bindingNotion(b), b.provenance, go, b);
    }
    if (d.nbn) push("drug_nbn", d.name, d.nbn, d.nbnProvenance, go,
      { sources: d.nbnSources });
    for (const br of d.brandsOrdered || []) {
      const src = (br.sources || [])[0];
      push("drug_brands", d.name, br.name, src && src.provenance, go, br);
    }
    if ((d.categoryLabels || []).length) {
      push("drug_categories", d.name, d.categoryLabels.join(", "),
        d.categoryProvenance || "llm", go, { sources: d.categorySources });
    }
    if (d.halfLife) {
      push("drug_half_life", d.name, `T½ ${formatHalfLife(d.halfLife)}`,
        d.halfLifeProvenance, go, { sources: d.halfLifeSources });
    }
    for (const e of d.enzymes || []) {
      push("drug_enzymes", d.name, `${e.label}: ${e.roleLabel}`, e.provenance, go, e);
    }
    for (const m of d.metabolites || []) {
      const mKey = (m.name || "").toLowerCase();
      push("drug_metabolites", d.name, m.name, m.provenance, go, m);
      for (const f of m.formedBy || []) {
        push("drug_metabolite_enzyme", d.name,
          `${m.name}: ${t("drug.formedBy")} ${f.label}`, f.provenance, go, f);
      }
      for (const b of m.ownBindings || []) {
        const bKey = `${mKey}|${b.target}`;
        if (seenMetaboliteBinding.has(bKey)) continue;
        seenMetaboliteBinding.add(bKey);
        push("drug_metabolite_bindings", d.name, `${m.name}: ${bindingNotion(b)}`,
          b.provenance, go, b);
      }
    }
  }

  return rows;
}

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
 * @param {import("./data.js").BrainData} opts.data
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

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

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
  const moreBtn = el("button", "node-more");
  moreBtn.type = "button";
  moreBtn.hidden = true;

  // What a node IS, said once above the list, because a flat list of sentences does
  // not by itself reveal that each line is a record with fields. The header below
  // then names those fields, and the "as files" link hands over the very same nodes
  // in their stored form.
  const intro = el("p", "node-intro", t("nodes.intro"));
  const filesBtn = el("button", "node-datafiles", t("nodes.dataFiles"));
  filesBtn.type = "button";
  filesBtn.title = t("nodes.dataFilesHint");
  filesBtn.addEventListener("click", () => openDataFiles?.());
  intro.appendChild(document.createTextNode(" "));
  intro.appendChild(filesBtn);

  // The column header, built with a row's exact structure (grade cell, then a
  // three-column inner box mirroring .node-main) so the two share one grid template
  // in the stylesheet and each key really sits over the cell it names.
  const head = el("div", "node-head");
  const headMain = el("span", "node-head-main");
  for (const [key, tip] of COLUMNS) {
    const cell = el("span", `node-head-cell node-head-${key}`, key);
    cell.title = t(tip);
    (key === "grade" ? head : headMain).appendChild(cell);
  }
  head.appendChild(headMain);

  const rowEl = (r) => {
    // A div rather than a button: the grade pill is itself a <button> (it pins its
    // tooltip on touch), and nesting one inside another is invalid, so the clickable
    // half is an inner button beside the pill.
    const wrap = el("div", "node-row");
    // The row IS the pill's `{sources, uncertainty, ki}` argument, so a browser pill
    // opens on the node's verbatim quote (or its reasons to doubt, or its measured
    // Ki), exactly like the same node's pill inside a detail panel.
    wrap.appendChild(pill(r.grade, r));
    const main = el("button", r.go ? "node-main clickable" : "node-main");
    main.type = "button";
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
        dir * (GRADE_RANK[a.grade] - GRADE_RANK[b.grade]) || byName(a, b));
    }
    // The twins choice only ever splits or collapses `structures` rows, so offer it
    // only while the current result contains some (both readings keep the kind, so
    // the control does not hide itself the moment it is used).
    twinsLabel.hidden = !matches.some((r) => r.kind === "structures");
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
      ...["verified", "uncertain", "sourced", "llm", "nosource"]
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
    body.appendChild(head);
    body.appendChild(list);
    body.appendChild(moreBtn);
    apply();
  };

  return {
    /** Collect + render on first use; a no-op on every reopen. */
    open() { build(); },
  };
}
