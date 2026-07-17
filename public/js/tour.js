// Guided "take a tour" coach-marks. A small, app-agnostic overlay engine: it
// knows how to spotlight a DOM element (a dimmed backdrop with a cut-out ring)
// or float a caption over the live scene, and how to step Back / Next / Skip
// through an ordered list. It knows NOTHING about the brain, three.js or the
// data: the caller (js/main.js) supplies the steps, each carrying its own
// `before()` hook that sets the scene up (focus a drug, spread the brain, open a
// section) so the tour can show real features live rather than static pictures.
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
//     dim?:    boolean,            // darken the rest of the page. Defaults true
//                                  // for a spotlight/modal step, false for a
//                                  // caption (so a live brain demo stays visible).
//     placement?: "top" | "center", // caption position when there is no target
//                                  // ("top" = top-centre, "center" = middle).
//     before?: () => void,         // run when the step is shown (idempotent:
//                                  // it re-runs on Back too, so make it set the
//                                  // exact state it wants, not toggle).
//   }

const GAP = 14; // px between the spotlight ring and the bubble
const MARGIN = 12; // px min gap from the viewport edge
const RING_PAD = 6; // px the ring extends past the target on each side

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
  let elTitle, elBody, elStep, btnBack, btnNext, btnSkip;
  let index = -1; // current step, -1 when inactive
  let active = false;

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
    // Eat clicks so a mis-click on the page behind doesn't fire mid-tour; the
    // user drives with the buttons. Does not dismiss (avoids an accidental exit).
    blocker.addEventListener("click", (e) => e.stopPropagation());

    ring = document.createElement("div");
    ring.className = "tour-ring";

    bubble = document.createElement("div");
    bubble.className = "tour-bubble";
    bubble.setAttribute("role", "dialog");
    bubble.setAttribute("aria-modal", "true");
    if (labels.aria) bubble.setAttribute("aria-label", labels.aria);

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
    btnNext = mkBtn("tour-next", labels.next, () => go(index + 1));
    actions.append(btnSkip, btnBack, btnNext);
    foot.append(elStep, actions);

    bubble.append(elTitle, elBody, foot);
    root.append(blocker, ring, bubble);
    document.body.appendChild(root);
  }

  function mkBtn(cls, text, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tour-btn " + cls;
    b.textContent = text;
    b.addEventListener("click", onClick);
    return b;
  }

  // Resolve a step's target to an Element (or null for a caption step). A
  // selector that matches nothing, or an element with no box (display:none),
  // degrades gracefully to a caption.
  function targetOf(step) {
    let el = null;
    if (typeof step.target === "function") el = step.target();
    else if (typeof step.target === "string") el = document.querySelector(step.target);
    if (el && el.getClientRects().length === 0) el = null;
    return el || null;
  }

  function layout() {
    if (index < 0) return;
    const step = steps[index];
    const target = targetOf(step);
    const spotlight = !!target;
    const dim = step.dim !== undefined ? step.dim : (spotlight || !step.target);

    blocker.hidden = !dim;
    blocker.classList.toggle("modal", dim && !spotlight);

    if (spotlight) {
      const r = target.getBoundingClientRect();
      const x = Math.max(0, r.left - RING_PAD);
      const y = Math.max(0, r.top - RING_PAD);
      const w = r.width + RING_PAD * 2;
      const h = r.height + RING_PAD * 2;
      ring.hidden = false;
      ring.style.left = `${x}px`;
      ring.style.top = `${y}px`;
      ring.style.width = `${w}px`;
      ring.style.height = `${h}px`;
      placeBubbleBy({ left: x, top: y, right: x + w, bottom: y + h });
    } else {
      ring.hidden = true;
      placeCaption(step.placement || "top");
    }
  }

  // Position the bubble next to a spotlighted rect. Prefer the right side (the
  // controls panel and toolbar all sit on the left, so the bubble clears them),
  // then left, then below, then above, then clamp into the viewport.
  function placeBubbleBy(box) {
    bubble.style.maxWidth = "";
    const bw = bubble.offsetWidth;
    const bh = bubble.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left, top;
    if (box.right + GAP + bw <= vw - MARGIN) {
      left = box.right + GAP; // right of the target
    } else if (box.left - GAP - bw >= MARGIN) {
      left = box.left - GAP - bw; // left of the target
    } else {
      left = box.left; // stack; clamped below
    }
    // Vertically centre on the target, then clamp.
    top = box.top + (box.bottom - box.top) / 2 - bh / 2;
    left = clamp(left, MARGIN, vw - bw - MARGIN);
    top = clamp(top, MARGIN, vh - bh - MARGIN);
    bubble.style.left = `${left}px`;
    bubble.style.top = `${top}px`;
  }

  function placeCaption(where) {
    const bw = bubble.offsetWidth;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const left = clamp((vw - bw) / 2, MARGIN, vw - bw - MARGIN);
    const top = where === "center" ? (vh - bubble.offsetHeight) / 2 : MARGIN + 8;
    bubble.style.left = `${left}px`;
    bubble.style.top = `${Math.max(MARGIN, top)}px`;
  }

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function go(i) {
    if (i < 0) i = 0;
    if (i >= steps.length) {
      stop("completed");
      return;
    }
    index = i;
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
    btnNext.textContent = index === steps.length - 1 ? labels.done : labels.next;
    // Let the scene set-up (before()) and the new bubble text settle a frame,
    // then measure + position against the up-to-date layout.
    requestAnimationFrame(() => requestAnimationFrame(layout));
  }

  function onKey(e) {
    if (!active) return;
    if (e.key === "Escape") {
      stop("skipped");
    } else if (e.key === "ArrowRight" || e.key === "Enter") {
      go(index + 1);
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
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
    // Capture phase so the tour's keys take priority over the viewer shortcuts.
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", layout);
    window.addEventListener("scroll", layout, true);
    go(opts && opts.fromStep ? opts.fromStep : 0);
  }

  function stop(reason) {
    if (!active) return;
    active = false;
    index = -1;
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", layout);
    window.removeEventListener("scroll", layout, true);
    if (root) {
      root.hidden = true;
      root.setAttribute("aria-hidden", "true");
    }
    markSeen(); // a finished tour (done OR skipped) is not re-shown automatically
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
