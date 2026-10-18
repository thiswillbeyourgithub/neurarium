// Tour scrolling: bringing a scrollTo step's target into view, the "look this way"
// scroll arrow, the elastic clamp that keeps a locked panel step's target from
// being scrolled away, and the scroll-follow that keeps ring + bubble on the target.
// Reads and writes the shared tour state `st` (see js/tour/index.js).

import { clamp, primaryTarget, resolveTargets, unionRect } from "./layout.js";

const SCROLL_TOP_PAD = 12; // px above a scrollAlign:"top" target once scrolled to the top
export const SCROLL_RECHECK_MS = 200; // how often a scrollTo step re-checks its target is still in view
const SMOOTH_SCROLL_MAX_MS = 1200; // a smooth scroll not landed by then is finished with a jump
const ELASTIC_PX = 10; // px the ring rubber-bands when a panel step's scroll is clamped
const ARROW_EDGE_PAD = 30; // px inside the scroll container's edge the scroll arrow rides
const ARROW_TARGET_GAP = 16; // px off the target the arrow lands on before fading out
const ARROW_LINGER_MS = 500; // how long it rests on the arrived target before fading
const ARROW_FADE_MS = 320; // must match the .tour-scroll-arrow opacity transition

// "Enough of it is on screen": the box `er` shows at least its own height, or 60%
// of container `c` for a block taller than that. The one arrival test shared by the
// scroll-into-view retry, the reveal hold and the scroll arrow.
function shownEnough(er, c) {
  const cr = c.getBoundingClientRect();
  const shown = Math.max(0, Math.min(er.bottom, cr.bottom) - Math.max(er.top, cr.top));
  return shown >= Math.min(er.height, c.clientHeight * 0.6) - 2;
}

// Whether a scrollTo step's target has scrolled into view (true when the step
// does not scroll, or its target has no scroll container to leave).
export function targetArrived(step) {
  if (!step.scrollTo) return true;
  const els = resolveTargets(step);
  const c = els.length ? scrollParent(els[0]) : null;
  return !c || shownEnough(unionRect(els), c);
}

// Nearest ancestor of `el` that actually scrolls vertically (else null).
function scrollParent(el) {
  let n = el.parentElement;
  while (n) {
    const oy = getComputedStyle(n).overflowY;
    if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 1) return n;
    n = n.parentElement;
  }
  return null;
}

// On a panel step (dim:false, ring inside a scroll container), keep the highlighted
// target from being scrolled out of view: [lo, hi] is the scroll range where its
// top/bottom edge still reaches the container edge, so the ring can't drift off over
// the 3D scene (a short target locks in place; a target taller than the container can
// be scrolled through but not past). Null when the step is not locked (steps that WANT
// free scrolling, a scroll gate, opt out with scrollFree:true) or nothing scrolls.
// Two enforcers share it: onWheelClamp (before the fact) + clampTargetScroll (after).
function targetScrollBounds(step) {
  if (!step || step.dim !== false || step.scrollFree) return null;
  const el = primaryTarget(step);
  if (!el) return null;
  const c = scrollParent(el);
  if (!c) return null;
  const cr = c.getBoundingClientRect();
  const er = el.getBoundingClientRect();
  const tTop = c.scrollTop + (er.top - cr.top);      // target top within scroll content
  const a = tTop;                                    // scrollTop keeping the target top visible
  const b = tTop + er.height - c.clientHeight;        // ... keeping its bottom visible
  return {
    c,
    lo: Math.max(0, Math.min(a, b)),
    hi: Math.min(c.scrollHeight - c.clientHeight, Math.max(a, b)),
  };
}

/**
 * The scroll behaviours of one tour, over its shared state `st`.
 * @param {object} st  shared tour state
 * @param {{layout:()=>void, setAnim:(on:boolean)=>void}} hooks
 */
