// Provenance pills and source tooltips: the grade pill on every claim row, the
// tooltip listing its citations (corpus, page, heading trail, species, licence), and the
// uncertainty bullets. A factory over the panel kit P (see panel/info.js).

import { NOSOURCE_GLYPH } from "./format.js";
import { isWebUrl } from "../web-url.js";
import { extLink, btn } from "./dom.js";
import { attachTip, closeTip, linkifiedText } from "./tooltip.js";
import { GRADE_RANK, shownGrade } from "../grades.js";
import { withFetched } from "../data.js";

const { t } = window.__I18N__;

export function makePills(P) {
  const {
    data, el, sourcingModal,
  } = P;

  // withTip wraps an inline provenance pill in a .help-icon span and returns that
  // wrapper (so the pill anchors to itself). The whole hover/tap tooltip mechanism
  // lives in the module-level attachTip (shared with the sourcing coverage bars).
  const withTip = (trigger, tipText) => attachTip(trigger, tipText, { wrap: true });

  // Per-source provenance pill (how trustworthy the source's attribution is):
  // grey "?" = LLM-only (may be hallucinated), yellow "~" = the LLM had the source
  // document, green "✓" = quote-checked + agreed by a second LLM. The colour is a
  // `.src-prov-<level>` CSS class. A falsy / unknown level is the "no source yet"
  // case and renders the red ✕ NOSOURCE pill (`.src-todo`) instead. The pill is a
  // <button> so a tap pins its explanatory tooltip on touch (via withTip). Each
  // pill's tooltip explains its own grade, and the About panel ("Sources &
  // provenance") carries the full grade key, so there is no separate blanket "?"
  // caveat. The three stored grades come from the data (generate_data.py
  // PROVENANCE_LEVELS); `wikipedia` is a viewer-only presentation for a live-fetched
  // Wikipedia lead (a runtime read, not a stored node grade), green because it is a
  // verbatim programmatic extract of an inspectable source, so it can't drift from
  // Wikipedia. Only the glyph + tooltip live here.
  const PROVENANCE_PILLS = {
    llm: { glyph: "?", tip: "info.provLlm" },
    sourced: { glyph: "~", tip: "info.provSourced" },
    verified: { glyph: "✓", tip: "info.provVerified" },
    // Same source, same quote gate as `verified`, but the audit found the sentence
    // does not attribute the claim (see quotes/uncertainty.py). Its tooltip leads
    // with the reasons to doubt it, each itself badged; the grade is data, this is
    // the badge the data asks for.
    uncertain: { glyph: "⚠", tip: "info.provUncertain" },
    // Fallback marker for a live Wikipedia read. Normally the read's provenance is
    // the Wikipedia link itself, relocated into the description (see
    // liveWikiDescription); this ✓ pill only shows if that link could not be moved.
    // It shares the green of `verified` because both are an inspectable, non-LLM
    // extract of a real source (the tooltip names which).
    wikipedia: { glyph: "✓", tip: "info.provWikipedia" },
    // Not a grade: an addon whose basis is `dataset` (meta.addon_bases) states how this
    // dataset is built, so no source could back it and the red ✕ would misread as a
    // gap. Neutral, and its tooltip says why.
    dataset: { glyph: "◌", tip: "info.provDataset" },
    // Not a grade either: every required source was searched for this claim and none
    // states it (a recorded search, tools/data_generators/unknown.py). A finding, not
    // the to-do the red ✕ is, so it has its own glyph; its tooltip names the search.
    unknown: { glyph: "∅", tip: "info.provUnknown" },
  };

  // The UNKNOWN pill's tooltip body: when the search ran and every source it covered,
  // named from meta.sourceCorpora like any other source line.
  const unknownSearchTip = (stamp) => {
    if (!stamp) return "";
    const corpora = (data.meta && data.meta.sourceCorpora) || {};
    const names = (stamp.corpora || []).map((c) => `• ${(corpora[c] || {}).ref || c}`);
    return `${t("info.unknownSearched", { date: stamp.searched })}\n${names.join("\n")}`;
  };

  // The closing call to action of a provenance tooltip: opens the Sources &
  // provenance popup (the single place that explains what each grade means) and
  // dismisses its own tooltip first. Replaces the verbose per-grade paragraph that
  // used to be inlined into every pill (see makeProvenancePill).
  const makeDetailsCue = () => {
    const cue = btn("src-details-cue", t("info.provDetails"));
    cue.addEventListener("click", (e) => {
      e.stopPropagation();
      const tipEl = cue.closest(".help-tip");
      closeTip(tipEl);
      if (sourcingModal && sourcingModal.open) sourcingModal.open();
    });
    return cue;
  };

  // Tooltip = the grade in words, then `extra` (optional: the concrete source, i.e.
  // the verbatim quote + page ref, or a bibliographic citation), then a call-to-action
  // cue opening the Sources & provenance popup (the one place the grades are
  // explained). `base` (the full grade text) stays as the pill's aria-label.
  // (.help-tip is white-space:pre-line so the newlines show.)
  const makeProvenancePill = (level, extra) => {
    const spec = PROVENANCE_PILLS[level];
    const base = spec ? t(spec.tip) : t("info.provNone");
    const tip = document.createDocumentFragment();
    // The grade in words always leads, so even a pill with nothing else to show (a
    // bare ✕) says what it is; the closing cue then names what its click opens.
    tip.append(el("strong", "src-grade-name", t(`prov.name.${spec ? level : "none"}`)),
      document.createTextNode("\n\n"));
    if (extra instanceof Node) {
      tip.append(extra, document.createTextNode("\n\n"));
    } else if (extra) {
      tip.append(linkifiedText(`${extra}\n\n`));
    }
    tip.append(makeDetailsCue());
    const cls = spec ? `src-pill src-prov-${level}` : "src-pill src-todo";
    const pill = btn(cls, spec ? spec.glyph : NOSOURCE_GLYPH);
    pill.setAttribute("aria-label", base);
    return withTip(pill, tip);
  };

  // "How this quote got here: source page → an LLM finds the quote → ..." for one
  // source, or "" when the data names no pipeline (a bare reference with no quote).
  //
  // The steps come from `meta.quote_pipelines`, so adding a pipeline is a data edit plus
  // its translations and never a viewer edit, exactly like addon slots and uncertainty
  // reasons. The viewer only joins and localizes.
  const quoteChain = (pipeline) => {
    const steps = ((data.meta && data.meta.quotePipelines) || {})[pipeline];
    if (!Array.isArray(steps) || !steps.length) return "";
    return `${t("info.quoteChain")} ${steps.map((s) => t(`quotechain.${s}`)).join(" → ")}`;
  };

  // One tooltip line for a single source. Every source is quote-level
  // {corpus,page,quote,provenance} (the one shape used everywhere): it renders the
  // verbatim quote + "<ref>, p.N", resolving the ref from meta.sourceCorpora by
  // `corpus`. A corpus source with no page (e.g. a PDSP Ki reference) shows just the
  // ref line; a `quote` prefixes it.
  const sourceTipLine = (s) => {
    if (!s || !s.corpus) return "";
    const corpora = (data.meta && data.meta.sourceCorpora) || {};
    const c = corpora[s.corpus] || {};
    const label = c.ref || c.short || s.corpus;
    // `page` is a book page unless the corpus names what it holds instead (a PMID, a
    // DailyMed setid, a gene). The link is that exact page when the corpus can name it
    // (a stored per-page url such as a Wikipedia permalink or a paper's DOI, else the
    // `{page}` template), else the corpus's own landing page (a book's DOI or ISBN).
    const pageRef = c.page_kind ? `info.sourcePage.${c.page_kind}` : "info.sourceRef";
    const url = (s.page != null && (c.page_urls?.[s.page]
      || (c.page_url && c.page_url.replace("{page}", encodeURIComponent(s.page)))))
      || c.url;
    const pageUrl = url ? `\n${url}` : "";
    const ref = withFetched(s.page != null
      ? t(pageRef, { corpus: label, page: s.page })
      : label, s.fetched, t) + pageUrl;
    // Where in the book the passage sits, above the passage itself. The same
    // sentence reads very differently under "How the Drug Works" (a mechanism the
    // book attributes to this drug) than under "How Drug Causes Side Effects" (a
    // rule it prints without a subject), so the breadcrumb is what lets a reader
    // judge the quote rather than just confirm it exists.
    const trail = headingTrail(s.heading);
    const k = s.kiRow;
    const line = s.quote
      ? `${trail}“${s.quote}”\n— ${ref}`
      : k ? `${t("info.kiRow", {
        id: k.id, value: `${k.note === ">" || k.note === "<" ? k.note + " " : ""}${k.valueNm}`,
        species: k.species ? speciesLabel(k.species) : "?", radioligand: k.radioligand || "?",
        reference: k.reference || "?" })}\n— ${ref}`
        : `${trail}— ${ref}`;
    // An expression source (GtoPdb tissue distribution) names the assay species;
    // show it so a non-human claim is explicit on the pill itself, not only the tag.
    const withSpecies = s.species
      ? `${line}\n${t("info.sourceSpecies", { species: speciesLabel(s.species) })}`
      : line;
    // Last, under everything else: how this quote got here. Every green pill looks the
    // same, and it should, because the grade really is the same; but a sentence a model
    // read off a book page and a table cell a parser copied are different evidence, and
    // the reader is the one entitled to weigh that.
    // A blank line before it, so the trail reads apart from the quote block above.
    const chain = quoteChain(s.pipeline);
    return [withSpecies, licenceLine(s.licence), chain && `\n${chain}`,
      corpusCitations(s.corpus)]
      .filter(Boolean).join("\n");
  };

  // "Text licence: CC BY-NC" for a citation quoting an open-access text that asks for
  // credit (a Europe PMC full-text paper), else "". Shared by every source line and the
  // Ki reference, so any citation carrying a `licence` credits it the same way.
  const licenceLine = (licence) => (licence ? t("info.sourceLicence", { licence }) : "");

  // The citation a corpus asks for (meta.sourceCorpora[id].required_citations, e.g.
  // GtoPdb's database paper + licence), as a tooltip block, else "". Data-driven, so
  // honouring a new source's "how to cite us" is a generator edit only.
  const corpusCitations = (corpusId) => {
    const c = ((data.meta && data.meta.sourceCorpora) || {})[corpusId] || {};
    const cites = c.required_citations || [];
    return cites.length ? `${t("info.citeAs")}\n${cites.map((x) => `• ${x}`).join("\n")}` : "";
  };

  // "Clozapine › Side effects › How Drug Causes Side Effects\n" for a source that
  // knows where in its book it sits, else "". Stored as a plain outermost-first
  // list because the books do not share a heading shape (a Stahl monograph, a
  // Kandel part/chapter/section, a Nieuwenhuys chapter), so the viewer only joins.
  // The heading text itself stays in the book's language: it is part of the quote's
  // citation, not UI chrome, so only the separator comes from the catalogue.
  const headingTrail = (trail) =>
    Array.isArray(trail) && trail.length ? `${trail.join(" › ")}\n` : "";

  // Localized species name for an assay/expression source (Human/Rat/Mouse/Monkey,
  // as stored in the data); an unknown value passes through unchanged.
  // A species label: a corpus's own spelling ("Rat") or a tools/species.py key
  // ("guinea_pig", what an animal_evidence bullet carries), via `species.<key>`.
  const speciesLabel = (s) => {
    const key = `species.${String(s || "").toLowerCase().replace(/ /g, "_")}`;
    const label = t(key);
    return label === key ? (s || "") : label;
  };

  // A bullet's slot args as the sentence shows them: a species list is localized.
  const uncertaintyArgs = (args) => (args && Array.isArray(args.species)
    ? { ...args, species: args.species.map(speciesLabel).join(", ") } : args || {});

  // The tooltip tail under a per-claim provenance pill: every source (all
  // quote-level now) rendered as a line. Shared by the binding + NbN rows and the
  // pathway rows / connection panel, so a pathway's source shows on both endpoints'
  // panels.
  const sourcesTip = (sources) =>
    (sources || []).map(sourceTipLine).filter(Boolean).join("\n\n");

  // The corpus reference for a Ki source, rendered as the tooltip "extra": the corpus
  // label made a live link to the exact source (ki.reference pinned-revision permalink,
  // falling back to the corpus's generic URL) when a URL is available, else plain text
  // (the reference on its own line). Returned as a fragment so the link stays clickable.
  // Shared by kiChip's verified badge and the binding row's source pill, so a literature
  // Ki (e.g. a Wikipedia pharmacodynamics table) is reachable from both, not only the Ki
  // badge. `dash` prepends the leading source-line dash marker (the binding pill wants it;
  // kiChip does not, since it appends its own kiCited explainer after).
  const kiCorpusRefNode = (ki, { dash = false } = {}) => {
    const label = ki.corpusRef || "PDSP Ki Database";
    const refUrl = isWebUrl(ki.reference) ? ki.reference
      : (isWebUrl(ki.corpusUrl) ? ki.corpusUrl : "");
    const frag = document.createDocumentFragment();
    if (dash) frag.append("— ");
    if (refUrl) {
      frag.append(extLink(label, refUrl));
    } else {
      frag.append(label + (ki.reference ? "\n" + ki.reference : ""));
    }
    // The download date of the corpus the Ki was read from (PDSP's CSV, the
    // Wikipedia table), after the link so the link keeps its plain corpus label.
    if (ki.fetched) frag.append(withFetched("", ki.fetched, t));
    const licence = licenceLine(ki.licence);
    if (licence) frag.append("\n" + licence);
    const cites = corpusCitations(ki.corpus);
    if (cites) frag.append("\n" + cites);
    return frag;
  };

  // The provenance pill for a drug binding row (shared by the drug panel's "Acts
  // on" list and a target panel's "Interacting drugs" list, the same resolved
  // binding object). Its grade + tooltip come from whatever backs the binding: its
  // own quote-level Stahl source if present, else its measured PDSP Ki (which lifts
  // it to verified, mirroring _binding_grade), else nothing -> a NOSOURCE pill.
  // There is no drug-level citation fallback: an unsourced binding honestly shows
  // NOSOURCE rather than borrowing the book at large. When the backing is a Ki whose
  // corpus is URL-addressable (a literature Ki, e.g. the Wikipedia table), the label
  // is a clickable link, matching the Ki badge's tooltip below the row.
  // The generic "pill for a node, opening on whatever backs it": its quote-level
  // sources if any, else its measured Ki (the only other inspectable backing), else
  // nothing; reasons to doubt always lead. `node` is any object carrying
  // `{sources?, ki?, uncertainty?}`, which is the shape a binding already has and the
  // shape the Data browser's rows are built in, so both go through this one path and
  // a node badges identically wherever it is shown.
  // `what` (optional) names the claim the pill grades, as the tooltip's first line:
  // for a row carrying two pills (an enzyme row's role + its strength), so neither
  // reads as an unlabeled duplicate of the other.
  const sourceBackedPill = (grade, node, what) => {
    const labelled = (extra) => {
      if (!what) return extra;
      const frag = document.createDocumentFragment();
      frag.append(el("strong", null, what), document.createTextNode("\n\n"));
      if (extra instanceof Node) frag.append(extra);
      else if (extra) frag.append(document.createTextNode(extra));
      return frag;
    };
    const doubt = node && node.uncertainty && node.uncertainty.length
      ? node.uncertainty : null;
    // A doubted node reads orange whatever its own quote scored: `uncertain` is a
    // DISPLAY grade taken by any node carrying bullets (see quotes/uncertainty.py), so
    // it is decided here rather than at each call site, which cannot forget it. The
    // node keeps its own source in the tooltip, under the reasons to doubt it: same
    // evidence, honestly framed. A bare llm claim keeps its grey pill (shownGrade).
    if (grade === "unknown")
      return makeProvenancePill("unknown", labelled(unknownSearchTip(node && node.unknown)));
    const shown = shownGrade(grade, doubt);
    const sources = node && node.sources;
    if (sources && sources.length)
      return makeProvenancePill(shown, labelled(withUncertainty(doubt, sourcesTip(sources))));
    if (node && node.ki)
      return makeProvenancePill(shown,
        labelled(withUncertainty(doubt, kiCorpusRefNode(node.ki, { dash: true }))));
    return makeProvenancePill(shown, labelled(withUncertainty(doubt, null)));
  };

  // THE pill for a node-shaped claim `{provenance, sources, uncertainty?, ki?}`: every
  // row badging one goes through here, so a doubted node (a curated `contradicted`
  // holder, an animal-only region) reads orange wherever it is shown, never green
  // because one call site hand-rolled its pill. A flat facet (NbN, class, release)
  // passes a `{provenance, sources}` view of itself.
  const nodePill = (node, what) => sourceBackedPill((node && node.provenance) || null, node, what);

  // The binding's DIRECTION is its own node (kind `drug_binding_action`): "this drug
  // binds this target" and "it does so as an agonist" are two claims, and a measured Ki
  // only ever backs the first. Returns a pill ONLY when the direction is worse backed
  // than the binding beside it, so a row whose quote covers both stays a single pill and
  // the extra badge means something wherever it appears.
  const bindingActionPill = (binding) => {
    // The pill says what is missing about the DIRECTION, so its screen-reader label
    // replaces the generic grade text makeProvenancePill would otherwise announce.
    const pill = (level, why) => {
      const node = makeProvenancePill(level, why);
      const pillEl = node.matches && node.matches(".src-pill")
        ? node : node.querySelector(".src-pill");
      if (pillEl) pillEl.setAttribute("aria-label", why);
      return node;
    };
    if (binding.affinityOnly && binding.unknown)
      return pill("unknown", `${t("drug.actionUnknown")}\n\n${unknownSearchTip(binding.unknown)}`);
    if (binding.affinityOnly) return pill(null, t("drug.actionNoSource"));
    if (binding.actionProvenance === "llm"
        && (GRADE_RANK[binding.provenance] || 0) > GRADE_RANK.llm)
      return pill("llm", t("drug.actionLlm"));
    return null;
  };

  // The "why this is uncertain" block that leads a flagged binding's tooltip: a lead
  // line, then one row per reason. Each row carries its OWN badge, so the reader sees
  // at a glance which reasons rest on a source (green ✓, its quote right there) and
  // which are absences of evidence (red ✕, "the corpus never says this"). The badges
  // are inert spans, not real pills: nesting a .help-tip button inside a tooltip would
  // put a tooltip inside a tooltip. The sentences are i18n strings keyed by the reason
  // `kind`, so nothing here is stored prose (see quotes/uncertainty.py).
  // `shown` is the text of the pill's own source block printed under the reasons: a
  // reason resting on that very source (an animal-only Ki) would repeat it verbatim,
  // and only the copy below carries the live link, so the reason omits it.
  const uncertaintyTip = (list, shown = "") => {
    const box = el("div", "src-uncertain");
    box.appendChild(el("div", "src-uncertain-lead", t("info.uncertainLead")));
    const ul = el("ul", "src-uncertain-list");
    for (const u of list) {
      const li = el("li");
      const badge = el("span",
        u.absence ? "src-pill src-todo" : "src-pill src-prov-verified",
        u.absence ? NOSOURCE_GLYPH : "✓");
      badge.setAttribute("aria-hidden", "true");
      li.append(badge, el("span", "src-uncertain-text",
        t(`uncertain.${u.kind}`, uncertaintyArgs(u.args))));
      const src = (u.sources || []).map(sourceTipLine)
        .filter((line) => line && !shown.includes(line)).join("\n\n");
      if (src) li.appendChild(el("div", "src-uncertain-src", src));
      ul.appendChild(li);
    }
    box.appendChild(ul);
    return box;
  };

  // Prepend uncertaintyTip to whatever tooltip content a pill would otherwise get
  // (a string of source lines, a node, or nothing). Returns `extra` untouched when
  // the node is not flagged, so every non-flagged pill is byte-identical.
  // One "Found in" region's pill (a locationEntry): orange with its reasons first when
  // the region carries bullets (animal-only evidence), else its own grade.
  const locationPill = (meta) => {
    const doubt = meta.uncertainty && meta.uncertainty.length ? meta.uncertainty : null;
    const tip = meta.sources && meta.sources.length
      ? sourcesTip(meta.sources) : t("receptor.locUnsourced");
    return makeProvenancePill(shownGrade(meta.provenance, doubt), withUncertainty(doubt, tip));
  };

  const withUncertainty = (list, extra) => {
    if (!list) return extra;
    const frag = document.createDocumentFragment();
    frag.appendChild(uncertaintyTip(list,
      extra instanceof Node ? extra.textContent : extra || ""));
    if (extra instanceof Node) frag.append(extra);
    else if (extra) frag.append(document.createTextNode(extra));
    return frag;
  };

  return {
    bindingActionPill, corpusCitations, headingTrail, kiCorpusRefNode, licenceLine,
    locationPill, makeDetailsCue, makeProvenancePill, nodePill, PROVENANCE_PILLS,
    quoteChain, sourceBackedPill, sourcesTip, sourceTipLine, speciesLabel,
    uncertaintyArgs, uncertaintyTip, unknownSearchTip, withTip, withUncertainty,
  };
}
