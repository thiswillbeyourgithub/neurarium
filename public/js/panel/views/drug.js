// The Drug view: one drug, its bindings and their effects, formulations, timing,
// metabolism, pharmacogenomics, history and reference material.

import { appendDrugHistory } from "../../drug-history.js";
import { appendPhyschemChips, hasPhyschem } from "../../physchem.js";
import { appendTdmChips, valueChip } from "../../tdm.js";
import { bindingKi, formatHalfLife } from "../format.js";
import { flashRow, btn } from "../dom.js";
import { loadPkGrouping, savePkGrouping } from "../../legend/drugs.js";
import { toneWeightOf } from "../../data.js";

const { t } = window.__I18N__;


export function showDrug(P, drug, opts = {}) {
  const {
    addFactRow, appendAddons, appendDrugVariants, appendLookupLink,
    appendPossibleEffects, appendReference, appendReleaseChanges, appendWorkup,
    bindingRow, body, clearBody, clinpgxSearchUrl, data, derivedActiveMetabolites,
    derivedAutoModulation, derivedBox, directionArrow, drugById, drugNameLink, el,
    enzymeById, enzymeRow, fmtTone, foldBody, netTone, nodePill, onDrugPick,
    onEnzymePick, onImagePick, onProjectionGroupPick, onTargetPick, pgxSection,
    targetById,
  } = P;
  clearBody("drug");
  body.appendChild(el("h2", "info-title", drug.label || drug.name));
  if (drug.category) body.appendChild(el("div", "info-group", drug.category));
  // This drug IS another drug's active metabolite (paliperidone = risperidone's
  // 9-hydroxy metabolite): say so up top, each parent a link, the claim carrying
  // the parent's sourced metabolite pill.
  if (drug.metaboliteOf && drug.metaboliteOf.length) {
    const p = el("p", "info-desc metab-of", `${t("drug.activeMetaboliteOf")} `);
    drug.metaboliteOf.forEach(({ parent, ...claim }, i) => {
      if (i) p.appendChild(document.createTextNode(", "));
      p.appendChild(drugNameLink(parent));
      p.appendChild(nodePill(claim));
    });
    body.appendChild(p);
  }

  // Combination drug: no PDSP Ki of its own (it is a mixture). Warn, and link to
  // each constituent we model as a standalone drug so its binding profile is one
  // click away; interactions between the constituents may exist.
  if (drug.combo && drug.combo.length) {
    const warn = el("div", "combo-warning");
    warn.appendChild(el("strong", null, t("drug.combo")));
    warn.appendChild(el("p", null, t("drug.comboNote")));
    const links = el("div", "combo-parts");
    drug.combo.forEach((c, i) => {
      if (i) links.appendChild(document.createTextNode(" · "));
      const linked = c.drugId && drugById.get(c.drugId);
      if (linked && linked.focusable) {
        const a = btn("combo-link", linked.displayName);
        a.addEventListener("click", () => onDrugPick(linked));
        links.appendChild(a);
      } else {
        links.appendChild(el("span", "combo-plain", c.name));
      }
    });
    // A salt's declared composition is its own graded node (drug_constituents);
    // a combo named after its parts states nothing to grade.
    const cc = drug.constituentsClaim;
    if (cc) {
      links.appendChild(document.createTextNode(" "));
      links.appendChild(nodePill(cc));
    }
    warn.appendChild(links);
    body.appendChild(warn);
  }

  // Addon slot: a caveat about the drug as a whole, above everything it does.
  // Below the combo warning, which is about what this row even IS.
  appendAddons(body, "drug", drug.id, "drug.top");

  // Vendored molecular-structure SVG (from Wikipedia, see tools/fetch_molecules.py).
  // It is black/grey line art on transparent; the .mol-structure CSS inverts it
  // to read as light strokes on the dark panel. Absent when no SVG was fetched.
  if (drug.structureImage) {
    const fig = el("figure", "mol-structure");
    const img = document.createElement("img");
    img.alt = t("drug.structureAlt", { name: drug.name });
    img.decoding = "async";
    img.title = t("image.zoomHint");
    // A failed molecule SVG degrades gracefully (drop the figure, no broken
    // icon) and opts out of the global error banner, exactly like the Wikipedia
    // illustrations: an absent diagram is not an app error to shout about.
    img.dataset.optional = "1";
    img.addEventListener("error", () => fig.remove());
    // Click to enlarge; the lightbox inverts it too so the line-art reads on
    // the dark backdrop, matching the panel's .mol-structure treatment.
    img.addEventListener("click", () =>
      onImagePick(img.currentSrc || img.src, img.alt, { invert: true }));
    img.src = drug.structureImage; // set src last, after error handler is wired
    fig.appendChild(img);
    body.appendChild(fig);
  }

  // Description (the drug's Wikipedia lead, baked + live-refreshed) then the
  // Wikipedia link below it, via the shared appendReference. A "sourced"
  // description is the WP lead (CC BY-SA); an "llm" one a mechanism synthesis.
  const { paragraph, wiki } = appendReference({
    url: drug.wikipedia, description: drug.description,
    descriptionProvenance: drug.descriptionProvenance,
    descriptionExtra: drug.descriptionProvenance === "sourced"
      ? t("info.descFromWikipedia") : "",
  });
  // External drug-database lookup links beside the reference. Each is a
  // search-by-name link (it always lands on a results page), a convenience
  // lookup rather than a source for a specific claim, so none carries a
  // provenance pill; all are only linked (navigated to), never fetched, so the
  // CSP is unaffected. Vidal (the French database) shows only in French; the
  // EMA (Europe) and the US FDA show regardless of locale. ANSM is intentionally
  // absent: its ecodex search has no URL-addressable form to deep-link.
  if (wiki) {
    const addLookup = (labelKey, href, titleKey) =>
      appendLookupLink(wiki, labelKey, href, titleKey);
    const q = encodeURIComponent(drug.name);
    // Order: the two regulators first (EMA, FDA), then ClinPGx, then the
    // consumer-facing Drugs.com, so the list runs from the most authoritative
    // to the most readable.
    addLookup(
      "info.ema",
      "https://www.ema.europa.eu/en/search?search_api_fulltext=" + q,
      "info.emaTitle");
    addLookup(
      "info.fda",
      "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
        + "?event=BasicSearch.process&searchTerm=" + q,
      "info.fdaTitle");
    addLookup("info.clinpgx", clinpgxSearchUrl(drug.name), "info.clinpgxTitle");
    // Drugs.com search by name. A search link (always lands on the drug),
    // chosen over a direct /monograph/<name>.html so it never 404s for a drug
    // whose monograph slug differs (combos especially); shown regardless of
    // locale.
    addLookup(
      "info.drugscom",
      "https://www.drugs.com/search.php?searchterm="
        + encodeURIComponent(drug.name.toLowerCase()),
      "info.drugscomTitle");
    if (window.__I18N__.lang === "fr") {
      addLookup(
        "info.vidal",
        "https://www.vidal.fr/recherche/substances.html?query="
          + encodeURIComponent(drug.name.toLowerCase()),
        "info.vidalTitle");
    }
  }

  // The reference row itself (the Wikipedia link + the external-database
  // lookups) is its own tour anchor, so a step can point at "links to reputable
  // sources to read more" distinctly from the description that sits above it.
  if (wiki) wiki.dataset.tourSec = "links";
  // Group the description + Wikipedia link (+ lookups) under one anchor so the
  // guided tour can spotlight the "what it is" section; the live lead lands
  // inside it too (inserted above the link). No-op when there is no wiki wrap.
  if (wiki && wiki.parentNode) {
    const introWrap = el("div", "info-intro");
    introWrap.dataset.tourSec = "wiki";
    wiki.parentNode.insertBefore(introWrap, paragraph || wiki);
    if (paragraph) introWrap.appendChild(paragraph);
    introWrap.appendChild(wiki);
  }

  // Classification facts: the coarse class(es) and the NbN nomenclature line.
  // Both are clickable: each runs a search (class:"..." / nbn:"...") that filters
  // to the matching drugs, so you can pivot from one drug to its whole class. The
  // class list shows one clickable chip per category.
  const facts = el("div", "info-facts");
  facts.dataset.tourSec = "facts"; // guided-tour section anchor
  // The class classification is its own node: pill it (its own grade, or the
  // verbatim quote when category_sources exist), so the claim "this drug is an
  // SSRI/..." carries its provenance beside the value like every other node.
  const catPill = nodePill({ provenance: drug.categoryProvenance, sources: drug.categorySources });
  addFactRow(facts, t("drug.class"), null, null, {
    links: drug.categoryLabels.map((label) => ({
      text: label,
      query: `class:"${label}"`,
    })),
    pill: catPill,
  });
  if (drug.nbn) {
    // The NbN line is quote-sourced from Stahl; show its provenance pill
    // (with the verbatim quote in the tooltip) beside the clickable value. If a
    // drug ever carries an NbN value with no source, still show a pill (its
    // grade, else the red NOSOURCE pill) so the node is never left unbadged.
    const nbnPill = nodePill({ provenance: drug.nbnProvenance, sources: drug.nbnSources });
    addFactRow(facts, t("drug.nomenclature"), null, null, {
      links: [{ text: drug.nbn, query: `nbn:"${drug.nbn}"` }],
      pill: nbnPill,
      // A newer drug with no formal NbN carries Stahl's drug-class descriptor
      // instead; flag it so the value isn't misread as an official NbN.
      note: drug.nbnNonstandard ? t("drug.nbnNonstandard") : null,
    });
  }
  if (facts.childElementCount) body.appendChild(facts);

  // Commercial brand names, each its own graded node (Stahl backs na, Wikipedia
  // eu/fr). Listed in the locale's order (the primary/most-iconic brand first, the
  // same one shown after the drug name everywhere); the region tag is never shown.
  // Each brand carries its own provenance pill, so no node is left unbadged and a
  // mixed-grade list (once eu/fr are added) reads honestly.
  // A brand sold as one formulation (Seroquel XR) is listed under it in the
  // Pharmacokinetics table instead (see below), so this row keeps the molecule's.
  const appendBrand = (host, b) => {
    host.appendChild(el("span", "bind-target", b.name));
    // A brand's grade is its top-region source's (the one the row keeps).
  host.appendChild(nodePill({ ...b, provenance: b.sources && b.sources.length ? b.sources[0].provenance : null }));
  };
  // Administrative: the regulatory history (first approval + years since,
  // withdrawals) and the brands, i.e. what the drug is as a marketed product rather
  // than as a molecule. Omitted when it would hold nothing.
  const admin = el("div", "info-bindings info-admin");
  admin.appendChild(el("h3", null, t("drug.admin")));
  const history = el("div", "info-facts");
  appendDrugHistory(history, drug,
    { addFactRow, nodePill, t, lang: window.__I18N__.lang });
  if (history.childElementCount) admin.appendChild(history);
  const moleculeBrands = (drug.brandsOrdered || []).filter((b) => !b.release);
  if (moleculeBrands.length) {
    const brandsEl = el("div", "info-brands");
    brandsEl.dataset.tourSec = "brands"; // guided-tour section anchor
    brandsEl.appendChild(el("h4", null, t("drug.brands")));
    const ul = el("ul");
    for (const b of moleculeBrands) {
      const li = el("li");
      appendBrand(li, b);
      ul.appendChild(li);
    }
    brandsEl.appendChild(ul);
    admin.appendChild(brandsEl);
  }
  if (admin.childElementCount > 1) body.appendChild(admin);

  // Does the Metabolism section below carry a non-linear-kinetics admonition?
  // A single T½ is only meaningful when clearance is a straight line, so a drug
  // that changes its own clearance makes the number above misleading on its own.
  // The admonition is written down there (it needs the enzyme rows to make sense),
  // so the chip gets a warning that points at it rather than a second copy of it.
  // Either form counts: the authored addon (a mechanism a source attests) or, in
  // its absence, the derived autoModulation flag, exactly the fallback the section
  // itself uses. Gated on the section actually rendering, or the warning would
  // promise a place to jump to that is not there.
  const metabAddons = data.addonsBySlot
    ? data.addonsBySlot.get(`drug:${drug.id}:drug.metabolism`) || [] : [];
  const nonLinearPk = Boolean(drug.enzymes && drug.enzymes.length
    && (metabAddons.length || (drug.autoModulation || []).length));

  // The two per-drug durations, each its own sourced node, placed between brands
  // and the binding list and formatted to days/hours/minutes. They share one
  // section because they are the two ends of one curve (the peak is when the
  // drug arrives, the T½ how long it takes to leave), which is also how
  // js/sim-model.js reads them; either may be missing on its own. The blood
  // levels the AGNP guideline monitors (therapeutic range, alert level) close
  // the block: they are where on that curve the concentration should sit.
  const forms = drug.formulations || [];
  if (drug.halfLife || drug.tmax || drug.therapeuticRange || drug.alertLevel
      || forms.length) {
    const hlEl = el("div", "info-bindings info-halflife");
    hlEl.appendChild(el("h3", null, t("drug.pkTiming")));
    const chipHelpers = { el, nodePill, t,
                          lang: window.__I18N__.lang };
    if (drug.tmax) {
      hlEl.appendChild(valueChip(chipHelpers, {
        label: t("drug.tmax"), tip: t("drug.tmaxTip"),
        value: formatHalfLife(drug.tmax),
        provenance: drug.tmaxProvenance, sources: drug.tmaxSources }));
    }
    if (drug.halfLife) {
      const chip = valueChip(chipHelpers, {
        label: t("drug.halfLife"), value: formatHalfLife(drug.halfLife),
        provenance: drug.halfLifeProvenance, sources: drug.halfLifeSources });
      if (nonLinearPk) {
        const warn = el("button", "hl-warn",
          (data.meta.addonTones || {}).caution || "⚠");
        warn.type = "button";
        warn.title = t("drug.nonLinearPk");
        warn.setAttribute("aria-label", t("drug.nonLinearPk"));
        // Looked up at click time, not captured now: the Metabolism section is
        // built further down this same render, so it does not exist yet here.
        warn.addEventListener("click", () => {
          const sec = body.querySelector('[data-tour-sec="metabolism"]');
          if (sec) flashRow(sec);
        });
        chip.appendChild(warn);
      }
      hlEl.appendChild(chip);
    }
    // Addon slot: a caveat about what these two numbers measure (a serum
    // half-life the brain does not follow), right under the chips it qualifies.
    appendTdmChips(hlEl, drug, chipHelpers);
    appendAddons(hlEl, "drug", drug.id, "drug.timing");
    // Per-formulation list: what a source ties to ONE product (its release
    // type, a pill on the claim that it exists), under the molecule-level values
    // above, which no source tied to a product.
    if (forms.length) {
      const wrap = el("div", "formulations");
      wrap.appendChild(el("h4", null, t("drug.formulations")));
      for (const f of forms) {
        // One block per formulation: its release type (pill: the claim that
        // the product exists) and its Tmax / T½ on one line, its brands below.
        const row = el("div", "form-row");
        const head = el("div", "form-head");
        // The pill rides inside the release name, so the row's wide gap
        // only separates whole items (each chip already ends in its pill).
        const release = el("span", "form-release", `${f.label} `);
        release.appendChild(nodePill({ provenance: f.releaseProvenance, sources: f.releaseSources }));
        head.appendChild(release);
        if (f.tmax) {
          head.appendChild(valueChip(chipHelpers, {
            label: t("drug.tmax"), tip: t("drug.tmaxTip"),
            value: formatHalfLife(f.tmax),
            provenance: f.tmaxProvenance, sources: f.tmaxSources }));
        }
        if (f.halfLife) {
          head.appendChild(valueChip(chipHelpers, {
            label: t("drug.halfLife"), value: formatHalfLife(f.halfLife),
            provenance: f.halfLifeProvenance, sources: f.halfLifeSources }));
        }
        row.appendChild(head);
        if (f.brands.length) {
          const brands = el("div", "form-brands");
          for (const br of f.brands) {
            const item = el("span", "form-brand");
            appendBrand(item, br);
            brands.appendChild(item);
          }
          row.appendChild(brands);
        }
        wrap.appendChild(row);
      }
      hlEl.appendChild(wrap);
    }
    body.appendChild(hlEl);
  }

  // Physicochemistry and brain entry: the computed lipophilicity and polar surface
  // (PubChem) beside the curated blood-brain-barrier label (B3DB), each its own
  // node. Its own small section rather than the Pharmacokinetics block, which is
  // about time (when the drug peaks, how long it stays); this is about whether
  // and how easily it reaches the brain at all. Same chip layout (info-halflife).
  if (hasPhyschem(drug)) {
    const pc = el("div", "info-bindings info-halflife info-physchem");
    pc.appendChild(el("h3", null, t("drug.physchem")));
    appendPhyschemChips(pc, drug,
      { el, nodePill, t, lang: window.__I18N__.lang });
    body.appendChild(pc);
  }

  // (Ki ranking uses the shared bindingKi helper.)

  // What it binds: one row per target, coloured by the action's net effect.
  const acts = el("div", "info-bindings");
  acts.dataset.tourSec = "bindings"; // guided-tour section anchor
  acts.appendChild(el("h3", null, t("drug.actsOn")));
  const metabWarn = derivedActiveMetabolites(drug, body);
  if (metabWarn) acts.appendChild(metabWarn);
  // A prodrug's own graded claim (kind drug_prodrug): it binds nothing itself, so
  // every row below is borrowed from its active metabolite ("via ...").
  if (drug.prodrug) {
    const p = el("p", "info-desc", `${t("drug.prodrug")} `);
    p.title = t("drug.prodrugTip");
    p.appendChild(nodePill(drug.prodrug));
    acts.appendChild(p);
  }
  if (!drug.bindings.length) {
    acts.appendChild(el("p", "info-desc", t("drug.noTargets")));
  } else {
    const ul = el("ul");
    // Strongest-affinity first: order by the binding's representative Ki
    // ascending, so the target a drug grips hardest tops the list; bindings with
    // no measured Ki sink to the bottom. Sort a copy (leave the authored array
    // untouched); a stable sort keeps the authored order within each tier.
    const bindings = [...drug.bindings].sort((a, b) => bindingKi(a) - bindingKi(b));
    for (const b of bindings) {
      // If this binding's target is browsable on its own (in the merged
      // "Receptors & targets" list and focusable), make the row jump to it.
      const tgt = targetById.get(b.target);
      const onActivate = tgt && tgt.focusable
        ? () => onTargetPick(tgt) : null;
      const row = bindingRow(b, drug, b.targetName, onActivate);
      row.dataset.tourId = `ixtarget:${b.target}`; // guided-tour hook: target row in a drug panel
      ul.appendChild(row);
    }
    acts.appendChild(ul);
  }
  body.appendChild(acts);
  appendPossibleEffects(drug);
  appendReleaseChanges(drug);
  appendDrugVariants(drug);
  appendWorkup(drug);

  // Active metabolites: one row per metabolite (its own sourced identity node).
  // A metabolite that is itself a modeled drug links to it (jump via onDrugPick);
  // each shows its own T½ underneath, a bit like a binding's Ki. A non-modeled
  // metabolite's OWN receptor bindings (Wikipedia/PDSP-sourced) are listed under it
  // via the same bindingRow the drug's "Direct molecular targets" uses, so a reader can see what the
  // metabolite hits without hunting each receptor panel. (A linked metabolite shows
  // none here: its bindings live on its own drug row, reachable via the link.)
  if (drug.metabolites && drug.metabolites.length) {
    const metaEl = el("div", "info-bindings info-metabolites");
    metaEl.dataset.tourSec = "metabolites";
    metaEl.appendChild(el("h3", null, t("drug.metabolites")));
    const ul = el("ul");
    let flashLi = null; // the row to scroll to + flash (opts.highlightMetabolite)
    for (const m of drug.metabolites) {
      const li = el("li", "metab-row");
      if (opts.highlightMetabolite && m.name === opts.highlightMetabolite) flashLi = li;
      const head = el("div", "metab-head");
      const linked = m.drugId ? drugById.get(m.drugId) : null;
      if (linked && m.linkFocusable) {
        // A metabolite that IS a modeled drug: its name is the link to that drug's
        // panel, where its bindings live (never re-listed here: one source of truth).
        const a = drugNameLink(linked, m.name);
        if (linked.bindings.length)
          a.title = t("drug.metabSeeBindings", { n: linked.bindings.length });
        head.appendChild(a);
      } else {
        head.appendChild(el("span", "bind-target", m.name));
      }
      // The shared node pill, so a link another corpus denies reads orange.
      head.appendChild(nodePill(m));
      li.appendChild(head);
      // Which enzyme makes it, each its own sourced node and clickable to that
      // enzyme's panel: the prodrug story (why a CYP2D6 poor metabolizer gets a
      // different drug than the label says). Absent for the metabolites no corpus
      // pins down, which is most of them, so no NOSOURCE row is shown here.
      for (const f of m.formedBy || []) {
        const row = el("div", "metab-formed");
        const text = el("span", "bind-text");
        text.appendChild(el("span", "bind-action", `${t("drug.formedBy")} `));
        const name = el("span", "bind-target", f.label);
        text.appendChild(name);
        if (f.reactionLabel)
          text.appendChild(el("span", "bind-action", ` · ${f.reactionLabel}`));
        row.appendChild(text);
        row.appendChild(nodePill(f));
        const enz = enzymeById.get(f.enzyme);
        if (enz) {
          row.classList.add("clickable");
          row.addEventListener("click", () => onEnzymePick(enz));
        }
        li.appendChild(row);
      }
      const hlStr = formatHalfLife(m.halfLife);
      if (hlStr) {
        li.appendChild(valueChip({ el, nodePill }, {
          label: t("drug.halfLife"), value: hlStr, cls: "metab-hl", bare: true,
          provenance: m.halfLifeProvenance, sources: m.halfLifeSources }));
      }
      // A non-modeled metabolite's OWN sourced receptor bindings (m.ownBindings,
      // resolved in js/data.js from its Wikipedia/PDSP pharmacology). Rendered with
      // the same bindingRow the drug's "Direct molecular targets" uses, strongest-affinity first, each
      // row jumping to its target when browsable.
      if (m.ownBindings && m.ownBindings.length) {
        const bul = el("ul", "metab-bindings");
        const mbinds = [...m.ownBindings].sort((a, b) => bindingKi(a) - bindingKi(b));
        for (const b of mbinds) {
          const tgt = targetById.get(b.target);
          const onActivate = tgt && tgt.focusable ? () => onTargetPick(tgt) : null;
          bul.appendChild(bindingRow(b, drug, b.targetName, onActivate));
        }
        li.appendChild(bul);
      }
      ul.appendChild(li);
    }
    metaEl.appendChild(ul);
    body.appendChild(metaEl);
    // Arrived from a metabolite's receptor row: bring it into view and flash it, so
    // the user sees why the parent drug opened and where its metabolite's bindings are.
    flashRow(flashLi);
  }
  // No standalone drug-level "Source(s)" block: the Stahl citation that backs
  // the drug is shown per-binding (each binding's pill above), so a source
  // always refers to a specific binding node rather than "the whole drug".

  // Neurotransmitter tone (indicative): the ascending systems this drug's flow
  // overlay lights (drug.flowKinds, from meta.system_flow_kinds). A *derived*
  // inference from the drug's *tone-setter* bindings only (a reuptake/enzyme/
  // vesicle target or a presynaptic autoreceptor, see js/data.js toneBySystem):
  // each row shows the signed sum (up arrow = raises the tone, down arrow = lowers
  // it), jumps to that projection group, and lists the per-binding arithmetic with
  // each binding's own pill, so the value is traceable. A purely postsynaptic drug
  // sets no tone -> empty flowKinds -> section omitted.
  const groupsByKey = data.projectionGroupsByKey;
  const projColors = data.meta.projectionColors || {};
  if ((drug.flowKinds || []).length && groupsByKey) {
    const proj = el("div", "info-connections info-tone");
    proj.appendChild(el("h3", null, t("drug.tone")));
    const warn = derivedBox("caution", t("drug.toneWarnTitle"));
    warn.appendChild(el("p", "addon-text", t("drug.toneWarn")));
    proj.appendChild(warn);
    proj.appendChild(el("p", "legend-caption", t("drug.toneHow", {
      none: fmtTone(toneWeightOf(null)).slice(1),
      auto: fmtTone((data.meta.toneFactors || {}).autoreceptor ?? 1).slice(1) })));
    const ul = el("ul");
    for (const kind of drug.flowKinds) {
      const group = groupsByKey.get(`kind:${kind}`);
      if (!group) continue;
      const flow = drug.flowSystems[kind];
      const li = el("li", "clickable");
      li.title = group.name;
      li.appendChild(directionArrow(projColors[kind] || "#fff",
        flow.direction < 0 ? "down" : "up",
        (data.meta.kindLabels && data.meta.kindLabels[kind]) || kind));
      li.appendChild(el("span", "conn-label", group.name));
      li.appendChild(el("span", "tone-value", fmtTone(netTone(drug, kind))));
      li.addEventListener("click", () => onProjectionGroupPick(group));
      ul.appendChild(li);
      // The arithmetic behind the value: one line per tone-setting binding, each
      // with its own source pill, clickable to its target like a target row.
      const terms = el("li", "tone-terms");
      for (const b of flow.terms) {
        const row = el("div", "tone-term");
        row.appendChild(el("span", "tone-term-target", b.targetName));
        row.appendChild(el("span", "tone-term-rule", t(`tone.rule.${b.toneRule}`)));
        // "+1 × 0.50 × 0.43 = +0.21": sign, bucket factor (shown only when not 1),
        // Ki weight; the same product toneBySystem sums.
        const factor = b.toneFactor ?? 1;
        const mag = (v) => fmtTone(v).slice(1);
        row.appendChild(el("span", "tone-term-math",
          `${b.toneSign > 0 ? "+1" : "−1"}${factor !== 1 ? ` × ${mag(factor)}` : ""} × ${mag(b.toneWeight)}`
          + ` = ${fmtTone(b.toneSign * factor * b.toneWeight)}`));
        row.appendChild(nodePill(b));
        const tgt = targetById.get(b.target);
        if (tgt && tgt.focusable) {
          row.classList.add("clickable");
          row.addEventListener("click", (e) => {
            if (e.target.closest(".help-icon")) return;
            onTargetPick(tgt);
          });
        }
        terms.appendChild(row);
      }
      ul.appendChild(terms);
    }
    proj.appendChild(ul);
    body.appendChild(proj);
  }

  // Acts within (context): the ascending systems this drug engages only through a
  // POSTSYNAPTIC receptor (drug.contextKinds, e.g. an H1 / 5-HT2 blocker). Their
  // pathways light statically in the 3D view (dimmed, no beads); blocking a
  // postsynaptic receptor makes NO tone claim, so they are listed apart from
  // "Neurotransmitter tone" above, with a neutral swatch and no direction arrow.
  // Excludes any system already flowing (that one is a tone-setter row above).
  if ((drug.contextKinds || []).length && groupsByKey) {
    const ctx = el("div", "info-connections");
    ctx.appendChild(el("h3", null, t("drug.actsWithin")));
    ctx.appendChild(el("p", "legend-caption", t("drug.actsWithinHint")));
    const ul = el("ul");
    for (const kind of drug.contextKinds) {
      const group = groupsByKey.get(`kind:${kind}`);
      if (!group) continue;
      const li = el("li", "clickable");
      li.title = group.name;
      const sw = el("span", "swatch line");
      sw.style.background = projColors[kind] || "#fff";
      li.appendChild(sw);
      li.appendChild(el("span", "conn-label", group.name));
      li.addEventListener("click", () => onProjectionGroupPick(group));
      ul.appendChild(li);
    }
    ctx.appendChild(ul);
    body.appendChild(ctx);
  }

  // Metabolism, last: pharmacokinetics has no anatomy, so it sits AFTER the
  // sections that do (Direct molecular targets / Neurotransmitter tone / Acts within). The enzymes
  // that clear this drug or whose activity it changes, then the drug -> drug
  // interactions those roles imply.
  if (drug.enzymes && drug.enzymes.length) {
    const enzWrap = el("div", "info-bindings");
    enzWrap.dataset.tourSec = "metabolism"; // guided-tour section anchor
    enzWrap.appendChild(el("h3", null, t("drug.metabolism")));
    enzWrap.appendChild(el("p", "legend-caption", t("drug.metabolismHint")));
    // Where to go read the pharmacokinetic pathways themselves: the enzyme rows
    // below say *which* isoform, ClinPGx draws the route. A lookup link like the
    // ones beside the reference, so it carries no provenance pill.
    const pathRow = el("div", "info-wiki");
    pathRow.appendChild(el("span", null, t("info.pathways")));
    appendLookupLink(pathRow, "info.clinpgx",
      clinpgxSearchUrl(drug.name, "Pathway"), "info.clinpgxPathwaysTitle");
    enzWrap.appendChild(pathRow);
    // Addon slot: the coverage caveat on the list below (a union of the routes
    // some corpus names, never all of them). Anchored on the SECTION rather than
    // on this drug, since the claim holds for every drug at once; read before the
    // rows (folded to its title, so it does not push them down).
    appendAddons(enzWrap, "section", "metabolism", "section.metabolism");
    // Addon slot: a caveat about how this drug is cleared, which the per-isoform
    // rows below cannot state (a row gives a role, never a curve). Above the
    // first enzyme so it is read before them, not as a footnote after.
    // An authored addon states a mechanism a source attests; failing one, the
    // same slot takes the derived flag off the enzyme rows below.
    if (!appendAddons(enzWrap, "drug", drug.id, "drug.metabolism")) {
      const derived = derivedAutoModulation(drug);
      if (derived) enzWrap.appendChild(derived);
    }
    // One heading per role ("Substrate of", then what it does to others), the
    // isoforms indented under it, each carrying its role pill and, when a source
    // qualifies it, its strength + pill (strength is per (enzyme, role), so it
    // stays on the isoform's line rather than on the heading).
    const roleOrder = ["substrate", "inhibitor", "inducer"];
    const byRole = new Map();
    for (const row of drug.enzymes) {
      if (!byRole.has(row.role)) byRole.set(row.role, []);
      byRole.get(row.role).push(row);
    }
    // opts.highlightEnzymes: arrived from another drug's interaction row, so land
    // on the isoform the two share instead of making the reader find it.
    const wanted = new Set(opts.highlightEnzymes || []);
    let flashEnz = null;
    const roles = [...roleOrder.filter((r) => byRole.has(r)),
      ...[...byRole.keys()].filter((r) => !roleOrder.includes(r))];
    for (const role of roles) {
      const group = byRole.get(role).sort((a, b) => a.label.localeCompare(b.label));
      enzWrap.appendChild(el("h4", "enz-role", group[0].roleHeading));
      const enzUl = el("ul", "enz-role-list");
      for (const row of group) {
        const enz = enzymeById.get(row.enzyme);
        const li = enzymeRow(row, row.label, enz ? () => onEnzymePick(enz) : null);
        if (!flashEnz && wanted.has(row.enzyme)) flashEnz = li;
        enzUl.appendChild(li);
      }
      enzWrap.appendChild(enzUl);
    }
    body.appendChild(enzWrap);
    flashRow(flashEnz);

    // What a clearance speed means for THIS prescription (CPIC, corpus #15),
    // right under the isoforms that clear it: the two only answer a clinician's
    // question together, since the enzyme rows say who clears the drug and these
    // say what happens to someone who clears it slowly.
    const pgx = pgxSection(drug);
    if (pgx) body.appendChild(pgx);

    // Drug interactions: derived, never stored (see pkInteractionsOf). This drug
    // and the listed one meet at the same enzyme, so one COULD shift the other's
    // level; the wording stays conditional throughout because the edge is an
    // inference from the enzyme roles, not a measured interaction study.
    const pk = data.pkInteractionsOf ? data.pkInteractionsOf(drug) : null;
    const edges = pk ? [
      ...pk.affects.map((x) => ({ ...x, outgoing: true })),
      ...pk.affectedBy.map((x) => ({ ...x, outgoing: false })),
    ] : [];
    if (edges.length) {
      // info-interactors too: reuses that section's .drug-cat sub-heading style.
      // Collapsed by default (a `disclosure` <details>, same caret as the receptor
      // subtype dropdowns): a busy isoform yields dozens of derived rows, which
      // otherwise bury the sourced sections above. The summary carries the count so
      // the reader can see there is something worth opening.
      const pkWrap = el("details", "info-bindings info-interactors disclosure");
      pkWrap.dataset.tourSec = "pk"; // guided-tour section anchor
      const pkSummary = el(
        "summary", null, `${t("drug.pkInteractions")} (${edges.length})`);
      pkWrap.appendChild(pkSummary);
      // It is the panel's LAST section, so opening it unfolds everything below the
      // fold: bring the summary up to the top of the pane so what you see is the
      // list you just asked for, not the rows above it.
      pkWrap.addEventListener("toggle", () => {
        // setTimeout, not rAF: let the newly shown rows lay out first, and the
        // viewer's on-demand render loop can leave rAF idle.
        if (pkWrap.open) {
          setTimeout(
            () => pkSummary.scrollIntoView({ block: "start", behavior: "smooth" }), 0);
        }
      });
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
      body.appendChild(pkWrap);
    }
  }
  // Every headed section starts collapsed (a drug panel is long): the heading
  // opens it, its content indented under it.
  foldBody();
}
