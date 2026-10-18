// Reload onto the latest deploy when the page on screen is an older build.
//
// The service worker already asks the server first on every load (sw.js), so a stale
// build only reaches the screen two ways: the browser restores a tab it kept in memory
// (bfcache, a phone's frozen tab, an installed PWA brought back to the front) without
// loading anything, or the network was not up yet at launch (a phone waking) and sw.js
// fell back to its offline copy. Both are caught here: on load, when the tab becomes
// visible again, and when the connection comes back, fetch version.js past every cache
// and reload if it names another version. Offline the fetch fails and the cached build
// keeps running, which is the intended fallback.
//
// A reload keeps the view, since the view lives in the URL (js/url-state.js). One
// sessionStorage key remembers the last attempt as `{version, at}`, so a server that
// keeps answering a version this tab cannot load never loops: the same version is
// retried only after RETRY_MS, or at once when the connection comes back (the likely
// reason the reload landed on the old build). A check never reloads under an open
// guided tour, which a reload would end mid-step; a later check picks it up.
//
// Made with the help of Claude Code.

const TRIED_KEY = "neurarium-update-tried";
const MIN_INTERVAL_MS = 30_000;
export const RETRY_MS = 10 * 60_000;

/** The version string a version.js body declares, or null. */
export function extractAppVersion(text) {
  const m = /__APP_VERSION__\s*=\s*["']([^"']+)["']/.exec(text || "");
  return m ? m[1] : null;
}

/** The stored last attempt `{version, at}` (ms epoch), or null when none / unreadable. */
export function parseTried(raw) {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw);
    if (v && typeof v.version === "string") return { version: v.version, at: Number(v.at) || 0 };
  } catch { /* the plain-string format of older builds */ }
  return { version: String(raw), at: 0 };
}

/** Whether a tab running `local` should reload for `remote`, given its last attempt
 * (`tried`, null when none) at time `now`. `force` (the connection just came back)
 * retries the same version without waiting RETRY_MS. */
export function shouldReload(local, remote, tried, now = Date.now(), force = false) {
  if (!local || !remote || remote === local) return false;
  if (!tried || tried.version !== remote) return true;
  return force || now - tried.at >= RETRY_MS;
}

/** Whether the guided tour is on screen (js/tour.js mounts `#tour-root`). */
const tourOpen = () => {
  const root = document.getElementById("tour-root");
  return Boolean(root && !root.hidden);
};

function start() {
  const local = window.__APP_VERSION__;
  let last = 0;
  async function check(force = false) {
    const now = Date.now();
    if (!local || (!force && now - last < MIN_INTERVAL_MS)) return;
    last = now;
    let remote;
    try {
      const res = await fetch("version.js", { cache: "no-store" });
      if (!res.ok) return;
      remote = extractAppVersion(await res.text());
    } catch {
      return; // offline: keep the cached build
    }
    let tried = null;
    try { tried = parseTried(sessionStorage.getItem(TRIED_KEY)); } catch { /* storage blocked */ }
    if (!shouldReload(local, remote, tried, Date.now(), force) || tourOpen()) return;
    try {
      sessionStorage.setItem(TRIED_KEY, JSON.stringify({ version: remote, at: Date.now() }));
    } catch { /* storage blocked */ }
    location.reload();
  }
  check();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") check();
  });
  window.addEventListener("pageshow", (e) => { if (e.persisted) { last = 0; check(); } });
  window.addEventListener("online", () => check(true));
}

if (typeof window !== "undefined" && typeof document !== "undefined") start();
