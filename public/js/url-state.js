/**
 * The URL fragment as a complete, shareable description of what is on screen.
 *
 * One registry of `key -> {read, write}` view pairs, plus the two directions that
 * ride it:
 *   - **write direction** (`sync`): every registered view is asked for its value and
 *     the result replaces the hash, so the address bar is always the deep link for
 *     the current UI. Copying it is just selecting the URL bar, no dedicated button.
 *   - **read direction** (`applyHash`): the hash is parsed and each present key is
 *     handed to its view, reproducing that UI.
 *
 * Two rules make links short and safe to paste:
 *   - a view `read()`s **null** while it sits at its default, so a plain link carries
 *     only what is actually away from default;
 *   - a **missing** key is never written. The hash then carries no instruction about
 *     it, and a link that simply says nothing must not silently override a persisted
 *     preference (animations, panel-only mode, ...).
 *
 * `priority` orders both directions: a higher number is applied later, so a view that
 * must win over what another one implies (the camera over a focus's own framing)
 * registers above it. Same-priority views run in registration order.
 *
 * Values are percent-encoded only where a fragment parsed as `key=value&key=value`
 * would otherwise break (`%`, `&`, `#`, `+`, space), so ids, `:` separators and the
 * `a->b` of a pathway key stay readable in the address bar. Reading goes through
 * `URLSearchParams`, which decodes those escapes back.
 *
 * List-valued keys (the open detail tabs) join their parts with a comma: every id in
 * the dataset is `[A-Za-z0-9_.-]`, so no part can contain the separator.
 *
 * No dependency: DOM `history` + `location` only, nothing about this app's data.
 *
 * Built with the help of Claude Code.
 */

/** The separator for a list-valued key (see the module comment on why it is safe). */
export const LIST_SEP = ",";

/** Characters that would break `key=value&key=value` parsing, or (`+`) decode to a
 *  space. Everything else is left readable. */
const RESERVED = /[%&#+ ]/g;

const enc = (s) =>
  String(s).replace(RESERVED, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);

/**
 * Create the registry for one page.
 *
 * @returns {{
 *   register: (key: string, view: {read: () => string|null, write: (v: string) => void},
 *              priority?: number) => void,
 *   apply: (params: URLSearchParams) => number,
 *   applyHash: () => number,
 *   hash: () => string,
 *   sync: (delay?: number) => void,
 *   start: () => void,
 * }}
 */
export function createUrlState() {
  /** key -> {read, write, priority, seq} */
  const views = new Map();
  /** Values seen in a URL before their owner registered, applied the moment it does.
   *  A control can be wired later than the first applyHash(), and a link naming it
   *  must not be dropped on the floor. */
  const pending = new Map();
  let seq = 0; // registration counter, the tie-break within a priority
  let applying = false; // suppress sync() while we are the ones writing the state
  let timer = null; // the pending debounced sync, if any

  /** Registered views, in apply/write order. */
  const ordered = () =>
    [...views.entries()].sort(
      (a, b) => a[1].priority - b[1].priority || a[1].seq - b[1].seq);

  const writeInto = (view, value) => {
    applying = true;
    try {
      view.write(value);
    } finally {
      applying = false;
    }
  };

  function register(key, view, priority = 0) {
    const entry = { read: view.read, write: view.write, priority, seq: seq++ };
    views.set(key, entry);
    if (pending.has(key)) {
      const value = pending.get(key);
      pending.delete(key);
      writeInto(entry, value);
    }
  }

  /**
   * Reproduce the UI the params describe. Unknown keys are parked for a view that
   * has not registered yet (a screenshot query's `only=` / `view=` never registers
   * and simply stays parked, harmlessly).
   * @returns {number} how many keys were applied, so a caller can tell an
   *   instruction-carrying URL from a bare one.
   */
  function apply(params) {
    let applied = 0;
    for (const [key, view] of ordered()) {
      if (!params.has(key)) continue;
      writeInto(view, params.get(key));
      applied++;
    }
    for (const [key, value] of params) {
      if (!views.has(key)) pending.set(key, value);
    }
    return applied;
  }

  /** Apply the current `location.hash`. */
  function applyHash() {
    return apply(new URLSearchParams(window.location.hash.replace(/^#/, "")));
  }

  /** The fragment (with its leading `#`) describing the current UI, or "" when every
   *  view sits at its default. */
  function hash() {
    const parts = [];
    for (const [key, view] of ordered()) {
      const value = view.read();
      if (value != null) parts.push(`${key}=${enc(value)}`);
    }
    return parts.length ? `#${parts.join("&")}` : "";
  }

  /** Write the current UI into the address bar. `replaceState` fires no `hashchange`
   *  (so this never loops back into applyHash) and spams no back/forward entry. */
  function syncNow() {
    const want = hash();
    if (want === window.location.hash) return;
    history.replaceState(
      null, "", want || window.location.pathname + window.location.search);
  }

  /** Trailing-debounced `syncNow`: a burst of writes (one focus touches several views,
   *  a slider drag fires per frame) costs ONE history call, on the settled value.
   *  `delay` is how long to wait for the burst to end: 0 for a discrete action, a few
   *  hundred ms for a continuous one (a drag, a search box being typed into). A no-op
   *  while we are applying a URL, so a pasted link is not rewritten mid-flight. */
  function sync(delay = 0) {
    if (applying) return;
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      syncNow();
    }, delay);
  }

  /** React to later hash changes: a hand-edited URL, a pasted link, back/forward. The
   *  sync afterwards re-normalizes what was typed (a legacy alias, a key in another
   *  order) into the canonical fragment, and `replaceState` fires no `hashchange`, so
   *  this cannot loop. */
  function start() {
    window.addEventListener("hashchange", () => {
      applyHash();
      sync();
    });
  }

  return { register, apply, applyHash, hash, sync, start };
}
