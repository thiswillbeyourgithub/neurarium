// The Target view: one non-receptor drug target (transporter, enzyme, channel), its
// type, polarity, expression and the drugs that bind it.

const { t } = window.__I18N__;

/**
 * Populate the panel for a non-receptor *target* (a transporter / enzyme / ion
 * channel / receptor group, clicked in the merged "Receptors & targets" section
 * or a target search result): its name, its neurotransmitter system (or
 * "Other"), a Wikipedia link (or a TODO pill until one is gathered), the type +
 * system facts, and the regions it sits in. Receptors keep the richer
 * showReceptor view; this is the lighter sibling for the non-receptor targets.
 */
export function showTarget(P, target) {
  const {
    PDSP_KIDB_URL, addFactRow, appendAddons, appendDemographics, appendEffects,
    appendFoundIn, appendInteractingDrugs, appendLookupLink, appendReference,
    appendSubtypeInteractors, appendVariants, body, clearBody, clinpgxSearchUrl, el,
    foldBody, nodePill,
  } = P;
  clearBody("target");
  body.appendChild(el("h2", "info-title", target.name));
  body.appendChild(el(
    "div", "info-group", target.systemLabel || t("targets.otherSystem")));
  appendAddons(body, "target", target.id, "target.top");

  // Reference + live lead (targets carry no baked description), via the shared
  // appendReference, so the link sits under any live lead like every panel.
  const { wiki: tgtWiki } = appendReference({ url: target.wikipedia });
  // PDSP covers transporters / enzymes / ion channels too, so the same lookup,
  // and ClinPGx on the gene (SLC6A4 for SERT): a transporter or a metabolizing
  // enzyme is exactly what the pharmacogenomics literature is about. A group
  // target (α2 = ADRA2A/B/C) searches its representative member.
  appendLookupLink(tgtWiki, "info.pdsp", PDSP_KIDB_URL, "info.pdspTitle");
  if (target.gene) {
    appendLookupLink(tgtWiki, "info.clinpgx",
      clinpgxSearchUrl(target.gene), "info.clinpgxGeneTitle");
  }

  // The classification grade (type / system claims) sits on each fact's OWN row
  // rather than a single broad "Source" row below, so a source always grades the
  // specific node beside it. A fresh pill per row; only when the row has a value
  // (so an empty System row still drops instead of showing a bare pill).
  const tgtPill = () => nodePill({ provenance: target.classificationProvenance, sources: target.sources });
  const withPill = (v) => (v && target.classificationProvenance ? { pill: tgtPill() } : {});
  const facts = el("div", "info-facts");
  addFactRow(facts, t("receptor.type"), target.typeLabel, target.swatchColor,
    withPill(target.typeLabel));
  addFactRow(facts, t("receptor.system"), target.systemLabel, null,
    withPill(target.systemLabel));
  // Tone-polarity row: its OWN sourced sub-claim, NOT the classification grade.
  // The vesicular/sign flags flip the drug-flow overlay's direction, so a wrong
  // one silently inverts a drug's apparent effect on tone; surfacing it with its
  // own pill keeps that claim honestly graded (e.g. α2's autoreceptor character
  // reads llm until quote-verified, VMAT2's vesicular claim reads verified).
  if (target.polarityProvenance) {
    const polText = target.vesicular
      ? t("target.polarityVesicular")
      : (target.polaritySign === "inhibitory"
        ? t("target.polarityAutoreceptor") : null);
    if (polText) {
      const polPill = nodePill({ provenance: target.polarityProvenance, sources: target.polaritySources });
      addFactRow(facts, t("target.polarity"), polText, null, { pill: polPill });
    }
  }
  if (facts.childElementCount) body.appendChild(facts);

  // Where it sits (the same "Regional distribution" list as a receptor; empty -> no footprint).
  appendFoundIn(target, target.locationBases);
  appendEffects(target.effectInfo, target.effectsUnknown);
  appendDemographics(target.demographicInfo);
  appendVariants(target.variantInfo);

  // Drugs that act on this target, grouped by category.
  appendInteractingDrugs(target.id);
  // For a receptor_group (α2 / glutamate): drugs binding each modeled subtype
  // (α2A/B/C/D, ...) in a collapsed per-subtype dropdown below the group's own.
  appendSubtypeInteractors(target.subtypes);
  // Headed sections start folded, like the drug panel (see foldSections).
  foldBody();
}
