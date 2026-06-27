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

      "panel.separate": "Separate",
      "panel.transparency": "Transparency",
      "panel.autorotate": "Auto-rotate",
      "panel.seeInside": "See inside",
      "panel.arrowColors": "Arrow colours",
      "panel.colorNt": "Neurotransmitter",
      "panel.colorPotential": "Potential",
      "panel.structures": "Structures",
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
      "search.syntaxLabel": "Search syntax",
      "search.syntax": "Type to search by name. Filters: <code>class:&quot;SSRI&quot;</code> drugs of a class, <code>nbn:&quot;…&quot;</code> by nomenclature. Tip: click a drug's <b>Class</b> or <b>Nomenclature</b> to fill one in.",

      "shortcuts.title": "Keyboard shortcuts",
      "shortcuts.names": "Toggle all names",
      "shortcuts.spread": "Spread / collapse",
      "shortcuts.structures": "Toggle the structures",
      "shortcuts.projections": "Toggle the projections",
      "shortcuts.legend": "Toggle the legend key",
      "shortcuts.seeInside": "Toggle see inside",
      "shortcuts.receptors": "Toggle Receptors & targets",
      "shortcuts.drugs": "Toggle the Drugs section",
      "shortcuts.search": "Open search",
      "shortcuts.tabs": "Switch between tabs",
      "shortcuts.close": "Close search / collapse sections",

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
      "legendKey.pathways": "Pathways",
      "legendKey.speculative": "Speculative pathway (dotted)",

      "info.connection": "Connection",
      "info.sources": "Sources",
      "info.source": "Source",
      "info.noSource": "NOSOURCE",
      "info.wikipedia": "Wikipedia ↗",
      "info.reference": "Reference",
      "info.provNone": "No source for this claim yet.",
      "info.provLlm": "Source grade: LLM-only. Produced by an LLM from memory and not checked against any document, so it may be a hallucination.",
      "info.provSourced": "Source grade: sourced. Written by an LLM that was given the source document (e.g. Stahl's guide), but this specific claim was not quote-verified.",
      "info.provVerified": "Source grade: verified. An LLM extracted a quote, it was programmatically confirmed to appear in the source, and a separate LLM agreed the quote supports the claim. This is still the highest grade available here and remains LLM-driven, so it can still be wrong: going further would take considerable human effort and is itself error-prone, so it is out of scope for this project.",
      "info.descFromWikipedia": "This description is the lead section of the drug's Wikipedia article, used verbatim under CC BY-SA. See the Reference link above.",
      "info.descFromWikipediaLive": "This description was just fetched live from the drug's Wikipedia article (CC BY-SA), so it reflects the current article rather than a stored copy. See the Reference link above.",
      "info.sourceRef": "{corpus}, p. {page}",
      "info.noConnections": "No mapped connections yet.",
      "info.connections": "Connections",

      "receptor.system": "System",
      "receptor.neurotransmitter": "Neurotransmitter",
      "receptor.type": "Type",
      "receptor.effect": "Effect",
      "receptor.synaptic": "Synaptic site",
      "receptor.foundIn": "Found in",
      "receptor.ubiquitous": "Throughout the brain",
      "receptor.noRole": "No significant role in the central nervous system.",
      "receptor.stubHint": "No significant role in the central nervous system",
      "targets.otherSystem": "Other / non-aminergic",
      "targets.interactingDrugs": "Interacting drugs",

      "panel.drugs": "Drugs",
      "drugs.filter": "Filter drugs…",
      "drugs.none": "No matching drug.",
      "drug.class": "Class",
      "drug.nomenclature": "Nomenclature",
      "drug.actsOn": "Acts on",
      "drug.noTargets": "No mapped molecular targets yet.",
      "drug.source": "Source",
      "drug.stubHint": "No binding profile recorded yet",
      "drug.speculative": "speculative",
      "drug.structureAlt": "Chemical structure of {name}",

      "status.loading": "Loading brain data…",
      "status.loadError":
        "Could not load brain data: {msg}. Are you serving over HTTP? (see CLAUDE.md)",

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
      "about.sourcingIntro":
        "Every fact in this dataset carries a source grade. None of it has been " +
        "checked by a human yet, so even a verified fact can be wrong. The grades:",
      "about.gradeVerified":
        "Verified: the supporting quote was confirmed present in the cited source.",
      "about.gradeSourced":
        "Sourced: drawn from a document (e.g. Wikipedia), but the quote was not checked.",
      "about.gradeLlm":
        "LLM-only: produced by the model from memory; may be a hallucination.",
      "about.gradeNone": "No source: none gathered yet.",
      "about.coverageTitle": "Coverage",
      "about.sourcingHeadline":
        "{pct}% of the {total} factual claims here are sourced or verified.",
      "about.kindBindings": "Drug target bindings",
      "about.kindNbn": "Drug nomenclature (NbN)",
      "about.kindDescriptions": "Drug descriptions",
      "about.kindProjections": "Neuron pathways",
      "about.kindReceptors": "Receptor classifications",
      "about.kindTargets": "Target classifications",
      "about.kindStructures": "Brain-region anatomy",
      "about.kindReferences": "Reference links",
      "about.coverageNote":
        "Neuron pathways and reference links are the remaining gap.",

      "dev.wip": "Work in progress",
      "dev.restarted":
        "This container was last restarted {ago}, so it is actively being developed. ",
      "dev.activelyDeveloped": "This site is actively being developed. ",
      "dev.stayTuned": "Stay tuned, or come back later.",
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

      "panel.separate": "Séparer",
      "panel.transparency": "Transparence",
      "panel.autorotate": "Rotation auto",
      "panel.seeInside": "Voir l'intérieur",
      "panel.arrowColors": "Couleur des flèches",
      "panel.colorNt": "Neurotransmetteur",
      "panel.colorPotential": "Potentiel",
      "panel.structures": "Structures",
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
      "search.syntaxLabel": "Syntaxe de recherche",
      "search.syntax": "Tapez pour rechercher par nom. Filtres : <code>classe:&quot;IRSN&quot;</code> les médicaments d'une classe, <code>nbn:&quot;…&quot;</code> par nomenclature. Astuce : cliquez la <b>Classe</b> ou la <b>Nomenclature</b> d'un médicament pour en remplir un.",

      "shortcuts.title": "Raccourcis clavier",
      "shortcuts.names": "Afficher / masquer les noms",
      "shortcuts.spread": "Séparer / rassembler",
      "shortcuts.structures": "Afficher / masquer les structures",
      "shortcuts.projections": "Afficher / masquer les projections",
      "shortcuts.legend": "Afficher / masquer la légende",
      "shortcuts.seeInside": "Voir l'intérieur",
      "shortcuts.receptors": "Ouvrir Récepteurs et cibles",
      "shortcuts.drugs": "Ouvrir la section Médicaments",
      "shortcuts.search": "Ouvrir la recherche",
      "shortcuts.tabs": "Naviguer entre les onglets",
      "shortcuts.close": "Fermer la recherche / replier les sections",

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
      "legendKey.pathways": "Voies",
      "legendKey.speculative": "Voie hypothétique (pointillés)",

      "info.connection": "Connexion",
      "info.sources": "Sources",
      "info.source": "Source",
      "info.noSource": "SANS SOURCE",
      "info.wikipedia": "Wikipédia ↗",
      "info.reference": "Référence",
      "info.provNone": "Aucune source pour cette affirmation pour l’instant.",
      "info.provLlm": "Niveau de source : LLM seul. Produite de mémoire par un LLM, sans vérification dans aucun document : il peut donc s’agir d’une hallucination.",
      "info.provSourced": "Niveau de source : documentée. Rédigée par un LLM ayant eu accès au document source (par ex. le guide de Stahl), mais cette affirmation précise n’a pas été vérifiée par citation.",
      "info.provVerified": "Niveau de source : vérifiée. Un LLM a extrait une citation, sa présence dans la source a été confirmée par programme, et un second LLM a confirmé qu’elle étaye l’affirmation. C’est le niveau le plus élevé disponible ici et il reste piloté par un LLM : il peut donc encore se tromper. Aller plus loin demanderait un effort humain considérable, lui-même sujet à erreur, et sort donc du cadre de ce projet.",
      "info.descFromWikipedia": "Cette description est l’introduction de l’article Wikipédia du médicament, reprise telle quelle sous licence CC BY-SA. Voir le lien Référence ci-dessus.",
      "info.descFromWikipediaLive": "Cette description vient d’être récupérée en direct depuis l’article Wikipédia du médicament (CC BY-SA) : elle reflète donc l’article actuel plutôt qu’une copie enregistrée. Voir le lien Référence ci-dessus.",
      "info.sourceRef": "{corpus}, p. {page}",
      "info.noConnections": "Aucune connexion répertoriée pour l’instant.",
      "info.connections": "Connexions",

      "receptor.system": "Système",
      "receptor.neurotransmitter": "Neurotransmetteur",
      "receptor.type": "Type",
      "receptor.effect": "Effet",
      "receptor.synaptic": "Site synaptique",
      "receptor.foundIn": "Présent dans",
      "receptor.ubiquitous": "Dans tout le cerveau",
      "receptor.noRole": "Pas de rôle significatif dans le système nerveux central.",
      "receptor.stubHint": "Pas de rôle significatif dans le système nerveux central",
      "targets.otherSystem": "Autre / non-aminergique",
      "targets.interactingDrugs": "Médicaments en interaction",

      "panel.drugs": "Médicaments",
      "drugs.filter": "Filtrer les médicaments…",
      "drugs.none": "Aucun médicament correspondant.",
      "drug.class": "Classe",
      "drug.nomenclature": "Nomenclature",
      "drug.actsOn": "Agit sur",
      "drug.noTargets": "Aucune cible moléculaire répertoriée pour l'instant.",
      "drug.source": "Source",
      "drug.stubHint": "Aucun profil de liaison enregistré pour l'instant",
      "drug.speculative": "spéculative",
      "drug.structureAlt": "Structure chimique de {name}",

      "status.loading": "Chargement des données du cerveau…",
      "status.loadError":
        "Impossible de charger les données : {msg}. Le site est-il servi via HTTP ? (voir CLAUDE.md)",

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
      "about.sourcingIntro":
        "Chaque fait de ce jeu de données porte un niveau de source. Rien n’a " +
        "encore été vérifié par un humain : même un fait « vérifié » peut être " +
        "faux. Les niveaux :",
      "about.gradeVerified":
        "Vérifié : la citation à l’appui a été confirmée présente dans la source citée.",
      "about.gradeSourced":
        "Sourcé : tiré d’un document (p. ex. Wikipédia), mais la citation n’a pas été vérifiée.",
      "about.gradeLlm":
        "IA seule : produit par le modèle de mémoire ; peut être une hallucination.",
      "about.gradeNone": "Sans source : aucune réunie pour l’instant.",
      "about.coverageTitle": "Couverture",
      "about.sourcingHeadline":
        "{pct} % des {total} affirmations factuelles ici sont sourcées ou vérifiées.",
      "about.kindBindings": "Liaisons cibles des médicaments",
      "about.kindNbn": "Nomenclature des médicaments (NbN)",
      "about.kindDescriptions": "Descriptions des médicaments",
      "about.kindProjections": "Voies neuronales",
      "about.kindReceptors": "Classifications des récepteurs",
      "about.kindTargets": "Classifications des cibles",
      "about.kindStructures": "Anatomie des régions",
      "about.kindReferences": "Liens de référence",
      "about.coverageNote":
        "Les voies neuronales et les liens de référence constituent le manque restant.",

      "dev.wip": "En cours de développement",
      "dev.restarted":
        "Ce conteneur a été redémarré {ago} ; il est donc activement développé. ",
      "dev.activelyDeveloped": "Ce site est activement développé. ",
      "dev.stayTuned": "Revenez plus tard.",
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

  // Resolve a translatable *data* field: a plain string passes through; an
  // {en, fr} object collapses to the current language (then English, then any
  // value). Used by js/data.js and the viewer.
  function pick(field) {
    if (field == null || typeof field === "string") return field;
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
    setLang: setLang,
    applyStatic: applyStatic,
  };

  document.documentElement.lang = lang;
  document.addEventListener("DOMContentLoaded", function () {
    applyStatic(document);
    wireSwitch(document);
  });
})();
