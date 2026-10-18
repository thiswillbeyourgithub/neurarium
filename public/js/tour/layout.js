// Tour geometry: resolving a step's targets, the spotlight ring + click-through
// hole, and placing the bubble against a target (or as a caption) without covering
// it. Everything reads the shared tour state `st` (see js/tour/index.js); nothing
// here owns state of its own.

export const GAP = 14; // px between the spotlight ring and the bubble
export const MARGIN = 12; // px min gap from the viewport edge
const RING_PAD = 6; // px the ring extends past the target on each side

export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Resolve a step's target to a list of on-screen Elements. `target` may be a
// CSS selector, an Element, or a function returning any of those or an array
// (a group highlight, e.g. the five browse sections). Elements with no box
// (display:none) are dropped, so an unresolved target degrades to a caption.
export function resolveTargets(step, key = "target") {
  let t = step[key];
  if (typeof t === "function") t = t();
  if (t == null) return [];
  const raw = Array.isArray(t) ? t : [t];
  const els = [];
  for (const item of raw) {
    const el = typeof item === "string" ? document.querySelector(item) : item;
    if (el && el.getClientRects().length > 0) els.push(el);
  }
  return els;
}
// The element an interactive step scrolls to: the first target.
export const primaryTarget = (step) => resolveTargets(step)[0] || null;
// The element an interactive step listens on: its `tapTarget`, else the primary
// target. Must contain whatever a tap inside the ring hits, or the guard eats it.
export const tapTarget = (step) =>
  (step.tapTarget ? resolveTargets(step, "tapTarget")[0] : primaryTarget(step)) || null;
// Bounding box of one or many elements (the spotlight ring spans them all).
export function unionRect(els) {
  let L = Infinity, T = Infinity, R = -Infinity, B = -Infinity;
  for (const el of els) {
    const r = el.getBoundingClientRect();
    L = Math.min(L, r.left);
    T = Math.min(T, r.top);
    R = Math.max(R, r.right);
    B = Math.max(B, r.bottom);
  }
  return { left: L, top: T, right: R, bottom: B, width: R - L, height: B - T };
}

// Cut a rectangular hole in the click-eating blocker so a tap lands on the
// real element beneath it. clip-path removes the hole from hit-testing too, so
// pointer events pass straight through it; everything outside stays swallowed.
export function setHole(st, box) {
  const L = box.left,
    T = box.top,
    R = box.right,
    B = box.bottom;
  st.blocker.style.clipPath =
    `polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0, ` +
    `${L}px ${T}px, ${L}px ${B}px, ${R}px ${B}px, ${R}px ${T}px, ${L}px ${T}px)`;
}
export function clearHole(st) {
  st.blocker.style.clipPath = "none";
}

// Ring + blocker + bubble for the current step (the veils and the scroll arrow are
// the caller's, see layout() in js/tour/index.js).
export function layoutStep(st, step) {
  const { blocker, ring } = st;
  const els = resolveTargets(step);
  // A stayAfterTap step, once tapped, steps its spotlight aside so the live
  // demo it triggered is watchable: no ring, no dim, bubble tucked off the scene.
  const consumed = !!step.stayAfterTap && st.observed;
  const spotlight = els.length > 0 && !consumed;
  const interactive = spotlight && !!step.interactive;
  const dim = consumed
    ? false
    : step.dim !== undefined
      ? step.dim
      : spotlight || !step.target;

  blocker.hidden = !dim && !interactive; // an interactive step always needs the blocker (to hole it)
  blocker.classList.toggle("modal", dim && !spotlight);

  if (spotlight) {
    const r = unionRect(els);
    const x = Math.max(0, r.left - RING_PAD);
    const y = Math.max(0, r.top - RING_PAD);
    const w = r.width + RING_PAD * 2;
    const h = r.height + RING_PAD * 2;
    ring.hidden = false;
    ring.classList.toggle("interactive", interactive);
    // spotlightOnly: keep the accent ring but drop the page-dimming box-shadow, so
    // a popup the step is pointing INTO (e.g. the sources breakdown) stays readable.
    ring.classList.toggle("no-dim", !!step.spotlightOnly);
    ring.style.left = `${x}px`;
    ring.style.top = `${y}px`;
    ring.style.width = `${w}px`;
    ring.style.height = `${h}px`;
    const box = { left: x, top: y, right: x + w, bottom: y + h };
    if (interactive) setHole(st, box);
    else clearHole(st);
    // While a row scrolls into view the ring tracks it 1:1 (snapped, above), but
    // the bubble is left alone so it doesn't snap frame-by-frame: onScroll's
    // settle re-runs layout with the glide on, easing the bubble to its final
    // spot in one smooth move instead of jittering along with the scroll.
    if (!st.scrolling && !st.bubbleDragged) placeBubbleBy(st.bubble, box, step);
  } else {
    ring.hidden = true;
    clearHole(st);
    if (!st.scrolling && !st.bubbleDragged) {
      placeCaption(st.bubble, consumed ? "brain" : step.placement || "top");
    }
  }
}

