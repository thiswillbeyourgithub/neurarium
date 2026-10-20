// Drug-binding rows: the Ki chip with its corpus reference, the effect glyph, the
// binding row itself, and the lists of drugs acting on a target (grouped by category).

import { bindingKi, EFFECT_GLYPHS } from "./format.js";

const { t } = window.__I18N__;

export function makeBindings(P) {
  const {
    bindingActionPill, body, data, el, kiCorpusRefNode, makeProvenancePill, nodePill,
    onDrugPick, withTip,
  } = P;

  // The strongest-affinity binding a drug has feeding a transmitter system (the
  // binding whose flowKind == kind, min representative Ki), or undefined. The one
  // node behind the drug<->system link, so the drug panel's "Pharmacodynamics: net neurotransmission"
  // row and the projection-group panel's "Drugs acting on this system" row rank +
  // source it identically. (bindingKi, the shared Ki key, is module-scope above.)
  const strongestBindingForKind = (bindings, kind) =>
    bindings.filter((b) => b.flowKind === kind)
      .sort((a, b) => bindingKi(a) - bindingKi(b))[0];

  // A coloured effect glyph (+ boost / − block / ≈ modulate, in the effect's colour)
  // that replaces the plain colour bar at the head of a drug binding row, so the
  // action's direction reads at a glance. `label` (the localized effect name) is the
  // accessible name. When there is a label the glyph is wrapped in a tap-to-explain
  // tooltip (withTip): a tap on it shows the effect name and, crucially, stops the
  // tap from bubbling to the clickable binding row (so on a phone tapping the "+/−"
  // no longer navigates away, per the request); on desktop it also shows on hover.
  const effectGlyph = (effect, color, label) => {
    const g = el("span", "effect-glyph", EFFECT_GLYPHS[effect] || "·");
    g.style.color = color;
    if (label) g.setAttribute("aria-label", label);
    return label ? withTip(g, label) : g;
  };

  // Format a Ki (nM) to ~3 significant figures without trailing noise (0.29, 2.7,
  // 1240), so 0.28999999... reads as 0.29.
  const fmtKi = (n) => {
    const p = Number(n);
    return isFinite(p) ? String(parseFloat(p.toPrecision(3))) : "?";
  };

  // The measured PDSP Ki shown to the right of a binding's source badge: the median
  // value + [min-max] range + human/non-human assay counts, then its own "truth
  // badge" (a verified provenance pill whose tooltip cites the one representative
  // assay: species, preparation, radioligand, reference). A value borrowed through
  // the alias map (an enantiomer/prodrug/metabolite) also gets a visible ⚠ warning
  // naming the compound it was actually measured on, so it is never read as this
  // drug's own number. Returns a fragment appended to the binding row.
  const kiChip = (ki) => {
    const frag = document.createDocumentFragment();
    // A literature Ki (a quote-gated corpus like Wikipedia) is a single value quoted
    // from a source, not a raw assay: it has no ki_id and no human/non-human counts.
    // Render it plainly (value + optional range + a "literature value" tag), with the
    // corpus + revision permalink in the pill tooltip; skip the assay-only chrome
    // (species counts, "measured in non-human", the alias ⚠ warning).
    const measured = ki.kiId != null || ki.nHuman > 0 || ki.nNonhuman > 0;
    if (!measured) {
      const chip = el("span", "ki-chip");
      chip.appendChild(el("span", "ki-val", `Ki ${fmtKi(ki.median)} nM`));
      chip.appendChild(el("span", "ki-detail",
        (ki.min !== ki.max ? `${fmtKi(ki.min)}–${fmtKi(ki.max)} · ` : "")
        + t("drug.kiCited")));
      frag.appendChild(chip);
      // The corpus label doubles as the link to the exact source (see kiCorpusRefNode:
      // ki.reference's pinned-revision permalink, else the corpus URL), so a click opens
      // the very table the value was quoted from. The kiCited explainer follows;
      // makeProvenancePill then appends the grade explainer under it.
      const extra = kiCorpusRefNode(ki);
      extra.append("\n\n" + t("drug.kiCitedTip"));
      frag.appendChild(makeProvenancePill(ki.provenance, extra));
      return frag;
    }
    const chip = el("span", "ki-chip");
    chip.appendChild(el("span", "ki-val", `Ki ${fmtKi(ki.median)} nM`));
    chip.appendChild(el("span", "ki-detail",
      `${fmtKi(ki.min)}–${fmtKi(ki.max)} · `
      + t("drug.kiCounts", { h: ki.nHuman, n: ki.nNonhuman })
      + (ki.inactive ? " · " + t("drug.kiInactive", { n: ki.inactive }) : "")));
    if (ki.nHuman === 0) chip.classList.add("ki-nonhuman");
    frag.appendChild(chip);
    // Truth badge: the assay behind the value.
    const assay = [
      ki.kiId != null ? `#${ki.kiId}` : "",
      ki.valueNm != null ? `${fmtKi(ki.valueNm)} nM` : "",
      ki.species, ki.preparation, ki.radioligand, ki.reference,
    ].filter(Boolean).join(", ");
    let tip = t("drug.kiTip", { h: ki.nHuman, n: ki.nNonhuman,
      assay: `${ki.corpusRef}: ${assay}` });
    if (ki.nHuman === 0) {
      tip += "\n\n" + t("drug.kiTipNonHuman", { species: ki.species || "?" });
    }
    if (ki.inactive) {
      tip += "\n\n" + t("drug.kiInactiveTip", { n: ki.inactive });
    }
    const relationLabel = ki.mapped
      ? t(`drug.rel.${ki.relation}`) || ki.relation : "";
    if (ki.mapped) {
      tip += "\n\n" + t("drug.kiMappedTip",
        { compound: ki.measuredAs, relation: relationLabel });
    }
    frag.appendChild(makeProvenancePill(ki.provenance, tip));
    if (ki.mapped) {
      const warn = el("span", "ki-mapped",
        "⚠ " + t("drug.kiMapped", { compound: ki.measuredAs }));
      warn.title = t("drug.kiMappedTip",
        { compound: ki.measuredAs, relation: relationLabel });
      frag.appendChild(warn);
    }
    return frag;
  };

  // A drug's name as a plain clickable label, the same `.legend-item.clickable` look
  // as the Drugs list rows, so a name that jumps to a drug reads alike everywhere.
  const drugNameLink = (drug, text = drug.label || drug.name) => {
    const a = el("span", "legend-item clickable drug-name-link", text);
    a.setAttribute("role", "link");
    a.tabIndex = 0;
    a.addEventListener("click", () => onDrugPick(drug));
    a.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onDrugPick(drug); }
    });
    return a;
  };

  // One binding row, shared by the drug panel's "Pharmacodynamics: binding profile" list and a
  // receptor/target panel's "Interacting drugs" list: the two render the *same*
  // resolved binding from opposite ends (a drug's target vs a target's drug), so
  // the markup lives once. Layout: the effect glyph, then a text column holding
  // the leading name, the action line, and (stacked under them) the measured Ki
  // chip with its own verified badge; the binding's source pill sits to the right
  // of that whole block. `nameText` leads the row (the target name on a drug
  // panel, the drug name on a target panel); `onActivate`, when given, makes the
  // row a clickable link. An affinity_only binding (PDSP Ki, no known direction)
  // gets a muted neutral glyph + an "affinity only" line and no source pill (Stahl
  // never stated it; the Ki's verified badge is its only source).
  // `compound`, when given, names the molecule the row comes from (the drug or one
  // of its active metabolites, see metaboliteContributors) as an .eff-from tag,
  // which then replaces the "via" line.
  const bindingRow = (binding, drug, nameText, onActivate, compound = null) => {
    const li = el("li");
    const affinity = binding.affinityOnly;
    if (binding.tentative) li.classList.add("tentative");
    if (affinity) li.classList.add("affinity-only");
    li.appendChild(effectGlyph(
      binding.effect, affinity ? "#8a8f98" : binding.effectColor,
      affinity ? t("drug.affinityOnly") : binding.effectLabel));
    const txt = el("div", "bind-text");
    // Name + the binding's own source pill share the first line, so the pill sits
    // right of the target name rather than being stranded at the far panel edge
    // past the (wide) Ki line below it. An affinity_only binding carries no source
    // pill (its Ki's verified badge is the only source), so the name stands alone.
    const nameRow = el("div", "bind-name");
    nameRow.appendChild(el("span", "bind-target", nameText));
    if (compound) nameRow.appendChild(el("span", "eff-from", compound));
    if (!affinity) nameRow.appendChild(nodePill(binding));
    txt.appendChild(nameRow);
    const parts = [affinity ? t("drug.affinityOnly") : binding.actionLabel,
                   binding.note,
                   binding.viaMetabolite && !compound
                     ? t("drug.viaMetabolite", { name: binding.viaMetabolite }) : null];
    if (binding.tentative) parts.push(t("drug.speculative"));
    if (binding.peripheral) parts.push(t("drug.peripheral"));
    const detail = parts.filter(Boolean).join(" · ");
    if (detail) {
      const line = el("span", "bind-action", detail);
      // The direction's own grade rides the action line it grades, not the name row
      // (which carries the binding's).
      const dirPill = bindingActionPill(binding);
      if (dirPill) line.appendChild(dirPill);
      txt.appendChild(line);
    }
    // Ki stacked under the name+action, with its own verified badge beside it.
    if (binding.ki) {
      const kiLine = el("div", "bind-ki");
      kiLine.appendChild(kiChip(binding.ki));
      txt.appendChild(kiLine);
    }
    li.appendChild(txt);
    li.title = affinity
      ? `${t("drug.affinityOnly")} · ${nameText}`
      : `${binding.effectLabel} · ${nameText}`;
    if (onActivate) {
      li.classList.add("clickable");
      li.addEventListener("click", onActivate);
    }
    return li;
  };

  const appendDrugsByCategory = (list, container) => {
    const cats = data.meta.drugCategoryLabels || {};
    const byCat = new Map();
    for (const item of list) {
      const cat = (item.drug.categories && item.drug.categories[0]) || "other";
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(item);
    }
    for (const items of byCat.values()) {
      items.sort((a, b) => {
        const ka = bindingKi(a.binding), kb = bindingKi(b.binding);
        return ka !== kb ? ka - kb : a.drug.name.localeCompare(b.drug.name);
      });
    }
    const metaOrder = [...Object.keys(cats),
                       ...[...byCat.keys()].filter((c) => !(c in cats))];
    const classKi = new Map();
    for (const [cat, its] of byCat)
      classKi.set(cat, Math.min(...its.map((it) => bindingKi(it.binding))));
    const order = [...byCat.keys()].sort((a, b) => {
      const ka = classKi.get(a), kb = classKi.get(b);
      return ka !== kb ? ka - kb : metaOrder.indexOf(a) - metaOrder.indexOf(b);
    });
    for (const cat of order) {
      container.appendChild(el("h4", "drug-cat", cats[cat] || cat));
      const ul = el("ul");
      // Same shared row builder as the drug panel's "Pharmacodynamics: binding profile" list (same resolved
      // binding, seen from the target's side), so the effect glyph, action, the
      // measured Ki chip and the shared source pill all render identically here;
      // clicking a row opens that drug.
      for (const item of byCat.get(cat)) {
        const { drug, binding } = item;
        // A metabolite entry (its own non-drug binding surfaced here) reads
        // "NAME (metab. of PRODRUG)" and clicks through to the parent drug; a normal
        // drug entry just shows its display name. A metabolite shared by several parents
        // lists them all ("metab. of A, B") in one row (see drugsByTarget merge).
        const label = item.viaMetaboliteOfList
          ? `${item.metaboliteName} (${t("drug.metaboliteOf", { prodrug: item.viaMetaboliteOfList.join(", ") })})`
          : drug.displayName;
        // A metabolite deep-links to its parent drug (no standalone metabolite view),
        // passing its name so the parent panel scrolls to + flashes that metabolite's row.
        const row = bindingRow(binding, drug, label,
          item.viaMetaboliteOfList
            ? () => onDrugPick(drug, { highlightMetabolite: item.metaboliteName })
            : () => onDrugPick(drug));
        row.dataset.tourId = `ixdrug:${drug.id}`; // guided-tour hook: a drug row inside a target panel
        ul.appendChild(row);
      }
      container.appendChild(ul);
    }
  };

  // Shared by the receptor + target views: the drugs that act on this target, so
  // you can go from a target to every drug touching it (grouped by category, see
  // appendDrugsByCategory). Omitted entirely when no drug in the dataset acts on it.
  // A prodrug acting through a metabolite drug (lisdexamfetamine via
  // dextroamphetamine) is listed beside it, its row reading "via <metabolite>", but
  // left out of the count: the binding node is the metabolite's (see
  // data.prodrugsByTarget).
  const interactorsOf = (targetId) => ({
    list: (data.drugsByTarget && data.drugsByTarget.get(targetId)) || [],
    borrowed: (data.prodrugsByTarget && data.prodrugsByTarget.get(targetId)) || [],
  });

  const appendInteractingDrugs = (targetId) => {
    const { list, borrowed } = interactorsOf(targetId);
    if (!list.length && !borrowed.length) return;
    const wrap = el("div", "info-bindings info-interactors");
    wrap.dataset.tourSec = "drugs"; // guided-tour section anchor
    wrap.appendChild(el(
      "h3", null, `${t("targets.interactingDrugs")} (${list.length})`));
    appendDrugsByCategory([...list, ...borrowed], wrap);
    body.appendChild(wrap);
  };

  // A receptor_group panel (α2 / glutamate) links to its modeled subtype receptors
  // (target.subtypes, a sourceless taxonomy). Below the group's own interacting
  // drugs, list each subtype that has drugs of its own in a collapsed <details>
  // dropdown, so from the coarse α2 panel you can reach (and expand) the drugs that
  // bind α2A/B/C/D specifically (e.g. asenapine at α2A). Subtypes with no interacting
  // drug are skipped; the whole section is omitted when none qualify.
  const appendSubtypeInteractors = (subtypes) => {
    if (!Array.isArray(subtypes) || !subtypes.length) return;
    const withDrugs = subtypes
      .map(interactorsOf)
      .filter((s) => s.list.length || s.borrowed.length);
    if (!withDrugs.length) return;
    const wrap = el("div", "info-bindings info-interactors info-subtype-interactors");
    wrap.appendChild(el("h3", null, t("targets.bySubtype")));
    for (const { list, borrowed } of withDrugs) {
      const rows = [...list, ...borrowed];
      // The subtype's display name comes off the resolved binding (localized), so it
      // needs no separate receptor lookup and stays in sync with the drug panel.
      const name = (rows[0].binding && rows[0].binding.targetName) || "";
      const details = el("details", "disclosure subtype-group");
      details.appendChild(el("summary", null, `${name} (${list.length})`));
      appendDrugsByCategory(rows, details);
      wrap.appendChild(details);
    }
    body.appendChild(wrap);
  };

  return {
    appendDrugsByCategory, appendInteractingDrugs, appendSubtypeInteractors,
    bindingRow, drugNameLink, effectGlyph, fmtKi, interactorsOf, kiChip,
    strongestBindingForKind,
  };
}