export function createTourScroll(st, { layout, setAnim }) {
  let arrowDir = 0; // -1 up / +1 down: the direction it was raised in, kept while it lands
  let arrowTimer = null; // the linger timeout once the arrow has reached its target
  let arrowFade = null; // the timeout that display:none-s it after the fade-out
  let bounceTimer = null;
  let bouncing = false;
  let scrollTimer = null; // onScroll's settle timeout

  // A big purple chevron shown while a step's target sits outside its scroll
  // container. The tour scrolls the panel for you (scrollStepIntoView), but a pane
  // sliding on its own reads as "something moved", not as "look down here", so the
  // arrow names the direction. It rides the container edge the target is hiding
  // behind while it is still out of view, then, once the target shows, glides onto
  // it and fades: it ends up pointing at the box you were being taken to. It is
  // also what comes back when a hand-scroll pushed the target away, since the
  // auto-scroll deliberately stops fighting the user (see userScrolled).
  function updateScrollArrow() {
    const { scrollArrow } = st;
    if (!scrollArrow) return;
    if (!st.active || st.index < 0 || st.ring.hidden) return hideScrollArrow();
    const els = resolveTargets(st.steps[st.index]);
    const c = els.length ? scrollParent(els[0]) : null;
    if (!c) return hideScrollArrow();

    const cr = c.getBoundingClientRect();
    const er = unionRect(els);
    // The same test scrollStepIntoView settles on, so the arrow lands exactly when
    // the scroll stops chasing.
    if (!shownEnough(er, c)) {
      arrowDir = er.top < cr.top ? -1 : 1;
      placeArrow(
        clamp(er.left + er.width / 2, cr.left + ARROW_EDGE_PAD, cr.right - ARROW_EDGE_PAD),
        arrowDir > 0 ? cr.bottom - ARROW_EDGE_PAD : cr.top + ARROW_EDGE_PAD,
        false,
      );
      return;
    }
    // Arrived. Only meaningful if the arrow was actually raised: a step whose
    // target never left the pane must not flash one, and one already landing must
    // not restart its own descent every scroll frame.
    if (!scrollArrow.classList.contains("show")
      || scrollArrow.classList.contains("landed")) return;
    placeArrow(
      clamp(er.left + er.width / 2, cr.left + ARROW_EDGE_PAD, cr.right - ARROW_EDGE_PAD),
      arrowDir > 0 ? er.top - ARROW_TARGET_GAP : er.bottom + ARROW_TARGET_GAP,
      true,
    );
    arrowTimer = setTimeout(() => {
      arrowTimer = null;
      hideScrollArrow();
    }, ARROW_LINGER_MS);
  }

  function placeArrow(x, y, landed) {
    const { scrollArrow } = st;
    if (arrowFade) {
      clearTimeout(arrowFade); // a re-raise cancels a pending hide
      arrowFade = null;
    }
    scrollArrow.hidden = false;
    scrollArrow.style.left = `${x}px`;
    scrollArrow.style.top = `${y}px`;
    scrollArrow.classList.toggle("up", arrowDir < 0);
    scrollArrow.classList.toggle("landed", landed);
    scrollArrow.classList.add("show");
  }

  function hideScrollArrow() {
    const { scrollArrow } = st;
    if (arrowTimer) {
      clearTimeout(arrowTimer);
      arrowTimer = null;
    }
    if (!scrollArrow || scrollArrow.hidden || arrowFade) return;
    scrollArrow.classList.remove("show");
    // Let the fade-out run before taking it out of the layout, so the arrow
    // dissolves on the target rather than blinking off it.
    arrowFade = setTimeout(() => {
      arrowFade = null;
      scrollArrow.hidden = true;
      scrollArrow.classList.remove("landed");
    }, ARROW_FADE_MS);
  }

  // Hard-reset the scroll arrow (no fade: the whole overlay is about to vanish),
  // so a replay doesn't start with a stale one showing.
  function resetScrollArrow() {
    const { scrollArrow } = st;
    if (arrowTimer) { clearTimeout(arrowTimer); arrowTimer = null; }
    if (arrowFade) { clearTimeout(arrowFade); arrowFade = null; }
    if (scrollArrow) {
      scrollArrow.classList.remove("show", "landed");
      scrollArrow.hidden = true;
    }
  }

  // Smooth-scroll a scrollTo step's target to the centre of its scroll container
  // (native compositor smooth-scroll; the explicit `behavior` overrides the
  // container's CSS scroll-behavior:auto). Deferred to its OWN task (setTimeout)
  // rather than run inline in go(): doing it inline, in the same synchronous tick
  // that before() opened the section and go() rewrote the panel, made Chrome
  // collapse a short smooth scroll to an instant jump (the circuits list snapped
  // while the longer drugs scroll still glided). A clean task, after that layout
  // churn settles, lets it animate uniformly regardless of distance. setTimeout
  // (not rAF) because the viewer's on-demand render loop can leave rAF idle. The
  // scroll fires scroll events, so onScroll keeps the ring tracking the moving row.
  function scrollStepIntoView(step) {
    if (!step.scrollTo) return;
    const startIndex = st.index;
    let glide = null; // the smooth scroll in flight: { to, at }
    const attempt = (first) => {
      if (!st.active || st.index !== startIndex) return; // step already changed
      if (!first && st.userScrolled) return; // never fight a deliberate scroll
      const els = resolveTargets(step);
      if (!els.length) return;
      const c = scrollParent(els[0]);
      if (!c) return;
      const cr = c.getBoundingClientRect();
      // The WHOLE group, not just the first target: a group highlight (the four
      // browse sections) must land in view as one block, or the ring spans rows
      // that are off-screen.
      const er = unionRect(els);
      // A retry only acts on a target that is genuinely off-screen (see below):
      // enough of it showing means the first scroll worked, leave it alone.
      if (!first && shownEnough(er, c)) return;
      // Default: centre the target. "top" (or a block taller than the panel): land
      // its heading near the top instead, since centring a tall block scrolls past
      // its heading so you can't tell what you are looking at.
      const want = step.scrollAlign === "top" || er.height > c.clientHeight
        ? c.scrollTop + (er.top - cr.top) - SCROLL_TOP_PAD
        : c.scrollTop + (er.top - cr.top) - (c.clientHeight - er.height) / 2;
      const to = Math.max(0, Math.min(want, c.scrollHeight - c.clientHeight));
      if (Math.abs(to - c.scrollTop) < 2) return; // already centred enough
      // Never re-issue a smooth scroll toward the destination one is already gliding
      // to: each call restarts the animation, so on a busy main thread a retry every
      // tick kept the panel frozen where it was (the ring then pointed off-screen).
      // A glide still short of its mark after SMOOTH_SCROLL_MAX_MS is finished with a
      // jump instead, so the target always arrives.
      const now = performance.now();
      const same = glide && Math.abs(glide.to - to) < 2;
      if (same && now - glide.at < SMOOTH_SCROLL_MAX_MS) return;
      c.scrollTo({ top: to, behavior: same ? "instant" : "smooth" });
      glide = { to, at: now };
    };
    // Then re-checked for as long as the step shows: a panel's content keeps arriving
    // after the step opens (a live Wikipedia lead is a network fetch, an illustration
    // loads lazily, a section above collapses) and that reflow slides the target back
    // out of view under the first scroll, at any time. A time-capped poll left the ring
    // pointing off-screen when the reflow landed late. It costs a couple of rect reads
    // per tick, only while a scrollTo step is showing, and it stops the moment the user
    // scrolls by hand.
    setTimeout(() => attempt(true), 0);
    const poll = setInterval(() => {
      if (!st.active || st.index !== startIndex || st.userScrolled) clearInterval(poll);
      else attempt(false);
    }, SCROLL_RECHECK_MS);
  }

  // Elastic scroll-clamp: rubber-band the ring by a few px, then spring it back, as
  // tactile feedback that a panel step's scroll just hit a boundary. Uses transform
  // (layout() only writes left/top/width/height), so it composes with the ring flash.
  function ringBounce(dir) {
    const { ring } = st;
    // One bounce per clamp episode, NOT one per event: a wheel/touch flick against the
    // boundary fires scroll events every few ms, and restarting the animation on each
    // one pinned the ring at its offset and read as jitter rather than a rubber-band.
    if (!ring || ring.hidden || bouncing) return;
    bouncing = true;
    const y = dir > 0 ? ELASTIC_PX : -ELASTIC_PX;
    ring.style.transition = "transform 0.10s ease-out";
    ring.style.transform = `translateY(${y}px)`;
    if (bounceTimer) clearTimeout(bounceTimer);
    bounceTimer = setTimeout(() => {
      ring.style.transition = "transform 0.26s cubic-bezier(0.22, 1, 0.36, 1)";
      ring.style.transform = "translateY(0)";
      bounceTimer = setTimeout(() => {
        ring.style.transition = "";
        ring.style.transform = "";
        bouncing = false;
      }, 280);
    }, 110);
  }

  function clampTargetScroll(step) {
    const bounds = targetScrollBounds(step);
    if (!bounds) return false;
    const { c, lo, hi } = bounds;
    const top = c.scrollTop;
    if (top >= lo - 0.5 && top <= hi + 0.5) return false; // within bounds: allow the scroll
    const clamped = Math.max(lo, Math.min(hi, top));
    const over = top - clamped;
    c.scrollTop = clamped;                              // snap back inside bounds
    ringBounce(over > 0 ? 1 : -1);
    return true;
  }

  // Cancel an out-of-bounds wheel BEFORE the browser acts on it. clampTargetScroll alone
  // is an after-the-fact snap, and against a trackpad's inertia (which keeps firing for
  // ~a second) that means scroll-out/jump-back every frame: visible jitter. Cancelling at
  // the boundary makes it simply stop, with one rubber-band bounce.
  function onWheelClamp(e) {
    if (st.index < 0 || e.ctrlKey) return; // ctrl+wheel is a zoom gesture, not a scroll
    const bounds = targetScrollBounds(st.steps[st.index]);
    if (!bounds) return;
    const { c, lo, hi } = bounds;
    if (!c.contains(e.target)) return; // a wheel over the scene / another panel is not ours
    // deltaMode: 0 px, 1 lines, 2 pages (Firefox reports lines for a mouse wheel).
    const px = e.deltaMode === 1 ? e.deltaY * 16
      : e.deltaMode === 2 ? e.deltaY * c.clientHeight
        : e.deltaY;
    const next = c.scrollTop + px;
    if (next >= lo - 0.5 && next <= hi + 0.5) return; // stays in range: let it through
    e.preventDefault();
    const clamped = Math.max(lo, Math.min(hi, next));
    if (Math.abs(clamped - c.scrollTop) > 0.5) {
      c.scrollTop = clamped; // travel the part of the gesture that IS in range
      layout();
    }
    ringBounce(next > hi ? 1 : -1);
  }

  // Follow the target while the page/panel scrolls (e.g. a row sliding into view,
  // or the user scrolling the list). Snap during the scroll so the ring tracks
  // tightly, then restore the smooth glide once it settles.
  function onScroll() {
    if (st.index < 0) return;
    const step = st.steps[st.index];
    // Elastic clamp first: on a locked panel step this snaps the scroll back and bounces
    // the ring instead of letting the target (and the ring) leave the panel.
    if (clampTargetScroll(step)) { layout(); return; }
    // Just after a step change, a reflow-scroll must not snap: keep the glide on and
    // re-place (the step-to-step move eases in). scrollTo steps are exempt so their
    // programmatic smooth-scroll still snap-tracks its row 1:1.
    if (step && !step.scrollTo && performance.now() < st.navGuardUntil) {
      layout();
      return;
    }
    st.scrolling = true; // freeze the bubble (layout skips it); the ring still tracks 1:1
    setAnim(false);
    layout();
    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      if (st.index < 0) return;
      st.scrolling = false;
      setAnim(true);
      layout(); // re-place the bubble with the glide on, easing it to its settled spot
    }, 140);
  }

  // Drop onScroll's pending settle (a step change or teardown).
  function cancelScrollSettle() {
    if (scrollTimer) { clearTimeout(scrollTimer); scrollTimer = null; }
  }

  // A real scroll gesture (as opposed to our own programmatic scrollTo, which emits
  // "scroll" but no wheel/touch): it tells scrollStepIntoView to stop re-centring.
  function onUserScroll() {
    st.userScrolled = true;
  }

  return {
    updateScrollArrow, hideScrollArrow, resetScrollArrow, scrollStepIntoView,
    onScroll, onWheelClamp, onUserScroll, cancelScrollSettle,
  };
}
