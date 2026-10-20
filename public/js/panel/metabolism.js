// Metabolism rows on a drug panel: one enzyme row per (enzyme, role), and the CPIC
// readout pairing a phenotype's frequency in the picked population group with what CPIC
// says follows (the group is never persisted).

import { attachTip } from "./tooltip.js";
import { subSection } from "./dom.js";

const { t } = window.__I18N__;

export function makeMetabolism(P) {
  const {
    appendLookupLink, el, nodePill, sourceBackedPill,
  } = P;

  // Group a {drug, binding}[] by primary drug category and append the category
  // sub-headings + rows into `container`. Shared by the group/target's own
  // "Interacting drugs" list and the per-subtype dropdowns below it, so the sort +
  // row shape can never drift between the two. Sort: within a class, strongest-
  // affinity drug first (by this target's binding Ki, Infinity when unmeasured; equal
  // Ki tie-broken by name); classes ordered by the class's hardest binding (its min
  // Ki), classes with no measured Ki keeping the meta / Drugs-legend order among
  // themselves. Matches the drug panel's "Pharmacodynamics: binding profile" order and the target legend.
  /**
   * One row of a metabolism list, shared by the drug panel's Metabolism section and
   * the enzyme panel's drug list so both render the same claim identically (the
   * no-duplication rule: the two views are the same node seen from either end).
   *
   * `label` is whichever end the *other* panel is not: the enzyme's name on a drug
   * panel, the drug's name on an enzyme panel. Both callers group the rows under a
   * role heading, so the role itself is not repeated on the row.
   * @param {object} row       the normalized enzyme row (js/data.js)
   * @param {string} label     the row's headline text
   * @param {(() => void)|null} onClick  jump target, or null for an inert row
   */
  const enzymeRow = (row, label, onClick) => {
    const li = el("li");
    const text = el("span", "bind-text");
    const line = el("span", "bind-name");
    line.appendChild(el("span", "bind-target", label));
    // Each pill sits right after the words it grades and names them in its tooltip.
    // The rows are grouped under a role heading (both callers), so the name's own pill
    // grades the (enzyme, role) claim; how MUCH of the clearing this isoform does is a
    // second node (the CYP quote gate checks the isoform is named, never the tier; see
    // quotes/attestation.py), so it carries its own pill after the strength word.
    // Both go through the shared node pill, so the quote and any "another corpus
    // denies this" lead (quotes/contradictions.py) still show.
    line.appendChild(sourceBackedPill(row.provenance || null, row,
      t("enzyme.gradesRole", { role: row.roleLabel })));
    if (row.strengthLabel) {
      const strength = (row.claims || {}).strength;
      line.append(
        el("span", "bind-action", `· ${row.strengthLabel}`),
        sourceBackedPill((strength && strength.grade) || "llm", strength,
          t("enzyme.gradesStrength", { strength: row.strengthLabel })));
    }
    text.appendChild(line);
    li.appendChild(text);
    if (onClick) {
      li.classList.add("clickable");
      li.addEventListener("click", onClick);
    }
    return li;
  };

  // Which population group the pharmacogenomic rows are read under. Deliberately NOT
  // persisted, unlike every other lasting choice (js/prefs.js): nobody's browser needs
  // to keep a record of which ancestry group they looked up. It outlives one panel so
  // comparing two drugs does not mean re-picking, and resets on reload.
  let pgxGroup = null;

  /**
   * The CPIC guidance subsection of a drug panel's Metabolism (corpus #15), or null when it has none.
   *
   * The one section here that states a clinical action, so it is built to be read as
   * what it is: CPIC's own two sentences per row, quoted verbatim with their pill, the
   * guideline linked, the recommendation's strength named, and the caveat about base
   * rates versus individuals sitting with the rows rather than hidden in a tooltip.
   *
   * Two datasets meet in each row. The guidance comes from CPIC; the "how common is
   * that" figure beside it comes from the enzyme's own frequency profile (corpus #13),
   * which is why the group picker lists the groups that profile actually covers.
   *
   * @param {object} drug the normalized drug record (js/data.js)
   * @returns {HTMLElement|null}
   */
  const pgxSection = (drug) => {
    const blocks = drug.pgx || [];
    if (!blocks.length) return null;
    // A subsection of the drug's Pharmacogenomics section (views/drug.js), first.
    const wrap = subSection(t("drug.pgx"), "info-pgx", t("drug.pgxSub"));
    wrap.dataset.tourSec = "pgx";
    wrap.appendChild(el("p", "legend-caption", t("drug.pgxHint")));

    // One picker for the whole section: every block's profile covers the same groups,
    // and two selects on one panel would read as two different questions.
    const groups = blocks[0].groups || [];
    const pick = el("div", "pgx-pick");
    const label = el("label", null, `${t("drug.pgxGroup")} `);
    const select = el("select", "pgx-group");
    const none = el("option", null, t("drug.pgxNoGroup"));
    none.value = "";
    select.appendChild(none);
    for (const g of groups) {
      const opt = el("option", null, g.label);
      opt.value = g.key;
      if (g.key === pgxGroup) opt.selected = true;
      select.appendChild(opt);
    }
    label.appendChild(select);
    pick.appendChild(label);
    wrap.appendChild(pick);

    const freqCells = [];
    const paint = () => {
      for (const { cell, row } of freqCells) {
        const hit = pgxGroup ? row.freqByGroup.get(pgxGroup) : null;
        cell.textContent = !pgxGroup ? ""
          : hit ? t("drug.pgxFreq", { pct: `${(hit.freq * 100).toFixed(1)}%` })
            : t("drug.pgxNoFreq");
        cell.classList.toggle("pgx-freq-none", Boolean(pgxGroup && !hit));
      }
    };
    select.addEventListener("change", () => {
      pgxGroup = select.value || null;
      paint();
    });

    for (const block of blocks) {
      const head = el("h4", "drug-cat", block.label);
      head.appendChild(attachTip(el("span", "pgx-level",
        t("drug.pgxLevel", { level: block.level })), t("drug.pgxLevelTitle")));
      wrap.appendChild(head);
      // A guideline CPIC writes for one kind of patient only (atomoxetine's rows are
      // adults, phenytoin's are people new to the drug) says so on the block, because
      // the rows below are that population's, not everyone's.
      if (block.population) {
        wrap.appendChild(el("p", "pgx-population",
          t("drug.pgxPopulation", { population: block.population })));
      }
      const guide = el("div", "info-wiki");
      guide.appendChild(el("span", null, block.guideline.name));
      appendLookupLink(guide, "drug.pgxGuideline", block.guideline.url,
        "drug.pgxGuideline");
      wrap.appendChild(guide);
      const ul = el("ul", "pgx-rows");
      for (const row of block.rows) {
        const li = el("li");
        const headline = el("div", "pgx-headline");
        // The same slow -> fast colour ramp the enzyme panel's bars use, as a swatch
        // rather than a fill: a tinted chip would need a literal text colour, which
        // only `--accent` is allowed (tools/tests/test_theme_tokens.py).
        const pheno = el("span", "pgx-pheno");
        pheno.appendChild(el("span",
          `var-swatch var-${row.phenotype.toLowerCase()}`));
        pheno.appendChild(el("span", null, row.label));
        headline.appendChild(attachTip(pheno, row.note));
        const freq = el("span", "pgx-freq");
        freqCells.push({ cell: freq, row });
        headline.appendChild(freq);
        // One node, two quotes (the implication, then the recommendation), so one pill
        // whose tooltip carries both: see tools/data_generators/cpic.py.
        headline.appendChild(nodePill(row));
        li.appendChild(headline);
        li.appendChild(el("p", "pgx-implication", row.implication));
        li.appendChild(el("p", "pgx-recommendation", row.recommendation));
        const foot = el("div", "pgx-foot");
        foot.appendChild(el("span", "pgx-class", row.classification));
        // CPIC doses the tricyclics and the SRIs on two genes at once, so a row filed
        // under one of them only holds with the other at normal activity. Shown, never
        // implied: a reader who misses it would read a joint claim as a single-gene one.
        if (row.assumes) {
          foot.appendChild(el("span", "pgx-assumes",
            t("drug.pgxAssumes", { genes: Object.keys(row.assumes).join(", ") })));
        }
        li.appendChild(foot);
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
    }
    paint();
    wrap.appendChild(el("p", "var-caveat", t("drug.pgxCaveat")));
    return wrap;
  };

  return {
    enzymeRow, pgxGroup, pgxSection,
  };
}
