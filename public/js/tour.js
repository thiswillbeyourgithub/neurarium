// Guided "take a tour" coach-marks. A small, app-agnostic overlay engine: it
// knows how to spotlight a DOM element (a dimmed backdrop with a cut-out ring)
// or float a caption over the live scene, and how to step Back / Skip through an
// ordered list. It knows NOTHING about the brain, three.js or the data: the
// caller (js/main.js) supplies the steps, each carrying its own `before()` hook
// that sets the scene up (spread the brain, open a section) so the tour can show
// real features live rather than static pictures.
//
// Forward is a Next button (right of Back + Skip), but it stays DISABLED on a
// hands-on step until the required action is done, so the user still cannot
// fast-forward past a demo and leave the UI half-set-up (see awaiting()):
//   - passive / caption: Next is enabled immediately; a click on the dim backdrop
//     also advances.
//   - interactive (`interactive:true`): the backdrop gets a click-through hole
//     over the target (a clip-path cut-out), so the user's real tap reaches the
//     highlighted control. A plain tap advances the tour; a `stayAfterTap` tap
//     fires a live demo, keeps the tour on the step (spotlight steps aside), and
//     ungreys Next. Next stays disabled until the tap, so it can't skip the action.
//   - gate (`gate(signal)`): the step arms a signal the app fires when the user
//     performs a gesture (rotate / move a slider / scroll / close a modal); Next
//     ungreys then, or the step auto-advances when `gateAdvances`.
// Back/Skip (and Esc) stay the escapes.
//
// Kept dependency-free (like js/circuit-schedule.js) so it stays reusable and
// the no-build viewer loads it as a plain ES module.
//
// A step:
//   {
//     title:   string,             // already localized (caller resolves via t())
//     body:    string,             // already localized (may contain safe HTML)
//     target?: string | () => Element | null,  // element to spotlight; a CSS
//                                  // selector or a resolver. Absent/unresolved
//                                  // => a caption step (no spotlight).
//     interactive?: boolean,       // let the user's tap reach the target and
//                                  // advance the tour (click-through hole).
//     stayAfterTap?: boolean,      // (interactive) the tap fires a demo to watch:
//                                  // stay on the step, step the spotlight aside,
//                                  // ungrey Next instead of auto-advancing.
//     gate?: (signal) => cleanup,  // arm a gesture gate: call signal() when the
//                                  // required action happens; returns a teardown.
//     gateAdvances?: boolean,      // (gate) auto-advance on signal() instead of
//                                  // just ungreying Next (e.g. close-to-proceed).
//     veil?: sel|el|fn|array,      // translucent dim over these element(s) only
//                                  // (pointer-events:none), e.g. the controls panel
//                                  // while the brain stays draggable.
//     scrollTo?: boolean,          // scrollIntoView the target when shown (rows
//                                  // deep in a scrolling panel).
//     scrollAlign?: "center"|"top",// where scrollTo lands the target (default
//                                  // "center"; "top" brings a tall section's heading
//                                  // to the top of the panel instead of scrolling
//                                  // past it to centre the whole block).
//     spotlightOnly?: boolean,     // ring the target with NO page-dimming shadow, so
//                                  // a popup the step is explaining stays fully
//                                  // readable (a plain highlight, not a spotlight).
//     clickThrough?: sel|el|fn|array, // extra element(s) the user may click on a
//                                  // non-interactive step. Off the bubble and these
//                                  // (and an interactive step's own target), EVERY
//                                  // click is inert while a step shows, so a stray tap
//                                  // on a row/toolbar can't derail the walkthrough.
//                                  // Scroll + brain-drag use wheel/pointer events (not
//                                  // click), so they keep working regardless.
//     dim?:    boolean,            // darken the rest of the page. Defaults true
//                                  // for a spotlight/modal step, false for a
//                                  // caption (so a live brain demo stays visible).
//     placement?: "top"|"center"|"brain"|"aside", // caption position when there is
//                                  // no target. "brain" = keep the 3D scene clear.
//                                  // "aside" = left edge on desktop, centered on a
//                                  // portrait phone (clear of a centered modal).
//     before?: () => void,         // run when the step is shown (idempotent:
//                                  // it re-runs on Back too, so make it set the
//                                  // exact state it wants, not toggle).
//   }

