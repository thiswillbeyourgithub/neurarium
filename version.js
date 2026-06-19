// Single source of truth for the app version, shown in the Neurarium panel
// header and (when enabled) the DEV "work in progress" banner.
//
// A plain global (like app-config.js) rather than an ES module, so both the
// module code (js/main.js) and the classic scripts (js/dev-banner.js) can read
// it with no build step. Loaded early in index.html's <head>.
//
// Bump this on a release. Semantic versioning: MAJOR.MINOR.PATCH.
window.__APP_VERSION__ = "0.5.0";
