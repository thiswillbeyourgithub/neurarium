// The BETA receptor sections: effects (stored and derived), downstream release
// modulation, demographics, genetic variants and the work-up list, each a betaSection.

import { attachTip } from "./tooltip.js";
import { isWebUrl } from "../web-url.js";
import { extLink, btn, heading, withSubtitle } from "./dom.js";
import { deriveReleaseChanges, transmitterVars } from "../release-modulation.js";
import { formatConditions, groupWorkup } from "../workup.js";
import { groupByVariant, variantsForDrug } from "../receptor-variants.js";
import { groupByMode } from "../receptor-effects.js";

const { ofNoun, t } = window.__I18N__;

export function makeSections(P) {
  const {
    body, data, derivedActiveMetabolites, effectById, el, metaboliteContributors,
    nodePill, onEffectPick, onTargetPick, resolveBase, sourceBackedPill, targetById,
  } = P;

  // receptor_effect (BETA) section heading: the label plus the same quiet "beta"
  // qualifier the Simulation section wears (.beta-tag, i18n sim.beta), then the
  // subtitle (withSubtitle) after the tag.
  const betaHeading = (key, vars, sub, tag = "h3") => {
    const h = el(tag, tag === "h4" ? "panel-subsec-title" : null, t(key, vars));
    h.appendChild(el("span", "beta-tag", t("sim.beta")));
    return withSubtitle(h, sub);
  };

  // The shell every list section of a panel shares (effects, release modulation,
  // demographics, variants, workup): a tour-anchored block, its heading (with the
  // quiet "beta" tag unless `beta: false`, and the `subKey` subtitle), its caption, then either one list (`ul`)
  // or, `grouped`, one sub-heading + list per `group(label)` call (a label string, or
  // a ready heading node). `close()` appends the not-medical-advice style caveat
  // (`caveatKey`) after the content and mounts the section on the panel. `nested`
  // makes it an `<h4>` subsection (dom.js subSection's look) of a section the caller
  // builds: `close()` then returns it unmounted, for the caller to place.
  const betaSection = (tourSec, headingKey, hintKey,
    { vars, grouped = false, caveatKey = null, beta = true, cls = "info-effects", subKey = null,
      nested = false } = {}) => {
    const sec = el("div", `info-locations ${cls}${nested ? " panel-subsec" : ""}`);
    sec.dataset.tourSec = tourSec;
    const sub = subKey && t(subKey);
    const tag = nested ? "h4" : "h3";
    sec.appendChild(beta ? betaHeading(headingKey, vars, sub, tag)
      : heading(tag, t(headingKey, vars), sub, nested ? "panel-subsec-title" : null));
    sec.appendChild(el("p", "legend-caption", t(hintKey)));
    const ul = grouped ? null : sec.appendChild(el("ul"));
    const group = (label, headCls = "loc-group-label") => {
      sec.appendChild(typeof label === "string" ? el("h4", headCls, label) : label);
      return sec.appendChild(el("ul"));
    };
    const close = () => {
      if (caveatKey) sec.appendChild(el("p", "var-caveat", t(caveatKey)));
      if (!nested) body.appendChild(sec);
      return sec;
    };
    return { sec, ul, group, close };
  };

  // One derived "via" chip on a drug panel: the binding (jumps to its target) plus
  // the pill of the receptor-level node it was joined with, and, when the readout
  // mixes compounds, the compound this binding is (`compound`, see
  // metaboliteContributors).
  const viaChip = (binding, node, compound = null) => {
    const tgt = targetById.get(binding.target);
    const chip = el("button", "eff-chip",
      `${binding.targetName} (${binding.actionLabel || binding.action})`);
    if (compound) chip.appendChild(el("span", "eff-from", compound));
    chip.type = "button";
    if (tgt && tgt.focusable) chip.addEventListener("click", () => onTargetPick(tgt));
    else chip.disabled = true;
    const wrap = el("span", "eff-via-item");
    wrap.append(chip, nodePill(node));
    return wrap;
  };

  // One derived drug-panel row: its conditional sentence (or a ready head node, the
  // effect panel's drug name), then one via chip each, labelled by `compoundOf`.
  const derivedRow = (text, via, compoundOf = null) => {
    const li = el("li", "eff-row");
    li.appendChild(typeof text === "string" ? el("span", "loc-name", text) : text);
    const box = el("span", "eff-via");
    for (const { binding, node } of via)
      box.appendChild(viaChip(binding, node, compoundOf && compoundOf(binding)));
    li.appendChild(box);
    return li;
  };

  // A row head that opens a panel: the effect panel from a receptor / drug panel's
  // effect row, a drug from the effect panel's drug list. A plain `.loc-name` when
  // `onClick` is null (an effect absent from the index cannot happen, but stays inert).
  const linkName = (text, onClick) => {
    const span = el("span", "loc-name", text);
    if (onClick) {
      span.classList.add("eff-link");
      span.addEventListener("click", onClick);
    }
    return span;
  };

  const effectLink = (effectId, text) => {
    const effect = effectById.get(effectId);
    return linkName(text, effect ? () => onEffectPick(effect) : null);
  };

  // A receptor / target panel's "Effects" section (BETA): one row per receptor_effect
  // node with its own pill, grouped under one heading per mode (Agonism, Antagonism,
  // ..., groupByMode). An owner with no effect but a recorded search (`unknown`,
  // {searched, corpora}) gets one row with the blue UNKNOWN pill naming that search;
  // with neither, nothing.
  const appendEffects = (rows, unknown) => {
    const has = !!(rows && rows.length);
    if (!has && !unknown) return;
    const { ul, group, close } = betaSection("effects", "effects.heading", "effects.hint",
      { grouped: has });
    if (!has) {
      const li = el("li");
      li.appendChild(el("span", "loc-name", t("effects.unknown")));
      li.appendChild(sourceBackedPill("unknown", { unknown }));
      ul.appendChild(li);
    }
    for (const { rows: inMode } of groupByMode(rows, (e) => e.mode, data.meta.effectModes)) {
      const list = group(inMode[0].modeLabel, "drug-cat");
      for (const e of inMode) {
        const li = el("li");
        li.appendChild(effectLink(e.effect, e.label));
        li.appendChild(nodePill(e));
        list.appendChild(li);
      }
    }
    close();
  };

  // A derived drug readout whose via chips include an active metabolite's bindings:
  // the shared "several compounds" caution box goes above its list, and the returned
  // contributors label every chip by compound. Null (no box) when all are the drug's own.
  const mixedCompounds = (drug, sec, ul, via) => {
    const mix = metaboliteContributors(drug, via.map((v) => v.binding));
    if (mix) sec.insertBefore(derivedActiveMetabolites(drug, body, mix), ul);
    return mix;
  };

  // The drug panel's derived "Predicted effects (target-based)" (BETA): the drug's
  // directional bindings joined with the receptor_effect nodes of their targets, read
  // from the build-time effect index (data.possibleEffectsByDrug, see
  // tools/data_generators/effect_index.py). Never stored, and worded conditionally: it
  // says what acting on these receptors can cause, never that this drug does.
  // Folded with the rest of the drug panel by its final foldSections.
  const appendPossibleEffects = (drug) => {
    const effects = data.possibleEffectsByDrug.get(drug.id) || [];
    if (!effects.length) return;
    const { sec, ul, close } = betaSection("effects", "effects.drugHeading", "effects.drugHint",
      { subKey: "effects.drugHeadingSub" });
    const mix = mixedCompounds(drug, sec, ul, effects.flatMap((e) => e.via));
    for (const e of effects) {
      ul.appendChild(derivedRow(effectLink(e.effect, t("effects.couldCause", { effect: e.label })),
        e.via, mix && mix.compoundOf));
    }
    close();
  };

  // " in <structure>" for a release-modulation line, or "" when the node names none.
  const inStructure = (base) => (base
    ? t("relmod.inStructure", { structure: resolveBase(base)?.base_name
        || resolveBase(base)?.name || base })
    : "");

  // A receptor panel's "Downstream" section (BETA): one row per
  // receptor_release_modulation node, "activating it decreases dopamine release"
  // + "heteroreceptor on GABA interneurons in VTA" with that node's own pill.
  const appendDownstream = (rows) => {
    if (!rows || !rows.length) return;
    const { ul, close } = betaSection("downstream", "relmod.heading", "relmod.hint");
    for (const n of rows) {
      const li = el("li", "eff-row");
      li.appendChild(el("span", "loc-name", t(`relmod.activation.${n.effect}`,
        transmitterVars(n.transmitterLabel, ofNoun))));
      li.appendChild(nodePill(n));
      li.appendChild(el("span", "eff-mode eff-site", t("relmod.site",
        { kind: n.kindLabel, cell: n.cellLabel, where: inStructure(n.structure) })));
      ul.appendChild(li);
    }
    close();
  };

  // A receptor / target panel's "Across age and sex" section (BETA): one row per
  // receptor_demographic node, a direction chip ("↓ Age") then the conditional
  // sentence ("reported to decline with age in Caudate nucleus") with that node's own
  // pill, and the paper's own magnitude wording under it when it states one.
  const appendDemographics = (rows) => {
    if (!rows || !rows.length) return;
    const { ul, close } = betaSection("demographics", "demog.heading", "demog.hint");
    for (const n of rows) {
      const li = el("li", "eff-row");
      li.appendChild(el("span", "demog-chip", `${n.glyph} ${n.factorLabel}`));
      li.appendChild(el("span", "loc-name", t(n.textKey, { where: inStructure(n.structure) })));
      li.appendChild(nodePill(n));
      if (n.magnitude) {
        li.appendChild(el("span", "eff-mode eff-site", t("demog.magnitude", { magnitude: n.magnitude })));
      }
      ul.appendChild(li);
    }
    close();
  };

  // One receptor_variant row: the evidence-level chip (its meaning on hover), the
  // conditional sentence, the node's pill (ClinPGx's per-genotype sentences on hover),
  // then a muted line with the phenotypes, the population and the ClinPGx link.
  // `prefix` names the variant when the row is not already under its heading.
  const variantRow = (row, prefix) => {
    const li = el("li", "var-row");
    li.appendChild(attachTip(el("span", "var-level",
      t("variant.level", { level: row.level, strength: row.strength })), row.levelLabel));
    const drugs = [...row.drugs.map((d) => d.name), ...row.drugNames].join(", ");
    const category = row.categories.join(", ");
    const text = drugs ? t("variant.assoc", { category, drugs })
      : t("variant.assocNoDrug", { category });
    li.appendChild(el("span", "loc-name",
      prefix ? t("variant.withVariant", { variant: prefix, text }) : text));
    li.appendChild(nodePill(row));
    const meta = el("span", "var-meta",
      [row.phenotypes.join(", "),
       row.population ? t("variant.population", { population: row.population }) : ""]
        .filter(Boolean).join(" · "));
    if (isWebUrl(row.url)) {
      const a = extLink(t("variant.link"), row.url);
      a.title = t("variant.linkTitle");
      if (meta.textContent) meta.appendChild(document.createTextNode(" · "));
      meta.appendChild(a);
    }
    li.appendChild(meta);
    return li;
  };

  // A receptor / target panel's "Genetic variants" section (ClinPGx #20): the gene's
  // annotated variants, one sub-heading per variant, strongest level first, folded,
  // with the not-medical-advice caveat once at the end.
  const appendVariants = (rows) => {
    if (!rows || !rows.length) return;
    const { group, close } = betaSection("variants", "variant.heading", "variant.hint",
      { beta: false, cls: "info-variants", grouped: true, caveatKey: "variant.caveat" });
    for (const g of groupByVariant(rows)) {
      const ul = group(g.variant, "var-name");
      for (const row of g.rows) ul.appendChild(variantRow(row));
    }
    close();
  };

  // The drug panel's "Pharmacogenomic associations (ClinPGx)": every receptor_variant
  // node naming this drug, grouped under the target whose gene carries it (the
  // heading jumps to that target). A BETA subsection of the drug's Pharmacogenomics
  // section (views/drug.js), returned for the caller to place; null when none.
  const drugVariantsSubsection = (drug) => {
    const hits = variantsForDrug(drug.id, data.targets);
    if (!hits.length) return null;
    const { group, close } = betaSection("variants", "variant.drugHeading", "variant.drugHint",
      { cls: "info-variants", grouped: true, caveatKey: "variant.caveat",
        subKey: "variant.drugHeadingSub", nested: true });
    const byTarget = new Map();
    for (const { target, row } of hits) {
      if (!byTarget.has(target)) byTarget.set(target, []);
      byTarget.get(target).push(row);
    }
    for (const [target, rows] of byTarget) {
      const head = el("h4", "var-name");
      const chip = btn("var-target", target.name);
      if (target.focusable) chip.addEventListener("click", () => onTargetPick(target));
      else chip.disabled = true;
      head.appendChild(chip);
      const ul = group(head);
      for (const row of rows) ul.appendChild(variantRow(row, row.variant));
    }
    return close();
  };

  // The drug panel's derived "Presynaptic modulation" (BETA): its directional
  // bindings joined with the release-modulation nodes of their receptors
  // (js/release-modulation.js), an antagonist flipping the effect of activation and
  // affinity_only contributing nothing. Computed, never stored, worded conditionally.
  const appendReleaseChanges = (drug) => {
    const changes = deriveReleaseChanges(
      drug.allBindings, (tid) => data.modulationByTarget.get(tid) || [], data.meta.effectModes);
    if (!changes.length) return;
    const { sec, ul, close } = betaSection("downstream", "relmod.drugHeading", "relmod.drugHint",
      { subKey: "relmod.drugHeadingSub" });
    const mix = mixedCompounds(drug, sec, ul, changes.flatMap((c) => c.via));
    for (const c of changes) {
      ul.appendChild(derivedRow(t(`relmod.could.${c.direction}`,
        { ...transmitterVars(c.transmitterLabel, ofNoun), where: inStructure(c.structure) }),
        c.via, mix && mix.compoundOf));
    }
    close();
  };

  // A drug panel's "Checks before and during treatment" section (BETA): one row per
  // drug_workup node, grouped by timing, each with its own pill (the RCP sentence on
  // hover). Neutral wording ("the French label asks for"), plus the not-medical-advice
  // caveat, since a label's checklist is a regulatory text, not a care plan.
  const appendWorkup = (drug) => {
    if (!drug.workup || !drug.workup.length) return;
    const { group, close } = betaSection("workup", "drug.workup", "drug.workupHint",
      { grouped: true, caveatKey: "drug.workupCaveat", subKey: "drug.workupSub" });
    for (const g of groupWorkup(drug.workup)) {
      const list = group(t(`drug.workup.${g.timing}`));
      for (const n of g.rows) {
        const li = el("li", "eff-row");
        li.appendChild(el("span", "loc-name", n.testLabel));
        const cond = formatConditions(n, t("drug.workupOnlyIf"));
        if (cond) li.appendChild(el("span", "workup-cond", cond));
        li.appendChild(nodePill(n));
        list.appendChild(li);
      }
    }
    close();
  };

  return {
    appendDemographics, appendDownstream, drugVariantsSubsection, appendEffects,
    appendPossibleEffects, appendReleaseChanges, appendVariants, appendWorkup,
    betaHeading, betaSection, derivedRow, effectLink, inStructure, linkName,
    variantRow, viaChip,
  };
}
