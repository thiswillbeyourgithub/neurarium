// Injects a privacy-friendly umami metrics tag when configured at runtime.
//
// Config arrives in window.__APP_CONFIG__ from app-config.js, which the
// container fills from docker/.env (see docker/Caddyfile). When the values are
// empty or still contain the un-substituted "{{" template placeholders (local
// dev, or metrics disabled), this is a no-op so the page works offline and
// without any tracking. (Both files are named generically so content filters /
// proxies that block "analytics" paths don't 404 them; see app-config.js.)

const cfg = window.__APP_CONFIG__ || {};

/** A value is "set" only if it is a non-empty, non-placeholder string. */
function isSet(value) {
  return typeof value === "string" && value.length > 0 && !value.startsWith("{{");
}

// Value for umami's data-do-not-track attribute, mirroring WebSend's UMAMI_DNT:
// "true" (the default) respects the browser's Do Not Track signal so those
// visitors are not tracked; "false" tracks everyone. Any other value, including
// the un-substituted "{{...}}" placeholder, falls back to the privacy-friendly
// "true" default.
function resolveDnt(value) {
  return typeof value === "string" && value.trim().toLowerCase() === "false"
    ? "false"
    : "true";
}

if (isSet(cfg.url) && isSet(cfg.websiteId)) {
  const script = document.createElement("script");
  script.defer = true;
  script.src = cfg.url;
  script.setAttribute("data-website-id", cfg.websiteId);
  // Always emit data-do-not-track explicitly so the chosen behavior is visible.
  script.setAttribute("data-do-not-track", resolveDnt(cfg.dnt));
  // Optional Subresource Integrity for the umami script (requires CORS).
  if (isSet(cfg.sri)) {
    script.integrity = cfg.sri;
    script.crossOrigin = "anonymous";
  }
  document.head.appendChild(script);
}

// A guarded event tracker: forwards to umami when it loaded (and only then, so a
// dev / metrics-disabled build sends nothing and stays offline), swallowing any
// error. Exposed as window.trackEvent so any module can emit a semantic event
// (e.g. main.js records which node the user focused, the thing we most want to
// learn: "what are users interested about"). Umami respects the DNT signal above,
// so this stays privacy-friendly.
window.trackEvent = function trackEvent(name, data) {
  try {
    if (window.umami && typeof window.umami.track === "function") {
      window.umami.track(name, data);
    }
  } catch (_) { /* metrics are best-effort, never break the app */ }
};

// Delegated click analytics: one capture-phase listener records every button /
// toolbar / detail-tab / legend-row / link click, labelled by (in priority) an
// explicit data-track, its aria-label, its id, or its trimmed text. No per-call-site
// wiring, and a no-op when umami is absent.
document.addEventListener("click", (ev) => {
  const el = ev.target.closest(
    "[data-track], button, .legend-item, .detail-tab, .panel-tab, #search-results li, a[href]");
  if (!el) return;
  const label = (el.getAttribute("data-track")
    || el.getAttribute("aria-label")
    || el.id
    || (el.textContent || "").trim()).slice(0, 60);
  if (label) window.trackEvent("click", { target: label });
}, { capture: true });
