// Optional "work in progress" banner across the top of the page.
//
// When the container is started with DEV=1 (docker/.env -> Caddy templates ->
// app-config.js), this shows a warning banner telling visitors the site is
// actively (re)deployed: how long ago the container was last restarted, plus a
// "stay tuned / come back later" note. STARTED_AT (epoch seconds) is stamped by
// the compose entrypoint at container start, so "X ago" reflects the real
// restart and stays accurate as the tab stays open.
//
// Off entirely unless DEV resolved to the literal "1": empty, "0" or the
// leftover "{{...}}" placeholder (local dev served without templating) all keep
// it hidden, so production looks normal unless explicitly enabled. Plain script
// (not a module), loaded after app-config.js so window.__APP_CONFIG__ exists.
//
// Clicking the banner dismisses it for the rest of the browser session (the
// dismissal is remembered in sessionStorage, so a reload won't bring it back).

(function () {
  const cfg = window.__APP_CONFIG__ || {};
  // Enabled only on an exact "1" so an unset/placeholder value never trips it.
  if (cfg.dev !== "1") return;

  const banner = document.getElementById("dev-banner");
  if (!banner) return;

  // Container start time in epoch seconds. May be absent/unparseable when served
  // without templating; then we drop the "X ago" phrase and show a generic note.
  const startedAt = Number(cfg.startedAt);
  const hasStart = Number.isFinite(startedAt) && startedAt > 0;

  /**
   * Human "X minutes/hours/days ago" from a count of elapsed seconds. Rounds to
   * the coarsest sensible unit so the banner reads naturally as time passes.
   */
  function humanAgo(seconds) {
    const minutes = Math.max(0, Math.round(seconds / 60));
    if (minutes < 1) return "less than a minute ago";
    if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
    const days = Math.round(hours / 24);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }

  // Version tag (single source: window.__APP_VERSION__ from version.js), shown
  // in the banner so WIP visitors can tell which build they are looking at.
  const version = window.__APP_VERSION__ ? ` (v${window.__APP_VERSION__})` : "";

  function render() {
    // Client clock vs container clock can differ slightly; close enough for a
    // human "restarted ~X ago" cue. Clamp negatives (skewed clocks) to 0.
    const elapsed = hasStart ? Date.now() / 1000 - startedAt : 0;
    const when = hasStart
      ? `This container was last restarted ${humanAgo(elapsed)}, so it is actively being developed. `
      : "This site is actively being developed. ";
    banner.innerHTML =
      `<strong>Work in progress${version}.</strong> ${when}Stay tuned, or come back later.`;
  }

  render();

  // Dismissable: clicking the banner hides it and remembers that for the rest of
  // the browser session (per-tab sessionStorage), so a reload doesn't nag again.
  // Checked before showing so a dismissed banner never flashes back on reload.
  const DISMISS_KEY = "neurarium:dev-banner-dismissed";
  const dismissed = () => {
    try { return sessionStorage.getItem(DISMISS_KEY) === "1"; } catch { return false; }
  };
  if (dismissed()) return;

  // Reveal it in the shared #banners stack. The top-anchored #status pill is
  // kept below the stack by the --banners-height variable that js/error-banner.js
  // maintains (a ResizeObserver on #banners), so no per-banner body class here.
  banner.hidden = false;
  // Keep the "X ago" fresh without a reload while the tab stays open.
  const timer = hasStart ? setInterval(render, 60 * 1000) : null;

  banner.style.cursor = "pointer";
  banner.title = "Click to dismiss";
  banner.addEventListener("click", () => {
    banner.hidden = true;
    if (timer) clearInterval(timer);
    try { sessionStorage.setItem(DISMISS_KEY, "1"); } catch { /* ignore */ }
  });
})();
