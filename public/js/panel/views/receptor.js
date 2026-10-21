// The Receptor view: one receptor, its classification claims, expression, effects,
// release modulation, demographics, variants and the drugs that bind it.

const { t } = window.__I18N__;

/**
 * Populate the panel for a *receptor* (clicking a receptor legend row): its
 * name, neurotransmitter system, a Wikipedia link, a one-line description, the
 * classification facts (neurotransmitter, mechanism type, excit/inhib/modulatory
 * effect with its sign swatch, pre/post-synaptic site) and where it is
 * expressed (the region list, "Throughout the brain" for a ubiquitous receptor,
 * or a no-CNS-role note for a stub). Built fresh each call like the others.
 */
export function showReceptor(P, receptor) {
  const {
    PDSP_KIDB_URL, addFactRow, appendAddons, appendDemographics, appendDownstream,
    appendEffects, appendFoundIn, appendInteractingDrugs, appendLookupLink, appendReference,
    appendVariants, body, clearBody, clinpgxSearchUrl, el, foldBody, gtopdbSearchUrl,
    sourceBackedPill, uniprotSearchUrl,
  } = P;
  clearBody("receptor");
  body.appendChild(el("h2", "info-title", receptor.name));
  body.appendChild(el("div", "info-group", receptor.familyLabel));
  appendAddons(body, "receptor", receptor.id, "receptor.top");

  const { wiki: recWiki } = appendReference({
    url: receptor.wikipedia, description: receptor.description,
  });
  // External lookups beside the reference: PDSP Ki (binding affinity; a browse
  // link, PDSP has no per-target search URL), UniProt, ClinPGx (pharmacogenomics)
  // and the Guide to Pharmacology (GtoPdb). The first two are protein/gene
  // databases, so they search the HGNC symbol (`ADRA1A`; the display name "α1A"
  // finds nothing there), falling back to the name for the one stub receptor
  // with no human gene; GtoPdb indexes the pharmacological name itself.
  const recGene = receptor.gene || receptor.name;
  appendLookupLink(recWiki, "info.pdsp", PDSP_KIDB_URL, "info.pdspTitle");
  appendLookupLink(recWiki, "info.uniprot", uniprotSearchUrl(recGene), "info.uniprotTitle");
  appendLookupLink(recWiki, "info.clinpgx", clinpgxSearchUrl(recGene), "info.clinpgxGeneTitle");
  appendLookupLink(recWiki, "info.gtopdb", gtopdbSearchUrl(receptor.name), "info.gtopdbTitle");

  // Classification facts as label / value rows; the "effect" value carries the
  // sign swatch so the colour matches the dots + legend row. Each attribute
  // (family / class / sign / synaptic) is its OWN graded sub-claim, so each row
  // shows its OWN pill from receptor.classification[attr]: a quote that only
  // backs the sign no longer lends a verified badge to the GPCR or pre/post
  // claim it never addressed. Unsourced attributes read honestly as llm.
  // Through the shared node pill, so an attribute another corpus denies
  // (quotes/contradictions.py) goes orange with the denial leading its tooltip.
  const attrPill = (attr) => {
    const entry = (receptor.classification || {})[attr] || {};
    return sourceBackedPill(entry.grade, entry);
  };
  const facts = el("div", "info-facts");
  facts.dataset.tourSec = "facts"; // guided-tour section anchor
  addFactRow(facts, t("receptor.neurotransmitter"), receptor.neurotransmitter,
    null, { pill: attrPill("family") });
  addFactRow(facts, t("receptor.type"), receptor.classLabel,
    null, { pill: attrPill("receptor_class") });
  addFactRow(facts, t("receptor.effect"), receptor.signLabel, receptor.signColor,
    { pill: attrPill("sign") });
  addFactRow(facts, t("receptor.synaptic"), receptor.synapticLabel,
    null, { pill: attrPill("synaptic") });
  body.appendChild(facts);

  // Where it is expressed.
  appendFoundIn(receptor, receptor.locations, "regions"); // guided-tour section anchor
  appendEffects(receptor.effectInfo, receptor.effectsUnknown, "receptor");
  appendDownstream(receptor.modulationInfo, "receptor");
  appendDemographics(receptor.demographicInfo, "receptor");
  appendVariants(receptor.variantInfo, "receptor");

  // Drugs that act on this receptor, grouped by category.
  appendInteractingDrugs(receptor.id, "receptor");
  // Headed sections start folded, like the drug panel (see foldSections).
  foldBody();
}
