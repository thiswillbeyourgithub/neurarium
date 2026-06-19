// Red, dismissible error banners stacked at the top of the page.
//
// Instead of hiding failures in the eruda console (which a visitor would never
// open), anything that goes wrong is shown as an explicit red banner in the
// shared #banners stack (alongside the optional dev banner): the real error
// message, and where it came from, so it is actionable rather than a vague
// "something went wrong". Multiple errors pile up as separate banners (they do
// not overwrite each other); each has a × button to dismiss it. Identical errors
// are de-duplicated into a single banner with an "(×N)" repeat counter, so a
// fault firing every animation frame can't flood the screen.
//
// Plain script (not a module), loaded before the other scripts that might fail
// so its window error handlers are already installed. Exposes a global
// `window.showErrorBanner(message)` so app code (e.g. js/main.js's data-load
// catch) can surface its own explicit errors the same way.

(function () {
  // UI strings via the shared catalogue (js/i18n.js ran first). Fall back to the
  // key if i18n didn't load, so an error is still surfaced rather than swallowed.
  const t = (k, v) => (window.__I18N__ ? window.__I18N__.t(k, v) : k);

  const container = document.getElementById("banners");
  // message -> { banner, count, countEl }, so a repeat bumps the counter instead
  // of stacking a duplicate, and dismissing frees the message to show again.
  const active = new Map();
  // Safety cap so a storm of *distinct* errors can't bury the whole viewport.
  const MAX_BANNERS = 6;

  function showErrorBanner(message) {
    if (!container || !message) return;
    message = String(message);

    const existing = active.get(message);
    if (existing) {
      existing.count += 1;
      existing.countEl.textContent = ` (×${existing.count})`;
      return;
    }
    if (active.size >= MAX_BANNERS) return;

    const banner = document.createElement("div");
    banner.className = "error-banner";
    banner.setAttribute("role", "alert");

    const text = document.createElement("span");
    text.textContent = message;
    const countEl = document.createElement("span"); // filled on repeats

    const close = document.createElement("button");
    close.type = "button";
    close.className = "banner-close";
    close.setAttribute("aria-label", t("error.dismiss"));
    close.textContent = "×"; // ×
    close.addEventListener("click", () => {
      banner.remove();
      active.delete(message);
    });

    banner.append(text, countEl, close);
    container.appendChild(banner); // newest stacks below the dev banner / earlier errors
    active.set(message, { banner, count: 1, countEl });
  }

  // Surface uncaught script errors. Capture phase so resource-load failures
  // (which don't bubble) are caught too.
  window.addEventListener("error", (event) => {
    if (event.message || event.error) {
      const file = event.filename
        ? ` (${event.filename.split("/").pop()}:${event.lineno || 0})`
        : "";
      showErrorBanner(`${t("error.prefix", { msg: event.message || event.error })}${file}`);
    } else if (event.target && (event.target.src || event.target.href)) {
      // A failed <script>/<img>/<link> etc.: name what didn't load.
      showErrorBanner(t("error.failedLoad", { what: event.target.src || event.target.href }));
    }
  }, true);

  // Promise rejections that nothing caught (e.g. a failed fetch not awaited).
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    const text = (reason && (reason.message || reason.toString())) || reason;
    showErrorBanner(t("error.unhandled", { msg: text }));
  });

  // Keep the top-anchored #status pill below however many banners are stacked,
  // by republishing the stack's height as a CSS variable (consumed in the
  // #status rule). One observer covers the dev banner appearing and every error
  // banner added/removed.
  if (container && "ResizeObserver" in window) {
    new ResizeObserver(() => {
      document.body.style.setProperty("--banners-height", `${container.offsetHeight}px`);
    }).observe(container);
  }

  window.showErrorBanner = showErrorBanner;
})();