const GAP = 14; // px between the spotlight ring and the bubble
const MARGIN = 12; // px min gap from the viewport edge
const RING_PAD = 6; // px the ring extends past the target on each side
const ADVANCE_MS = 360; // let the tapped action (open a tab, spread) settle first
const REVEAL_MS = 1000; // hold the dim + highlight back this long, then fade it in,
// so the scene the step just set up reads for a beat before the overlay lands on it
const SCROLL_TOP_PAD = 12; // px above a scrollAlign:"top" target once scrolled to the top
const ELASTIC_PX = 10; // px the ring rubber-bands when a panel step's scroll is clamped

/**
 * @param {{
 *   steps: Array<object>,
 *   labels: { next:string, back:string, done:string, skip:string,
 *             step:(n:number,total:number)=>string, aria?:string },
 *   onEnd?: (reason:"completed"|"skipped") => void,
 *   seenKey?: string,   // localStorage key; when set, a finished tour is
 *                       // remembered so maybeAutoStart() won't run it again.
 * }} deps
 */
export function createTour({ steps, labels, onEnd, seenKey }) {
  let root = null; // the overlay DOM (built lazily on first start)
  let blocker = null; // full-screen click-eater / modal dim
  let ring = null; // the spotlight cut-out (box-shadow does the dimming)
  let bubble = null;
  let elTitle, elBody, elStep, btnBack, btnSkip, btnNext;
  let index = -1; // current step, -1 when inactive
  let active = false;
  let waitEl = null; // the element an interactive step is waiting on
  let waitFn = null; // its one-shot click handler (removed on leave)
  let observed = false; // a stayAfterTap step whose demo has been triggered
  let gateFired = false; // a gate step's signal() has fired (Next may ungrey)
  let gateCleanup = null; // the current gate's teardown (removes its listeners)
  let veilEls = []; // pooled translucent "veil" divs (partial dim over UI)
  let shownOnce = false; // false until the first step paints (snap it, don't fly in)
  let navGuardUntil = 0; // performance.now() until which a reflow-scroll after a step
  // change must NOT snap (so the step-to-step move glides); see go() + onScroll()
  let scrolling = false; // true while a scrollTo row is easing into view (see onScroll)
  let revealTimer = null; // the setTimeout that ends a step's opening beat + fades in the overlay
  let bubbleDragged = false; // user dragged the bubble this step: stop auto-placing it

  const seen = () => {
    if (!seenKey) return false;
    try {
      return localStorage.getItem(seenKey) === "1";
    } catch (e) {
      return false; // storage blocked: treat as unseen, no worse than a re-show
    }
  };
  const markSeen = () => {
    if (!seenKey) return;
    try {
      localStorage.setItem(seenKey, "1");
    } catch (e) {
      /* best-effort, like the Animations toggle persistence */
    }
  };

  function build() {
    if (root) return;
    root = document.createElement("div");
    root.id = "tour-root";
    root.setAttribute("aria-hidden", "true");

    blocker = document.createElement("div");
    blocker.className = "tour-blocker";
    // Eat clicks so a mis-click on the page behind doesn't fire mid-tour. On a
    // passive/caption step a click on the dim backdrop is "continue" (there is no
    // Next button). On an interactive step a clip-path hole (see setHole) lets the
    // tap through to the real target and awaiting() is true, so a click that
    // lands on the blocker (off the target) is swallowed without advancing: the
    // user must act on the highlighted control. Never dismisses (no accidental exit).
    blocker.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!awaiting()) go(index + 1);
    });

    ring = document.createElement("div");
    ring.className = "tour-ring";

    bubble = document.createElement("div");
    bubble.className = "tour-bubble";
    bubble.setAttribute("role", "dialog");
    bubble.setAttribute("aria-modal", "true");
    if (labels.aria) bubble.setAttribute("aria-label", labels.aria);
    enableBubbleDrag();

    elTitle = document.createElement("div");
    elTitle.className = "tour-title";
    elBody = document.createElement("div");
    elBody.className = "tour-body";

    const foot = document.createElement("div");
    foot.className = "tour-foot";
    elStep = document.createElement("span");
    elStep.className = "tour-step";
    const actions = document.createElement("div");
    actions.className = "tour-actions";
    btnSkip = mkBtn("tour-skip", labels.skip, () => stop("skipped"));
    btnBack = mkBtn("tour-back", labels.back, () => go(index - 1));
    // The Next button is the sole forward affordance (no "click to continue" link).
    // On a hands-on step it stays disabled until the required action is done (see
    // awaiting()); clicking it advances, or finishes on the last step.
    btnNext = mkBtn("tour-next", labels.next, () => { if (!awaiting()) go(index + 1); });
    actions.append(btnSkip, btnBack, btnNext);
    foot.append(elStep, actions);

    bubble.append(elTitle, elBody, foot);
    root.append(blocker, ring, bubble);
    document.body.appendChild(root);
  }

  // Let the user drag the bubble out of the way (touch or mouse) so it can be
  // moved off anything it happens to occlude. Once dragged, the bubble stays put
  // for the rest of the step (layout() stops auto-placing it); a step change
  // (go()) resets it. A press that starts on a button or a link is left alone so
  // those keep working; a tiny jitter under the threshold still counts as a click.
  function enableBubbleDrag() {
    let dragging = false;
    let sx = 0, sy = 0, ox = 0, oy = 0, moved = false;
    const onDown = (e) => {
      if (e.target.closest("button, a")) return;
      if (e.button != null && e.button !== 0) return; // primary button / touch only
      dragging = true;
      moved = false;
      sx = e.clientX;
      sy = e.clientY;
      const r = bubble.getBoundingClientRect();
      ox = r.left;
      oy = r.top;
      bubble.style.transition = "none"; // track the pointer 1:1 while dragging
      try { bubble.setPointerCapture(e.pointerId); } catch (_) { /* older UA */ }
    };
    const onMove = (e) => {
      if (!dragging) return;
      const dx = e.clientX - sx;
      const dy = e.clientY - sy;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 3) return; // ignore jitter (keep clicks)
      moved = true;
      e.preventDefault();
      const bw = bubble.offsetWidth;
      const bh = bubble.offsetHeight;
      bubble.style.left = `${clamp(ox + dx, MARGIN, window.innerWidth - bw - MARGIN)}px`;
      bubble.style.top = `${clamp(oy + dy, MARGIN, window.innerHeight - bh - MARGIN)}px`;
    };
    const onUp = (e) => {
      if (!dragging) return;
      dragging = false;
      bubble.style.transition = "";
      try { bubble.releasePointerCapture(e.pointerId); } catch (_) { /* older UA */ }
      if (moved) bubbleDragged = true; // stop auto-placing it for the rest of this step
    };
    bubble.addEventListener("pointerdown", onDown);
    bubble.addEventListener("pointermove", onMove);
    bubble.addEventListener("pointerup", onUp);
    bubble.addEventListener("pointercancel", onUp);
  }

  function mkBtn(cls, text, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tour-btn " + cls;
    b.textContent = text;
    b.addEventListener("click", onClick);
    return b;
  }

  // Resolve a step's target to a list of on-screen Elements. `target` may be a
  // CSS selector, an Element, or a function returning any of those or an array
  // (a group highlight, e.g. the four browse sections). Elements with no box
  // (display:none) are dropped, so an unresolved target degrades to a caption.
  function resolveTargets(step) {
    let t = step.target;
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
  // The element an interactive step listens on / scrolls to: the first target.
  const primaryTarget = (step) => resolveTargets(step)[0] || null;
  // Bounding box of one or many elements (the spotlight ring spans them all).
  function unionRect(els) {
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
  function setHole(box) {
    const L = box.left,
      T = box.top,
      R = box.right,
      B = box.bottom;
    blocker.style.clipPath =
      `polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0, ` +
      `${L}px ${T}px, ${L}px ${B}px, ${R}px ${B}px, ${R}px ${T}px, ${L}px ${T}px)`;
  }
  function clearHole() {
    blocker.style.clipPath = "none";
  }

  // A translucent "veil" over specific elements (e.g. the controls panel) so a step
  // can dim just those while leaving the 3D scene fully interactive. The veils are
  // pointer-events:none (purely visual: the veiled UI still works), pooled, and
  // re-sized every layout(). `step.veil` is a selector, an element, a resolver, or
  // an array of those.
  function applyVeil(step) {
    const raw = step && step.veil;
    const sel = typeof raw === "function" ? raw() : raw;
    const items = sel == null ? [] : Array.isArray(sel) ? sel : [sel];
    const els = [];
    for (const it of items) {
      const el = typeof it === "string" ? document.querySelector(it) : it;
      if (el && el.getClientRects().length > 0) els.push(el);
    }
    while (veilEls.length < els.length) {
      const v = document.createElement("div");
      v.className = "tour-veil";
      root.appendChild(v);
      veilEls.push(v);
    }
    for (let k = 0; k < veilEls.length; k++) {
      const v = veilEls[k];
      if (k < els.length) {
        const r = els[k].getBoundingClientRect();
        v.hidden = false;
        v.style.left = `${r.left}px`;
        v.style.top = `${r.top}px`;
        v.style.width = `${r.width}px`;
        v.style.height = `${r.height}px`;
      } else {
        v.hidden = true;
      }
    }
  }
  function removeVeils() {
    for (const v of veilEls) v.remove();
    veilEls = [];
  }

  // Is `target` a control the current step invites the user to click? The tour's
  // own bubble is always live; beyond it, only an interactive step's tap target and
  // any `clickThrough` element(s) are. Everything else is inert while a step shows
  // (see onClickCapture), so a stray tap on a row/toolbar can't derail the tour.
  function isClickAllowed(target) {
    const step = index >= 0 ? steps[index] : null;
    if (!step) return false;
    if (step.interactive && waitEl && (waitEl === target || waitEl.contains(target))) {
      return true;
    }
    const ct = step.clickThrough;
    const raw = typeof ct === "function" ? ct() : ct;
    const items = raw == null ? [] : Array.isArray(raw) ? raw : [raw];
    for (const it of items) {
      const el = typeof it === "string" ? document.querySelector(it) : it;
      if (el && (el === target || el.contains(target))) return true;
    }
    return false;
  }

  // Capture-phase click guard, live for the whole tour: a click that is not on the
  // bubble or an allowed control is swallowed (stopPropagation + preventDefault)
  // before the app's own handlers see it, so reading a highlighted section can't be
  // interrupted by a mis-click that opens some other panel. Scroll (wheel/touchmove)
  // and rotating the brain (pointer drag) are not clicks, so they are unaffected; a
  // tap on the 3D scene is separately made inert in js/main.js (handleSelect).
  function onClickCapture(e) {
    if (!active) return;
    if (bubble && bubble.contains(e.target)) return;
    if (isClickAllowed(e.target)) return;
    e.stopPropagation();
    e.preventDefault();
  }

  function layout() {
    if (index < 0) return;
    const step = steps[index];
    applyVeil(step);
    const els = resolveTargets(step);
    // A stayAfterTap step, once tapped, steps its spotlight aside so the live
    // demo it triggered is watchable: no ring, no dim, bubble tucked off the scene.
    const consumed = !!step.stayAfterTap && observed;
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
      if (interactive) setHole(box);
      else clearHole();
      // While a row scrolls into view the ring tracks it 1:1 (snapped, above), but
      // the bubble is left alone so it doesn't snap frame-by-frame: onScroll's
      // settle re-runs layout with the glide on, easing the bubble to its final
      // spot in one smooth move instead of jittering along with the scroll.
      if (!scrolling && !bubbleDragged) placeBubbleBy(box);
    } else {
      ring.hidden = true;
      clearHole();
      if (!scrolling && !bubbleDragged) placeCaption(consumed ? "brain" : step.placement || "top");
    }
  }

  // Position the bubble against a spotlighted rect without covering it. Try to
  // the right, then left, then below, then above; if none fits (a full-width
  // bottom sheet on a phone leaves no side room), dock to the emptier vertical
  // edge. This is what keeps the bubble off the brain and off the control on a
  // narrow portrait screen, where the old "right-then-clamp" logic overlapped.
  function placeBubbleBy(box) {
    bubble.style.maxWidth = "";
    const step = index >= 0 ? steps[index] : null;
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

  function placeCaption(where) {
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

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // Stop waiting on the current step's action (leaving the step, or teardown): drop
  // the interactive-tap listener, run the gate's teardown, and remove any veils.
  function clearWait() {
    if (waitEl && waitFn) waitEl.removeEventListener("click", waitFn);
    waitEl = null;
    waitFn = null;
    if (gateCleanup) {
      try { gateCleanup(); } catch (e) { /* best-effort teardown */ }
      gateCleanup = null;
    }
    gateFired = false;
    removeVeils();
  }

  // True while the step's only way forward is a required action not yet done: an
  // interactive step whose target resolved and whose tap (or stayAfterTap demo) has
  // not fired, OR a gate step whose signal() has not fired. When true the Next button
  // is disabled, the backdrop eats every off-target click, and the forward keys are
  // inert, so the user cannot skip the hands-on action. A stayAfterTap step drops out
  // once tapped (its demo is playing), and a gate step once signalled.
  function awaiting() {
    if (index < 0) return false;
    const step = steps[index];
    if (!step) return false;
    if (step.interactive && waitEl && !(step.stayAfterTap && observed)) return true;
    if (step.gate && !gateFired) return true;
    return false;
  }

  // Reflect the current state on the Next button: disabled while an action is still
  // required (see awaiting()), and labelled "Done" on the last step. An interactive
  // tap step hides Next entirely: the highlighted control IS the forward action, so a
  // greyed "Next" beside it is just noise. A stayAfterTap step keeps Next (its tap
  // fires a demo, then Next proceeds); gate and caption steps keep it too.
  function refreshNav() {
    if (index < 0) return;
    const step = steps[index];
    btnNext.hidden = !!(step && step.interactive && !step.stayAfterTap);
    btnNext.disabled = awaiting();
    btnNext.textContent =
      index === steps.length - 1 ? labels.done : labels.next;
  }

  function go(i) {
    clearWait();
    if (i < 0) i = 0;
    if (i >= steps.length) {
      stop("completed");
      return;
    }
    index = i;
    observed = false;
    bubbleDragged = false; // a fresh step re-auto-places the bubble (drop any drag offset)
    bubble.style.transition = ""; // clear a drag's inline transition:none
    scrolling = false; // a fresh step always places its bubble (a prior scroll may not have settled)
    if (scrollTimer) { clearTimeout(scrollTimer); scrollTimer = null; }
    // The very first step snaps into place (no fly-in from the corner); every
    // later step glides from the previous one (smooth step-to-step transitions).
    setAnim(shownOnce);
    shownOnce = true;
    // A step change often triggers a reflow-scroll (before() opens/collapses a
    // section, a modal closes). Guard the next moment so onScroll doesn't flip the
    // ring/bubble to no-anim and snap them: the step-to-step move must glide.
    navGuardUntil = performance.now() + 320;
    // Hold the dim + highlight back for a beat (pre-reveal keeps ring/dim/veil at
    // opacity 0), then fade them in: the scene before() set up reads first, and the
    // overlay lands smoothly rather than snapping on. The bubble text is not held.
    if (revealTimer) { clearTimeout(revealTimer); revealTimer = null; }
    root.classList.add("pre-reveal");
    const step = steps[index];
    try {
      step.before && step.before();
    } catch (e) {
      console.warn("tour step before() failed", e);
    }
    elTitle.textContent = step.title || "";
    elBody.innerHTML = step.body || "";
    elStep.textContent = labels.step(index + 1, steps.length);
    btnBack.disabled = index === 0;

    // Interactive step: the user's real tap on the highlighted target drives it
    // (the app's own handler runs first; our listener is added after it).
    //   - default: the tap advances the tour (open a list, then move on).
    //   - stayAfterTap: the tap fires a live demo we want watched, so the tour
    //     stays put; the spotlight steps aside (see layout `consumed`) and Next
    //     ungreys so the user proceeds when ready.
    if (step.interactive) {
      const el = primaryTarget(step);
      if (el) {
        waitEl = el;
        waitFn = () => {
          if (step.stayAfterTap) {
            observed = true; // the demo is now playing: get the overlay out of its way
            layout();
            refreshNav(); // demo fired: ungrey Next now that no tap is pending
          } else {
            ring.hidden = true; // the target is about to change/disappear; hide it now
            clearHole();
            setTimeout(() => {
              if (active && index === i) go(i + 1);
            }, step.advanceMs || ADVANCE_MS);
          }
        };
        el.addEventListener("click", waitFn, { once: true });
      }
    }

    // Gate step: arm its signal. When the app reports the required action (the user
    // rotated the brain / moved the slider / scrolled the panel / closed the modal)
    // the step stops "awaiting" and Next ungreys, or auto-advances when gateAdvances.
    // step.gate(signal) sets up its own listeners and returns a teardown (run on leave
    // by clearWait). `fired` dedupes; the index guard ignores a late signal after a
    // manual Back/Next moved on.
    if (step.gate) {
      let fired = false;
      const signal = () => {
        if (fired || !active || index !== i) return;
        fired = true;
        gateFired = true;
        if (step.gateAdvances) go(i + 1);
        else refreshNav();
      };
      try {
        gateCleanup = step.gate(signal) || null;
      } catch (e) {
        console.warn("tour step gate() failed", e);
      }
    }

    // Smooth-scroll a scrollTo step's target into view (deferred to its own task;
    // see scrollStepIntoView for why inline would jump). onScroll keeps the ring
    // tracking the row as it slides.
    scrollStepIntoView(step);

    // Reflect the Next button state now that waitEl / the gate (if any) are attached.
    refreshNav();

    // Let the scene set-up (before()) and the new bubble text settle, then
    // measure + position. A scrolled-into-view row or a just-opened list can
    // still reflow a frame or two later (its final rect differs from the first),
    // so re-settle a couple of times: the bubble must track the target's final
    // spot, or it can end up covering the very control the user must tap.
    scheduleLayout();

    // After the opening beat, drop pre-reveal so the (already positioned, still
    // invisible) dim + highlight fade in over the settled scene. The index guard
    // ignores a stale timer after a fast Back/Next moved on.
    revealTimer = setTimeout(() => {
      if (!active || index !== i) return;
      revealTimer = null;
      layout();
      root.classList.remove("pre-reveal");
    }, REVEAL_MS);
  }

  // Whether the ring + bubble ease between positions (smooth) or snap (tight
  // tracking). Steps glide by default; during an active scroll we snap so the
  // ring rides the scrolling row 1:1 instead of lagging behind it.
  function setAnim(on) {
    root.classList.toggle("no-anim", !on);
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
    const startIndex = index;
    setTimeout(() => {
      if (!active || index !== startIndex) return; // step already changed
      const el = primaryTarget(step);
      if (!el) return;
      const c = scrollParent(el);
      if (!c) return;
      const cr = c.getBoundingClientRect();
      const er = el.getBoundingClientRect();
      // Default: centre the target. "top": land its heading near the top of the
      // panel instead (for a section taller than the viewport, centring scrolls
      // past its heading so you can't tell what you're looking at; top keeps it).
      const want = step.scrollAlign === "top"
        ? c.scrollTop + (er.top - cr.top) - SCROLL_TOP_PAD
        : c.scrollTop + (er.top - cr.top) - (c.clientHeight - er.height) / 2;
      const to = Math.max(0, Math.min(want, c.scrollHeight - c.clientHeight));
      if (Math.abs(to - c.scrollTop) < 2) return; // already centred enough
      c.scrollTo({ top: to, behavior: "smooth" });
    }, 0);
  }

  function scheduleLayout() {
    // A step change glides to the new target (smooth). Re-settle a couple of
    // times: a scrolled-into-view row or a just-opened list can reflow a frame
    // or two later, and the bubble must track the target's final spot.
    requestAnimationFrame(() => requestAnimationFrame(layout));
    setTimeout(layout, 180);
    setTimeout(layout, 380);
  }

  // Elastic scroll-clamp: rubber-band the ring by a few px, then spring it back, as
  // tactile feedback that a panel step's scroll just hit a boundary. Uses transform
  // (layout() only writes left/top/width/height), so it composes with the ring flash.
  let bounceTimer = null;
  function ringBounce(dir) {
    if (!ring || ring.hidden) return;
    const y = dir > 0 ? ELASTIC_PX : -ELASTIC_PX;
    ring.style.transition = "transform 0.10s ease-out";
    ring.style.transform = `translateY(${y}px)`;
    if (bounceTimer) clearTimeout(bounceTimer);
    bounceTimer = setTimeout(() => {
      ring.style.transition = "transform 0.26s cubic-bezier(0.22, 1, 0.36, 1)";
      ring.style.transform = "translateY(0)";
      bounceTimer = setTimeout(() => { ring.style.transition = ""; ring.style.transform = ""; }, 280);
    }, 110);
  }

  // On a panel step (dim:false, ring inside a scroll container), keep the highlighted
  // target from being scrolled out of view: if the scroll passes the point where the
  // target's top/bottom edge reaches the container edge, snap it back to that boundary
  // and bounce, so the ring can't drift off over the 3D scene (a short target locks in
  // place; a target taller than the container can be scrolled through but not past).
  // Steps that WANT free scrolling (a scroll gate, see tourGateScroll) opt out with
  // scrollFree:true. Returns true when it clamped.
  function clampTargetScroll(step) {
    if (!step || step.dim !== false || step.scrollFree) return false;
    const el = primaryTarget(step);
    if (!el) return false;
    const c = scrollParent(el);
    if (!c) return false;
    const cr = c.getBoundingClientRect();
    const er = el.getBoundingClientRect();
    const tTop = c.scrollTop + (er.top - cr.top);      // target top within scroll content
    const a = tTop;                                    // scrollTop keeping the target top visible
    const b = tTop + er.height - c.clientHeight;        // ... keeping its bottom visible
    const lo = Math.max(0, Math.min(a, b));
    const hi = Math.min(c.scrollHeight - c.clientHeight, Math.max(a, b));
    const st = c.scrollTop;
    if (st >= lo - 0.5 && st <= hi + 0.5) return false; // within bounds: allow the scroll
    const clamped = Math.max(lo, Math.min(hi, st));
    const over = st - clamped;
    c.scrollTop = clamped;                              // snap back inside bounds
    ringBounce(over > 0 ? 1 : -1);
    return true;
  }

  // Follow the target while the page/panel scrolls (e.g. a row sliding into view,
  // or the user scrolling the list). Snap during the scroll so the ring tracks
  // tightly, then restore the smooth glide once it settles.
  let scrollTimer = null;
  function onScroll() {
    if (index < 0) return;
    const step = steps[index];
    // Elastic clamp first: on a locked panel step this snaps the scroll back and bounces
    // the ring instead of letting the target (and the ring) leave the panel.
    if (clampTargetScroll(step)) { layout(); return; }
    // Just after a step change, a reflow-scroll must not snap: keep the glide on and
    // re-place (the step-to-step move eases in). scrollTo steps are exempt so their
    // programmatic smooth-scroll still snap-tracks its row 1:1.
    if (step && !step.scrollTo && performance.now() < navGuardUntil) {
      layout();
      return;
    }
    scrolling = true; // freeze the bubble (layout skips it); the ring still tracks 1:1
    setAnim(false);
    layout();
    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      if (index < 0) return;
      scrolling = false;
      setAnim(true);
      layout(); // re-place the bubble with the glide on, easing it to its settled spot
    }, 140);
  }

  function onKey(e) {
    if (!active) return;
    if (e.key === "Escape") {
      stop("skipped");
    } else if (e.key === "ArrowRight" || e.key === "Enter") {
      if (!awaiting()) go(index + 1); // when an action is required, keys can't skip it
    } else if (e.key === "ArrowLeft") {
      go(index - 1);
    } else {
      return; // let other keys through
    }
    // Win over the app's global shortcut handlers (n/s/l/.../Esc) while touring.
    e.preventDefault();
    e.stopPropagation();
  }

  function start(opts) {
    if (active) return;
    build();
    active = true;
    shownOnce = false; // snap the first step into place, glide the rest
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
    // Capture phase so the tour's keys take priority over the viewer shortcuts.
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", layout);
    window.addEventListener("scroll", onScroll, true);
    // Capture phase so an off-target click is swallowed before the app's own
    // handlers fire (keeps the walkthrough on the rails, see onClickCapture).
    window.addEventListener("click", onClickCapture, true);
    go(opts && opts.fromStep ? opts.fromStep : 0);
  }

  function stop(reason) {
    if (!active) return;
    active = false;
    index = -1;
    clearWait();
    if (scrollTimer) clearTimeout(scrollTimer);
    if (revealTimer) { clearTimeout(revealTimer); revealTimer = null; }
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", layout);
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("click", onClickCapture, true);
    if (root) {
      clearHole();
      root.classList.remove("pre-reveal");
      root.hidden = true;
      root.setAttribute("aria-hidden", "true");
    }
    // A finished tour (completed) OR one the user explicitly dismissed (Skip / Esc,
    // reason "skipped") is not re-shown automatically. An interrupted visit (reload /
    // tab-close mid-tour) never reaches stop(), so it re-appears next time.
    if (reason === "completed" || reason === "skipped") markSeen();
    try {
      onEnd && onEnd(reason || "completed");
    } catch (e) {
      console.warn("tour onEnd() failed", e);
    }
  }

  return {
    /** Start the tour now (ignores the seen gate; used by the replay button). */
    start,
    /** Stop + run onEnd. */
    stop,
    /** True while the tour is on screen. */
    get active() {
      return active;
    },
    /**
     * Auto-start ONCE on first visit. Runs only when `canStart` is true (the
     * caller's eligibility: not a screenshot/deep-link view, nothing already
     * focused) and the tour was never finished before. Idempotent + safe to
     * call from more than one trigger.
     */
    maybeAutoStart(canStart) {
      if (active || seen() || !canStart) return false;
      start();
      return true;
    },
  };
}
