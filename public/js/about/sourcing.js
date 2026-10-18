// The Sources & provenance popup body: intro, grade key, the per-kind coverage bars
// (each expandable to one example node) and the measured-affinity line.

import { exampleRow, KIND_LABELS } from "../kinds.js";
import { formatHalfLife, NOSOURCE_GLYPH } from "../panel/format.js";
import { collectNodes } from "../node-browser.js";
import { backed } from "../grades.js";
import { el, btn } from "../panel/dom.js";

const { t } = window.__I18N__;

// Display grade -> its short i18n label ("Verified", "No source", ...), shared by
// the Sources popup's bar segments and the Data browser's grade filter.
export const GRADE_LABELS = {
  verified: "about.segVerified",
  uncertain: "about.segUncertain",
  sourced: "about.segSourced",
  llm: "about.segLlm",
  nosource: "about.segNone",
  unknown: "about.segUnknown",
};

/**
 * Fill the About panel's "Sources & provenance" block from meta.provenanceStats:
 * the grade key (reusing the .src-pill swatches the info panel shows beside each
 * source) and the programmatic coverage tally. The numbers come straight from the
 * data (generate_data.py _provenance_stats), so the headline % is a real count.
 */
export function buildAboutSourcing(meta, opts = {}) {
  const host = document.getElementById("about-sourcing");
  if (!host) return;
  host.replaceChildren();

  // The "Sources & provenance" title is the #sourcing-modal's own <h2>; this block
  // is the intro + grade key + coverage tally. The intro + grade key need no loaded
  // data, so render them always: the popup is meaningful the instant it opens (on
  // demand), called first with no meta, then again with data.meta once loaded to
  // fill the tally.
  host.appendChild(el("p", "about-text", t("about.sourcingIntro")));
  // A source is not proof: sources err, quote-to-claim mapping can slip, and the
  // viewer has bugs. Keep this prominent so nobody reads a pill as "true".
  host.appendChild(el("p", "about-caveat", t("about.sourcingCaveat")));

  // Grade key: a pill swatch + its meaning, in weakest-to-strongest order (NOSOURCE
  // first, then LLM-only, then verified). The swatches reuse the info-panel CSS classes
  // so the legend matches what is shown next to each source. The `~ sourced` (orange)
  // and live-Wikipedia (green) rows are intentionally omitted: no *knowledge* node is
  // ever graded `sourced` (only Wikipedia references are, and they render as the green
  // link, not a coverage bar), so both rows explained pills that never label a tallied
  // node here and only added noise.
  const key = el("ul", "src-key");
  const keyRows = [
    ["src-todo", NOSOURCE_GLYPH, "about.gradeNone"],
    ["src-prov-unknown", "∅", "about.gradeUnknown"],
    ["src-prov-llm", "?", "about.gradeLlm"],
    ["src-prov-uncertain", "⚠", "about.gradeUncertain"],
    ["src-prov-verified", "✓", "about.gradeVerified"],
  ];
  for (const [cls, glyph, tip] of keyRows) {
    const li = document.createElement("li");
    li.appendChild(el("span", `src-pill ${cls}`, glyph));
    li.appendChild(el("span", null, t(tip)));
    key.appendChild(li);
  }
  // The grade key answers "how well is this backed"; this paragraph answers the
  // question it leaves open, "backed by what process". Two nodes can be equally green
  // and have got there by different routes, so rather than split the pill into tiers
  // nobody could rank, each source tooltip ends with its own chain of custody.
  key.appendChild(el("li", "src-key-note", t("about.quoteChains")));

  // Coverage tally: needs the loaded dataset's provenance stats, so it is skipped
  // on the first (pre-load, meta=null) call and filled in on the second. The grade
  // key reads better *after* the bars it explains, so append it last (below the
  // tally when there is one, otherwise it is all we have to show).
  const stats = meta && meta.provenanceStats;
  if (!stats) { host.appendChild(key); return; }

  // A headline over the knowledge nodes, then a per-node-kind bar.
  const a = stats.nodes || {};
  const wrap = el("div", "src-stats");
  // Rows are sorted best-coverage-first (highest % of backed nodes), ties broken by
  // the larger node count, so the strongest-sourced kinds head the list.
  const rows = [];
  for (const [kind, labelKey] of Object.entries(KIND_LABELS)) {
    const c = (stats.by_kind || {})[kind];
    if (!c || !c.total) continue;
    const verified = c.verified || 0;
    // Quote-checked like `verified`, so it counts as backed here exactly as it does
    // in the global bar; it only leaves the green segment. Omitting it left the
    // flagged nodes out of both the bar (a gap) and the kind's %.
    const uncertain = c.uncertain || 0;
    const sourced = c.sourced || 0;
    // Older meta lacked the llm/nosource split; fall back to lumping them as llm
    // (grey) so an out-of-date dataset still renders a sensible bar.
    const nosource = c.nosource != null ? c.nosource : 0;
    const llm = c.llm != null ? c.llm : (c.missing || 0) - nosource;
    const backedCount = backed(c);
    const pct = Math.round((100 * backedCount) / c.total);
    rows.push({
      kind, labelKey, verified, uncertain, sourced, llm, nosource,
      unknown: c.unknown || 0, backed: backedCount, total: c.total, pct,
    });
  }
  rows.sort((x, y) => y.pct - x.pct || y.total - x.total);
  // The grade segments, strongest to weakest: (count field, CSS class). `uncertain`
  // sits between verified and sourced on purpose: still quote-checked (it is not a
  // weaker document), but the sentence does not attribute the claim. Labels come
  // from the shared GRADE_LABELS.
  const SEGMENTS = [
    ["verified", "src-seg-verified"],
    ["uncertain", "src-seg-uncertain"],
    ["sourced", "src-seg-sourced"],
    ["llm", "src-seg-llm"],
    ["nosource", "src-seg-nosource"],
  ];
  // One flush segment per non-empty grade, width proportional to its share, so a
  // partly-sourced kind reads as green+yellow+grey+red instead of green-on-empty.
  const buildBar = (counts, total) => {
    const bar = el("div", "src-stat-bar");
    for (const [field, cls] of SEGMENTS) {
      const n = counts[field] || 0;
      if (!n || !total) continue;
      const seg = el("span", cls);
      seg.style.width = `${(100 * n) / total}%`;
      bar.appendChild(seg);
    }
    return bar;
  };
  // Only grades that actually occur, so a kind with nothing "sourced"/no-source reads
  // "Verified: 54" instead of trailing a row of zeros (the ~sourced tier is always 0
  // for knowledge nodes, which is why its legend row was dropped).
  // UNKNOWN (searched, nothing states it) is listed after the bar's grades but never
  // drawn in the bar: it sits outside the total the bar divides.
  const gradeCountsText = (counts) => [...SEGMENTS, ["unknown"]]
    .filter(([field]) => counts[field])
    .map(([field]) => `${t(GRADE_LABELS[field])}: ${counts[field]}`)
    .join("  ·  ");

  // The GLOBAL bar is the only thing shown by default: one aggregate number + bar over
  // every knowledge node. It is a button that expands the per-node-kind breakdown, so
  // the popup stays a single glanceable figure until the reader asks for detail.
  const globalCounts = {
    verified: a.verified || 0, uncertain: a.uncertain || 0, sourced: a.sourced || 0,
    llm: a.llm || 0, nosource: a.nosource || 0,
  };
  const globalBtn = btn("src-global");
  globalBtn.setAttribute("aria-expanded", "false");
  globalBtn.appendChild(el("p", "src-stat-headline",
    t("about.sourcingHeadline", { pct: a.pct_backed, total: a.total })));
  globalBtn.appendChild(buildBar(globalCounts, a.total));
  if (a.unknown) {
    globalBtn.appendChild(el("p", "src-stat-unknown",
      t("about.sourcingUnknown", { n: a.unknown })));
  }
  globalBtn.appendChild(el("span", "src-global-hint", t("about.sourcingByKind")));
  wrap.appendChild(globalBtn);

  // The per-kind breakdown, hidden until the global bar is clicked. Each kind is itself
  // a button revealing its grade counts + one clickable example node (built from the
  // loaded dataset when available, so it navigates to a real drug/receptor/structure).
  const kindsBox = el("div", "src-kinds");
  kindsBox.hidden = true;
  let rowsCache = null;
  const exampleRows = () => rowsCache
    || (rowsCache = collectNodes(opts.data, { t, formatHalfLife, nav: opts.nav },
      { twins: false }));
  for (const r of rows) {
    const row = el("div", "src-stat-row");
    const head = btn("src-stat-head");
    head.setAttribute("aria-expanded", "false");
    head.appendChild(el("span", "src-stat-label", t(r.labelKey)));
    head.appendChild(el("span", "src-stat-count", `${r.backed} / ${r.total} (${r.pct}%)`));
    head.appendChild(buildBar(r, r.total));

    const detail = el("div", "src-ex-wrap");
    detail.hidden = true;
    detail.appendChild(el("div", "src-ex-counts", gradeCountsText(r)));
    // The example is built on the first expand: it needs every node collected, and a
    // visitor who never expands a bar should not pay for that walk.
    let exampleBuilt = false;

    head.addEventListener("click", () => {
      const open = detail.hidden;
      if (open && !exampleBuilt && opts.data && opts.nav) {
        exampleBuilt = true;
        const example = buildKindExample(r.kind, exampleRows());
        if (example) detail.appendChild(example);
      }
      detail.hidden = !open;
      head.setAttribute("aria-expanded", String(open));
    });
    row.appendChild(head);
    row.appendChild(detail);
    kindsBox.appendChild(row);
  }
  globalBtn.addEventListener("click", () => {
    const open = kindsBox.hidden;
    kindsBox.hidden = !open;
    globalBtn.setAttribute("aria-expanded", String(open));
  });
  wrap.appendChild(kindsBox);

  // Measured-affinity (PDSP Ki) coverage: a SEPARATE honesty line, not a grade bar. A
  // binding backed by a Stahl quote with no Ki is still sourced, so this does not feed
  // the % above; it surfaces how much of the corpus carries a *measured* affinity and
  // how many drugs never had one looked up, so a fully quote-only corpus can't read as
  // exhaustively measured.
  const ki = stats.ki_coverage;
  if (ki && ki.bindings_total) {
    wrap.appendChild(el("p", "src-stat-kifoot", t("about.kiCoverage", {
      pct: ki.pct_bindings_with_ki,
      total: ki.bindings_total,
      drugsNone: ki.drugs_without_ki,
      drugs: ki.drugs_total,
    })));
  }
  // The bars count the nodes; the Data browser lists them. A per-kind example answers
  // "which ones?" with a single node, so say outright that all of them are one click
  // away and link it, rather than leaving the browser to be discovered in the panel.
  // Skipped when no `browser` callback was handed in (the pre-load call, and any host
  // with no panel to open it in).
  if (opts.nav && opts.nav.browser) {
    const line = el("p", "src-stat-browser", t("about.sourcingBrowser"));
    const link = btn("src-browser-link", t("about.sourcingBrowserLink"));
    link.addEventListener("click", () => opts.nav.browser());
    line.appendChild(document.createTextNode(" "));
    line.appendChild(link);
    wrap.appendChild(line);
  }
  host.appendChild(wrap);
  host.appendChild(key);

  // The citations a source asks every reuse to carry (GtoPdb's database paper,
  // its Concise Guide chapter, its licence), deduplicated across its corpora.
  const cites = [...new Set(Object.values(meta.sourceCorpora || {})
    .flatMap((c) => c.required_citations || []))];
  if (cites.length) {
    host.appendChild(el("p", "about-text", t("about.requiredCitations")));
    const list = el("ul", "src-cite-list");
    for (const c of cites) list.appendChild(el("li", null, c));
    host.appendChild(list);
  }
}