// Position the bubble against a spotlighted rect without covering it. Try to
// the right, then left, then below, then above; if none fits (a full-width
// bottom sheet on a phone leaves no side room), dock to the emptier vertical
// edge. This is what keeps the bubble off the brain and off the control on a
// narrow portrait screen.
function placeBubbleBy(bubble, box, step) {
  bubble.style.maxWidth = "";
  const bw = bubble.offsetWidth;
  const bh = bubble.offsetHeight;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const needW = bw + GAP + MARGIN;
  const needH = bh + GAP + MARGIN;
  const cx = box.left + (box.right - box.left) / 2;
  const cy = box.top + (box.bottom - box.top) / 2;
  let left, top;
  if (step && step.bubbleDock === "bottom" && vh >= vw) {
    // Portrait override: dock the bubble low on the screen (over the least
    // informative area, e.g. a sources popup's mostly-empty progress bars) so it
    // covers neither the target nor the upper text. Landscape keeps the side
    // placement below (there is room beside the target, no need to cover anything).
    top = vh - bh - MARGIN;
    left = (vw - bw) / 2;
  } else if (vw - box.right >= needW) {
    left = box.right + GAP; // right of the target
    top = cy - bh / 2;
  } else if (box.left >= needW) {
    left = box.left - GAP - bw; // left of the target
    top = cy - bh / 2;
  } else if (vh - box.bottom >= needH) {
    top = box.bottom + GAP; // below
    left = cx - bw / 2;
  } else if (box.top >= needH) {
    top = box.top - GAP - bh; // above
    left = cx - bw / 2;
  } else {
    // No room on any side: dock to whichever vertical edge is roomier.
    top = box.top >= vh - box.bottom ? MARGIN : vh - bh - MARGIN;
    left = cx - bw / 2;
  }
  bubble.style.left = `${clamp(left, MARGIN, vw - bw - MARGIN)}px`;
  bubble.style.top = `${clamp(top, MARGIN, vh - bh - MARGIN)}px`;
}

function placeCaption(bubble, where) {
  const bw = bubble.offsetWidth;
  const bh = bubble.offsetHeight;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let left = clamp((vw - bw) / 2, MARGIN, vw - bw - MARGIN);
  let top;
  if (where === "center") {
    top = (vh - bh) / 2;
  } else if (where === "aside") {
    // Wide screen: dock to the left edge (clear of a centered modal). Portrait
    // phone: keep it centered (partially over the coverage bars, which matter
    // least here), since there is no roomy side.
    top = (vh - bh) / 2;
    if (vw > vh) left = MARGIN;
  } else if (where === "brain") {
    // Keep the 3D scene clear. On a portrait phone the brain is the top half
    // and the panel the bottom, so the bubble goes to the bottom; on a wide
    // screen the scene fills the middle, so the top edge stays clear.
    top = vh >= vw ? vh - bh - MARGIN : MARGIN + 8;
  } else {
    top = MARGIN + 8; // "top"
  }
  bubble.style.left = `${left}px`;
  bubble.style.top = `${clamp(top, MARGIN, vh - bh - MARGIN)}px`;
}
