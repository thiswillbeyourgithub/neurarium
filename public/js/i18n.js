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
      "panel.legend": "Legend",
      "panel.receptors": "Receptors",
      "panel.about": "About",

      "toolbar.reset": "Reset view",
      "toolbar.search": "Search",
      "toolbar.searchAria": "Search structures and connections",
      "search.placeholder": "Search structure or connection...",
      "search.noMatch": "No match",

      "legend.showNames": "Show all names",
      "legend.hideNames": "Hide all names",
      "legend.hideProjections": "Hide projections",
      "legend.showProjections": "Show projections",
      "legend.projections": "Projections",
      "legend.circuits": "Circuits",
      "legend.hypothetical": "Hypothetical pathways",
      "legend.hypotheticalHint":
        "Less-certain connections, drawn as dotted arrows. Off by default.",
      "legend.showSpeculative": "Show speculative",
      "legend.hideSpeculative": "Hide speculative",

      "info.connection": "Connection",
      "info.sources": "Sources",
      "info.source": "Source",
      "info.linkTodo": " (link: TODO)",
      "info.wikipedia": "Wikipedia ↗",
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

      "status.loading": "Loading brain data…",
      "status.loadError":
        "Could not load brain data: {msg}. Are you serving over HTTP? (see CLAUDE.md)",

      "about.p1":
        "neurarium is a work-in-progress, interactive 3D map of brain regions " +
        "and the neuron projections between them. The shapes are schematic, " +
        "meant to help you find and relate structures, not to be anatomically " +
        "exact.",
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
      "about.sourceCode": "Source code",
      "about.license":
        'Licensed under the <a href="https://www.gnu.org/licenses/agpl-3.0.html" ' +
        'target="_blank" rel="noopener noreferrer">GNU AGPL-3.0</a>.',

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
      "panel.legend": "Légende",
      "panel.receptors": "Récepteurs",
      "panel.about": "À propos",

      "toolbar.reset": "Recentrer la vue",
      "toolbar.search": "Rechercher",
      "toolbar.searchAria": "Rechercher structures et connexions",
      "search.placeholder": "Rechercher une structure ou une connexion…",
      "search.noMatch": "Aucun résultat",

      "legend.showNames": "Afficher tous les noms",
      "legend.hideNames": "Masquer les noms",
      "legend.hideProjections": "Masquer les projections",
      "legend.showProjections": "Afficher les projections",
      "legend.projections": "Projections",
      "legend.circuits": "Circuits",
      "legend.hypothetical": "Voies hypothétiques",
      "legend.hypotheticalHint":
        "Connexions moins certaines, tracées en pointillés. Masquées par défaut.",
      "legend.showSpeculative": "Afficher les spéculatives",
      "legend.hideSpeculative": "Masquer les spéculatives",

      "info.connection": "Connexion",
      "info.sources": "Sources",
      "info.source": "Source",
      "info.linkTodo": " (lien : TODO)",
      "info.wikipedia": "Wikipédia ↗",
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

      "status.loading": "Chargement des données du cerveau…",
      "status.loadError":
        "Impossible de charger les données : {msg}. Le site est-il servi via HTTP ? (voir CLAUDE.md)",

      "about.p1":
        "neurarium est une carte 3D interactive, en cours de développement, " +
        "des régions cérébrales et des projections neuronales qui les " +
        "relient. Les formes sont schématiques : elles aident à situer et " +
        "relier les structures, sans prétendre à l’exactitude anatomique.",
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
      "about.sourceCode": "Code source",
      "about.license":
        'Sous licence <a href="https://www.gnu.org/licenses/agpl-3.0.html" ' +
        'target="_blank" rel="noopener noreferrer">GNU AGPL-3.0</a>.',

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
