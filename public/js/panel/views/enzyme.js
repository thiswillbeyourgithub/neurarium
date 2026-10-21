// The Enzyme view: one metabolizing enzyme, its substrates, inhibitors and inducers,
// and the population variability of its metabolizer phenotypes.

import { attachTip } from "../tooltip.js";
import { emptySection } from "../dom.js";

const { t } = window.__I18N__;


/**
 * Populate the panel for a metabolic *enzyme* (a row in the Enzymes section, or
 * an enzyme row inside a drug's Metabolism list): its Wikipedia reference, then
 * the drugs at it grouped by the role they play (substrates first, then the
 * inhibitors and inducers that move them).
 *
 * Deliberately the lightest panel in the app: an enzyme is pharmacokinetics, so
 * it has no anatomy to show, no expression regions and nothing to light in the
 * 3D scene. Each drug row carries the grade pill of the very node that put it
 * here (the Stahl pharmacokinetics line), so the claim is auditable in place.
 */
export function showEnzyme(P, enzyme) {
  const {
    PHARMFREQ_URL, appendLookupLink, appendReference, body, clearBody,
    clinpgxSearchUrl, el, enzymeRow, foldBody, nodePill, onDrugPick,
  } = P;
  clearBody("enzyme");
  body.appendChild(el("h2", "info-title", enzyme.label));
  body.appendChild(el("div", "info-group", t("enzyme.heading")));
  const { wiki: enzWiki } = appendReference({ url: enzyme.wikipedia });
  // ClinPGx covers exactly what this panel cannot: which variants of this
  // isoform make a carrier a poor or ultra-rapid metabolizer, and the dosing
  // guidance that follows. Lookup link, so no provenance pill.
  if (enzWiki) {
    appendLookupLink(enzWiki, "info.clinpgx",
      clinpgxSearchUrl(enzyme.label), "info.clinpgxEnzymeTitle");
  }

  // The active metabolites this isoform MAKES, the other half of the metabolism
  // graph (the rows below are what it *handles*). Same node seen from the enzyme's
  // end: each row carries the very grade pill the parent drug's panel shows, and
  // clicks through to that parent, where the metabolite is listed.
  const made = enzyme.metabolites || [];
  if (made.length) {
    const box = el("div", "info-bindings info-metabolites");
    box.appendChild(el("h3", null, `${t("enzyme.forms")} (${made.length})`));
    const ul = el("ul");
    for (const { drug, metabolite, formedBy } of made) {
      const li = el("li");
      const text = el("span", "bind-text");
      text.appendChild(el("span", "bind-target", metabolite.name));
      const parts = [t("enzyme.formsOf", { drug: drug.displayName })];
      if (formedBy.reactionLabel) parts.push(formedBy.reactionLabel);
      text.appendChild(el("span", "bind-action", ` ${parts.join(" · ")}`));
      li.appendChild(text);
      li.appendChild(nodePill(formedBy));
      li.classList.add("clickable");
      li.addEventListener("click",
        () => onDrugPick(drug, { highlightMetabolite: metabolite.name }));
      ul.appendChild(li);
    }
    box.appendChild(ul);
    body.appendChild(box);
  } else {
    body.appendChild(emptySection(el("h3", null, t("enzyme.forms")), "enzyme"));
  }

  // How fast people clear a drug through this isoform, and how common each speed
  // is per population group (PharmFreq, corpus #13). It sits above the drug lists
  // because it qualifies every one of them: a "major substrate" row means
  // something different to a poor metabolizer than to a normal one. One graded
  // node for the whole profile, so one pill on the heading.
  const variability = enzyme.variability;
  if (variability) {
    const box = el("div", "info-bindings info-variability");
    const head = el("h3", null, t("enzyme.variability"));
    head.appendChild(nodePill(variability));
    box.appendChild(head);
    box.appendChild(el("p", "var-caveat", t("enzyme.variabilityCaveat")));
    // Where these numbers come from, and where to go past them: we publish one
    // profile per isoform we model, PharmFreq publishes the whole atlas. A lookup
    // link like the ClinPGx one on a drug's Metabolism section, so no pill: the
    // pill on the heading above already names the source of the claim itself.
    const freqRow = el("div", "info-wiki");
    freqRow.appendChild(el("span", null, t("info.frequencies")));
    appendLookupLink(freqRow, "info.pharmfreq", PHARMFREQ_URL,
      "info.pharmfreqTitle");
    box.appendChild(freqRow);
    // The key doubles as the caption: PM/IM/NM/UM are jargon, and the colour a
    // reader is about to see in every bar is defined here once rather than in a
    // tooltip they would have to hunt for.
    const key = el("ul", "var-key");
    for (const { phenotype, label, note } of variability.groups[0].cells) {
      const li = el("li");
      li.appendChild(el("span", `var-swatch var-${phenotype.toLowerCase()}`));
      li.appendChild(el("span", "var-key-label", label));
      li.appendChild(el("span", "var-key-note", ` · ${note}`));
      key.appendChild(li);
    }
    box.appendChild(key);
    const ul = el("ul", "var-rows");
    for (const group of variability.groups) {
      const li = el("li");
      li.appendChild(el("span", "var-group", group.label));
      const bar = el("span", "var-bar");
      for (const cell of group.cells) {
        const seg = el("span", `var-seg var-${cell.phenotype.toLowerCase()}`);
        seg.style.width = `${cell.freq * 100}%`;
        bar.appendChild(seg);
      }
      // The exact figures, on the bar rather than on each segment: a 1%-wide
      // segment is not a hover target, and reading one speed against the others is
      // the whole point of the bar, so the tip carries the row entire. Nothing is
      // rounded or dropped on the way here; the bar is the shape of the numbers
      // and this is the numbers.
      li.appendChild(attachTip(bar, `${group.label}\n` + group.cells
        .map((c) => `${c.label} ${(c.freq * 100).toFixed(1)}%`).join("\n")));
      ul.appendChild(li);
    }
    box.appendChild(ul);
    body.appendChild(box);
  } else {
    // An empty section rather than no section: 13 of the 18 isoforms we model have
    // no published profile, the two the drug roster leans on hardest among them
    // (CYP3A4 clears 109 of the drugs here, CYP1A2 46), and a reader who sees a
    // bar chart on CYP2D6 and nothing on CYP3A4 would read the blank as "not
    // variable". It carries no pill because it is a statement about this dataset
    // and its corpus's scope, not a sourced claim about the enzyme.
    const box = el("div", "info-bindings info-variability");
    box.appendChild(el("h3", null, t("enzyme.variability")));
    box.appendChild(el("p", "var-caveat", t("enzyme.variabilityNone")));
    const freqRow = el("div", "info-wiki");
    freqRow.appendChild(el("span", null, t("info.frequencies")));
    appendLookupLink(freqRow, "info.pharmfreq", PHARMFREQ_URL,
      "info.pharmfreqTitle");
    box.appendChild(freqRow);
    body.appendChild(box);
  }

  const rows = enzyme.rows || [];
  const wrap = el("div", "info-bindings info-interactors");
  wrap.appendChild(el("h3", null, `${t("enzyme.drugs")} (${rows.length})`));
  if (!rows.length) {
    wrap.appendChild(el("p", "info-desc", t("enzyme.noDrugs")));
    body.appendChild(wrap);
    foldBody();
    return;
  }
  // Group by role in the vocabulary's own order (substrate, inhibitor, inducer)
  // rather than alphabetically: a reader wants "what does this enzyme clear"
  // before "what interferes with it".
  const byRole = new Map();
  for (const r of rows) {
    if (!byRole.has(r.enzyme.role)) byRole.set(r.enzyme.role, []);
    byRole.get(r.enzyme.role).push(r);
  }
  for (const role of ["substrate", "inhibitor", "inducer"]) {
    const group = byRole.get(role);
    if (!group) continue;
    group.sort((a, b) => a.drug.displayName.localeCompare(b.drug.displayName));
    wrap.appendChild(el("h4", "drug-cat", group[0].enzyme.roleLabel));
    const ul = el("ul");
    for (const { drug, enzyme: row } of group) {
      ul.appendChild(enzymeRow(row, drug.displayName, () => onDrugPick(drug)));
    }
    wrap.appendChild(ul);
  }
  body.appendChild(wrap);
  // Headed sections start folded, like the drug panel (see foldSections).
  foldBody();
}
