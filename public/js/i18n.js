// Lightweight, no-build internationalization (en / fr).
//
// This is a CLASSIC script (like app-config.js / version.js), loaded early so
// every later script - the ES module viewer (js/main.js) AND the classic banner
// scripts (js/error-banner.js, js/dev-banner.js) - can read `window.__I18N__`.
//
// It owns ONE message catalogue (the single source of every UI string, in both
// languages) plus the language choice. The translatable *data* strings (region
// names, pathway labels, ...) are NOT here: they live in the data file as
// {en, fr} objects and are resolved by js/data.js using the language picked
// here (see `pick`). Because js/data.js resolves at load time, switching the
// language reloads the page (setLang) rather than re-rendering the scene live.
//
// Static markup in index.html carries `data-i18n` / `data-i18n-html` /
// `data-i18n-attr` hooks and is filled from this catalogue at DOMContentLoaded,
// so the English text is not duplicated between the HTML and here.
(function () {
  "use strict";

  var STORAGE_KEY = "neurarium:lang";
  var SUPPORTED = ["en", "fr"];

  // Pick the language: a ?lang= query param wins (and is persisted, so a deep
  // link sets the default); otherwise a saved choice; otherwise the browser
  // locale (any fr* => French); otherwise English.
  function detectLang() {
    try {
      var q = new URLSearchParams(window.location.search).get("lang");
      if (q && SUPPORTED.indexOf(q.toLowerCase()) !== -1) {
        q = q.toLowerCase();
        // Persist like clicking the switch, so the choice sticks on later visits.
        try { localStorage.setItem(STORAGE_KEY, q); } catch (e2) { /* ignore */ }
        return q;
      }
    } catch (e) { /* no URLSearchParams / weird env: fall through */ }
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (SUPPORTED.indexOf(saved) !== -1) return saved;
    } catch (e) { /* private mode / disabled storage: fall through */ }
    var locales = (navigator.languages && navigator.languages.length)
      ? navigator.languages
      : [navigator.language || navigator.userLanguage || "en"];
    for (var i = 0; i < locales.length; i++) {
      if (/^fr\b/i.test(String(locales[i]))) return "fr";
    }
    return "en";
  }

  var MESSAGES = {
    en: {
      "lang.en": "EN",
      "lang.fr": "FR",
      "lang.switchTo": "Switch language",

      "panel.controls": "Controls",
      "panel.separate": "Separate",
      "panel.transparency": "Transparency",
      "panel.autorotate": "Auto-rotate",
      "panel.seeInside": "See inside",
      "panel.animations": "Animations",
      "panel.speed": "Animation speed",
      "panel.arrowColors": "Arrow colours",
      "panel.colorNt": "Neurotransmitter",
      "panel.colorPotential": "Potential",
      "panel.structures": "Brain structures",
      "panel.projections": "Projections & Circuits",
      "panel.legend": "Legend",
      "panel.receptors": "Receptors & targets",
      "panel.about": "About",
      "panel.tabSettings": "Settings",
      "panel.tabDetails": "Details",
      "panel.closeTab": "Close tab",

      "toolbar.reset": "Reset view",
      "toolbar.search": "Search",
      "toolbar.searchAria": "Search structures, connections, receptors and drugs",
      "search.placeholder": "Search structure, connection, receptor/target or drug...",
      "search.noMatch": "No match",
      "search.tagCircuit": "circuit",
      "search.tagPathways": "pathways",
      "search.filterAll": "All",
      "search.clear": "Clear search",
      "search.syntaxLabel": "Search syntax",
      "search.syntax": "Type to search by name. Filters: <code>class:&quot;SSRI&quot;</code> drugs of a class, <code>nbn:&quot;…&quot;</code> by nomenclature. Tip: click a drug's <b>Class</b> or <b>Nomenclature</b> to fill one in.",

      "shortcuts.title": "Keyboard shortcuts",
      "shortcuts.names": "Toggle all names",
      "shortcuts.spread": "Spread / collapse",
      "shortcuts.structures": "Toggle the brain structures",
      "shortcuts.projections": "Toggle the projections",
      "shortcuts.legend": "Toggle the legend key",
      "shortcuts.seeInside": "Toggle see inside",
      "shortcuts.receptors": "Toggle Receptors & targets",
      "shortcuts.drugs": "Toggle the Drugs section",
      "shortcuts.search": "Open search",
      "shortcuts.tabs": "Switch between tabs",
      "shortcuts.close": "Close search / collapse sections",

      "tour.start": "Take a tour",
      "tour.next": "Next",
      "tour.back": "Back",
      "tour.done": "Done",
      "tour.skip": "Skip",
      "tour.step": "{n} of {total}",
      "tour.aria": "Guided tour",
      "tour.welcome.title": "Welcome to neurarium",
      "tour.welcome.body":
        "A 3D map of the brain: its regions, the pathways between them, and the receptors and drugs that act on them. This quick tour shows the main features. You can leave any time.",
      "tour.rotate.title": "Move around",
      "tour.rotate.body":
        "<b>Drag</b> the brain to rotate it (scroll or pinch to zoom, two fingers or right-click to pan). Every shape is a real brain structure. Give it a spin to continue.",
      "tour.separate.title": "Pull it apart",
      "tour.separate.body":
        "The <b>Separate</b> slider blows the brain open, exposing the deep nuclei otherwise buried under the cortex. Watch it sweep out and back, then grab the slider yourself to continue.",
      "tour.sourcesOpen.title": "Every fact is sourced",
      "tour.sourcesOpen.body":
        "This dataset is LLM-assisted, so each fact carries a provenance grade. Click the highlighted <b>Sources &amp; provenance</b> button to open the breakdown.",
      "tour.sourcesDetail.title": "The provenance breakdown",
      "tour.sourcesDetail.body":
        "This popup tallies how much of the data is verified against a quoted source, merely sourced, or still unchecked. Close it (the highlighted &times;) to continue.",
      "tour.browse.title": "Browse the data",
      "tour.browse.body":
        "Everything lives in four lists: <b>Drugs</b> ({drugs}+), <b>Receptors &amp; targets</b> ({receptors}+), <b>Structures</b> ({structures}+) and <b>Projections &amp; Circuits</b> ({projections}+). Open any one and click a row to focus it. Let's try a few.",
      "tour.openDrugs.title": "Open a list",
      "tour.openDrugs.body":
        "Let's start with a drug. Click the highlighted <b>Drugs</b> to open the list.",
      "tour.drugTap.title": "Focus a drug",
      "tour.drugTap.body":
        "Click the highlighted <b>Olanzapine</b> row. The brain dims and its effects animate: coloured dots on the regions it reaches, and flow along the systems whose tone it shifts.",
      "tour.drugActs.title": "What it acts on",
      "tour.drugActs.body":
        "Its <b>bindings</b>: every receptor and target it touches, the effect, and the measured affinity (Ki) where known, which is what drives the animation. <b>One caveat:</b> the drug animations are by far the least scientific part of neurarium and are still being worked out, so treat them as an evolving illustration, not settled fact.",
      "tour.drugToReceptor.title": "Follow it to a receptor",
      "tour.drugToReceptor.body":
        "Each binding is a link. Click the highlighted <b>H1</b> row to open that receptor's own panel.",
      "tour.receptorFacts.title": "How it's classified",
      "tour.receptorFacts.body":
        "Its <b>classification</b>: neurotransmitter family, mechanism, whether it excites or inhibits, and where on the synapse it sits. Each fact carries its own provenance grade.",
      "tour.receptorRegions.title": "Where it's found",
      "tour.receptorRegions.body":
        "The <b>regions</b> where this receptor is expressed, each with its own source. Click any region to jump to it.",
      "tour.closePanel.title": "Close the panel",
      "tour.closePanel.body":
        "Done reading? Click the highlighted <b>&times;</b> to close this panel and go back to the lists.",
      "tour.openStructures.title": "Open a structure",
      "tour.openStructures.body":
        "Now a different kind of node. Click the highlighted <b>Structures</b> to open the list.",
      "tour.structureTap.title": "Isolate a region",
      "tour.structureTap.body":
        "Click the highlighted <b>Hippocampus</b> row. It is isolated from the rest of the brain so you can see it on its own.",
      "tour.structureLook.title": "Read about it",
      "tour.structureLook.body":
        "Each panel opens with an illustration and a live description pulled from Wikipedia. <b>Scroll the panel</b> down to continue.",
      "tour.openProjections.title": "Open the projections",
      "tour.openProjections.body":
        "One last kind of node: the pathways between regions. Click the highlighted <b>Projections</b>.",
      "tour.projectionTap.title": "A whole system",
      "tour.projectionTap.body":
        "Click the highlighted <b>Dopamine</b> system. It pins every dopaminergic pathway at once, from the midbrain out across the brain.",
      "tour.projectionLook.title": "Read about it",
      "tour.projectionLook.body":
        "Its <b>member pathways</b> and a description. <b>Scroll the panel</b> down to continue.",
      "tour.backToSettings.title": "Back to the panel",
      "tour.backToSettings.body":
        "One last feature. Click <b>Settings</b> to leave this panel and return to the main panel.",
      "tour.openSearch.title": "Open search",
      "tour.openSearch.body":
        "Click the highlighted <b>magnifier</b> to open the search box.",
      "tour.search.title": "Find anything",
      "tour.search.body":
        "<b>Search</b> jumps straight to any region, pathway, receptor or drug by name (try typing here). You can also filter drugs by class or nomenclature.",
      "tour.wrap.title": "You're set",
      "tour.wrap.body":
        "That's the tour. Settings, the EN/FR switch and this tour all live in the panel; you can replay the tour any time from <b>About</b>. Enjoy exploring.",

      "legend.showNames": "Show all names",
      "legend.showProjections": "Show projections",
      "legend.projections": "Projections",
      "legend.circuits": "Circuits",
      "legend.hypothetical": "Hypothetical pathways",
      "legend.hypotheticalHint":
        "Less-certain connections, drawn as dotted arrows. Off by default.",
      "legend.showSpeculative": "Show speculative",
      "legend.hideSpeculative": "Hide speculative",

      "legendKey.dots": "Expression dots",
      "legendKey.dotsDesc": "Focusing a receptor or target scatters glowing dots over every region it sits in, coloured by its action:",
      "legendKey.effects": "Drug effects",
      "legendKey.effectsDesc": "Focusing a drug pulses dots and a wash of light over each region it acts on, coloured by the effect:",
      "legendKey.flow": "Flowing beads (drug focus)",
      "legendKey.flowDesc": "A drug focus also sends beads travelling along the ascending pathways of the neurotransmitter system(s) whose *tone* it sets, so you see which broadcast “highways” it drives. Only tone-setting bindings flow: reuptake blockers, enzyme inhibitors, vesicle blockers and presynaptic autoreceptors; a purely postsynaptic receptor stays as dots only. The beads run bright/fast/dense when the drug raises that system's tone and dim/slow/sparse when it lowers it (an SSRI drives the serotonergic fan up, buspirone's 5-HT1A agonism damps it, a VMAT2 blocker depletes it), and their intensity follows the drug's measured affinity. The system is read from the drug's targets, not from which regions light up. Only these diffuse ascending systems with a modelled source nucleus flow:",
      "legendKey.pathways": "Pathways",
      "legendKey.speculative": "Speculative pathway (dotted)",

      "info.connection": "Connection",
      "info.projectionType": "Projection",
      "info.dirOut": "Outgoing projection",
      "info.dirIn": "Incoming projection",
      "info.dirBoth": "Reciprocal projection (both directions)",
      "info.arrowColour": "The colour marks the pathway type: {label}.",
      "info.wikipedia": "Wikipedia ↗",
      "info.vidal": "Vidal ↗",
      "info.vidalTitle": "Look this substance up on Vidal (French drug database)",
      "info.drugscom": "Drugs.com ↗",
      "info.drugscomTitle": "Look this drug up on Drugs.com",
      "info.ema": "EMA ↗",
      "info.emaTitle": "Search the European Medicines Agency",
      "info.fda": "FDA ↗",
      "info.fdaTitle": "Search the US FDA drug database (Drugs@FDA)",
      "info.pdsp": "PDSP Ki ↗",
      "info.pdspTitle": "Browse the PDSP Ki binding-affinity database (NIMH)",
      "info.uniprot": "UniProt ↗",
      "info.uniprotTitle": "Search UniProt for this receptor (human only)",
      "info.gtopdb": "GtoPdb ↗",
      "info.gtopdbTitle": "Search the Guide to Pharmacology for this receptor",
      "info.reference": "Reference",
      "info.provDetails": "Click for details",
      "info.provNone": "No source for this node yet.",
      "info.provLlm": "Source grade: LLM-only. Produced by an LLM from memory and not checked against any document, so it may be a hallucination.",
      "info.provSourced": "Source grade: sourced. Written by an LLM that was given the source document (e.g. Stahl's guide), but this specific node was not quote-verified.",
      "info.provVerified": "Source grade: verified. An LLM extracted a quote, it was programmatically confirmed to appear in the source, and a separate LLM agreed the quote supports this node. This is still the highest grade available here and remains LLM-driven, so it can still be wrong: going further would take considerable human effort and is itself error-prone, so it is out of scope for this project.",
      "info.provWikipedia": "Loaded directly from Wikipedia. This text is fetched live and verbatim from the current Wikipedia article (CC BY-SA), with no LLM in the loop, so it cannot drift from the article. See the Reference link above to inspect the source.",
      "info.descFromWikipedia": "This description is the lead section of the drug's Wikipedia article, used verbatim under CC BY-SA. See the Reference link above.",
      "info.sourceRef": "{corpus}, p. {page}",
      "info.sourceSpecies": "Assay species: {species}",
      "info.noConnections": "No mapped connections yet.",
      "info.connections": "Connections",

      "circuit.heading": "Functional circuit",
      "circuit.structures": "Structures in this loop",
      "circuit.pathways": "Pathways in this loop",
      "group.kindHeading": "Pathways by neurotransmitter",
      "group.signHeading": "Pathways by effect",
      "group.pathways": "Pathways",
      "group.actingDrugs": "Drugs acting on this system",

      "receptor.system": "System",
      "receptor.neurotransmitter": "Neurotransmitter",
      "receptor.type": "Type",
      "receptor.effect": "Effect",
      "receptor.synaptic": "Synaptic site",
      "receptor.foundIn": "Found in",
      "receptor.foundOther": "Other regions",
      "receptor.ubiquitous": "Throughout the brain",
      "receptor.noRole": "No significant role in the central nervous system.",
      "receptor.locUnsourced": "Which regions this is found in is LLM-authored (general knowledge), not yet checked against an expression atlas.",
      "receptor.speciesTag": "· {species}",
      "receptor.speciesTip": "Expression checked in {species}, not human.",
      "receptor.stubHint": "No significant role in the central nervous system",
      "species.human": "human",
      "species.rat": "rat",
      "species.mouse": "mouse",
      "species.monkey": "monkey",
      "targets.otherSystem": "Other / non-aminergic",
      "targets.interactingDrugs": "Interacting drugs",
      "targets.bySubtype": "By receptor subtype",
      "target.polarity": "Tone polarity",
      "target.polarityVesicular": "Vesicular transporter (blocking depletes stores, lowers tone)",
      "target.polarityAutoreceptor": "Presynaptic inhibitory autoreceptor (blocking raises tone)",

      "panel.drugs": "Drugs",
      "drugs.filter": "Filter drugs…",
      "drugs.none": "No matching drug.",
      "drug.class": "Class",
      "drug.nomenclature": "Nomenclature",
      "drug.nbnNonstandard": "· drug class, no formal NbN",
      "drug.brands": "Brands",
      "drug.actsOn": "Acts on",
      "drug.noTargets": "No mapped molecular targets yet.",
      "drug.projectionsAffected": "Projections affected",
      "drug.projectionsAffectedHint": "Ascending pathways whose tone this drug sets. Derived from its tone-setting bindings (reuptake, enzyme, vesicle or autoreceptor); an out-arrow raises the system's tone, an in-arrow lowers it.",
      "drug.actsWithin": "Acts within",
      "drug.actsWithinHint": "Systems this drug engages only through a postsynaptic receptor. Their pathways are lit for context (no beads): blocking a postsynaptic receptor does not itself raise or lower the transmitter's tone.",
      "drug.stubHint": "No binding profile recorded yet",
      "drug.speculative": "speculative",
      "drug.affinityOnly": "affinity only, direction not established",
      "drug.kiCounts": "{h} human, {n} non-human",
      "drug.kiTip": "Measured binding affinity (Ki), lower = tighter. Median over {h} human + {n} non-human assays; the badge cites one representative assay: {assay}",
      "drug.kiTipNonHuman": "No human assay: this Ki is from non-human tissue ({species}).",
      "drug.kiInactive": "{n} inactive",
      "drug.kiInactiveTip": "Plus {n} assay(s) at the ≥10 µM ceiling (tested, essentially no binding); excluded from the median above.",
      "drug.kiMapped": "measured as {compound}",
      "drug.kiMappedTip": "This binding's Ki was measured on {compound} ({relation}), which PDSP lists this drug under.",
      "drug.kiCited": "literature value",
      "drug.kiCitedTip": "Affinity value quoted from the cited source's binding table (a literature value, not a raw measured assay). The link pins the exact source revision.",
      "drug.rel.identity": "same molecule",
      "drug.rel.enantiomer": "enantiomer",
      "drug.rel.racemate": "racemate",
      "drug.rel.prodrug": "active form",
      "drug.rel.metabolite": "metabolite",
      "drug.combo": "Combination drug",
      "drug.comboNote": "Binding data is shown per constituent below; interactions between them may exist. Open a constituent for its full profile:",
      "drug.structureAlt": "Chemical structure of {name}",
      "structure.imageAlt": "Illustration of the {name}",
      "structure.galleryShow": "Show {n} more image(s)",
      "structure.galleryHide": "Show fewer images",
      "image.close": "Close",
      "image.zoomHint": "Click to enlarge",

      "status.loadError":
        "Could not load brain data: {msg}. Are you serving over HTTP? (see CLAUDE.md)",

      "loading.start": "Loading…",
      "loading.data": "Loading data…",
      "loading.shapes": "Loading shapes…",
      "loading.meshing": "Building {name}…",
      "loading.building": "Assembling the brain…",
      "loading.tagline": "a (mostly) sourced atlas of psychiatric neuroscience",
      "loading.cta":
        'Have an idea for a feature? I\'d happily build it, ' +
        '<a href="https://olicorne.org/en/contact" target="_blank" ' +
        'rel="noopener noreferrer">get in touch</a>.',
      "loading.enter": "Start exploring",
      "common.byline":
        'by <a href="https://olicorne.org/en" target="_blank" ' +
        'rel="noopener noreferrer">Olivier Cornelis</a>',

      "about.p1":
        "neurarium is a work-in-progress, interactive 3D map of the brain. It " +
        "shows brain regions and the neuron projections between them, named " +
        "functional circuits you can watch a pulse travel around, the " +
        "neurotransmitter receptors each region expresses, and psychiatric " +
        "drugs animated to show what each one does to the brain. Everything is " +
        "searchable and clickable, and every fact carries a source grade (see " +
        "Sources & provenance below). The shapes are schematic, meant to help " +
        "you find and relate structures rather than to be anatomically exact, " +
        "and the receptor and drug data are machine-generated and unreviewed, " +
        "so treat all of it as illustrative, not as medical advice.",
      "about.p2":
        'Made by <a href="https://olicorne.org/" target="_blank" ' +
        'rel="noopener noreferrer">Olivier Cornelis</a> (developer and ' +
        'psychiatrist) and <a href="https://claude.com/claude-code" ' +
        'target="_blank" rel="noopener noreferrer">Claude</a>.',
      "about.p3":
        "Under the hood it is a plain static site: vanilla JavaScript modules " +
        'and <a href="https://threejs.org/" target="_blank" ' +
        'rel="noopener noreferrer">three.js</a> (vendored, no build step), the ' +
        "anatomy stored as generated data files, served by Caddy.",
      "about.animationModel":
        "About the drug animation: it is a <em>tone-setter</em> model, not a literal " +
        "picture of drug molecules. A drug's binding data drives it: postsynaptic " +
        "receptors it hits show as coloured gem dots over the regions that express them " +
        "(boost / block / modulate), while its <em>tone-setting</em> bindings (reuptake " +
        "blockers, enzyme inhibitors, vesicle blockers, presynaptic autoreceptors) send " +
        "beads streaming along the ascending pathways of the neurotransmitter systems " +
        "they raise or lower. Density and speed are normalized per drug, so what you read " +
        "is the <em>relative</em> activity across systems, not an absolute dose. " +
        "<strong>The drug animations are by far the least scientific part of neurarium " +
        "and are still very much being worked out</strong>: treat them as an " +
        "evolving illustration, not settled fact.",
      "about.dataSummary": "The data is yours to reuse",
      "about.dataIntro":
        "The whole dataset is plain JSONL / JSON, kept separate from the rendering and " +
        "free to reuse. Each file below is served directly from this site (one JSON " +
        "object per line, self-describing, every row graded and sourced):",
      "about.dataRepo": "Or browse it in the source repository →",
      "about.outreach":
        "I think this kind of interactive viewer could be genuinely useful to the field, " +
        "and I would happily build similar animations for other medical topics. If you " +
        "have an idea for one, or feedback on this one, please get in touch (the issue " +
        "tracker below is the easiest channel) and tell me what would help you.",
      "about.issues":
        "Found a bug, an inaccuracy, or have a feature request? Please " +
        '<a id="about-issues" target="_blank" rel="noopener noreferrer">open an ' +
        "issue</a>.",
      "about.sourceCode": "Source code",
      "about.license":
        'Licensed under the <a href="https://www.gnu.org/licenses/agpl-3.0.html" ' +
        'target="_blank" rel="noopener noreferrer">GNU AGPL-3.0</a>.',
      "about.attribution":
        "Drug descriptions and molecular-structure images come from Wikipedia, " +
        'used under <a href="https://creativecommons.org/licenses/by-sa/4.0/" ' +
        'target="_blank" rel="noopener noreferrer">CC BY-SA</a>; each drug panel ' +
        "links to its source article.",
      "about.sourcingTitle": "Sources & provenance",
      "sourcing.openLink": "Sources & provenance →",
      "about.sourcingIntro":
        "Every node in this dataset (any sourceable datum: a region, a pathway, a " +
        "receptor, a drug binding, ...) carries a source grade. None of it has been " +
        "checked by a human yet, so even a verified node can be wrong. The grades:",
      "about.sourcingCaveat":
        "Being sourced does not make a claim true. A source can itself be wrong, the AI " +
        "may have attached a correct quote to the wrong claim, and the viewer code has " +
        "occasional bugs of its own. Please stay critical: if something looks off, it may " +
        "well be an error. Corrections are very welcome via the issue link below.",
      "about.gradeVerified":
        "Verified: the supporting quote was confirmed present in the cited source.",
      "about.gradeSourced":
        "Sourced: drawn from a document (e.g. Wikipedia), but the quote was not checked.",
      "about.gradeLlm":
        "AI only: may be a hallucination.",
      "about.gradeNone": "No source: none gathered yet.",
      "about.gradeWikipedia":
        "Wikipedia link: shown instead of a grade on a live description. The text is " +
        "the article's current lead, read live and verbatim (no AI); the link is the " +
        "source, click it to open the article.",
      "about.segVerified": "Verified",
      "about.segSourced": "Sourced",
      "about.segLlm": "AI only",
      "about.segNone": "No source",
      "about.coverageTitle": "Coverage",
      "about.sourcingHeadline":
        "{pct}% of the {total} knowledge nodes here are sourced or verified.",
      "about.kiCoverage":
        "Measured binding affinity (PDSP Ki): {pct}% of {total} drug bindings carry one; {drugsNone} of {drugs} drugs have none (quote-sourced or unsourced).",
      "about.kindBindings": "Drug target bindings",
      "about.kindNbn": "Drug nomenclature (NbN)",
      "about.kindDrugBrands": "Drug brand names",
      "about.kindDrugCategories": "Drug class",
      "about.kindProjections": "Neuron pathways",
      "about.kindCircuits": "Functional circuits",
      "about.kindProjectionGroups": "Projection groups",
      "about.kindReceptors": "Receptor system/family",
      "about.kindReceptorClass": "Receptor mechanism class",
      "about.kindReceptorSign": "Receptor sign (excitatory/inhibitory)",
      "about.kindReceptorSynaptic": "Receptor pre/postsynaptic site",
      "about.kindReceptorLocations": "Receptor expression regions",
      "about.kindTargets": "Target classifications",
      "about.kindTargetPolarity": "Target tone polarity",
      "about.kindTargetLocations": "Target expression regions",
      "about.kindStructures": "Brain-region anatomy",

      "dev.wip": "Work in progress",
      "dev.restarted":
        "This container was last restarted {ago}, so it is actively being developed. ",
      "dev.activelyDeveloped": "This site is actively being developed. ",
      "dev.stayTuned": "If anything looks broken, come back later.",
      "dev.source": "Source",
      "dev.clickHide": "Click to hide (shows again on reload)",
      "time.lessThanMinute": "less than a minute ago",
      "time.minutes": "{n} minute{s} ago",
      "time.hours": "{n} hour{s} ago",
      "time.days": "{n} day{s} ago",

      "error.dismiss": "Dismiss",
      "error.prefix": "Error: {msg}",
      "error.unhandled": "Unhandled error: {msg}",
      "error.failedLoad": "Failed to load {what}",
    },
    fr: {
      "lang.en": "EN",
      "lang.fr": "FR",
      "lang.switchTo": "Changer de langue",

      "panel.controls": "Contrôles",
      "panel.separate": "Séparer",
      "panel.transparency": "Transparence",
      "panel.autorotate": "Rotation auto",
      "panel.seeInside": "Voir l'intérieur",
      "panel.animations": "Animations",
      "panel.speed": "Vitesse d'animation",
      "panel.arrowColors": "Couleur des flèches",
      "panel.colorNt": "Neurotransmetteur",
      "panel.colorPotential": "Potentiel",
      "panel.structures": "Structures cérébrales",
      "panel.projections": "Projections et circuits",
      "panel.legend": "Légende",
      "panel.receptors": "Récepteurs et cibles",
      "panel.about": "À propos",
      "panel.tabSettings": "Réglages",
      "panel.tabDetails": "Détails",
      "panel.closeTab": "Fermer l’onglet",

      "toolbar.reset": "Recentrer la vue",
      "toolbar.search": "Rechercher",
      "toolbar.searchAria": "Rechercher structures, connexions, récepteurs et médicaments",
      "search.placeholder": "Rechercher une structure, une connexion, un récepteur/cible ou un médicament…",
      "search.noMatch": "Aucun résultat",
      "search.tagCircuit": "circuit",
      "search.tagPathways": "voies",
      "search.filterAll": "Tous",
      "search.clear": "Effacer la recherche",
      "search.syntaxLabel": "Syntaxe de recherche",
      "search.syntax": "Tapez pour rechercher par nom. Filtres : <code>classe:&quot;IRSN&quot;</code> les médicaments d'une classe, <code>nbn:&quot;…&quot;</code> par nomenclature. Astuce : cliquez la <b>Classe</b> ou la <b>Nomenclature</b> d'un médicament pour en remplir un.",

      "shortcuts.title": "Raccourcis clavier",
      "shortcuts.names": "Afficher / masquer les noms",
      "shortcuts.spread": "Séparer / rassembler",
      "shortcuts.structures": "Afficher / masquer les structures cérébrales",
      "shortcuts.projections": "Afficher / masquer les projections",
      "shortcuts.legend": "Afficher / masquer la légende",
      "shortcuts.seeInside": "Voir l'intérieur",
      "shortcuts.receptors": "Ouvrir Récepteurs et cibles",
      "shortcuts.drugs": "Ouvrir la section Médicaments",
      "shortcuts.search": "Ouvrir la recherche",
      "shortcuts.tabs": "Naviguer entre les onglets",
      "shortcuts.close": "Fermer la recherche / replier les sections",

      "tour.start": "Visite guidée",
      "tour.next": "Suivant",
      "tour.back": "Précédent",
      "tour.done": "Terminer",
      "tour.skip": "Passer",
      "tour.step": "{n} sur {total}",
      "tour.aria": "Visite guidée",
      "tour.welcome.title": "Bienvenue sur neurarium",
      "tour.welcome.body":
        "Une carte 3D du cerveau : ses régions, les voies qui les relient, et les récepteurs et médicaments qui agissent dessus. Cette courte visite présente les principales fonctionnalités. Vous pouvez la quitter à tout moment.",
      "tour.rotate.title": "Se déplacer",
      "tour.rotate.body":
        "<b>Faites glisser</b> le cerveau pour le tourner (défilez ou pincez pour zoomer, deux doigts ou clic droit pour vous déplacer). Chaque forme est une structure cérébrale réelle. Faites-le tourner pour continuer.",
      "tour.separate.title": "Écarter les régions",
      "tour.separate.body":
        "Le curseur <b>Séparer</b> ouvre le cerveau vers l'extérieur, révélant les noyaux profonds autrement enfouis sous le cortex. Regardez-le balayer puis revenir, puis saisissez le curseur vous-même pour continuer.",
      "tour.sourcesOpen.title": "Chaque fait est sourcé",
      "tour.sourcesOpen.body":
        "Ce jeu de données est assisté par IA : chaque fait porte donc une note de provenance. Cliquez sur le bouton <b>Sources et provenance</b> (en surbrillance) pour ouvrir le récapitulatif.",
      "tour.sourcesDetail.title": "Le récapitulatif de provenance",
      "tour.sourcesDetail.body":
        "Cette fenêtre chiffre la part des données vérifiée face à une citation, simplement sourcée, ou encore non contrôlée. Fermez-la (le &times; en surbrillance) pour continuer.",
      "tour.browse.title": "Parcourir les données",
      "tour.browse.body":
        "Tout se trouve dans quatre listes : <b>Médicaments</b> ({drugs}+), <b>Récepteurs et cibles</b> ({receptors}+), <b>Structures</b> ({structures}+) et <b>Projections et circuits</b> ({projections}+). Ouvrez-en une et cliquez sur une ligne pour la mettre en avant. Essayons-en quelques-unes.",
      "tour.openDrugs.title": "Ouvrir une liste",
      "tour.openDrugs.body":
        "Commençons par un médicament. Cliquez sur <b>Médicaments</b> (en surbrillance) pour ouvrir la liste.",
      "tour.drugTap.title": "Mettre un médicament en avant",
      "tour.drugTap.body":
        "Cliquez sur la ligne <b>olanzapine</b> en surbrillance. Le cerveau s'assombrit et ses effets s'animent : des points colorés sur les régions qu'il atteint, et un flux le long des systèmes dont il modifie le tonus.",
      "tour.drugActs.title": "Ce sur quoi il agit",
      "tour.drugActs.body":
        "Ses <b>liaisons</b> : tous les récepteurs et cibles qu'il touche, l'effet, et l'affinité mesurée (Ki) lorsqu'elle est connue, ce qui pilote l'animation. <b>Une réserve :</b> les animations de médicaments sont de loin l'aspect le moins scientifique de neurarium et sont encore en cours d'élaboration ; considérez-les comme une illustration qui évolue, pas un fait établi.",
      "tour.drugToReceptor.title": "Suivre vers un récepteur",
      "tour.drugToReceptor.body":
        "Chaque liaison est un lien. Cliquez sur la ligne <b>H1</b> en surbrillance pour ouvrir le panneau de ce récepteur.",
      "tour.receptorFacts.title": "Sa classification",
      "tour.receptorFacts.body":
        "Sa <b>classification</b> : famille de neurotransmetteur, mécanisme, s'il excite ou inhibe, et sa position sur la synapse. Chaque fait porte sa propre note de provenance.",
      "tour.receptorRegions.title": "Où on le trouve",
      "tour.receptorRegions.body":
        "Les <b>régions</b> où ce récepteur est exprimé, chacune avec sa source. Cliquez sur une région pour y accéder.",
      "tour.closePanel.title": "Fermer le panneau",
      "tour.closePanel.body":
        "Lecture terminée ? Cliquez sur le <b>&times;</b> en surbrillance pour fermer ce panneau et revenir aux listes.",
      "tour.openStructures.title": "Ouvrir une structure",
      "tour.openStructures.body":
        "Passons à un autre type de nœud. Cliquez sur <b>Structures</b> (en surbrillance) pour ouvrir la liste.",
      "tour.structureTap.title": "Isoler une région",
      "tour.structureTap.body":
        "Cliquez sur la ligne <b>hippocampe</b> en surbrillance. Elle est isolée du reste du cerveau pour que vous puissiez la voir seule.",
      "tour.structureLook.title": "En savoir plus",
      "tour.structureLook.body":
        "Chaque panneau s'ouvre sur une illustration et une description tirée en direct de Wikipédia. <b>Faites défiler le panneau</b> vers le bas pour continuer.",
      "tour.openProjections.title": "Ouvrir les projections",
      "tour.openProjections.body":
        "Un dernier type de nœud : les voies entre régions. Cliquez sur <b>Projections</b> en surbrillance.",
      "tour.projectionTap.title": "Un système entier",
      "tour.projectionTap.body":
        "Cliquez sur le système <b>dopamine</b> en surbrillance. Il épingle d'un coup toutes les voies dopaminergiques, du mésencéphale à travers le cerveau.",
      "tour.projectionLook.title": "En savoir plus",
      "tour.projectionLook.body":
        "Ses <b>voies membres</b> et une description. <b>Faites défiler le panneau</b> vers le bas pour continuer.",
      "tour.backToSettings.title": "Retour au panneau",
      "tour.backToSettings.body":
        "Une dernière fonctionnalité. Cliquez sur <b>Réglages</b> pour quitter ce panneau et revenir au panneau principal.",
      "tour.openSearch.title": "Ouvrir la recherche",
      "tour.openSearch.body":
        "Cliquez sur la <b>loupe</b> en surbrillance pour ouvrir le champ de recherche.",
      "tour.search.title": "Tout retrouver",
      "tour.search.body":
        "La <b>recherche</b> mène directement à n'importe quelle région, voie, récepteur ou médicament par son nom (essayez d'en taper un ici). Vous pouvez aussi filtrer les médicaments par classe ou nomenclature.",
      "tour.wrap.title": "Vous êtes prêt",
      "tour.wrap.body":
        "Voilà pour la visite. Les réglages, le sélecteur EN/FR et cette visite se trouvent dans le panneau ; vous pouvez relancer la visite à tout moment depuis <b>À propos</b>. Bonne exploration.",

      "legend.showNames": "Afficher tous les noms",
      "legend.showProjections": "Afficher les projections",
      "legend.projections": "Projections",
      "legend.circuits": "Circuits",
      "legend.hypothetical": "Voies hypothétiques",
      "legend.hypotheticalHint":
        "Connexions moins certaines, tracées en pointillés. Masquées par défaut.",
      "legend.showSpeculative": "Afficher les spéculatives",
      "legend.hideSpeculative": "Masquer les spéculatives",

      "legendKey.dots": "Points d'expression",
      "legendKey.dotsDesc": "Sélectionner un récepteur ou une cible disperse des points lumineux sur chaque région où il se trouve, colorés selon son action :",
      "legendKey.effects": "Effets des médicaments",
      "legendKey.effectsDesc": "Sélectionner un médicament fait pulser des points et une onde de lumière sur chaque région où il agit, colorés selon l'effet :",
      "legendKey.flow": "Billes en mouvement (médicament)",
      "legendKey.flowDesc": "Sélectionner un médicament envoie aussi des billes le long des voies ascendantes du ou des systèmes de neurotransmetteurs dont il règle le *tonus*, pour montrer quelles « autoroutes » de diffusion il pilote. Seules les liaisons qui règlent le tonus circulent : inhibiteurs de recapture, inhibiteurs d'enzyme, bloqueurs vésiculaires et autorécepteurs présynaptiques ; un récepteur purement postsynaptique reste sous forme de points. Les billes sont vives/rapides/denses quand le médicament augmente le tonus du système et ternes/lentes/rares quand il le baisse (un ISRS augmente l'éventail sérotoninergique, l'agonisme 5-HT1A de la buspirone l'atténue, un bloqueur VMAT2 l'épuise), et leur intensité suit l'affinité mesurée du médicament. Le système est lu depuis les cibles du médicament, pas depuis les régions qui s'allument. Seuls ces systèmes ascendants diffus dotés d'un noyau source modélisé circulent :",
      "legendKey.pathways": "Voies",
      "legendKey.speculative": "Voie hypothétique (pointillés)",

      "info.connection": "Connexion",
      "info.projectionType": "Projection",
      "info.dirOut": "Projection sortante",
      "info.dirIn": "Projection entrante",
      "info.dirBoth": "Projection réciproque (deux sens)",
      "info.arrowColour": "La couleur indique le type de voie : {label}.",
      "info.wikipedia": "Wikipédia ↗",
      "info.vidal": "Vidal ↗",
      "info.vidalTitle": "Rechercher cette substance sur Vidal (base de données du médicament)",
      "info.drugscom": "Drugs.com ↗",
      "info.drugscomTitle": "Rechercher ce médicament sur Drugs.com",
      "info.ema": "EMA ↗",
      "info.emaTitle": "Rechercher sur l’Agence européenne des médicaments",
      "info.fda": "FDA ↗",
      "info.fdaTitle": "Rechercher dans la base de données de la FDA (États-Unis)",
      "info.pdsp": "PDSP Ki ↗",
      "info.pdspTitle": "Parcourir la base d’affinités de liaison PDSP Ki (NIMH)",
      "info.uniprot": "UniProt ↗",
      "info.uniprotTitle": "Rechercher ce récepteur dans UniProt (humain uniquement)",
      "info.gtopdb": "GtoPdb ↗",
      "info.gtopdbTitle": "Rechercher ce récepteur dans le Guide to Pharmacology",
      "info.reference": "Référence",
      "info.provDetails": "Cliquez pour le détail",
      "info.provNone": "Aucune source pour ce nœud pour l’instant.",
      "info.provLlm": "Niveau de source : LLM seul. Produite de mémoire par un LLM, sans vérification dans aucun document : il peut donc s’agir d’une hallucination.",
      "info.provSourced": "Niveau de source : documentée. Rédigée par un LLM ayant eu accès au document source (par ex. le guide de Stahl), mais ce nœud précis n’a pas été vérifié par citation.",
      "info.provVerified": "Niveau de source : vérifiée. Un LLM a extrait une citation, sa présence dans la source a été confirmée par programme, et un second LLM a confirmé qu’elle étaye ce nœud. C’est le niveau le plus élevé disponible ici et il reste piloté par un LLM : il peut donc encore se tromper. Aller plus loin demanderait un effort humain considérable, lui-même sujet à erreur, et sort donc du cadre de ce projet.",
      "info.provWikipedia": "Chargé directement depuis Wikipédia. Ce texte est récupéré en direct et tel quel depuis l’article Wikipédia actuel (CC BY-SA), sans aucun LLM : il ne peut donc pas s’écarter de l’article. Voir le lien Référence ci-dessus pour inspecter la source.",
      "info.descFromWikipedia": "Cette description est l’introduction de l’article Wikipédia du médicament, reprise telle quelle sous licence CC BY-SA. Voir le lien Référence ci-dessus.",
      "info.sourceRef": "{corpus}, p. {page}",
      "info.sourceSpecies": "Espèce testée : {species}",
      "info.noConnections": "Aucune connexion répertoriée pour l’instant.",
      "info.connections": "Connexions",

      "circuit.heading": "Circuit fonctionnel",
      "circuit.structures": "Structures de cette boucle",
      "circuit.pathways": "Voies de cette boucle",
      "group.actingDrugs": "Médicaments agissant sur ce système",
      "group.kindHeading": "Voies par neurotransmetteur",
      "group.signHeading": "Voies par effet",
      "group.pathways": "Voies",

      "receptor.system": "Système",
      "receptor.neurotransmitter": "Neurotransmetteur",
      "receptor.type": "Type",
      "receptor.effect": "Effet",
      "receptor.synaptic": "Site synaptique",
      "receptor.foundIn": "Présent dans",
      "receptor.foundOther": "Autres régions",
      "receptor.ubiquitous": "Dans tout le cerveau",
      "receptor.noRole": "Pas de rôle significatif dans le système nerveux central.",
      "receptor.locUnsourced": "La liste des régions où cela se trouve est rédigée par IA (connaissances générales), pas encore vérifiée contre un atlas d'expression.",
      "receptor.speciesTag": "· {species}",
      "receptor.speciesTip": "Expression vérifiée chez : {species}, pas chez l'humain.",
      "species.human": "humain",
      "species.rat": "rat",
      "species.mouse": "souris",
      "species.monkey": "singe",
      "receptor.stubHint": "Pas de rôle significatif dans le système nerveux central",
      "targets.otherSystem": "Autre / non-aminergique",
      "targets.interactingDrugs": "Médicaments en interaction",
      "targets.bySubtype": "Par sous-type de récepteur",
      "target.polarity": "Polarité tonique",
      "target.polarityVesicular": "Transporteur vésiculaire (le bloquer épuise les stocks, abaisse le tonus)",
      "target.polarityAutoreceptor": "Autorécepteur inhibiteur présynaptique (le bloquer élève le tonus)",

      "panel.drugs": "Médicaments",
      "drugs.filter": "Filtrer les médicaments…",
      "drugs.none": "Aucun médicament correspondant.",
      "drug.class": "Classe",
      "drug.nomenclature": "Nomenclature",
      "drug.nbnNonstandard": "· classe du médicament, pas de NbN formelle",
      "drug.brands": "Noms commerciaux",
      "drug.actsOn": "Agit sur",
      "drug.noTargets": "Aucune cible moléculaire répertoriée pour l'instant.",
      "drug.projectionsAffected": "Projections concernées",
      "drug.projectionsAffectedHint": "Voies ascendantes dont ce médicament règle le tonus. Déduit de ses liaisons régulatrices (recapture, enzyme, vésicule ou autorécepteur) ; une flèche sortante augmente le tonus du système, une flèche entrante le baisse.",
      "drug.actsWithin": "Agit au sein de",
      "drug.actsWithinHint": "Systèmes que ce médicament n'engage qu'à travers un récepteur postsynaptique. Leurs voies sont éclairées à titre indicatif (sans billes) : bloquer un récepteur postsynaptique ne modifie pas en soi le tonus du neurotransmetteur.",
      "drug.stubHint": "Aucun profil de liaison enregistré pour l'instant",
      "drug.speculative": "spéculative",
      "drug.affinityOnly": "affinité seule, sens non établi",
      "drug.kiCounts": "{h} humaines, {n} non humaines",
      "drug.kiTip": "Affinité de liaison mesurée (Ki), plus bas = plus forte. Médiane sur {h} études humaines + {n} non humaines ; le badge cite une étude représentative : {assay}",
      "drug.kiTipNonHuman": "Aucune étude humaine : ce Ki provient de tissu non humain ({species}).",
      "drug.kiInactive": "{n} inactive(s)",
      "drug.kiInactiveTip": "Plus {n} étude(s) au plafond de ≥10 µM (testé, liaison quasi nulle) ; exclues de la médiane ci-dessus.",
      "drug.kiMapped": "mesuré sur {compound}",
      "drug.kiCitedTip": "Valeur d'affinité citée depuis le tableau de liaison de la source (une valeur bibliographique, pas une mesure brute). Le lien pointe vers la révision exacte de la source.",
      "drug.kiCited": "valeur bibliographique",
      "drug.kiMappedTip": "Le Ki de cette liaison a été mesuré sur {compound} ({relation}), sous lequel PDSP répertorie ce médicament.",
      "drug.rel.identity": "même molécule",
      "drug.rel.enantiomer": "énantiomère",
      "drug.rel.racemate": "racémique",
      "drug.rel.prodrug": "forme active",
      "drug.rel.metabolite": "métabolite",
      "drug.combo": "Médicament combiné",
      "drug.comboNote": "Les données de liaison sont indiquées par constituant ci-dessous ; des interactions entre eux peuvent exister. Ouvrez un constituant pour son profil complet :",
      "drug.structureAlt": "Structure chimique de {name}",
      "structure.imageAlt": "Illustration de {name}",
      "structure.galleryShow": "Voir {n} image(s) de plus",
      "structure.galleryHide": "Voir moins d'images",
      "image.close": "Fermer",
      "image.zoomHint": "Cliquer pour agrandir",

      "status.loadError":
        "Impossible de charger les données : {msg}. Le site est-il servi via HTTP ? (voir CLAUDE.md)",

      "loading.start": "Chargement…",
      "loading.data": "Chargement des données…",
      "loading.shapes": "Chargement des formes…",
      "loading.meshing": "Construction : {name}…",
      "loading.building": "Assemblage du cerveau…",
      "loading.tagline": "un atlas (en grande partie) sourcé des neurosciences psychiatriques",
      "loading.cta":
        'Une idée de fonctionnalité ? Je la réaliserais volontiers, ' +
        '<a href="https://olicorne.org/fr/contact" target="_blank" ' +
        'rel="noopener noreferrer">prenez contact</a>.',
      "loading.enter": "Commencer l'exploration",
      "common.byline":
        'par <a href="https://olicorne.org/fr" target="_blank" ' +
        'rel="noopener noreferrer">Olivier Cornelis</a>',

      "about.p1":
        "neurarium est une carte 3D interactive du cerveau, en cours de " +
        "développement. Elle montre les régions cérébrales et les projections " +
        "neuronales qui les relient, des circuits fonctionnels nommés autour " +
        "desquels on peut voir une impulsion circuler, les récepteurs de " +
        "neurotransmetteurs exprimés par chaque région, et des médicaments " +
        "psychiatriques animés pour montrer ce que chacun fait au cerveau. " +
        "Tout est consultable et cliquable, et chaque fait porte une note de " +
        "source (voir Sources et provenance ci-dessous). Les formes sont " +
        "schématiques : elles aident à situer et relier les structures, sans " +
        "prétendre à l’exactitude anatomique ; les données sur les récepteurs " +
        "et les médicaments sont générées automatiquement et non vérifiées : " +
        "considérez tout ceci comme illustratif, et non comme un avis médical.",
      "about.p2":
        'Réalisé par <a href="https://olicorne.org/" target="_blank" ' +
        'rel="noopener noreferrer">Olivier Cornelis</a> (développeur et ' +
        'psychiatre) et <a href="https://claude.com/claude-code" ' +
        'target="_blank" rel="noopener noreferrer">Claude</a>.',
      "about.p3":
        "Sous le capot, c’est un simple site statique : des modules " +
        'JavaScript natifs et <a href="https://threejs.org/" target="_blank" ' +
        'rel="noopener noreferrer">three.js</a> (embarqué, sans étape de ' +
        "build), l’anatomie stockée dans des fichiers de données " +
        "générés, servis par Caddy.",
      "about.animationModel":
        "À propos de l’animation des médicaments : c’est un modèle de <em>réglage du " +
        "tonus</em>, pas une image littérale des molécules. Ce sont les données de liaison " +
        "du médicament qui la pilotent : les récepteurs postsynaptiques qu’il touche " +
        "apparaissent en billes-gemmes colorées sur les régions qui les expriment " +
        "(renforce / bloque / module), tandis que ses liaisons qui <em>règlent le tonus</em> " +
        "(inhibiteurs de recapture, inhibiteurs d’enzyme, bloqueurs vésiculaires, " +
        "autorécepteurs présynaptiques) envoient des billes le long des voies ascendantes " +
        "des systèmes de neurotransmetteurs qu’il augmente ou diminue. La densité et la " +
        "vitesse sont normalisées par médicament : ce que vous lisez est l’activité " +
        "<em>relative</em> entre systèmes, pas une dose absolue. " +
        "<strong>Les animations de médicaments sont de loin l’aspect le moins " +
        "scientifique de neurarium et sont encore très largement en cours " +
        "d’élaboration</strong> : voyez-les comme une illustration évolutive, pas " +
        "comme un fait établi.",
      "about.dataSummary": "Les données sont libres de réutilisation",
      "about.dataIntro":
        "L’ensemble des données est du simple JSONL / JSON, séparé du rendu et libre de " +
        "réutilisation. Chaque fichier ci-dessous est servi directement depuis ce site " +
        "(un objet JSON par ligne, auto-descriptif, chaque ligne graduée et sourcée) :",
      "about.dataRepo": "Ou parcourez-les dans le dépôt du code source →",
      "about.outreach":
        "Je pense que ce genre de visualiseur interactif pourrait être vraiment utile au " +
        "domaine médical, et je réaliserais volontiers des animations similaires pour " +
        "d’autres sujets. Si vous avez une idée, ou un retour sur celui-ci, n’hésitez pas à " +
        "me contacter (le plus simple est le suivi des tickets ci-dessous) et à me dire ce " +
        "qui vous serait utile.",
      "about.issues":
        "Vous avez repéré un bug, une inexactitude ou une idée de fonctionnalité ? " +
        'Merci d’<a id="about-issues" target="_blank" rel="noopener noreferrer">ouvrir ' +
        "un ticket</a>.",
      "about.sourceCode": "Code source",
      "about.license":
        'Sous licence <a href="https://www.gnu.org/licenses/agpl-3.0.html" ' +
        'target="_blank" rel="noopener noreferrer">GNU AGPL-3.0</a>.',
      "about.attribution":
        "Les descriptions des médicaments et les schémas de structure moléculaire " +
        'proviennent de Wikipédia, sous licence <a ' +
        'href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" ' +
        'rel="noopener noreferrer">CC BY-SA</a> ; chaque fiche de médicament ' +
        "renvoie à son article source.",
      "about.sourcingTitle": "Sources et provenance",
      "sourcing.openLink": "Sources et provenance →",
      "about.sourcingIntro":
        "Chaque nœud de ce jeu de données (toute donnée sourçable : une région, " +
        "une voie, un récepteur, une liaison médicamenteuse, ...) porte un niveau " +
        "de source. Rien n’a encore été vérifié par un humain : même un nœud " +
        "« vérifié » peut être faux. Les niveaux :",
      "about.sourcingCaveat":
        "Une donnée sourcée n’est pas pour autant vraie. La source peut elle-même se " +
        "tromper, l’IA peut avoir rattaché une citation correcte à la mauvaise affirmation, " +
        "et le code d’affichage comporte parfois ses propres bugs. Restez critique : si " +
        "quelque chose semble faux, c’est peut-être une erreur. Les corrections sont les " +
        "bienvenues via le lien de signalement ci-dessous.",
      "about.gradeVerified":
        "Vérifié : la citation à l’appui a été confirmée présente dans la source citée.",
      "about.gradeSourced":
        "Sourcé : tiré d’un document (p. ex. Wikipédia), mais la citation n’a pas été vérifiée.",
      "about.gradeLlm":
        "IA seule : peut être une hallucination.",
      "about.gradeNone": "Sans source : aucune réunie pour l’instant.",
      "about.gradeWikipedia":
        "Lien Wikipédia : affiché à la place d’un niveau sur une description en direct. " +
        "Le texte est l’introduction actuelle de l’article, lue en direct et telle quelle " +
        "(sans IA) ; le lien est la source, cliquez pour ouvrir l’article.",
      "about.segVerified": "Vérifié",
      "about.segSourced": "Sourcé",
      "about.segLlm": "IA seule",
      "about.segNone": "Sans source",
      "about.coverageTitle": "Couverture",
      "about.sourcingHeadline":
        "{pct} % des {total} nœuds de connaissance ici sont sourcés ou vérifiés.",
      "about.kiCoverage":
        "Affinité de liaison mesurée (Ki PDSP) : {pct} % des {total} liaisons en portent une ; {drugsNone} des {drugs} médicaments n'en ont aucune (sourcés par citation ou sans source).",
      "about.kindBindings": "Liaisons cibles des médicaments",
      "about.kindNbn": "Nomenclature des médicaments (NbN)",
      "about.kindDrugBrands": "Noms commerciaux des médicaments",
      "about.kindDrugCategories": "Classe du médicament",
      "about.kindProjections": "Voies neuronales",
      "about.kindCircuits": "Circuits fonctionnels",
      "about.kindProjectionGroups": "Groupes de projections",
      "about.kindReceptors": "Système/famille du récepteur",
      "about.kindReceptorClass": "Classe mécanistique du récepteur",
      "about.kindReceptorSign": "Signe du récepteur (excitateur/inhibiteur)",
      "about.kindReceptorSynaptic": "Site pré/postsynaptique du récepteur",
      "about.kindReceptorLocations": "Régions d'expression des récepteurs",
      "about.kindTargets": "Classifications des cibles",
      "about.kindTargetPolarity": "Polarité tonique de la cible",
      "about.kindTargetLocations": "Régions d'expression des cibles",
      "about.kindStructures": "Anatomie des régions",

      "dev.wip": "En cours de développement",
      "dev.restarted":
        "Ce conteneur a été redémarré {ago} ; il est donc activement développé. ",
      "dev.activelyDeveloped": "Ce site est activement développé. ",
      "dev.stayTuned": "En cas de problème, revenez plus tard.",
      "dev.source": "Source",
      "dev.clickHide": "Cliquer pour masquer (réapparaît au rechargement)",
      "time.lessThanMinute": "il y a moins d’une minute",
      "time.minutes": "il y a {n} minute{s}",
      "time.hours": "il y a {n} heure{s}",
      "time.days": "il y a {n} jour{s}",

      "error.dismiss": "Fermer",
      "error.prefix": "Erreur : {msg}",
      "error.unhandled": "Erreur non gérée : {msg}",
      "error.failedLoad": "Échec du chargement de {what}",
    },
  };

  var lang = detectLang();

  // Look up a UI string, with optional {token} interpolation. Falls back to the
  // English entry, then to the key itself, so a missing translation is visible
  // but never blank.
  function t(key, vars) {
    var table = MESSAGES[lang] || MESSAGES.en;
    var s = table[key];
    if (s == null) s = MESSAGES.en[key];
    if (s == null) return key;
    if (vars) {
      s = s.replace(/\{(\w+)\}/g, function (m, name) {
        return name in vars ? String(vars[name]) : m;
      });
    }
    return s;
  }

  // The data-translation side table (English string -> French), loaded from
  // data/translations.fr.json by js/data.js, but ONLY in French (English users
  // never fetch it). The emitted data is English-only, so an English data string
  // is looked up here to get its French. Empty until setDataTranslations runs.
  var DATA_FR = {};
  function setDataTranslations(obj) {
    DATA_FR = (obj && typeof obj === "object") ? obj : {};
  }

  // Resolve a translatable *data* field. The emitted data is English-only, so a
  // plain string is the English datum: in French, return its side-table
  // translation (falling back to the English string when the table lacks it, e.g.
  // an identical en==fr pair we deliberately did not store). A legacy {en, fr}
  // object still collapses to the current language, so an older dataset keeps
  // working. Used by js/data.js and the viewer.
  function pick(field) {
    if (field == null) return field;
    if (typeof field === "string") {
      return (lang === "fr" && DATA_FR[field] != null) ? DATA_FR[field] : field;
    }
    if (typeof field === "object") {
      if (field[lang] != null) return field[lang];
      if (field.en != null) return field.en;
      for (var k in field) if (Object.prototype.hasOwnProperty.call(field, k)) return field[k];
    }
    return field;
  }

  // Persist the choice and reload (js/data.js resolves the data language at
  // load, so a live re-render isn't needed - a reload is simplest and robust).
  function setLang(next) {
    if (SUPPORTED.indexOf(next) === -1 || next === lang) return;
    try { localStorage.setItem(STORAGE_KEY, next); } catch (e) { /* ignore */ }
    location.reload();
  }

  // Fill static markup. Elements opt in via:
  //   data-i18n="key"            -> textContent
  //   data-i18n-html="key"       -> innerHTML (for the About paragraphs' links)
  //   data-i18n-attr="attr:key"  -> sets an attribute (e.g. placeholder/title;
  //                                 several allowed, comma-separated)
  function applyStatic(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    scope.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      el.innerHTML = t(el.getAttribute("data-i18n-html"));
    });
    scope.querySelectorAll("[data-i18n-attr]").forEach(function (el) {
      el.getAttribute("data-i18n-attr").split(",").forEach(function (pair) {
        var bits = pair.split(":");
        if (bits.length === 2) el.setAttribute(bits[0].trim(), t(bits[1].trim()));
      });
    });
  }

  // Wire the EN/FR switch (buttons carrying data-lang) and mark the active one.
  function wireSwitch(scope) {
    (scope || document).querySelectorAll("[data-lang]").forEach(function (btn) {
      var btnLang = btn.getAttribute("data-lang");
      btn.classList.toggle("active", btnLang === lang);
      btn.setAttribute("aria-pressed", String(btnLang === lang));
      btn.addEventListener("click", function () { setLang(btnLang); });
    });
  }

  window.__I18N__ = {
    lang: lang,
    t: t,
    pick: pick,
    setDataTranslations: setDataTranslations,
    setLang: setLang,
    applyStatic: applyStatic,
  };

  document.documentElement.lang = lang;
  document.addEventListener("DOMContentLoaded", function () {
    applyStatic(document);
    wireSwitch(document);
  });
})();
