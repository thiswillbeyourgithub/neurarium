// Swiping the panel's header bar steps it between three sizes, like a bottom sheet:
// collapsed (the bar alone) <-> half (the default) <-> full (the reading mode, see
// setNo3d). Up grows it one step, down shrinks it one step. A tap still toggles.

// A vertical move shorter than this (px), or more sideways than vertical, is not a swipe.
const SWIPE_PX = 40;

/**
 * The size one swipe leads to; the same size when there is no step that way.
 * @param {"collapsed"|"half"|"full"} size
 * @param {"up"|"down"} dir
 * @returns {"collapsed"|"half"|"full"}
 */
export function swipeStep(size, dir) {
  const order = ["collapsed", "half", "full"];
  const i = order.indexOf(size) + (dir === "up" ? 1 : -1);
  return order[Math.max(0, Math.min(order.length - 1, i))];
}

/** @param {{no3dOn: () => boolean, setNo3d: (on: boolean, opts?: object) => void}} o */
export function wirePanelSwipe({ no3dOn, setNo3d }) {
  const header = document.getElementById("controls-header");
  const toggle = document.getElementById("controls-toggle");
  const body = document.getElementById("controls-body");
  if (!header || !toggle || !body) return;
  const size = () => (body.hidden ? "collapsed" : no3dOn() ? "full" : "half");
  // Every route goes through the existing controls (the toggle's click collapses or
  // expands, and leaves the reading mode on a collapse), so the URL state, the brain's
  // pan aside and the persisted preferences stay theirs.
  const go = (from, to) => {
    if (from === "collapsed" || to === "collapsed") toggle.click();
    // A swipe borrows the full size for this visit, like the Data browser does; only
    // the header button records it as a lasting preference.
    else setNo3d(to === "full", { persist: to !== "full" });
  };

  let start = null, swiped = false;
  header.addEventListener("pointerdown", (ev) => {
    swiped = false;
    start = ev.isPrimary ? { x: ev.clientX, y: ev.clientY } : null;
  });
  header.addEventListener("pointerup", (ev) => {
    if (!start) return;
    const dx = ev.clientX - start.x, dy = ev.clientY - start.y;
    start = null;
    if (Math.abs(dy) < SWIPE_PX || Math.abs(dy) < Math.abs(dx)) return;
    const from = size(), to = swipeStep(from, dy < 0 ? "up" : "down");
    if (to !== from) go(from, to);
    swiped = true;
  });
  header.addEventListener("pointercancel", () => { start = null; });
  // The click that ends a swipe would toggle the panel again: swallow it, in the capture
  // phase ahead of the toggle's own handler. `go`'s own click runs before `swiped` is set.
  header.addEventListener("click", (ev) => {
    if (!swiped) return;
    swiped = false;
    ev.stopPropagation();
    ev.preventDefault();
  }, true);
}