/**
 * Build one clickable "example node" for a node kind, shown when its coverage bar is
 * expanded in the Sources popup. It reads a representative node from the loaded dataset
 * and renders it as a knowledge triplet: a clickable subject (which navigates to the
 * real drug / receptor / structure / circuit / group) followed by the node's specific
 * notion in quotation marks. Deliberately NOT an "A -> B" arrow: the quoted notion is
 * what makes each abstraction concrete ("Olanzapine" ... "Antagonist, 5-HT2A").
 *
 * The node is a Data browser row (kinds.js exampleRow over collectNodes), so the
 * popup example and the browser can never word the same node differently.
 *
 * @param {string} kind    a provenance by_kind key (e.g. "drug_bindings")
 * @param {object[]} rows  collectNodes rows built with the popup's nav (each row's
 *                         `go` closes the popup and focuses its owner)
 * @returns {HTMLElement|null} the example line, or null when this kind has no clean example
 */
function buildKindExample(kind, rows) {
  const row = exampleRow(rows, kind);
  if (!row) return null;
  // Locale-aware quotation marks around the notion (French uses guillemets + NBSP).
  const fr = (document.documentElement.lang || "").startsWith("fr");
  const quoted = (s) => (fr ? `\u00ab\u00a0${s}\u00a0\u00bb` : `\u201c${s}\u201d`);
  // A row with no notion is a node that IS the named thing (a circuit, a group), so
  // its subject itself is quoted.
  const div = el("div", "src-ex");
  div.appendChild(el("span", "src-ex-lead", `${t("about.exampleLead")} `));
  const a = el("a", "src-ex-link", row.notion ? row.name : quoted(row.name));
  a.href = "#";
  a.addEventListener("click", (e) => { e.preventDefault(); row.go(); });
  div.appendChild(a);
  if (row.notion) div.appendChild(el("span", "src-ex-notion", ` ${quoted(row.notion)}`));
  return div;
}
