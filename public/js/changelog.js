// "What's new": the per-version release notes, shown once after an update.
//
// The bullets are authored under docs/changelog/<version>/changelog.md and emitted
// to data/changelog.json (docs/ is not web-exposed). This module fetches that file
// lazily - only when the popup actually opens - so it costs nothing at boot.
//
// The seen-version gate is the whole point: the browser remembers the version it
// last showed notes for, and on the next visit shows every version *after* it, so a
// visitor who skipped three releases still reads all three. A first-ever visitor is
// silently marked as up to date (they get the guided tour instead; a changelog for
// software they have never seen is noise).

const STORAGE_KEY = "neurarium.changelogSeen";

/** `"3.39.0" -> [3, 39, 0]`, or null when the string is not a semver triple. */
export function parseVersion(version) {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(String(version || "").trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

/** -1 / 0 / +1, comparing two version strings numerically (unparseable sorts low). */
export function compareVersions(a, b) {
  const pa = parseVersion(a) || [0, 0, 0];
  const pb = parseVersion(b) || [0, 0, 0];
  for (let i = 0; i < 3; i += 1) {
    if (pa[i] !== pb[i]) return pa[i] < pb[i] ? -1 : 1;
  }
  return 0;
}

/**
 * The releases to show: everything newer than `seen`, up to and including `current`.
 * A version newer than the running build is skipped (a stale cached changelog.json
 * must never announce a feature this build does not have).
 */
export function releasesSince(versions, seen, current) {
  return (versions || []).filter((release) =>
    compareVersions(release.version, seen) > 0
    && compareVersions(release.version, current) <= 0);
}

/**
 * A GitHub-style commit url, or "" when `sourceUrl` is not a repository.
 *
 * Same rule as the About popup's "open an issue" link: the committed default is the
 * bare public-site domain, where /commit/<sha> would 404, so a bare domain yields no
 * link and the sha renders as plain text. Nothing about the repo is hardcoded here.
 */
export function commitUrl(sourceUrl, sha) {
  const base = String(sourceUrl || "").trim();
  if (!/^https?:\/\//i.test(base) || !/^[0-9a-f]{7,40}$/i.test(sha)) return "";
  try {
    const u = new URL(base);
    if (u.pathname.replace(/\/+$/, "") === "") return "";  // a bare domain, not a repo
    return `${base.replace(/\/+$/, "")}/commit/${sha}`;
  } catch {
    return "";
  }
}

/**
 * An authored `YYYY-MM-DD` as a long date in the reader's language, or "" if unset.
 *
 * The locale is read from the document rather than captured, so the date follows an
 * EN/FR switch without the popup having to be rebuilt. Built from the parts instead of
 * `new Date(iso)`, which would read the string as UTC and slide a day west of Greenwich.
 */
export function formatDate(iso, lang) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return "";
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  try {
    return d.toLocaleDateString(lang || undefined,
      { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return iso;                                     // an odd locale tag: the raw date still reads
  }
}

/**
 * The "What's new" popup controller.
 *
 * @param {object} opts
 * @param {string} opts.version   the running build (window.__APP_VERSION__)
 * @param {string} opts.sourceUrl app-config's sourceUrl, for the commit links
 * @param {(key:string)=>string} opts.t   UI-string lookup (i18n.t)
 * @param {(field:any)=>any} opts.pick    data-string lookup (i18n.pick)
 * @param {(o:object)=>{open:()=>void, close:()=>void, isOpen:boolean}} opts.wireModal
 * @returns {{open:()=>Promise<void>, close:()=>void, isOpen:boolean,
 *            showIfUnseen:()=>Promise<boolean>}}
 */
export function createChangelog({ version, sourceUrl, t, pick, wireModal }) {
  const body = document.getElementById("changelog-body");
  const ctrl = wireModal({ modalId: "changelog-modal", closeId: "changelog-close" });
  let cache = null;

  async function load() {
    if (cache) return cache;
    // A plain fetch: the service worker already revalidates every same-origin
    // asset, so freshness is handled there rather than with a per-call cache mode.
    const res = await fetch("data/changelog.json");
    if (!res.ok) throw new Error(`changelog.json: HTTP ${res.status}`);
    const data = await res.json();
    cache = Array.isArray(data?.versions) ? data.versions : [];
    return cache;
  }

  function seenVersion() {
    try { return localStorage.getItem(STORAGE_KEY) || ""; } catch { return ""; }
  }

  function markSeen() {
    try { localStorage.setItem(STORAGE_KEY, version); } catch { /* private mode */ }
  }

  /** One release: its version heading, then its bullets grouped under category headings. */
  function renderRelease(release) {
    const section = document.createElement("section");
    section.className = "changelog-release";
    const h = document.createElement("h3");
    h.textContent = release.version;
    const when = formatDate(release.date, document.documentElement.lang);
    if (when) {
      const stamp = document.createElement("time");
      stamp.className = "changelog-date";
      stamp.dateTime = release.date;
      stamp.textContent = when;
      h.append(" ", stamp);
    }
    section.append(h);

    // Group by category, keeping the authored order of both the categories and the
    // bullets inside each (the file is the editorial order; don't re-sort it).
    const groups = new Map();
    for (const entry of release.entries || []) {
      if (!groups.has(entry.category)) groups.set(entry.category, []);
      groups.get(entry.category).push(entry);
    }
    for (const [category, entries] of groups) {
      const label = document.createElement("h4");
      label.className = `changelog-cat changelog-cat-${category}`;
      label.textContent = t(`changelog.cat.${category}`);
      section.append(label);
      const ul = document.createElement("ul");
      ul.className = "changelog-list";
      for (const entry of entries) {
        const li = document.createElement("li");
        li.textContent = pick(entry.text);
        for (const sha of entry.commits || []) {
          const url = commitUrl(sourceUrl, sha);
          const short = sha.slice(0, 7);
          const tag = document.createElement(url ? "a" : "span");
          tag.className = "changelog-commit";
          tag.textContent = short;
          if (url) {
            tag.href = url;
            tag.target = "_blank";
            tag.rel = "noopener noreferrer";
            tag.title = t("changelog.commit");
          }
          li.append(" ", tag);
        }
        ul.append(li);
      }
      section.append(ul);
    }
    return section;
  }

  /** Every release this build can honestly show, newest first. */
  function shippedReleases() {
    return (cache || []).filter((r) => compareVersions(r.version, version) <= 0);
  }

  function render(releases) {
    if (!body) return;
    body.textContent = "";
    if (!releases.length) {
      const empty = document.createElement("p");
      empty.className = "changelog-empty";
      empty.textContent = t("changelog.empty");
      body.append(empty);
      return;
    }
    for (const release of releases) body.append(renderRelease(release));
    // After an update the popup opens on just the new releases, which is the point;
    // the rest of the history is one click away rather than scrolled past.
    const all = shippedReleases();
    if (releases.length < all.length) {
      const more = document.createElement("button");
      more.type = "button";
      more.className = "changelog-showall";
      more.textContent = t("changelog.showAll");
      more.addEventListener("click", () => render(all));
      body.append(more);
    }
    body.scrollTop = 0;
  }

  /** Open showing the full history (the About link's behaviour). */
  async function open() {
    let releases = [];
    try {
      releases = await load();
    } catch { /* offline / missing file: the empty message says so */ }
    render(shippedReleases());
    markSeen();
    ctrl.open();
  }

  /**
   * Open showing only what changed since the last visit; resolves to whether it
   * opened. Records the current version either way, so a first visit (and a build
   * with no notes) stays silent from then on.
   */
  async function showIfUnseen() {
    const seen = seenVersion();
    if (!seen) { markSeen(); return false; }          // first ever visit: stay quiet
    if (compareVersions(seen, version) >= 0) return false;
    let releases = [];
    try {
      releases = releasesSince(await load(), seen, version);
    } catch { /* can't fetch: don't nag with an empty popup */ }
    markSeen();
    if (!releases.length) return false;
    render(releases);
    ctrl.open();
    return true;
  }

  return { open, close: ctrl.close, get isOpen() { return ctrl.isOpen; }, showIfUnseen };
}
