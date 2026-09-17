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

      "panel.controls": "3D Controls",
      "panel.separate": "Separate",
      "panel.transparency": "Transparency",
      "panel.autorotate": "Auto-rotate",
      "panel.seeInside": "See inside",
      "panel.animations": "Animations",
      "panel.no3d": "Hide the 3D model (the panel fills the screen)",
      "panel.show3d": "Show the 3D model again",
      "panel.speed": "Animation speed",
      "panel.arrowColors": "Arrow colours",
      "panel.colorNt": "Neurotransmitter",
      "panel.colorPotential": "Potential",
      "panel.structures": "Brain structures",
      "panel.projections": "Projections & Circuits",
      "panel.legend": "Legend",
      "panel.receptors": "Receptors & targets",
      "panel.enzymes": "Enzymes",
      "panel.nodes": "Data browser",
      "panel.simulation": "Simulation",
      "panel.about": "About",
      // The Data browser section (js/node-browser.js): one flat list of every
      // graded fact, with a filter box and three selects over it.
      "nodes.filter": "Filter facts…",
      "nodes.kindLabel": "Kind of fact",
      "nodes.gradeLabel": "Sourcing",
      "nodes.sortLabel": "Sort by",
      "nodes.allKinds": "All kinds",
      "nodes.allGrades": "All sourcing",
      "nodes.sortWeakest": "Least sourced first",
      "nodes.sortStrongest": "Best sourced first",
      "nodes.sortName": "Name",
      "nodes.sortKind": "Kind",
      "nodes.count": "{shown} of {total}",
      "nodes.twins": "Show both hemispheres",
      "nodes.twinsHint": "A left/right pair of a region is two facts saying the same "
        + "thing, so each region is read once, without its side. Tick to list both "
        + "separately, which is what the sourcing counts count.",
      "nodes.intro": "Every fact below is one node: a named thing (name) stating one "
        + "notion, of one kind, backed at one grade. One row is one node; click a "
        + "grade badge for its source, or the row to open what it belongs to.",
      "nodes.dataFiles": "The same data as files →",
      "nodes.dataFilesHint": "Open the list of downloadable data files (and the "
        + "source repository) from the About popup",
      "nodes.colGrade": "grade: how well this fact is sourced (click the badge for "
        + "the source itself)",
      "nodes.colName": "name: the thing the fact is about",
      "nodes.colNotion": "notion: what the fact states about it",
      "nodes.colKind": "kind: which sort of fact it is, as counted in the sourcing "
        + "coverage",

      "sim.beta": "beta",
      "sim.lead": "How much of each receptor a combination of drugs engages, and the same question backwards: which combination would come close to a profile you describe. Both ends are about receptor occupancy.",
      "sim.leadUnit": "What is drawn is a relative index, not a percentage of receptors occupied: an affinity says how tightly a drug holds a receptor, never how much of it reaches the receptor.",
      "sim.warnTitle": "What this simulation does not know",
      "sim.warnNotExhaustive": "This list is not exhaustive. It names the shortcuts taken knowingly; others are certainly missing from it.",
      "sim.warn.interactions": "No drug-drug interaction is modeled: nothing here changes another drug's level.",
      "sim.warn.halfLife": "One average half-life per ligand (the midpoint of a published range), where real values vary widely between people.",
      "sim.warn.plasma": "Plasma kinetics only: exposure in the brain is not simply proportional to it.",
      "sim.warn.dose": "No dose, bioavailability, distribution volume, free fraction or brain penetration, so no concentration at a receptor can be worked out: the bars stay an index rather than a percentage occupied. A single oral dose is assumed, rising to the drug's own sourced time-to-peak where one exists, and to {h} h for the drugs no source states one for.",
      "sim.warn.endogenous": "The brain's own transmitter is ignored: a drug competes at a receptor with the dopamine or serotonin already there, which is why a measured occupancy never matches a test-tube affinity.",
      "sim.warn.additive": "Potencies simply add up, with no competition at a receptor, no efficacy and no tolerance.",
      "sim.warn.unknown": "A receptor whose direction nobody sourced is drawn as a grey \"binds, effect unknown\" band, and is not counted in the net.",
      "sim.warn.assumedKi": "A binding with a known direction but no measured Ki is assumed at {ki}.",
      "sim.warn.metabolite": "An active metabolite is assumed to be formed in full.",
      "sim.warnBetween": "Between these drugs",
      "sim.flag.sharedSubstrate": "{a} and {b} are both cleared by {enzyme}.",
      "sim.flag.inhibits": "{a} inhibits {enzyme}, which clears {b}.",
      "sim.flag.induces": "{a} induces {enzyme}, which clears {b}.",
      "sim.flag.profile": "{assumed} binding(s) at an assumed affinity, {unknown} with no sourced direction.",
      "sim.flag.unknownList": "Which ones?",
      "sim.drugs": "Drugs",
      "sim.empty": "Add a drug to start.",
      "sim.addDrug": "Add drug",
      "sim.searchDrug": "Type a drug name",
      "sim.noMatch": "No match",
      "sim.ratio": "Relative dose",
      "sim.ratioHint": "How much of this drug relative to the others (the first one is the reference).",
      "sim.less": "Less",
      "sim.more": "More",
      "sim.remove": "Remove",
      "sim.toggleVisible": "Show or hide this drug in both plots",
      "sim.openPanel": "Open this drug's panel",
      "sim.metabolites": "Include active metabolites",
      "sim.pkTitle": "Plasma level over time",
      "sim.pkCaption": "Relative level of each ligand after one dose at t = 0, every drug sharing an assumed {h} h time-to-peak. Hover or drag across the plot to read the receptor plot below at that moment.",
      "sim.pkNone": "No picked drug has a half-life to plot.",
      "sim.pkAtPeak": "Read at each ligand's own peak.",
      "sim.pkHours": "{n} h",
      "sim.pkDays": "{n} d",
      "sim.pkAxisHours": "hours",
      "sim.pkAxisDays": "days",
      "sim.rxTitle": "Receptor engagement",
      "sim.rxCaption": "Bar height is log10(1 + potency / floor), the floor being a {floor} affinity (below it an assay counts as inactive), so one unit is roughly a tenfold gain: {scale}. Above the line the combination raises a receptor, below it blocks it.",
      "sim.rxNone": "Nothing is engaged above the threshold.",
      "sim.rxThreshold": "Hide below",
      "sim.rxUnknownToggle": "Show unknown-direction bands",
      "sim.rxBoost": "Boost",
      "sim.rxBlock": "Block",
      "sim.rxUnknown": "Binds, effect unknown",
      "sim.rxNet": "Net",
      "sim.rxWhich": "Which drugs:",
      "sim.systemOther": "Other",
      "sim.solveTitle": "Find drugs for a profile",
      "sim.solveCaption": "State the profile you want receptor by receptor, then let the solver look for a combination that reproduces it. The drugs listed above are held as they are, so this answers \"what should I add\".",
      "sim.addReceptor": "Add receptor",
      "sim.searchReceptor": "Type a receptor or target name",
      "sim.useCurrent": "Use current profile",
      "sim.useCurrentHint": "Fill the list from the net values the receptor plot shows right now.",
      "sim.onlyListed": "Only these receptors",
      "sim.onlyListedHint": "Fit only the receptors listed here. Unticked, every other receptor the candidates touch becomes a row wanted at zero, so an off-target hit costs the fit.",
      "sim.maxDrugs": "Max drugs",
      "sim.solve": "Find drugs",
      "sim.solving": "Searching...",
      "sim.fit": "Fit: {pct}% over {n} receptor(s)",
      "sim.pickOpposes": "pulls against your wish at {targets}: it only compensates what the listed drugs overshoot",
      "sim.noPicks": "Nothing improves on what is already listed.",
      "sim.addPick": "Add",
      "sim.addAll": "Add all",
      "sim.solveNote": "Many combinations fit about as well; this is one of them.",
      "sim.solveEmpty": "Add at least one receptor first.",
      "sim.boostLabel": "boost",
      "sim.blockLabel": "block",
      "panel.tabSettings": "Settings",
      "panel.tabDetails": "Details",
      "panel.closeTab": "Close tab",

      "toolbar.reset": "Reset view",
      "toolbar.search": "Search",
      "toolbar.searchAria": "Search structures, connections, receptors and drugs",
      "search.placeholder": "Search structure, connection, receptor/target, drug or a control...",
      "search.noMatch": "No match",
      "search.tagCircuit": "circuit",
      "search.tagPathways": "pathways",
      "search.tagEnzyme": "enzyme",
      "search.filterAll": "All",
      "search.filterCommands": "Controls",
      "search.on": "on",
      "search.off": "off",
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

      "tour.start": "Start the tutorial",
      "tour.next": "Next",
      "tour.back": "Back",
      "tour.done": "Done",
      "tour.skip": "Skip",
      "tour.step": "{n} of {total}",
      "tour.aria": "Guided tour",
      "tour.scrollHint": "Scroll this way to the highlighted part",
      "tour.welcome.title": "Welcome to neurarium",
      "tour.welcome.body":
        "A 3D map of the brain: its regions, their pathways, and the receptors and drugs acting on them. The tour takes about 4 minutes, and you can leave any time.",
      "tour.rotate.title": "Move around",
      "tour.rotate.body":
        "<b>Drag</b> to spin the brain, scroll to zoom. Give it a spin to continue.",
      "tour.separate.title": "Pull it apart",
      "tour.separate.body":
        "The <b>Separate</b> slider pulls the brain apart to reveal the deep nuclei. Grab it to continue.",
      "tour.legendOpen.title": "The key to the scene",
      "tour.legendOpen.body":
        "Colours and symbols carry meaning here. Click <b>Legend</b> to see what they stand for.",
      "tour.legendLook.title": "The legend",
      "tour.legendLook.body":
        "Every colour and symbol the 3D view uses, in one place. It stays a click away in the toolbar. Close it (the <b>&times;</b>) to continue.",
      "tour.sourcesOpen.title": "Every fact is sourced",
      "tour.sourcesOpen.body":
        "The data is LLM-assisted, so every fact is graded. Click <b>Sources &amp; provenance</b> to see the breakdown.",
      "tour.sourcesDetail.title": "The provenance breakdown",
      "tour.sourcesDetail.body":
        "How much of the data is verified, sourced, or still unchecked. Close it (the <b>&times;</b>) to continue.",
      "tour.nodesOpen.title": "Read the facts themselves",
      "tour.nodesOpen.body":
        "Each of those graded facts is a row you can read. Click <b>Data browser</b> to open the list.",
      "tour.nodesLook.title": "The Data browser",
      "tour.nodesLook.body":
        "Every fact in the dataset, in one list: filter it, sort it, keep only one kind or one grade. Each row opens the thing it describes. It is a wide table, so it borrows the whole window and the 3D view steps aside.",
      "tour.show3d.title": "Show or hide the brain",
      "tour.show3d.body":
        "This button hides the 3D view so the panel can fill the screen, for reading. The brain is hidden right now: click it to bring it back.",
      "tour.collapsePanel.title": "Fold the panel away",
      "tour.collapsePanel.body":
        "The other way round: click the <b>neurarium</b> header to fold the panel down to a single line and leave the brain alone on screen. Try it, then <b>Next</b>.",
      "tour.browse.title": "Browse the data",
      "tour.browse.body":
        "Everything sits in five lists, in panel order: <b>Drugs</b> ({drugs}+), <b>Receptors &amp; targets</b> ({receptors}+), <b>Enzymes</b>, <b>Brain structures</b> ({structures}+) and <b>Projections &amp; Circuits</b> ({projections}+). We'll open a few next.",
      "tour.openDrugs.title": "Open a list",
      "tour.openDrugs.body":
        "Start with a drug. Click <b>Drugs</b> to open the list.",
      "tour.drugTap.title": "Focus a drug",
      "tour.drugTap.body":
        "Click <b>Olanzapine</b>. The brain dims and its effects animate on the regions it reaches.",
      "tour.drugActs.title": "What it acts on",
      "tour.drugActs.body":
        "Its <b>bindings</b>, ordered strongest affinity first: each target it hits, the effect, and the affinity (Ki) that drives the animation. <b>Heads-up:</b> the drug animations are the least scientific part of neurarium, still a work in progress, so read them as illustration, not fact.",
      "tour.drugMetabolism.title": "How the body clears it",
      "tour.drugMetabolism.body":
        "Further down, its <b>metabolism</b>: the liver enzymes that break this drug down, or whose activity it changes. Each one is sourced, and clickable. This is pharmacokinetics, so nothing lights up in the 3D view.",
      "tour.drugPk.title": "And what that implies",
      "tour.drugPk.body":
        "Open <b>Drug interactions</b>. These rows are <b>inferred</b> from the enzymes above, never measured: two drugs meeting at one enzyme <i>could</i> shift each other's blood level. Then <b>Next</b> to continue.",
      "tour.drugToReceptor.title": "Follow it to a receptor",
      "tour.drugToReceptor.body":
        "Back up to the bindings: each one is a link. Click the <b>H1</b> row to open that receptor.",
      "tour.receptorFacts.title": "How it's classified",
      "tour.receptorFacts.body":
        "Its <b>classification</b>: family, mechanism, excites or inhibits, synapse site. Each fact has its own grade.",
      "tour.receptorRegions.title": "Where it's found",
      "tour.receptorRegions.body":
        "The <b>regions</b> where it's expressed, each with its own source, and each one clickable.",
      "tour.closePanel.title": "Close the panel",
      "tour.closePanel.body":
        "Done reading? Click the <b>&times;</b> to close the panel.",
      "tour.openStructures.title": "Open a structure",
      "tour.openStructures.body":
        "A different kind of node. Click <b>Brain structures</b> to open the list.",
      "tour.structureTap.title": "Isolate a region",
      "tour.structureTap.body":
        "Click <b>Hippocampus</b>. It's isolated so you can see it on its own.",
      "tour.structureLook.title": "Read about it",
      "tour.structureLook.body":
        "Each panel opens with an image and a live Wikipedia description. <b>Scroll down</b> to continue.",
      "tour.openProjections.title": "Open the projections",
      "tour.openProjections.body":
        "Last kind of node: the pathways between regions. Click <b>Projections &amp; Circuits</b>.",
      "tour.projectionTap.title": "A whole system",
      "tour.projectionTap.body":
        "Click the <b>Dopamine</b> system. It pins every dopaminergic pathway at once.",
      "tour.projectionLook.title": "Read about it",
      "tour.projectionLook.body":
        "Its <b>member pathways</b> and a description. <b>Scroll down</b> to continue.",
      "tour.backToSettings.title": "Back to the panel",
      "tour.backToSettings.body":
        "Now back to the controls. Click <b>Settings</b> to return to the main panel.",
      "tour.openSearch.title": "Open search",
      "tour.openSearch.body":
        "Click the <b>magnifier</b> to open search.",
      "tour.search.title": "Find anything",
      "tour.search.body":
        "<b>Search</b> jumps to any structure, pathway, receptor or drug by name (try it). You can also filter drugs by class.",
      "tour.wrap.title": "You're set",
      "tour.wrap.body":
        "That's the tour. Settings, the EN / FR switch and a replay of this tour all live in the panel (replay from <b>About</b>). Enjoy.",

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
      "info.clinpgx": "ClinPGx ↗",
      "info.clinpgxTitle": "Search ClinPGx (pharmacogenomics: gene variants and drug response)",
      "info.clinpgxPathwaysTitle": "Search ClinPGx for this drug's pharmacokinetic pathways",
      "info.clinpgxEnzymeTitle": "Search ClinPGx for this enzyme (variants, phenotypes, dosing guidance)",
      "info.clinpgxGeneTitle": "Search ClinPGx for this protein's gene (variants and their effect on drug response)",
      "info.pathways": "Pathways",
      "info.pharmfreq": "PharmFreq ↗",
      "info.pharmfreqTitle": "Browse PharmFreq, the atlas these frequencies come from (its Metabolizer status tool covers more genes than we model)",
      "info.frequencies": "Frequencies",
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
      "info.provUncertain": "Source grade: uncertain. The quote below really is in the source and really is about this subject, but it never states this precise claim: it says something broader, so pinning it here is an inference. The reasons to doubt it are listed above, each with its own source.",
      "info.uncertainLead": "Here are LLM-written reasons to be uncertain about this claim:",
      "uncertain.side_effect_rule": "The source sentence explains a side effect, and its subject is the mechanism rather than the drug, so it never states that this drug has the action.",
      "uncertain.family_claim": "One sentence in the source covers {n} receptor subtypes at once, so it names the family and never this subtype: splitting it into subtypes is our own reading.",
      "uncertain.class_wide": "The same sentence is printed on {n} other drug monographs, so it may be a rule about the mechanism rather than a measurement on this drug.",
      "uncertain.measured_ki": "An independent measured affinity backs it: median Ki {ki} nM over {n} assays.",
      "uncertain.no_measured_ki": "No measured binding affinity was found for this target, so nothing independent backs the sentence.",
      "uncertain.not_a_mechanism": "The source never lists this action among the drug's mechanisms of action.",
      "uncertain.blanket_claim": "One sentence in the source covers {n} pathways out of this structure at once and names none of their targets: it describes how widely the system spreads, so drawing it to this region in particular is our own reading.",
      "uncertain.contradicted": "Another source in this dataset denies this outright, and is quoted below. Corpora most often disagree over what a laboratory measurement means in a living body (an effect real in vitro that does not show up in vivo), so both are kept here rather than one being dropped in silence.",
      "info.quoteChain": "How this quote got here:",
      "quotechain.raw_data": "raw data",
      "quotechain.page": "source page",
      "quotechain.extract_code": "deterministic extraction",
      "quotechain.extract_llm": "an LLM finds the quote",
      "quotechain.gate": "code checks the quote is on the page",
      "quotechain.judge_llm": "an amnesic LLM judges the quote",
      "quotechain.neurarium": "neurarium",
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
      "receptor.density": "Relative amount",
      "receptor.densityAgreement": "donor agreement r = {r}",
      "receptor.densityTip": "How much of it sits in each region, relative to this gene's own average across the brain. Measured as mRNA (Allen Human Brain Atlas microarray), so it is transcript, not protein, and it sits in cell bodies rather than at the far end of a projection: a transporter therefore reads highest at its source nucleus, not in the regions it acts on.",
      "receptor.densityAgreementTip": "How well the {donors} donor brains reproduce this pattern (correlation between their profiles). Near 1 means every brain ranks the regions the same way; a low value would mean the gene sits near the measurement noise floor, so only patterns above {min} are shown at all.",
      "receptor.densityValueTip": "{z} standard deviations from this gene's brain-wide average.",
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
      "drug.halfLife": "Half-life",
      "drug.pkTiming": "Timing",
      "drug.tmax": "Time to peak",
      "drug.tmaxTip": "How long after a single oral dose the blood concentration peaks (Tmax). It says when the drug arrives, while the half-life says how long it takes to leave.",
      "drug.nonLinearPk": "Non-linear pharmacokinetics detected. Read more in the Metabolism section below; click to jump there.",
      "drug.hlMinutes": "min",
      "drug.hlHours": "h",
      "drug.hlDays": "days",
      "drug.metabolites": "Active metabolites",
      "drug.metaboliteOf": "metab. of {prodrug}",
      "drug.metabSeeBindings": "See its {n} bindings →",
      "drug.formedBy": "formed by",
      "drugs.showMetabolites": "Show active metabolites",
      "drug.metabolism": "Metabolism",
      "drug.metabolismHint": "The liver enzymes that clear this drug, or whose activity it changes. Pharmacokinetics, so nothing is lit in the 3D view.",
      "panel.themeLight": "Switch to the light theme",
      "panel.themeDark": "Switch to the dark theme",
      "drug.autoPkTitle": "Non-linear pharmacokinetics",
      "drug.autoPkInhibits": "This drug is listed below as both a substrate and an inhibitor of {enzymes}, so it could slow its own clearance: blood levels may then climb faster than the dose does.",
      "drug.autoPkInduces": "This drug is listed below as both a substrate and an inducer of {enzymes}, so it could speed up its own clearance over the first weeks: blood levels may then drift down at an unchanged dose.",
      "drug.autoPkDerived": "Derived from the enzyme rows below, each of which carries its own source. No source states this consequence for this drug: reading the two roles together is our own.",
      "drug.pkInteractions": "Drug interactions",
      "drug.pkInteractionsHint": "Inferred from the enzymes above, not measured: this drug and the listed one meet at the same enzyme, so one could shift the other's blood level. \"Could raise\" means the other drug's level may go up (this one inhibits the enzyme that clears it), \"could lower\" that it may go down (this one induces it). Whether it actually matters depends on the dose, the route and the person, so it is a flag worth checking with a prescriber, never a contraindication, and the absence of a row is not a safety claim.",
      "info.more": "+{n} more",
      "structure.expressed": "Receptors found here",
      "structure.expressedCaption": "Receptors and other drug targets whose expression list names this region, grouped by neurotransmitter system. Each row carries that region's own source grade, the same claim the receptor's own panel shows from the other end.",
      "structure.expressedEverywhere": "throughout the brain",
      "drug.pkByDrug": "By drug",
      "drug.pkByEnzyme": "By enzyme",
      "drug.pkHeadRaises": "Could raise the level of",
      "drug.pkHeadLowers": "Could lower the level of",
      "drug.pkHeadRaisedBy": "Its level could be raised by",
      "drug.pkHeadLoweredBy": "Its level could be lowered by",
      "enzyme.heading": "Metabolic enzyme",
      "enzyme.drugs": "Drugs at this enzyme",
      "enzyme.forms": "Active metabolites it forms",
      "enzyme.formsOf": "from {drug}",
      "enzyme.noDrugs": "No drug recorded at this enzyme yet.",
      "enzyme.variability": "How fast people clear it",
      "enzyme.variabilityCaveat":
        "How common each clearance speed is, per broad population group. These are "
        + "frequencies across study cohorts, not a prediction about any one person: "
        + "most groups contain every speed, and only a genetic test says which one "
        + "someone has.",
      "enzymes.title": "Enzymes",
      "enzymes.hint": "The drug-metabolising enzymes (mostly liver cytochrome P450). Not part of the brain: this is pharmacokinetics, so selecting one changes nothing in the 3D view.",
      "drug.actsOn": "Acts on",
      "drug.noTargets": "No mapped molecular targets yet.",
      "drug.projectionsAffected": "Projections affected",
      "drug.projectionsAffectedHint": "Ascending pathways whose tone this drug sets. Derived from its tone-setting bindings (reuptake, enzyme, vesicle or autoreceptor); an out-arrow raises the system's tone, an in-arrow lowers it.",
      "drug.actsWithin": "Acts within",
      "drug.actsWithinHint": "Systems this drug engages only through a postsynaptic receptor. Their pathways are lit for context (no beads): blocking a postsynaptic receptor does not itself raise or lower the transmitter's tone.",
      "drug.stubHint": "No binding profile recorded yet",
      "drug.speculative": "speculative",
      "drug.affinityOnly": "affinity only, direction not established",
      "drug.actionNoSource": "No source says whether it activates or blocks this target",
      "drug.actionLlm": "The direction is stated from memory; only the binding itself is sourced",
      "drug.peripheral": "outside the brain, so nothing lights up",
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
      "loading.shapes": "Loading shapes… ({done}/{total})",
      "loading.meshing": "Building {name}… ({done}/{total})",
      "loading.geometry": "Loading the 3D shapes… ({done}/{total})",
      "loading.building": "Assembling the brain…",
      "loading.reducedQuality":
        "This device is meshing slowly, so the remaining structures were built at reduced detail to keep the load time reasonable. The data is unaffected: only the 3D shapes are a little softer.",
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
      "about.animCaveat":
        "<strong>The drug animations are by far the least scientific part of neurarium " +
        "and are still very much being worked out</strong>: treat them as an evolving " +
        "illustration, not settled fact.",
      "about.animSummary": "What the animations mean",
      "about.animIntro":
        "The drug animation is a <em>tone-setter</em> model, not a literal picture of " +
        "drug molecules travelling through the brain. Everything below is derived from " +
        "the drug's binding data, so it changes as that data does.",
      "about.animList":
        "<li><b>Coloured gem dots on the surface of a brain structure: a receptor this " +
        "drug binds is expressed there.</b> The dots are scattered over every region " +
        "that expresses that target, and their colour is what the drug does to it:" +
        "<ul>" +
        "<li>green = boosts it (agonist, reuptake blocker, releaser)</li>" +
        "<li>red = blocks it (antagonist, inverse agonist, blocker)</li>" +
        "<li>violet = modulates it (partial agonist, modulator)</li>" +
        "</ul>" +
        "Denser and brighter dots mean a stronger measured affinity, so a drug's main " +
        "target reads louder than a side one. Focusing a receptor on its own uses the " +
        "same dots without the colour coding: there, they only say <em>expressed " +
        "here</em>.</li>" +
        "<li><b>Beads streaming along an arrow: the drug shifts that whole system's " +
        "tone.</b> Only <em>tone-setting</em> bindings do this (reuptake blockers, " +
        "enzyme inhibitors, vesicle blockers, presynaptic autoreceptors); a purely " +
        "postsynaptic drug gets dots and glow only, and no beads at all. Which way it " +
        "shifts shows in the beads:" +
        "<ul>" +
        "<li>warm, bright, fast and dense = raises that system's tone</li>" +
        "<li>cool, dim, slow and sparse = lowers it</li>" +
        "</ul>" +
        "Speed and density are normalized <em>per drug</em>, so what you read is which " +
        "of that drug's systems it engages most, never an absolute dose. Watch for the " +
        "counter-intuitive case: an antipsychotic blocking the D2 <em>autoreceptor</em> " +
        "reads as raising dopamine tone, while its blockade of the postsynaptic D2 " +
        "receptors shows in the red dots.</li>" +
        "<li><b>Beads firing in sequence rather than streaming: that is a circuit, not " +
        "a drug.</b> Selecting a named circuit plays its signal in order, each leg " +
        "lighting once the one feeding it has arrived, with a wash of light where each " +
        "bead lands. A drug focus streams continuously instead, because a drug does not " +
        "fire a circuit, it changes a background level.</li>" +
        "<li><b>A glow washing over a whole region: the same dots, read at a " +
        "glance.</b> One wash per region and per effect, in the same green / red / " +
        "violet, so a region carrying twenty of the drug's targets glows once rather " +
        "than twenty times over.</li>" +
        "<li><b>A pale rim around one structure: that is the one you selected.</b> " +
        "Hovering shows its name; clicking pins it and opens its panel.</li>" +
        "<li><b>A dotted arrow instead of a solid one: that pathway is tentative.</b> " +
        "The connection is proposed rather than well established, and its source grade " +
        "in the panel says how well it is backed.</li>",
      "about.dataSummary": "Click to access the structured data",
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
        "issue on GitHub</a>.",
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
      // "What's new" popup (js/changelog.js). The category labels key off the
      // closed vocabulary in tools/data_generators/changelog.py: adding one there
      // means adding a changelog.cat.* string here (and in the FR block).
      "changelog.title": "What's new",
      "changelog.openLink": "What's new →",
      "changelog.commit": "See this change in the source repository",
      "changelog.empty": "No release notes yet.",
      "changelog.showAll": "Show all release notes",
      "changelog.cat.added": "New",
      "changelog.cat.improved": "Improved",
      "changelog.cat.fixed": "Fixed",
      "changelog.cat.data": "Data & sources",
      "changelog.cat.docs": "Documentation",
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
      "about.gradeLlm":
        "AI only: may be a hallucination.",
      "about.gradeNone": "No source: none gathered yet.",
      "about.quoteChains": "Not every green check was earned the same way: some quotes were copied out of a machine-readable table by code alone, others were found on a book page by an LLM, checked word for word against that page, then judged by a second LLM that had not seen the first one’s reasoning. Each source tooltip ends with the exact chain that produced it, so you can weigh it yourself.",
      "about.gradeUncertain":
        "Uncertain: the quote is confirmed present, but it does not attribute the claim. " +
        "Hover the badge for the reasons, each with its own source.",
      "about.segVerified": "Verified",
      "about.segUncertain": "Uncertain",
      "about.segSourced": "Sourced",
      "about.segLlm": "AI only",
      "about.segNone": "No source",
      "about.coverageTitle": "Coverage",
      "about.sourcingHeadline":
        "{pct}% of the {total} knowledge nodes here are sourced or verified.",
      // The global sourcing bar is clickable to reveal the per-node-kind breakdown;
      // each kind row is in turn clickable to reveal its grade counts + an example node.
      "about.sourcingByKind": "Break it down by node kind",
      "about.exampleLead": "e.g.",
      "about.kiCoverage":
        "Measured binding affinity (PDSP Ki): {pct}% of {total} drug bindings carry one; {drugsNone} of {drugs} drugs have none (quote-sourced or unsourced).",
      // Under the tally: the bars count the nodes, the Data browser lists them.
      "about.sourcingBrowser":
        "Every node counted above is listed one by one in the Data browser, "
        + "with its own source, filterable by kind and by how well sourced it is.",
      "about.sourcingBrowserLink": "Open the Data browser \u2192",
      "about.kindBindings": "Drug target bindings",
      "about.kindBindingAction": "Drug binding directions",
      "about.kindNbn": "Drug nomenclature (NbN)",
      "about.kindDrugBrands": "Drug brand names",
      "about.kindDrugCategories": "Drug class",
      "about.kindDrugHalfLife": "Drug half-life (T½)",
      "about.kindDrugTmax": "Drug time to peak (Tmax)",
      "about.kindDrugEnzymes": "Drug metabolising enzymes",
      "about.kindEnzymeVariability": "Enzyme clearance speed by population",
      "about.kindDrugMetabolites": "Drug active metabolites",
      "about.kindDrugMetaboliteEnzyme": "Metabolite-forming enzymes",
      "about.kindDrugMetaboliteBindings": "Drug metabolite bindings",
      "about.kindProjections": "Neuron pathways",
      "about.kindProjectionTransmitter": "Pathway transmitter",
      "about.kindProjectionSign": "Pathway sign (excitatory/inhibitory)",
      "about.kindCircuits": "Functional circuits",
      "about.kindProjectionGroups": "Projection groups",
      "about.kindReceptors": "Receptor system/family",
      "about.kindReceptorClass": "Receptor mechanism class",
      "about.kindReceptorSign": "Receptor sign (excitatory/inhibitory)",
      "about.kindReceptorSynaptic": "Receptor pre/postsynaptic site",
      "about.kindReceptorLocations": "Receptor expression regions",
      "about.kindReceptorDensity": "Receptor relative amount per region",
      "about.kindTargets": "Target classifications",
      "about.kindTargetPolarity": "Target tone polarity",
      "about.kindTargetLocations": "Target expression regions",
      "about.kindTargetDensity": "Target relative amount per region",
      "about.kindStructures": "Brain-region anatomy",
      "about.kindAddons": "Panel annotations",

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

      "panel.controls": "Contrôles 3D",
      "panel.separate": "Séparer",
      "panel.transparency": "Transparence",
      "panel.autorotate": "Rotation auto",
      "panel.seeInside": "Voir l'intérieur",
      "panel.animations": "Animations",
      "panel.no3d": "Masquer le modèle 3D (le panneau occupe tout l'écran)",
      "panel.show3d": "Réafficher le modèle 3D",
      "panel.speed": "Vitesse d'animation",
      "panel.arrowColors": "Couleur des flèches",
      "panel.colorNt": "Neurotransmetteur",
      "panel.colorPotential": "Potentiel",
      "panel.structures": "Structures cérébrales",
      "panel.projections": "Projections et circuits",
      "panel.legend": "Légende",
      "panel.receptors": "Récepteurs et cibles",
      "panel.enzymes": "Enzymes",
      "panel.nodes": "Explorateur de données",
      "panel.simulation": "Simulation",
      "panel.about": "À propos",
      "nodes.filter": "Filtrer les faits…",
      "nodes.kindLabel": "Type de fait",
      "nodes.gradeLabel": "Sources",
      "nodes.sortLabel": "Trier par",
      "nodes.allKinds": "Tous les types",
      "nodes.allGrades": "Toutes les sources",
      "nodes.sortWeakest": "Les moins sourcés d’abord",
      "nodes.sortStrongest": "Les mieux sourcés d’abord",
      "nodes.sortName": "Nom",
      "nodes.sortKind": "Type",
      "nodes.count": "{shown} sur {total}",
      "nodes.twins": "Afficher les deux hémisphères",
      "nodes.twinsHint": "Une région gauche/droite forme deux faits qui disent la "
        + "même chose : chaque région est donc lue une seule fois, sans son côté. "
        + "Cochez pour les lister séparément, ce que comptent les statistiques de "
        + "sources.",
      "nodes.intro": "Chaque fait ci-dessous est un nœud : une chose nommée (name) "
        + "qui énonce une notion, d’un certain type (kind), avec un niveau de source "
        + "(grade). Une ligne = un nœud ; cliquez la pastille pour voir sa source, ou "
        + "la ligne pour ouvrir ce à quoi elle appartient.",
      "nodes.dataFiles": "Les mêmes données en fichiers →",
      "nodes.dataFilesHint": "Ouvrir la liste des fichiers de données téléchargeables "
        + "(et le dépôt du code source) depuis la fenêtre À propos",
      "nodes.colGrade": "grade : à quel point ce fait est sourcé (cliquez la pastille "
        + "pour la source elle-même)",
      "nodes.colName": "name : la chose dont parle le fait",
      "nodes.colNotion": "notion : ce que le fait en dit",
      "nodes.colKind": "kind : la sorte de fait dont il s’agit, telle que comptée "
        + "dans la couverture des sources",

      "sim.beta": "bêta",
      "sim.lead": "Dans quelle mesure une association de médicaments engage chaque récepteur, et la même question à l'envers : quelle association approcherait un profil que vous décrivez. Les deux bouts parlent d'occupation des récepteurs.",
      "sim.leadUnit": "Ce qui est tracé est un indice relatif, non un pourcentage de récepteurs occupés : une affinité dit avec quelle force un médicament tient un récepteur, jamais quelle quantité lui parvient.",
      "sim.warnTitle": "Ce que cette simulation ignore",
      "sim.warnNotExhaustive": "Cette liste n'est pas exhaustive. Elle nomme les raccourcis pris en connaissance de cause ; d'autres y manquent certainement.",
      "sim.warn.interactions": "Aucune interaction médicamenteuse n'est modélisée : rien ici ne modifie le niveau d'un autre médicament.",
      "sim.warn.halfLife": "Une seule demi-vie moyenne par ligand (le milieu de l'intervalle publié), alors que les valeurs réelles varient beaucoup d'une personne à l'autre.",
      "sim.warn.plasma": "Cinétique plasmatique seulement : l'exposition cérébrale ne lui est pas simplement proportionnelle.",
      "sim.warn.dose": "Ni dose, ni biodisponibilité, ni volume de distribution, ni fraction libre, ni pénétration cérébrale : aucune concentration au récepteur ne peut donc être calculée, et les barres restent un indice plutôt qu'un pourcentage d'occupation. Une prise orale unique est supposée, montant jusqu'au délai de pic sourcé du médicament quand il en existe un, et jusqu'à {h} h pour ceux dont aucune source ne le donne.",
      "sim.warn.endogenous": "Le neurotransmetteur du cerveau lui-même est ignoré : un médicament entre en compétition au récepteur avec la dopamine ou la sérotonine déjà présentes, ce qui explique qu'une occupation mesurée ne corresponde jamais à une affinité en éprouvette.",
      "sim.warn.additive": "Les puissances s'additionnent simplement, sans compétition au récepteur, sans efficacité ni tolérance.",
      "sim.warn.unknown": "Un récepteur dont la direction n'a jamais été sourcée apparaît en bande grise « se lie, effet inconnu », et n'entre pas dans le net.",
      "sim.warn.assumedKi": "Une liaison de direction connue mais sans Ki mesuré est supposée à {ki}.",
      "sim.warn.metabolite": "Un métabolite actif est supposé formé en totalité.",
      "sim.warnBetween": "Entre ces médicaments",
      "sim.flag.sharedSubstrate": "{a} et {b} sont tous deux éliminés par {enzyme}.",
      "sim.flag.inhibits": "{a} inhibe {enzyme}, qui élimine {b}.",
      "sim.flag.induces": "{a} induit {enzyme}, qui élimine {b}.",
      "sim.flag.profile": "{assumed} liaison(s) à une affinité supposée, {unknown} sans direction sourcée.",
      "sim.flag.unknownList": "Lesquelles ?",
      "sim.drugs": "Médicaments",
      "sim.empty": "Ajoutez un médicament pour commencer.",
      "sim.addDrug": "Ajouter un médicament",
      "sim.searchDrug": "Tapez un nom de médicament",
      "sim.noMatch": "Aucun résultat",
      "sim.ratio": "Dose relative",
      "sim.ratioHint": "Quelle quantité de ce médicament par rapport aux autres (le premier sert de référence).",
      "sim.less": "Moins",
      "sim.more": "Plus",
      "sim.remove": "Retirer",
      "sim.toggleVisible": "Afficher ou masquer ce médicament dans les deux graphiques",
      "sim.openPanel": "Ouvrir la fiche de ce médicament",
      "sim.metabolites": "Inclure les métabolites actifs",
      "sim.pkTitle": "Taux plasmatique au cours du temps",
      "sim.pkCaption": "Taux relatif de chaque ligand après une prise unique à t = 0, tous les médicaments partageant un délai de pic supposé de {h} h. Survolez le graphique ou faites-y glisser le doigt pour lire le graphique des récepteurs à cet instant.",
      "sim.pkNone": "Aucun médicament choisi n'a de demi-vie à tracer.",
      "sim.pkAtPeak": "Lecture au pic propre de chaque ligand.",
      "sim.pkHours": "{n} h",
      "sim.pkDays": "{n} j",
      "sim.pkAxisHours": "heures",
      "sim.pkAxisDays": "jours",
      "sim.rxTitle": "Engagement des récepteurs",
      "sim.rxCaption": "La hauteur vaut log10(1 + puissance / seuil), le seuil étant une affinité de {floor} (en deçà, un dosage compte comme inactif) : une unité vaut donc environ un facteur dix : {scale}. Au-dessus de la ligne la combinaison active un récepteur, en dessous elle le bloque.",
      "sim.rxNone": "Rien n'est engagé au-dessus du seuil.",
      "sim.rxThreshold": "Masquer en dessous de",
      "sim.rxUnknownToggle": "Afficher les bandes de direction inconnue",
      "sim.rxBoost": "Activation",
      "sim.rxBlock": "Blocage",
      "sim.rxUnknown": "Se lie, effet inconnu",
      "sim.rxNet": "Net",
      "sim.rxWhich": "Quels médicaments :",
      "sim.systemOther": "Autre",
      "sim.solveTitle": "Trouver des médicaments pour un profil",
      "sim.solveCaption": "Indiquez récepteur par récepteur le profil souhaité, puis laissez le solveur chercher une combinaison qui le reproduit. Les médicaments listés ci-dessus sont conservés tels quels : la réponse dit donc quoi ajouter.",
      "sim.addReceptor": "Ajouter un récepteur",
      "sim.searchReceptor": "Tapez un nom de récepteur ou de cible",
      "sim.useCurrent": "Reprendre le profil actuel",
      "sim.useCurrentHint": "Remplir la liste à partir des valeurs nettes affichées en ce moment par le graphique des récepteurs.",
      "sim.onlyListed": "Seulement ces récepteurs",
      "sim.onlyListedHint": "N'ajuster que les récepteurs listés ici. Décoché, chaque autre récepteur touché par les candidats devient une ligne souhaitée à zéro : un effet hors cible coûte alors de la qualité d'ajustement.",
      "sim.maxDrugs": "Nombre max.",
      "sim.solve": "Chercher",
      "sim.solving": "Recherche...",
      "sim.fit": "Ajustement : {pct} % sur {n} récepteur(s)",
      "sim.pickOpposes": "va à l'encontre du souhait sur {targets} : il ne fait que compenser ce que les médicaments listés dépassent",
      "sim.noPicks": "Rien n'améliore ce qui est déjà listé.",
      "sim.addPick": "Ajouter",
      "sim.addAll": "Tout ajouter",
      "sim.solveNote": "Beaucoup de combinaisons conviennent aussi bien ; celle-ci en est une.",
      "sim.solveEmpty": "Ajoutez d'abord au moins un récepteur.",
      "sim.boostLabel": "activation",
      "sim.blockLabel": "blocage",
      "panel.tabSettings": "Réglages",
      "panel.tabDetails": "Détails",
      "panel.closeTab": "Fermer l’onglet",

      "toolbar.reset": "Recentrer la vue",
      "toolbar.search": "Rechercher",
      "toolbar.searchAria": "Rechercher structures, connexions, récepteurs et médicaments",
      "search.placeholder": "Rechercher une structure, une connexion, un récepteur/cible, un médicament ou un réglage…",
      "search.noMatch": "Aucun résultat",
      "search.tagCircuit": "circuit",
      "search.tagPathways": "voies",
      "search.tagEnzyme": "enzyme",
      "search.filterAll": "Tous",
      "search.filterCommands": "Réglages",
      "search.on": "activé",
      "search.off": "désactivé",
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

      "tour.start": "Démarrer le tutoriel",
      "tour.next": "Suivant",
      "tour.back": "Précédent",
      "tour.done": "Terminer",
      "tour.skip": "Passer",
      "tour.step": "{n} sur {total}",
      "tour.aria": "Visite guidée",
      "tour.scrollHint": "Faites défiler dans ce sens jusqu'à la partie en surbrillance",
      "tour.welcome.title": "Bienvenue sur neurarium",
      "tour.welcome.body":
        "Une carte 3D du cerveau : ses régions, leurs voies, et les récepteurs et médicaments qui agissent dessus. La visite dure environ 4 minutes, et vous pouvez la quitter quand vous voulez.",
      "tour.rotate.title": "Se déplacer",
      "tour.rotate.body":
        "<b>Faites glisser</b> pour tourner le cerveau, défilez pour zoomer. Faites-le tourner pour continuer.",
      "tour.separate.title": "Écarter les régions",
      "tour.separate.body":
        "Le curseur <b>Séparer</b> ouvre le cerveau et révèle les noyaux profonds. Saisissez-le pour continuer.",
      "tour.legendOpen.title": "La clé de la scène",
      "tour.legendOpen.body":
        "Ici, les couleurs et les symboles ont un sens. Cliquez sur <b>Légende</b> pour voir lequel.",
      "tour.legendLook.title": "La légende",
      "tour.legendLook.body":
        "Toutes les couleurs et tous les symboles de la vue 3D, au même endroit. Elle reste à un clic dans la barre d'outils. Fermez-la (le <b>&times;</b>) pour continuer.",
      "tour.sourcesOpen.title": "Chaque fait est sourcé",
      "tour.sourcesOpen.body":
        "Les données sont assistées par IA : chaque fait est noté. Cliquez sur <b>Sources et provenance</b> pour voir le détail.",
      "tour.sourcesDetail.title": "Le récapitulatif de provenance",
      "tour.sourcesDetail.body":
        "La part des données vérifiée, sourcée, ou encore non contrôlée. Fermez-la (le <b>&times;</b>) pour continuer.",
      "tour.nodesOpen.title": "Lire les faits eux-mêmes",
      "tour.nodesOpen.body":
        "Chacun de ces faits notés est une ligne que vous pouvez lire. Cliquez sur <b>Explorateur de données</b> pour ouvrir la liste.",
      "tour.nodesLook.title": "L'explorateur de données",
      "tour.nodesLook.body":
        "Tous les faits du jeu de données en une liste : filtrez, triez, ne gardez qu'un type ou qu'une note. Chaque ligne ouvre la chose qu'elle décrit. C'est un tableau large : il emprunte toute la fenêtre et la vue 3D s'efface.",
      "tour.show3d.title": "Afficher ou masquer le cerveau",
      "tour.show3d.body":
        "Ce bouton masque la vue 3D pour que le panneau occupe tout l'écran, pour lire. Le cerveau est masqué en ce moment : cliquez pour le faire revenir.",
      "tour.collapsePanel.title": "Replier le panneau",
      "tour.collapsePanel.body":
        "Et l'inverse : cliquez sur l'en-tête <b>neurarium</b> pour replier le panneau en une seule ligne et laisser le cerveau seul à l'écran. Essayez, puis <b>Suivant</b>.",
      "tour.browse.title": "Parcourir les données",
      "tour.browse.body":
        "Tout tient en cinq listes, dans l'ordre du panneau : <b>Médicaments</b> ({drugs}+), <b>Récepteurs et cibles</b> ({receptors}+), <b>Enzymes</b>, <b>Structures cérébrales</b> ({structures}+) et <b>Projections et circuits</b> ({projections}+). On en ouvre quelques-unes ensuite.",
      "tour.openDrugs.title": "Ouvrir une liste",
      "tour.openDrugs.body":
        "Commençons par un médicament. Cliquez sur <b>Médicaments</b> pour ouvrir la liste.",
      "tour.drugTap.title": "Mettre un médicament en avant",
      "tour.drugTap.body":
        "Cliquez sur <b>olanzapine</b>. Le cerveau s'assombrit et ses effets s'animent sur les régions qu'il atteint.",
      "tour.drugActs.title": "Ce sur quoi il agit",
      "tour.drugActs.body":
        "Ses <b>liaisons</b>, classées de la plus forte affinité à la plus faible : chaque cible touchée, l'effet, et l'affinité (Ki) qui pilote l'animation. <b>À noter :</b> les animations de médicaments sont l'aspect le moins scientifique de neurarium, encore en chantier ; voyez-les comme une illustration, pas un fait.",
      "tour.drugMetabolism.title": "Comment le corps l'élimine",
      "tour.drugMetabolism.body":
        "Plus bas, son <b>métabolisme</b> : les enzymes hépatiques qui dégradent ce médicament, ou dont il modifie l'activité. Chacune est sourcée, et cliquable. C'est de la pharmacocinétique : rien ne s'allume dans la vue 3D.",
      "tour.drugPk.title": "Et ce que cela implique",
      "tour.drugPk.body":
        "Ouvrez <b>Interactions médicamenteuses</b>. Ces lignes sont <b>déduites</b> des enzymes ci-dessus, jamais mesurées : deux médicaments qui se croisent sur une même enzyme <i>pourraient</i> déplacer leur concentration sanguine. Puis <b>Suivant</b> pour continuer.",
      "tour.drugToReceptor.title": "Suivre vers un récepteur",
      "tour.drugToReceptor.body":
        "Remontez aux liaisons : chacune est un lien. Cliquez sur la ligne <b>H1</b> pour ouvrir ce récepteur.",
      "tour.receptorFacts.title": "Sa classification",
      "tour.receptorFacts.body":
        "Sa <b>classification</b> : famille, mécanisme, excite ou inhibe, place sur la synapse. Chaque fait a sa propre note.",
      "tour.receptorRegions.title": "Où on le trouve",
      "tour.receptorRegions.body":
        "Les <b>régions</b> où il est exprimé, chacune avec sa source, et toutes cliquables.",
      "tour.closePanel.title": "Fermer le panneau",
      "tour.closePanel.body":
        "Lecture terminée ? Cliquez sur le <b>&times;</b> pour fermer le panneau.",
      "tour.openStructures.title": "Ouvrir une structure",
      "tour.openStructures.body":
        "Un autre type de nœud. Cliquez sur <b>Structures cérébrales</b> pour ouvrir la liste.",
      "tour.structureTap.title": "Isoler une région",
      "tour.structureTap.body":
        "Cliquez sur <b>hippocampe</b>. Il est isolé pour que vous le voyiez seul.",
      "tour.structureLook.title": "En savoir plus",
      "tour.structureLook.body":
        "Chaque panneau s'ouvre sur une image et une description Wikipédia en direct. <b>Faites défiler</b> vers le bas pour continuer.",
      "tour.openProjections.title": "Ouvrir les projections",
      "tour.openProjections.body":
        "Dernier type de nœud : les voies entre régions. Cliquez sur <b>Projections et circuits</b>.",
      "tour.projectionTap.title": "Un système entier",
      "tour.projectionTap.body":
        "Cliquez sur le système <b>dopamine</b>. Il épingle d'un coup toutes les voies dopaminergiques.",
      "tour.projectionLook.title": "En savoir plus",
      "tour.projectionLook.body":
        "Ses <b>voies membres</b> et une description. <b>Faites défiler</b> vers le bas pour continuer.",
      "tour.backToSettings.title": "Retour au panneau",
      "tour.backToSettings.body":
        "Retour aux commandes. Cliquez sur <b>Réglages</b> pour revenir au panneau principal.",
      "tour.openSearch.title": "Ouvrir la recherche",
      "tour.openSearch.body":
        "Cliquez sur la <b>loupe</b> pour ouvrir la recherche.",
      "tour.search.title": "Tout retrouver",
      "tour.search.body":
        "La <b>recherche</b> mène à toute structure, voie, récepteur ou médicament par son nom (essayez). Vous pouvez aussi filtrer les médicaments par classe.",
      "tour.wrap.title": "Vous êtes prêt",
      "tour.wrap.body":
        "Voilà la visite. Les réglages, le sélecteur EN/FR et une relance de la visite sont dans le panneau (relance depuis <b>À propos</b>). Bonne exploration.",

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
      "info.clinpgx": "ClinPGx ↗",
      "info.clinpgxTitle": "Rechercher sur ClinPGx (pharmacogénomique : variants génétiques et réponse au médicament)",
      "info.clinpgxPathwaysTitle": "Rechercher sur ClinPGx les voies pharmacocinétiques de ce médicament",
      "info.clinpgxEnzymeTitle": "Rechercher cette enzyme sur ClinPGx (variants, phénotypes, adaptation posologique)",
      "info.clinpgxGeneTitle": "Rechercher sur ClinPGx le gène de cette protéine (variants et effet sur la réponse aux médicaments)",
      "info.pathways": "Voies",
      "info.pharmfreq": "PharmFreq ↗",
      "info.pharmfreqTitle": "Parcourir PharmFreq, l’atlas d’où viennent ces fréquences (son outil « Metabolizer status » couvre plus de gènes que nous n’en modélisons)",
      "info.frequencies": "Fréquences",
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
      "info.provUncertain": "Niveau de source : incertaine. La citation ci-dessous figure bien dans la source et porte bien sur ce sujet, mais elle n’énonce jamais cette affirmation précise : elle dit quelque chose de plus large, la rattacher ici est donc une inférence. Les raisons d’en douter sont listées ci-dessus, chacune avec sa propre source.",
      "info.uncertainLead": "Voici des raisons, rédigées par un LLM, de douter de cette affirmation :",
      "uncertain.side_effect_rule": "La phrase source explique un effet indésirable, et son sujet est le mécanisme plutôt que le médicament : elle n’affirme donc jamais que ce médicament a cette action.",
      "uncertain.family_claim": "Une seule phrase de la source couvre {n} sous-types de récepteurs à la fois : elle nomme la famille et jamais ce sous-type précis, dont le découpage relève de notre propre lecture.",
      "uncertain.class_wide": "La même phrase est imprimée sur {n} autres monographies, elle peut donc énoncer une règle sur le mécanisme plutôt qu’une mesure sur ce médicament.",
      "uncertain.measured_ki": "Une affinité mesurée indépendante l’étaye : Ki médian de {ki} nM sur {n} essais.",
      "uncertain.no_measured_ki": "Aucune affinité de liaison mesurée n’a été trouvée pour cette cible : rien d’indépendant n’étaye la phrase.",
      "uncertain.not_a_mechanism": "La source ne cite jamais cette action parmi les mécanismes d’action du médicament.",
      "uncertain.blanket_claim": "Une seule phrase de la source couvre {n} voies issues de cette structure à la fois et ne nomme aucune de leurs cibles : elle décrit l’étendue du système, et la tracer jusqu’à cette région en particulier relève de notre propre lecture.",
      "uncertain.contradicted": "Une autre source de ce jeu de données affirme le contraire, et elle est citée ci-dessous. Les corpus divergent le plus souvent sur ce qu’une mesure de laboratoire signifie chez l’être vivant (un effet réel in vitro qui ne se retrouve pas in vivo) : les deux sont donc conservées ici plutôt que l’une écartée en silence.",
      "info.quoteChain": "Parcours de cette citation :",
      "quotechain.raw_data": "données brutes",
      "quotechain.page": "page source",
      "quotechain.extract_code": "extraction déterministe",
      "quotechain.extract_llm": "un LLM trouve la citation",
      "quotechain.gate": "le code vérifie que la citation est sur la page",
      "quotechain.judge_llm": "un LLM amnésique juge la citation",
      "quotechain.neurarium": "neurarium",
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
      "receptor.density": "Quantité relative",
      "receptor.densityAgreement": "accord entre donneurs r = {r}",
      "receptor.densityTip": "La quantité présente dans chaque région, rapportée à la moyenne de ce gène sur l'ensemble du cerveau. Mesure d'ARNm (puces à ADN de l'Allen Human Brain Atlas) : c'est donc du transcrit et non de la protéine, et il se situe dans les corps cellulaires plutôt qu'au bout des projections. Un transporteur ressort donc surtout dans son noyau d'origine, pas dans les régions où il agit.",
      "receptor.densityAgreementTip": "À quel point les {donors} cerveaux donneurs reproduisent ce profil (corrélation entre leurs mesures). Proche de 1, tous classent les régions de la même façon ; une valeur basse signalerait un gène proche du bruit de mesure, et seuls les profils au-dessus de {min} sont affichés.",
      "receptor.densityValueTip": "{z} écarts-types par rapport à la moyenne de ce gène sur tout le cerveau.",
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
      "drug.halfLife": "Demi-vie",
      "drug.pkTiming": "Chronologie",
      "drug.tmax": "Délai du pic",
      "drug.tmaxTip": "Combien de temps après une prise orale unique la concentration sanguine atteint son maximum (Tmax). Il dit quand le médicament arrive, là où la demi-vie dit combien de temps il met à partir.",
      "drug.nonLinearPk": "Pharmacocinétique non linéaire détectée. En savoir plus dans la section Métabolisme ci-dessous ; cliquez pour y aller.",
      "drug.hlMinutes": "min",
      "drug.hlHours": "h",
      "drug.hlDays": "jours",
      "drug.metabolites": "Métabolites actifs",
      "drug.metaboliteOf": "métab. de {prodrug}",
      "drug.metabSeeBindings": "Voir ses {n} liaisons →",
      "drug.formedBy": "formé par",
      "drugs.showMetabolites": "Afficher les métabolites actifs",
      "drug.metabolism": "Métabolisme",
      "drug.metabolismHint": "Les enzymes hépatiques qui éliminent ce médicament, ou dont il modifie l'activité. Pharmacocinétique : rien n'est allumé dans la vue 3D.",
      "panel.themeLight": "Passer au thème clair",
      "panel.themeDark": "Passer au thème sombre",
      "drug.autoPkTitle": "Pharmacocinétique non linéaire",
      "drug.autoPkInhibits": "Ce médicament figure ci-dessous à la fois comme substrat et comme inhibiteur du {enzymes} : il pourrait donc ralentir sa propre élimination, et les concentrations sanguines augmenter plus vite que la dose.",
      "drug.autoPkInduces": "Ce médicament figure ci-dessous à la fois comme substrat et comme inducteur du {enzymes} : il pourrait donc accélérer sa propre élimination au fil des premières semaines, et les concentrations sanguines baisser à dose constante.",
      "drug.autoPkDerived": "Déduit des lignes d'enzymes ci-dessous, dont chacune porte sa propre source. Aucune source n'énonce cette conséquence pour ce médicament : rapprocher les deux rôles relève de notre lecture.",
      "drug.pkInteractions": "Interactions médicamenteuses",
      "drug.pkInteractionsHint": "Déduit des enzymes ci-dessus, non mesuré : ce médicament et celui listé se rencontrent sur la même enzyme, donc l'un pourrait déplacer la concentration sanguine de l'autre. « Pourrait augmenter » signifie que la concentration de l'autre pourrait monter (celui-ci inhibe l'enzyme qui l'élimine), « pourrait diminuer » qu'elle pourrait baisser (il l'induit). Que cela compte vraiment dépend de la dose, de la voie et de la personne : c'est un signal à vérifier avec un prescripteur, jamais une contre-indication, et l'absence de ligne ne vaut pas garantie d'innocuité.",
      "info.more": "+{n} de plus",
      "structure.expressed": "Récepteurs présents ici",
      "structure.expressedCaption": "Récepteurs et autres cibles médicamenteuses dont la liste d’expression nomme cette région, regroupés par système de neurotransmission. Chaque ligne porte la note de source propre à cette région, la même affirmation que la fiche du récepteur montre depuis l’autre bout.",
      "structure.expressedEverywhere": "dans tout le cerveau",
      "drug.pkByDrug": "Par médicament",
      "drug.pkByEnzyme": "Par enzyme",
      "drug.pkHeadRaises": "Pourrait augmenter la concentration de",
      "drug.pkHeadLowers": "Pourrait diminuer la concentration de",
      "drug.pkHeadRaisedBy": "Sa concentration pourrait être augmentée par",
      "drug.pkHeadLoweredBy": "Sa concentration pourrait être diminuée par",
      "enzyme.heading": "Enzyme du métabolisme",
      "enzyme.drugs": "Médicaments sur cette enzyme",
      "enzyme.forms": "Métabolites actifs qu'elle forme",
      "enzyme.formsOf": "à partir de {drug}",
      "enzyme.noDrugs": "Aucun médicament enregistré sur cette enzyme.",
      "enzyme.variability": "Vitesse d'élimination selon les personnes",
      "enzyme.variabilityCaveat":
        "Fréquence de chaque vitesse d'élimination, par grand groupe de population. "
        + "Ce sont des fréquences observées dans des cohortes d'étude, pas une "
        + "prédiction pour une personne donnée : la plupart des groupes contiennent "
        + "toutes les vitesses, et seul un test génétique dit laquelle on a.",
      "enzymes.title": "Enzymes",
      "enzymes.hint": "Les enzymes qui métabolisent les médicaments (surtout les cytochromes P450 du foie). Elles ne font pas partie du cerveau : c'est de la pharmacocinétique, donc en sélectionner une ne change rien à la vue 3D.",
      "drug.actsOn": "Agit sur",
      "drug.noTargets": "Aucune cible moléculaire répertoriée pour l'instant.",
      "drug.projectionsAffected": "Projections concernées",
      "drug.projectionsAffectedHint": "Voies ascendantes dont ce médicament règle le tonus. Déduit de ses liaisons régulatrices (recapture, enzyme, vésicule ou autorécepteur) ; une flèche sortante augmente le tonus du système, une flèche entrante le baisse.",
      "drug.actsWithin": "Agit au sein de",
      "drug.actsWithinHint": "Systèmes que ce médicament n'engage qu'à travers un récepteur postsynaptique. Leurs voies sont éclairées à titre indicatif (sans billes) : bloquer un récepteur postsynaptique ne modifie pas en soi le tonus du neurotransmetteur.",
      "drug.stubHint": "Aucun profil de liaison enregistré pour l'instant",
      "drug.speculative": "spéculative",
      "drug.affinityOnly": "affinité seule, sens non établi",
      "drug.actionNoSource": "Aucune source ne dit si la cible est activée ou bloquée",
      "drug.actionLlm": "Le sens est énoncé de mémoire ; seule la liaison elle-même est sourcée",
      "drug.peripheral": "hors du cerveau, donc rien ne s’allume",
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
      "loading.shapes": "Chargement des formes… ({done}/{total})",
      "loading.meshing": "Construction : {name}… ({done}/{total})",
      "loading.geometry": "Chargement des formes 3D… ({done}/{total})",
      "loading.building": "Assemblage du cerveau…",
      "loading.reducedQuality":
        "Cet appareil construit les maillages lentement : les structures restantes ont donc été générées avec moins de détail pour garder un temps de chargement raisonnable. Les données ne sont pas affectées, seules les formes 3D sont un peu plus lisses.",
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
      "about.animCaveat":
        "<strong>Les animations de médicaments sont de loin l’aspect le moins " +
        "scientifique de neurarium et sont encore très largement en cours " +
        "d’élaboration</strong> : voyez-les comme une illustration évolutive, pas " +
        "comme un fait établi.",
      "about.animSummary": "Ce que signifient les animations",
      "about.animIntro":
        "L’animation des médicaments est un modèle de <em>réglage du tonus</em>, pas une " +
        "image littérale de molécules circulant dans le cerveau. Tout ce qui suit est " +
        "dérivé des données de liaison du médicament, et évolue donc avec elles.",
      "about.animList":
        "<li><b>Billes-gemmes colorées à la surface d’une structure cérébrale : un " +
        "récepteur lié par ce médicament y est exprimé.</b> Les billes sont dispersées " +
        "sur chaque région qui exprime cette cible, et leur couleur dit ce que le " +
        "médicament lui fait :" +
        "<ul>" +
        "<li>vert = il la renforce (agoniste, inhibiteur de recapture, libérateur)</li>" +
        "<li>rouge = il la bloque (antagoniste, agoniste inverse, bloqueur)</li>" +
        "<li>violet = il la module (agoniste partiel, modulateur)</li>" +
        "</ul>" +
        "Des billes plus denses et plus vives signalent une affinité mesurée plus forte : " +
        "la cible principale d’un médicament ressort donc davantage qu’une cible " +
        "secondaire. Sélectionner un récepteur seul utilise les mêmes billes sans le code " +
        "couleur : elles disent alors seulement <em>exprimé ici</em>.</li>" +
        "<li><b>Des billes qui filent le long d’une flèche : le médicament déplace le " +
        "tonus de tout un système.</b> Seules les liaisons qui <em>règlent le tonus</em> " +
        "le font (inhibiteurs de recapture, inhibiteurs d’enzyme, bloqueurs vésiculaires, " +
        "autorécepteurs présynaptiques) ; un médicament purement postsynaptique n’a que " +
        "des billes et une lueur, et aucun flux. Le sens du déplacement se lit dans les " +
        "billes :" +
        "<ul>" +
        "<li>chaudes, vives, rapides et denses = il augmente le tonus du système</li>" +
        "<li>froides, ternes, lentes et clairsemées = il le diminue</li>" +
        "</ul>" +
        "Vitesse et densité sont normalisées <em>par médicament</em> : ce que vous lisez " +
        "est lequel de ses systèmes il engage le plus, jamais une dose absolue. Guettez " +
        "le cas contre-intuitif : un antipsychotique qui bloque l’<em>autorécepteur</em> " +
        "D2 se lit comme une hausse du tonus dopaminergique, tandis que son blocage des " +
        "récepteurs D2 postsynaptiques apparaît dans les billes rouges.</li>" +
        "<li><b>Des billes qui s’allument en séquence plutôt qu’en flux : c’est un " +
        "circuit, pas un médicament.</b> Sélectionner un circuit nommé joue son signal " +
        "dans l’ordre, chaque tronçon s’allumant une fois atteint par celui qui " +
        "l’alimente, avec une onde de lumière là où chaque bille arrive. Une sélection de " +
        "médicament produit un flux continu : un médicament ne déclenche pas un circuit, " +
        "il change un niveau de fond.</li>" +
        "<li><b>Une lueur qui baigne toute une région : les mêmes billes, d’un coup " +
        "d’œil.</b> Une lueur par région et par effet, dans les mêmes vert / rouge / " +
        "violet, pour qu’une région portant vingt cibles du médicament brille une fois " +
        "et non vingt.</li>" +
        "<li><b>Un liseré pâle autour d’une structure : c’est celle que vous avez " +
        "sélectionnée.</b> Le survol affiche son nom ; le clic l’épingle et ouvre sa " +
        "fiche.</li>" +
        "<li><b>Une flèche en pointillés plutôt que pleine : cette voie est " +
        "hypothétique.</b> La connexion est proposée plutôt que bien établie, et sa note " +
        "de source dans la fiche dit à quel point elle est étayée.</li>",
      "about.dataSummary": "Cliquez pour accéder aux données structurées",
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
        "un ticket sur GitHub</a>.",
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
      "changelog.title": "Nouveautés",
      "changelog.openLink": "Nouveautés →",
      "changelog.commit": "Voir ce changement dans le dépôt du code source",
      "changelog.empty": "Pas encore de notes de version.",
      "changelog.showAll": "Voir toutes les notes de version",
      "changelog.cat.added": "Nouveau",
      "changelog.cat.improved": "Améliorations",
      "changelog.cat.fixed": "Corrections",
      "changelog.cat.data": "Données et sources",
      "changelog.cat.docs": "Documentation",
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
      "about.gradeLlm":
        "IA seule : peut être une hallucination.",
      "about.gradeNone": "Sans source : aucune réunie pour l’instant.",
      "about.quoteChains": "Toutes les coches vertes ne s’obtiennent pas de la même manière : certaines citations ont été recopiées d’un tableau lisible par machine par du code seul, d’autres ont été trouvées sur une page de livre par un LLM, vérifiées mot pour mot sur cette page, puis jugées par un second LLM qui n’avait pas vu le raisonnement du premier. Chaque infobulle de source se termine par le parcours exact qui l’a produite, pour que vous puissiez en juger vous-même.",
      "about.gradeUncertain":
        "Incertain : la citation est bien présente, mais elle n’attribue pas " +
        "l’affirmation. Survolez le badge pour les raisons, chacune avec sa source.",
      "about.segVerified": "Vérifié",
      "about.segUncertain": "Incertain",
      "about.segSourced": "Sourcé",
      "about.segLlm": "IA seule",
      "about.segNone": "Sans source",
      "about.coverageTitle": "Couverture",
      "about.sourcingHeadline":
        "{pct} % des {total} nœuds de connaissance ici sont sourcés ou vérifiés.",
      "about.sourcingByKind": "Détailler par type de nœud",
      "about.exampleLead": "p. ex.",
      "about.kiCoverage":
        "Affinité de liaison mesurée (Ki PDSP) : {pct} % des {total} liaisons en portent une ; {drugsNone} des {drugs} médicaments n'en ont aucune (sourcés par citation ou sans source).",
      "about.sourcingBrowser":
        "Chacun des nœuds comptés ci-dessus est listé un par un dans l'explorateur "
        + "de données, avec sa propre source, filtrable par type et par qualité de sourçage.",
      "about.sourcingBrowserLink": "Ouvrir l'explorateur de données \u2192",
      "about.kindBindings": "Liaisons cibles des médicaments",
      "about.kindBindingAction": "Sens des liaisons médicamenteuses",
      "about.kindNbn": "Nomenclature des médicaments (NbN)",
      "about.kindDrugBrands": "Noms commerciaux des médicaments",
      "about.kindDrugCategories": "Classe du médicament",
      "about.kindDrugHalfLife": "Demi-vie du médicament (T½)",
      "about.kindDrugTmax": "Délai du pic du médicament (Tmax)",
      "about.kindDrugEnzymes": "Enzymes du métabolisme du médicament",
      "about.kindEnzymeVariability": "Vitesse d'élimination par population",
      "about.kindDrugMetabolites": "Métabolites actifs du médicament",
      "about.kindDrugMetaboliteEnzyme": "Enzymes formant les métabolites",
      "about.kindDrugMetaboliteBindings": "Liaisons des métabolites",
      "about.kindProjections": "Voies neuronales",
      "about.kindProjectionTransmitter": "Neurotransmetteur de la voie",
      "about.kindProjectionSign": "Signe de la voie (excitateur/inhibiteur)",
      "about.kindCircuits": "Circuits fonctionnels",
      "about.kindProjectionGroups": "Groupes de projections",
      "about.kindReceptors": "Système/famille du récepteur",
      "about.kindReceptorClass": "Classe mécanistique du récepteur",
      "about.kindReceptorSign": "Signe du récepteur (excitateur/inhibiteur)",
      "about.kindReceptorSynaptic": "Site pré/postsynaptique du récepteur",
      "about.kindReceptorLocations": "Régions d'expression des récepteurs",
      "about.kindReceptorDensity": "Quantité relative des récepteurs par région",
      "about.kindTargets": "Classifications des cibles",
      "about.kindTargetPolarity": "Polarité tonique de la cible",
      "about.kindTargetLocations": "Régions d'expression des cibles",
      "about.kindTargetDensity": "Quantité relative des cibles par région",
      "about.kindStructures": "Anatomie des régions",
      "about.kindAddons": "Annotations de panneau",

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
