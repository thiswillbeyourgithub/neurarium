// Reference material on a node panel: the baked description plus the live Wikipedia
// lead, the reference and lookup links (PDSP, UniProt, ClinPGx, GtoPdb, PharmFreq), and
// the image gallery.

import { clipLead, fetchWikiLead } from "../wiki.js";
import { isWebUrl } from "../web-url.js";
import { extLink, btn } from "./dom.js";

const { t } = window.__I18N__;

export function makeReference(P) {
  const {
    body, el, makeProvenancePill, onImagePick,
  } = P;

  // Shared by the structure / receptor / drug / target views: an external reference
  // link, rendered only for an http(s) url so a stray field can never inject markup.
  // A present link carries no provenance pill: the description just above it already
  // shows a "sourced" grade for the same Wikipedia source, so a second pill grading
  // the link only repeated it. A missing reference still renders the label + the
  // red NOSOURCE pill, so the gap stays visible like a source.
  const appendWiki = (url) => {
    const ok = isWebUrl(url);
    const wrap = el("div", "info-wiki");
    if (ok) {
      const a = extLink(t("info.wikipedia"), url);
      wrap.appendChild(a);
      // Stash the reference link so a successful live-lead fetch can relocate it
      // up into the description as that text's source marker (see
      // liveWikiDescription), in place of a grade pill: for a live verbatim read
      // the link both names the source and reaches it, so a checkmark beside a
      // link to the very same source is redundant.
      wrap._refLink = a;
    } else {
      wrap.appendChild(el("span", null, t("info.reference")));
      wrap.appendChild(makeProvenancePill(null)); // no reference -> NOSOURCE pill
    }
    body.appendChild(wrap);
    return wrap; // returned so it can anchor a live Wikipedia description below it
  };

  // Append an external "look this up" link (a search-by-name convenience that lands
  // on a results page, e.g. EMA / FDA / Drugs.com for a drug, PDSP for a receptor)
  // onto a reference row's wiki wrap, after a `·` separator. Not a source for any
  // specific claim, so it carries no provenance pill; only linked (navigated to),
  // never fetched, so the CSP is unaffected.
  const appendLookupLink = (wrap, labelKey, href, titleKey) => {
    wrap.appendChild(el("span", "ref-sep", "·"));
    const a = extLink(t(labelKey), href);
    a.title = t(titleKey);
    wrap.appendChild(a);
    return a;
  };

  // The PDSP Ki database has no URL-addressable per-target search, so every
  // receptor/target links to the same browse page (a "go look it up" convenience).
  const PDSP_KIDB_URL = "https://pdspdb.unc.edu/kidb2/kidb/web/kis-results/index";

  // PharmFreq is a Shiny app whose tools are in-page tabs, so it has no per-gene URL
  // either: the link is the same "go look it up" browse convenience as PDSP's, and it
  // is worth having because the Metabolizer status tool covers genes we do not model.
  const PHARMFREQ_URL = "https://pharmfreq.com/";

  // UniProt + Guide to Pharmacology (GtoPdb) name searches for a receptor: land on
  // each site's results page for the receptor's name. UniProt is filtered to human
  // (model_organism 9606). Convenience search links (navigated to, never fetched),
  // so no CSP change + no provenance pill.
  const uniprotSearchUrl = (name) =>
    `https://www.uniprot.org/uniprotkb?query=${encodeURIComponent(name)}&facets=model_organism%3A9606`;

  // ClinPGx (the former PharmGKB) name search: pharmacogenomics for a drug (which
  // gene variants change its response), for its pharmacokinetic pathways
  // (`type: "Pathway"`), and for a metabolizing enzyme. Same convenience-search
  // shape as the others (navigated to, never fetched).
  const clinpgxSearchUrl = (name, type = "") =>
    "https://www.clinpgx.org/search?query=" + encodeURIComponent(name)
    + (type ? "&type=" + encodeURIComponent(type) : "");

  const gtopdbSearchUrl = (name) =>
    "https://www.guidetopharmacology.org/GRAC/DatabaseSearchForward?searchString="
    + encodeURIComponent(name)
    + "&searchCategories=all&species=none&type=all&comments=includeComments&order=rank";

  // Live Wikipedia description, shared by every panel carrying a `wikipedia` link
  // (drug / receptor / structure / target). Best-effort: it fetches the current
  // lead for the viewer's locale (js/wiki.js, English fallback) and shows it as one
  // or more "sourced" info-desc paragraphs. `paragraph` is a baked description <p>
  // to swap
  // in place (drug/receptor); when there is none a fresh <p> is inserted relative to
  // `anchor` (the wiki link wrap) only once the live text arrives, so a structure /
  // target with no baked description gains one only on success. `before` puts that
  // fresh paragraph *above* the anchor (so the live description reads above the link
  // it backs, matching the baked-description panels); default is below. A failed /
  // blocked / absent fetch is a no-op, so the panel is unchanged offline. When the
  // live lead arrives it always rewrites the paragraph (text + green Wikipedia pill),
  // replacing any baked fallback: a live fetch is a programmatic verbatim read of the
  // article, so it grades higher than the baked snapshot it supersedes.
  const liveWikiDescription = (url, {
    paragraph = null, anchor = null, before = false, linkWrap = null,
  } = {}) => {
    if (!isWebUrl(url)) return;
    fetchWikiLead(url, window.__I18N__.lang).then((live) => {
      if (!live || !live.text) return;
      let p = paragraph;
      if (p) {
        if (!p.isConnected) return; // panel re-rendered to something else
      } else {
        if (!anchor || !anchor.isConnected) return; // panel gone / replaced
        p = el("p", "info-desc");
        anchor[before ? "before" : "after"](p);
      }
      // The live lead is the full intro (several newline-separated paragraphs).
      // Collapsed (the default) only the first paragraph shows, clipped to ~300
      // characters (clipLead); a "Read more" toggle expands the whole intro in
      // place and "Show less" folds it back. The source marker always trails
      // the last visible paragraph, so it all reads as one sourced block.
      const paras = live.text.split(/\n+/).map((s) => s.trim()).filter(Boolean);
      const full = paras.length ? paras : [live.text];
      const preview = clipLead(full[0]);
      // Provenance for a live verbatim read is the Wikipedia link itself, shown
      // here in place of a green ✓ pill: a checkmark beside a link to the very
      // same source added nothing (its tooltip only pointed back at the link),
      // whereas the link makes plain the text is *from* Wikipedia and clicks
      // through to it. Relocate the reference-row link up here (reusing the node,
      // so there is no duplicate) and style it as the green source pill, then
      // tidy the row it left: drop a now-leading "·" separator, and the whole row
      // if only the reference lived there (lookup links, if any, stay).
      const refLink = linkWrap && linkWrap._refLink;
      let marker;
      if (refLink && refLink.isConnected) {
        refLink.classList.add("src-pill", "src-prov-wikipedia", "wiki-src");
        marker = refLink;
        refLink.remove(); // detach first, so the row's new first child is inspected
        const lead = linkWrap.firstElementChild;
        if (lead && lead.classList.contains("ref-sep")) lead.remove();
        if (!linkWrap.querySelector("a")) linkWrap.remove();
      } else {
        marker = makeProvenancePill("wikipedia"); // fallback marker
      }
      const toggle = (full.length > 1 || preview !== full[0])
        ? el("button", "wiki-more") : null;
      let extras = [];
      const render = (expanded) => {
        for (const x of extras) x.remove();
        extras = [];
        p.textContent = expanded ? full[0] : preview; // detaches toggle + marker
        let last = p;
        if (expanded) {
          for (const text of full.slice(1)) {
            const extra = el("p", "info-desc", text);
            last.after(extra);
            extras.push(extra);
            last = extra;
          }
        }
        if (toggle) {
          toggle.textContent = t(expanded ? "wiki.readLess" : "wiki.readMore");
          toggle.setAttribute("aria-expanded", String(expanded));
          last.append(" ", toggle);
        }
        last.append(" ", marker);
      };
      if (toggle) {
        toggle.type = "button";
        toggle.addEventListener("click", () => {
          render(toggle.getAttribute("aria-expanded") !== "true");
        });
      }
      render(false);
    });
  };

  // The canonical "intro" block shared by EVERY node panel (structure / receptor
  // / target / drug): the baked description paragraph (when the node has one) with
  // its provenance pill, then the Wikipedia reference link *below* the text it
  // backs, then the live-lead refresh. Centralizing it guarantees the same
  // element order and the same sourcing treatment on every panel, instead of each
  // show*() re-composing the two and drifting (which is how the link came to sit
  // above the description on some panels and below it on the drug one). `description`
  // is the baked text (omit for a structure/target, which carry none); a present
  // wiki link with no baked description still gains the live lead *above* it.
  const appendReference = ({
    url, description = "", descriptionProvenance = "",
    descriptionExtra = "",
  } = {}) => {
    let paragraph = null;
    if (description) {
      paragraph = el("p", "info-desc", description);
      if (descriptionProvenance) {
        paragraph.appendChild(document.createTextNode(" "));
        paragraph.appendChild(
          makeProvenancePill(descriptionProvenance, descriptionExtra));
      }
      body.appendChild(paragraph);
    }
    // Link goes after the description so the reference sits below the text it backs.
    const wiki = appendWiki(url);
    liveWikiDescription(url, paragraph
      ? { paragraph, linkWrap: wiki }
      : { anchor: wiki, before: true, linkWrap: wiki });
    return { paragraph, wiki };
  };

  // Wikipedia illustration block (hero + lazy "show more" gallery), shared by the
  // structure and circuit panels: both hot-link a Wikimedia hero (resolved by
  // tools/fetch_structure_images.py) plus an optional gallery of further gif/svg.
  // Multi-MB, so hot-linked not vendored (CSP img-src allows upload.wikimedia.org),
  // with a spinner while loading and a silent figure-removal on failure. Colour art,
  // so never inverted. `altName` names the subject for the alt text; the gallery is
  // built lazily on first expand so the extra images never load unless asked. No-op
  // when there is no hero, so a panel can call it unconditionally.
  const appendWikiImages = (heroUrl, gallery, altName, tourSec = "") => {
    if (!heroUrl) return;
    const figure = (src) => {
      const fig = el("figure", "structure-image loading");
      fig.appendChild(el("div", "img-spinner"));
      const img = document.createElement("img");
      img.alt = t("structure.imageAlt", { name: altName });
      img.loading = "lazy";
      img.decoding = "async";
      img.title = t("image.zoomHint");
      img.dataset.optional = "1"; // self-handled failure: no global error banner
      img.addEventListener("load", () => fig.classList.remove("loading"));
      img.addEventListener("error", () => fig.remove());
      img.addEventListener("click", () =>
        onImagePick(img.currentSrc || img.src, img.alt, { invert: false }));
      img.src = src;
      fig.appendChild(img);
      return fig;
    };
    const hero = figure(heroUrl);
    if (tourSec) hero.dataset.tourSec = tourSec; // guided-tour section anchor
    body.appendChild(hero);
    const gal = gallery || [];
    if (!gal.length) return;
    const wrap = el("div", "structure-gallery");
    wrap.hidden = true;
    const toggle = btn("btn gallery-toggle");
    let built = false;
    const sync = () => {
      toggle.textContent = wrap.hidden
        ? t("structure.galleryShow", { n: gal.length })
        : t("structure.galleryHide");
    };
    toggle.addEventListener("click", () => {
      if (!built) {
        for (const url of gal) wrap.appendChild(figure(url));
        built = true;
      }
      wrap.hidden = !wrap.hidden;
      sync();
    });
    sync();
    body.appendChild(toggle);
    body.appendChild(wrap);
  };

  return {
    appendLookupLink, appendReference, appendWiki, appendWikiImages, clinpgxSearchUrl,
    gtopdbSearchUrl, liveWikiDescription, PDSP_KIDB_URL, PHARMFREQ_URL,
    uniprotSearchUrl,
  };
}
