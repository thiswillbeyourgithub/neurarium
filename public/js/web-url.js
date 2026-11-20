// The one scheme guard for data-derived links.
//
// DOM-free on purpose, so a pure module (changelog.js, unit-tested under node) can
// import it without pulling the panel's window-reading helpers along.

/** Whether `url` is an absolute http(s) link. Every data-derived `href` goes through
 *  this, so a stray `javascript:` or `data:` value in a committed field (or a future
 *  external one) can never become a clickable script. */
export function isWebUrl(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}

/** The configured repo's issue tracker (`sourceUrl` + "/issues"), or "" when
 *  `sourceUrl` is not an http(s) link INTO a repository: the committed default is the
 *  bare public-site domain, where "/issues" would 404, so a caller drops its link then.
 *  The repo URL comes from the SOURCE_URL env var (see app-config.js), so no
 *  repo/username is hardcoded. */
export function issuesUrl(sourceUrl) {
  if (!isWebUrl(sourceUrl)) return "";
  try {
    if (new URL(sourceUrl).pathname.replace(/\/+$/, "") === "") return "";
  } catch { return ""; }
  return `${sourceUrl.replace(/\/+$/, "")}/issues`;
}

/** The deployed config's issues URL (window.__APP_CONFIG__.sourceUrl), or "". */
export function configIssuesUrl() {
  return issuesUrl(String((globalThis.__APP_CONFIG__ || {}).sourceUrl || "").trim());
}
