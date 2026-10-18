// Lightweight, no-build internationalization (en / fr).
//
// This is a CLASSIC script (like app-config.js / version.js), loaded early so
// every later script - the ES module viewer (js/main.js) AND the classic banner
// scripts (js/error-banner.js, js/dev-banner.js) - can read `window.__I18N__`.
//
// It owns ONE message catalogue (the single source of every UI string, in both
// languages; each language's table lives in js/i18n/<lang>.js, loaded just before
// this script) plus the language choice. The translatable *data* strings (region
// names, pathway labels, ...) are NOT here: the data file holds them in English
// and js/data.js resolves each through the French side table using the language
// picked here (see `pick`). Because js/data.js resolves at load time, switching the
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

  // The per-language string tables, each its own classic script loaded just before
  // this one (js/i18n/en.js, js/i18n/fr.js).
  var MESSAGES = window.__I18N_MESSAGES__;

  var lang = detectLang();

  // Look up a UI string, with optional {token} interpolation. Falls back to the
  // English entry, then to the key itself, so a missing translation is visible
  // but never blank. `fill` maps each interpolated value to its text.
  function format(key, vars, fill) {
    var table = MESSAGES[lang] || MESSAGES.en;
    var s = table[key];
    if (s == null) s = MESSAGES.en[key];
    if (s == null) return key;
    if (vars) {
      s = s.replace(/\{(\w+)\}/g, function (m, name) {
        return name in vars ? fill(String(vars[name])) : m;
      });
    }
    return s;
  }

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function t(key, vars) {
    return format(key, vars, String);
  }

  // `t` for a string bound for innerHTML: the catalogue entry's own markup is kept
  // (it is authored here, trusted) but every interpolated value is HTML-escaped.
  function tHtml(key, vars) {
    return format(key, vars, escapeHtml);
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
  // an identical en==fr pair we deliberately did not store). Anything else (null,
  // a number) passes through. Used by js/data.js and the viewer.
  function pick(field) {
    if (typeof field === "string") {
      return (lang === "fr" && DATA_FR[field] != null) ? DATA_FR[field] : field;
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

  // A noun filling a slot that French reads as "de <noun>": the French template drops
  // its "de" and this supplies it, elided before a vowel or mute h ("libération
  // d'histamine", "de dopamine"). English gets the bare noun.
  function ofNoun(word) {
    if (lang !== "fr") return word;
    return /^[aeiouyhàâéèêîïôûœ]/i.test(word) ? "d'" + word : "de " + word;
  }

  window.__I18N__ = {
    lang: lang,
    t: t,
    tHtml: tHtml,
    ofNoun: ofNoun,
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
