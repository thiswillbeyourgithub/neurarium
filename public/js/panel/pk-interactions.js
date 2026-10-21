// The drug panel's "Pharmacokinetic interactions" subsection (derived, never stored): the
// drugs this one meets at a shared enzyme, grouped by drug or by isoform. Split out of
// panel/views/drug.js, which appends it last in the Metabolism section.

import { btn, emptySection, heading, subSection } from "./dom.js";
import { loadPkGrouping, savePkGrouping } from "../legend/drugs.js";

const { t } = window.__I18N__;

/**
 * The PK-interactions subsection for `drug` (the empty subsection when it shares no enzyme).
 * @param {object} P  the panel context showDrug receives
 * @param {object} drug
 * @returns {HTMLElement}
 */
export function pkInteractionsSection(P, drug) {
  const { data, el, enzymeById, onDrugPick, onEnzymePick } = P;
  // Pharmacokinetic interactions: derived, never stored (see pkInteractionsOf). This drug
  // and the listed one meet at the same enzyme, so one COULD shift the other's
  // level; the wording stays conditional throughout because the edge is an
  // inference from the enzyme roles, not a measured interaction study.
  const pk = data.pkInteractionsOf ? data.pkInteractionsOf(drug) : null;
  const edges = pk ? [
    ...pk.affects.map((x) => ({ ...x, outgoing: true })),
    ...pk.affectedBy.map((x) => ({ ...x, outgoing: false })),
  ] : [];
  if (!edges.length) {
    return emptySection(heading("h4", t("drug.pkInteractions"), t("drug.pkInteractionsSub"),
      "panel-subsec-title"), "drug", { tourSec: "pk", cls: "info-interactors" });
  }
  // The last subsection of the drug's Metabolism section (an <h4>, see subSection),
  // the count in its title so the reader sees how many rows follow. info-interactors
  // reuses that section's .drug-cat sub-heading style.
  const pkWrap = subSection(`${t("drug.pkInteractions")} (${edges.length})`,
    "info-interactors", t("drug.pkInteractionsSub"));
  pkWrap.dataset.tourSec = "pk"; // guided-tour section anchor
  pkWrap.appendChild(el("p", "legend-caption", t("drug.pkInteractionsHint")));

  // One row = one (other drug, direction) edge, and it carries the drug name
  // ALONE: the direction is always a heading above it (a bucket in by-drug mode,
  // a sub-heading under the isoform in by-enzyme mode), so spelling it out per
  // row just repeated the same phrase down the list. `showEnzymes` appends the
  // shared isoforms; by-enzyme mode drops them (the heading IS the isoform).
  const pkRow = (edge, showEnzymes) => {
    const li = el("li", "clickable");
    const text = el("span", "bind-text");
    text.appendChild(el("span", "bind-target", edge.drug.displayName));
    if (showEnzymes) {
      text.appendChild(el("span", "bind-action",
                          ` · ${edge.enzymes.map((x) => x.label).join(", ")}`));
    }
    li.appendChild(text);
    const via = edge.enzymes.map((x) => x.enzyme);
    li.addEventListener("click",
                        () => onDrugPick(edge.drug, { highlightEnzymes: via }));
    return li;
  };

  // Capped per HEADING, not globally: a global cap would swallow whole headings
  // (a CYP3A4 inhibitor legitimately meets dozens of substrates), so each one
  // shows its first rows and offers the rest in place rather than in a dead-end
  // count. Rows are built lazily so an unexpanded remainder costs nothing.
  const GROUP_CAP = 8;
  // One group = a heading plus its `sections`, each `{label?, rows}`. A section
  // label is the direction sub-heading by-enzyme mode needs (by-drug mode passes
  // a single unlabelled section, since its own heading IS the direction).
  const appendGroup = (box, label, sections, onLabel) => {
    const filled = sections.filter((s) => s.rows.length);
    if (!filled.length) return;
    const head = el("h4", "drug-cat", label);
    if (onLabel) {
      head.classList.add("clickable");
      head.addEventListener("click", onLabel);
    }
    box.appendChild(head);
    // The rows (and the "+n more" that extends them) live in their own indented
    // body under the heading, so which bucket / isoform a drug belongs to reads
    // at a glance in a list of several groups. A labelled section indents one
    // step further, under its own sub-heading.
    const groupBody = el("div", "pk-group-body");
    for (const section of filled) {
      let target = groupBody;
      if (section.label) {
        groupBody.appendChild(el("h5", "pk-dir", section.label));
        target = el("div", "pk-dir-body");
        groupBody.appendChild(target);
      }
      const ul = el("ul");
      for (const make of section.rows.slice(0, GROUP_CAP)) ul.appendChild(make());
      target.appendChild(ul);
      if (section.rows.length > GROUP_CAP) {
        const more = el("button", "pk-more",
                        t("info.more", { n: section.rows.length - GROUP_CAP }));
        more.type = "button";
        more.addEventListener("click", () => {
          for (const make of section.rows.slice(GROUP_CAP)) ul.appendChild(make());
          more.remove();
        });
        target.appendChild(more);
      }
    }
    box.appendChild(groupBody);
  };
  // The four direction readings, in the order they are useful: what this drug
  // does to others first (that half is the actionable one), then what others do
  // to it. by-drug mode makes each a top-level heading, by-enzyme mode a
  // sub-heading under every isoform, so the labels are defined once here.
  const PK_DIRECTIONS = [
    ["drug.pkHeadRaises", (e) => e.outgoing && e.direction > 0],
    ["drug.pkHeadLowers", (e) => e.outgoing && e.direction < 0],
    ["drug.pkHeadRaisedBy", (e) => !e.outgoing && e.direction > 0],
    ["drug.pkHeadLoweredBy", (e) => !e.outgoing && e.direction < 0],
  ];
  const byName = (a, b) => a.drug.displayName.localeCompare(b.drug.displayName);

  // Two readings of the SAME edges, because the useful question differs: "what
  // does this drug do to my other prescriptions" (by drug) vs "everything that
  // goes through CYP3A4" (by enzyme, where a pair sharing two isoforms shows up
  // under each; that duplication is the point of this reading).
  const byDrug = (box) => {
    for (const [key, keep] of PK_DIRECTIONS) {
      const rows = edges.filter(keep).sort(byName)
        .map((e) => () => pkRow(e, true));
      appendGroup(box, t(key), [{ rows }]);
    }
  };
  const byEnzyme = (box) => {
    const per = new Map();
    for (const edge of edges) {
      for (const enz of edge.enzymes) {
        if (!per.has(enz.enzyme)) per.set(enz.enzyme, { label: enz.label, rows: [] });
        per.get(enz.enzyme).rows.push(edge);
      }
    }
    // Busiest isoform first (that is where the risk concentrates), ties by name.
    const groups = [...per.entries()].sort((a, b) =>
      (b[1].rows.length - a[1].rows.length) || a[1].label.localeCompare(b[1].label));
    for (const [id, grp] of groups) {
      // Split by direction under the isoform, rather than spelling the direction
      // out on every row: an isoform's rows are mostly one direction, so the
      // per-row phrasing repeated itself line after line.
      const sections = PK_DIRECTIONS.map(([key, keep]) => ({
        label: t(key),
        rows: grp.rows.filter(keep).sort(byName)
          .map((e) => () => pkRow(e, false)),
      }));
      const enz = enzymeById.get(id);
      appendGroup(box, grp.label, sections, enz ? () => onEnzymePick(enz) : null);
    }
  };

  const listBox = el("div");
  const modeSwitch = el("div", "seg-switch");
  const render = (mode) => {
    listBox.innerHTML = "";
    for (const seg of modeSwitch.children) {
      seg.classList.toggle("active", seg.dataset.mode === mode);
    }
    if (mode === "enzyme") byEnzyme(listBox); else byDrug(listBox);
  };
  for (const [mode, key] of [["drug", "drug.pkByDrug"],
                             ["enzyme", "drug.pkByEnzyme"]]) {
    const seg = btn("seg-btn", t(key));
    seg.dataset.mode = mode;
    seg.addEventListener("click", () => {
      savePkGrouping(mode);
      render(mode);
    });
    modeSwitch.appendChild(seg);
  }
  pkWrap.appendChild(modeSwitch);
  pkWrap.appendChild(listBox);
  render(loadPkGrouping());
  return pkWrap;
}
