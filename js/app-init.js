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
