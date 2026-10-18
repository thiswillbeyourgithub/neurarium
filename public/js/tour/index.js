// Guided "see the tutorial" coach-marks. A small, app-agnostic overlay engine: it
// knows how to spotlight a DOM element (a dimmed backdrop with a cut-out ring)
// or float a caption over the live scene, and how to step Back / Skip through an
// ordered list. It knows NOTHING about the brain, three.js or the data: the
// caller (js/boot/tour-steps.js) supplies the steps, each carrying its own `before()` hook
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
// Split: overlay.js (DOM + drag + veils), layout.js (targets, ring, hole, bubble
// placement), scroll.js (scroll-into-view, scroll arrow, clamp, scroll-follow);
// this file owns the step machine (go / start / stop). Kept dependency-free (like
// js/circuit-schedule.js) so it stays reusable and the no-build viewer loads it as
// plain ES modules.
//
// A step:
//   {
//     title:   string,             // already localized (caller resolves via t())
//     body:    string,             // already localized HTML (built with i18n tHtml, which escapes interpolated values)
//     target?: string | () => Element | null,  // element to spotlight; a CSS
//                                  // selector or a resolver. Absent/unresolved
//                                  // => a caption step (no spotlight).
//     interactive?: boolean,       // let the user's tap reach the target and
//                                  // advance the tour (click-through hole).
//     stayAfterTap?: boolean,      // (interactive) the tap fires a demo to watch:
//                                  // stay on the step, step the spotlight aside,
//                                  // ungrey Next instead of auto-advancing.
//     tapTarget?: sel|el|fn,       // (interactive) the element whose click counts,
//                                  // when it is not the ringed one: e.g. ring a
//                                  // pointer-events:none label so the ring hugs
//                                  // it, while the tap lands on the hit button
//                                  // under it. Default: the first target.
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

import { loadString, saveString } from "../prefs.js";
import { applyVeil, buildOverlay, removeVeils } from "./overlay.js";
import { clearHole, layoutStep, primaryTarget, tapTarget } from "./layout.js";
import { SCROLL_RECHECK_MS, createTourScroll, targetArrived } from "./scroll.js";

const ADVANCE_MS = 360; // let the tapped action (open a tab, spread) settle first
const REVEAL_MS = 1000; // hold the dim + highlight back this long, then fade it in,
// so the scene the step just set up reads for a beat before the overlay lands on it
const REVEAL_WAIT_MAX_MS = 4000; // longest a scrollTo step holds its reveal for the target to arrive

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
  // State shared with overlay.js / layout.js / scroll.js. The overlay elements
  // (root, blocker, ring, bubble, scrollArrow, elTitle, elBody, elStep, btnSkip,
  // btnBack, btnNext) are filled in by buildOverlay on first start.
  const st = {
    steps,
    root: null, // the overlay DOM (built lazily on first start)
    blocker: null, // full-screen click-eater / modal dim
    ring: null, // the spotlight cut-out (box-shadow does the dimming)
    bubble: null,
    scrollArrow: null, // the purple "look this way" chevron (see updateScrollArrow)
    veilEls: [], // pooled translucent "veil" divs (partial dim over UI)
    index: -1, // current step, -1 when inactive
    active: false,
    observed: false, // a stayAfterTap step whose demo has been triggered
    navGuardUntil: 0, // performance.now() until which a reflow-scroll after a step
    // change must NOT snap (so the step-to-step move glides); see go() + onScroll()
    scrolling: false, // true while a scrollTo row is easing into view (see onScroll)
    bubbleDragged: false, // user dragged the bubble this step: stop auto-placing it
    userScrolled: false, // user scrolled by hand this step: scrollStepIntoView backs off
  };
  let waitEl = null; // the element an interactive step is waiting on
  let waitFn = null; // its one-shot click handler (removed on leave)
  let gateFired = false; // a gate step's signal() has fired (Next may ungrey)
  let gateCleanup = null; // the current gate's teardown (removes its listeners)
  let shownOnce = false; // false until the first step paints (snap it, don't fly in)
  let revealTimer = null; // the setTimeout that ends a step's opening beat + fades in the overlay

  // Storage blocked reads as unseen (no worse than a re-show); the mark is best-effort.
  const seen = () => !!seenKey && loadString(seenKey) === "1";
  const markSeen = () => {
    if (seenKey) saveString(seenKey, "1");
  };

  const scroll = createTourScroll(st, { layout, setAnim });
  const next = () => { if (!awaiting()) go(st.index + 1); };

  function build() {
    buildOverlay(st, labels, {
      onBlocker: next,
      onSkip: () => stop("skipped"),
      onBack: () => go(st.index - 1),
      onNext: next,
    });
  }

  // Is `target` a control the current step invites the user to click? The tour's
  // own bubble is always live; beyond it, only an interactive step's tap target and
  // any `clickThrough` element(s) are. Everything else is inert while a step shows
  // (see onClickCapture), so a stray tap on a row/toolbar can't derail the tour.
  function isClickAllowed(target) {
    const step = st.index >= 0 ? steps[st.index] : null;
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
  // tap on the 3D scene is separately made inert by the scene picking (handleSelect).
  function onClickCapture(e) {
    if (!st.active) return;
    if (st.bubble && st.bubble.contains(e.target)) return;
    if (isClickAllowed(e.target)) return;
    e.stopPropagation();
    e.preventDefault();
  }

  function layout() {
    if (st.index < 0) return;
    const step = steps[st.index];
    applyVeil(st, step);
    layoutStep(st, step);
    scroll.updateScrollArrow();
  }

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
    removeVeils(st);
  }

  // True while the step's only way forward is a required action not yet done: an
  // interactive step whose target resolved and whose tap (or stayAfterTap demo) has
  // not fired, OR a gate step whose signal() has not fired. When true the Next button
  // is disabled, the backdrop eats every off-target click, and the forward keys are
  // inert, so the user cannot skip the hands-on action. A stayAfterTap step drops out
  // once tapped (its demo is playing), and a gate step once signalled.
  function awaiting() {
    if (st.index < 0) return false;
    const step = steps[st.index];
    if (!step) return false;
    if (step.interactive && waitEl && !(step.stayAfterTap && st.observed)) return true;
    if (step.gate && !gateFired) return true;
    return false;
  }

  // Reflect the current state on the Next button: disabled while an action is still
  // required (see awaiting()), and labelled "Done" on the last step. An interactive
  // tap step hides Next entirely: the highlighted control IS the forward action, so a
  // greyed "Next" beside it is just noise. A stayAfterTap step keeps Next (its tap
  // fires a demo, then Next proceeds); gate and caption steps keep it too.
  function refreshNav() {
    if (st.index < 0) return;
    const step = steps[st.index];
    st.btnNext.hidden = !!(step && step.interactive && !step.stayAfterTap);
    st.btnNext.disabled = awaiting();
    st.btnNext.textContent =
      st.index === steps.length - 1 ? labels.done : labels.next;
  }

  function go(i) {
    clearWait();
    if (i < 0) i = 0;
    if (i >= steps.length) {
      stop("completed");
      return;
    }
    st.index = i;
    st.observed = false;
    st.userScrolled = false; // a fresh step may re-scroll its target into view (see scrollStepIntoView)
    st.bubbleDragged = false; // a fresh step re-auto-places the bubble (drop any drag offset)
    st.bubble.style.transition = ""; // clear a drag's inline transition:none
    st.scrolling = false; // a fresh step always places its bubble (a prior scroll may not have settled)
    scroll.hideScrollArrow(); // the previous step's arrow points nowhere now
    scroll.cancelScrollSettle();
    // The very first step snaps into place (no fly-in from the corner); every
    // later step glides from the previous one (smooth step-to-step transitions).
    setAnim(shownOnce);
    shownOnce = true;
    // A step change often triggers a reflow-scroll (before() opens/collapses a
    // section, a modal closes). Guard the next moment so onScroll doesn't flip the
    // ring/bubble to no-anim and snap them: the step-to-step move must glide.
    st.navGuardUntil = performance.now() + 320;
    // Hold the dim + highlight back for a beat (pre-reveal keeps ring/dim/veil at
    // opacity 0), then fade them in: the scene before() set up reads first, and the
    // overlay lands smoothly rather than snapping on. The bubble text is not held.
    if (revealTimer) { clearTimeout(revealTimer); revealTimer = null; }
    st.root.classList.add("pre-reveal");
    const step = steps[st.index];
    try {
      step.before && step.before();
    } catch (e) {
      console.warn("tour step before() failed", e);
    }
    st.elTitle.textContent = step.title || "";
    st.elBody.innerHTML = step.body || "";
    st.elStep.textContent = labels.step(st.index + 1, steps.length);
    st.btnBack.disabled = st.index === 0;

    // Interactive step: the user's real tap on the highlighted target drives it
    // (the app's own handler runs first; our listener is added after it).
    //   - default: the tap advances the tour (open a list, then move on).
    //   - stayAfterTap: the tap fires a live demo we want watched, so the tour
    //     stays put; the spotlight steps aside (see layout `consumed`) and Next
    //     ungreys so the user proceeds when ready.
    if (step.interactive) {
      const el = tapTarget(step);
      if (el) {
        waitEl = el;
        waitFn = () => {
          if (step.stayAfterTap) {
            st.observed = true; // the demo is now playing: get the overlay out of its way
            layout();
            refreshNav(); // demo fired: ungrey Next now that no tap is pending
          } else {
            st.ring.hidden = true; // the target is about to change/disappear; hide it now
            clearHole(st);
            setTimeout(() => {
              if (st.active && st.index === i) go(i + 1);
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
        if (fired || !st.active || st.index !== i) return;
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
    scroll.scrollStepIntoView(step);

    // Reflect the Next button state now that waitEl / the gate (if any) are attached.
    refreshNav();

    // Let the scene set-up (before()) and the new bubble text settle, then
    // measure + position. A scrolled-into-view row or a just-opened list can
    // still reflow a frame or two later (its final rect differs from the first),
    // so re-settle a couple of times: the bubble must track the target's final
    // spot, or it can end up covering the very control the user must tap.
    scheduleLayout();

    // After the opening beat, drop pre-reveal so the (already positioned, still
    // invisible) dim + highlight fade in over the settled scene. A scrollTo step also
    // holds it until its target has scrolled into view and stopped moving (bounded by
    // REVEAL_WAIT_MAX_MS), so the ring never lands on a row that is still off-screen.
    // The index guard ignores a stale timer after a fast Back/Next moved on.
    const revealAt = performance.now() + REVEAL_MS + REVEAL_WAIT_MAX_MS;
    let lastTop = null;
    const reveal = () => {
      if (!st.active || st.index !== i) return;
      const el = step.scrollTo ? primaryTarget(step) : null;
      const top = el ? el.getBoundingClientRect().top : null;
      const settled = !el || (targetArrived(step) && top === lastTop);
      lastTop = top;
      if (!settled && performance.now() < revealAt) {
        revealTimer = setTimeout(reveal, SCROLL_RECHECK_MS);
        return;
      }
      revealTimer = null;
      layout();
      st.root.classList.remove("pre-reveal");
    };
    revealTimer = setTimeout(reveal, REVEAL_MS);
  }

  // Whether the ring + bubble ease between positions (smooth) or snap (tight
  // tracking). Steps glide by default; during an active scroll we snap so the
  // ring rides the scrolling row 1:1 instead of lagging behind it.
  function setAnim(on) {
    st.root.classList.toggle("no-anim", !on);
  }

  function scheduleLayout() {
    // A step change glides to the new target (smooth). Re-settle a couple of
    // times: a scrolled-into-view row or a just-opened list can reflow a frame
    // or two later, and the bubble must track the target's final spot.
    requestAnimationFrame(() => requestAnimationFrame(layout));
    setTimeout(layout, 180);
    setTimeout(layout, 380);
  }

  function onKey(e) {
    if (!st.active) return;
    if (e.key === "Escape") {
      stop("skipped");
    } else if (e.key === "ArrowRight" || e.key === "Enter") {
      if (!awaiting()) go(st.index + 1); // when an action is required, keys can't skip it
    } else if (e.key === "ArrowLeft") {
      go(st.index - 1);
    } else {
      return; // let other keys through
    }
    // Win over the app's global shortcut handlers (n/s/l/.../Esc) while touring.
    e.preventDefault();
    e.stopPropagation();
  }

  function start(opts) {
    if (st.active) return;
    build();
    st.active = true;
    shownOnce = false; // snap the first step into place, glide the rest
    st.root.hidden = false;
    st.root.setAttribute("aria-hidden", "false");
    // Capture phase so the tour's keys take priority over the viewer shortcuts.
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", layout);
    window.addEventListener("scroll", scroll.onScroll, true);
    // Capture phase so an off-target click is swallowed before the app's own
    // handlers fire (keeps the walkthrough on the rails, see onClickCapture).
    window.addEventListener("click", onClickCapture, true);
    // A real scroll gesture (as opposed to our own programmatic scrollTo, which emits
    // "scroll" but no wheel/touch): it tells scrollStepIntoView to stop re-centring.
    window.addEventListener("wheel", scroll.onUserScroll, { capture: true, passive: true });
    window.addEventListener("touchmove", scroll.onUserScroll, { capture: true, passive: true });
    // Non-passive (it may preventDefault): the boundary stop for a locked panel step.
    window.addEventListener("wheel", scroll.onWheelClamp, { capture: true, passive: false });
    go(opts && opts.fromStep ? opts.fromStep : 0);
  }

  function stop(reason) {
    if (!st.active) return;
    st.active = false;
    st.index = -1;
    clearWait();
    scroll.cancelScrollSettle();
    if (revealTimer) { clearTimeout(revealTimer); revealTimer = null; }
    scroll.resetScrollArrow();
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", layout);
    window.removeEventListener("scroll", scroll.onScroll, true);
    window.removeEventListener("click", onClickCapture, true);
    window.removeEventListener("wheel", scroll.onUserScroll, true);
    window.removeEventListener("touchmove", scroll.onUserScroll, true);
    window.removeEventListener("wheel", scroll.onWheelClamp, true);
    if (st.root) {
      clearHole(st);
      st.root.classList.remove("pre-reveal");
      st.root.hidden = true;
      st.root.setAttribute("aria-hidden", "true");
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
      return st.active;
    },
    /**
     * Auto-start ONCE on first visit. Runs only when `canStart` is true (the
     * caller's eligibility: not a screenshot/deep-link view, nothing already
     * focused) and the tour was never finished before. Idempotent + safe to
     * call from more than one trigger.
     */
    maybeAutoStart(canStart) {
      if (st.active || seen() || !canStart) return false;
      start();
      return true;
    },
  };
}
