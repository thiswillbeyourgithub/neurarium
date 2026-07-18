// Guided "take a tour" coach-marks. A small, app-agnostic overlay engine: it
// knows how to spotlight a DOM element (a dimmed backdrop with a cut-out ring)
// or float a caption over the live scene, and how to step Back / Next / Skip
// through an ordered list. It knows NOTHING about the brain, three.js or the
// data: the caller (js/main.js) supplies the steps, each carrying its own
// `before()` hook that sets the scene up (spread the brain, open a section) so
// the tour can show real features live rather than static pictures.
//
// Two kinds of spotlight step:
//   - passive: the ring highlights an element while the backdrop eats every
//     click; the user reads and presses Next.
//   - interactive (`interactive:true`): the backdrop gets a click-through hole
//     over the target (a clip-path cut-out), so the user's real tap reaches the
//     highlighted control. The tour advances when they actually do it (Next
//     stays as a fallback so a stuck user is never trapped).
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
//     scrollTo?: boolean,          // scrollIntoView the target when shown (rows
//                                  // deep in a scrolling panel).
//     dim?:    boolean,            // darken the rest of the page. Defaults true
//                                  // for a spotlight/modal step, false for a
//                                  // caption (so a live brain demo stays visible).
//     placement?: "top" | "center" | "brain", // caption position when there is
//                                  // no target. "brain" = keep the 3D scene
//                                  // clear (bottom on a portrait phone where the
//                                  // brain is up top, top on a wide screen).
//     before?: () => void,         // run when the step is shown (idempotent:
//                                  // it re-runs on Back too, so make it set the
//                                  // exact state it wants, not toggle).
//   }

const GAP = 14; // px between the spotlight ring and the bubble
const MARGIN = 12; // px min gap from the viewport edge
const RING_PAD = 6; // px the ring extends past the target on each side
const ADVANCE_MS = 360; // let the tapped action (open a tab, spread) settle first

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
  let waitEl = null; // the element an interactive step is waiting on
  let waitFn = null; // its one-shot click handler (removed on leave)
  let observed = false; // a stayAfterTap step whose demo has been triggered

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
    // On an interactive step a clip-path hole (see setHole) lets the tap through
    // to the real target; everything else the blocker still swallows.
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

  function layout() {
    if (index < 0) return;
    const step = steps[index];
    const target = targetOf(step);
    // A stayAfterTap step, once tapped, steps its spotlight aside so the live
    // demo it triggered is watchable: no ring, no dim, bubble tucked off the scene.
    const consumed = !!step.stayAfterTap && observed;
    const spotlight = !!target && !consumed;
    const interactive = spotlight && !!step.interactive;
    const dim = consumed
      ? false
      : step.dim !== undefined
        ? step.dim
        : spotlight || !step.target;

    blocker.hidden = !dim && !interactive; // an interactive step always needs the blocker (to hole it)
    blocker.classList.toggle("modal", dim && !spotlight);

    if (spotlight) {
      const r = target.getBoundingClientRect();
      const x = Math.max(0, r.left - RING_PAD);
      const y = Math.max(0, r.top - RING_PAD);
      const w = r.width + RING_PAD * 2;
      const h = r.height + RING_PAD * 2;
      ring.hidden = false;
      ring.classList.toggle("interactive", interactive);
      ring.style.left = `${x}px`;
      ring.style.top = `${y}px`;
      ring.style.width = `${w}px`;
      ring.style.height = `${h}px`;
      const box = { left: x, top: y, right: x + w, bottom: y + h };
      if (interactive) setHole(box);
      else clearHole();
      placeBubbleBy(box);
    } else {
      ring.hidden = true;
      clearHole();
      placeCaption(consumed ? "brain" : step.placement || "top");
    }
  }

  // Position the bubble against a spotlighted rect without covering it. Try to
  // the right, then left, then below, then above; if none fits (a full-width
  // bottom sheet on a phone leaves no side room), dock to the emptier vertical
  // edge. This is what keeps the bubble off the brain and off the control on a
  // narrow portrait screen, where the old "right-then-clamp" logic overlapped.
  function placeBubbleBy(box) {
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
    if (vw - box.right >= needW) {
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
    const left = clamp((vw - bw) / 2, MARGIN, vw - bw - MARGIN);
    let top;
    if (where === "center") {
      top = (vh - bh) / 2;
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

  // Stop waiting on an interactive target (leaving the step, or teardown).
  function clearWait() {
    if (waitEl && waitFn) waitEl.removeEventListener("click", waitFn);
    waitEl = null;
    waitFn = null;
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

    // Interactive step: the user's real tap on the highlighted target drives it
    // (the app's own handler runs first; our listener is added after it). Next
    // stays visible as a fallback so a mis-tap can never trap the user.
    //   - default: the tap advances the tour (open a list, then move on).
    //   - stayAfterTap: the tap fires a live demo we want watched, so the tour
    //     stays put; the spotlight steps aside (see layout `consumed`) and Next
    //     proceeds when the user is ready.
    if (step.interactive) {
      const el = targetOf(step);
      if (el) {
        if (step.scrollTo) {
          try {
            el.scrollIntoView({ block: "center", inline: "nearest" });
          } catch (e) {
            el.scrollIntoView();
          }
        }
        waitEl = el;
        waitFn = () => {
          if (step.stayAfterTap) {
            observed = true; // the demo is now playing: get the overlay out of its way
            layout();
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

    // Let the scene set-up (before()) and the new bubble text settle, then
    // measure + position. A scrolled-into-view row or a just-opened list can
    // still reflow a frame or two later (its final rect differs from the first),
    // so re-settle a couple of times: the bubble must track the target's final
    // spot, or it can end up covering the very control the user must tap.
    scheduleLayout();
  }

  function scheduleLayout() {
    // Place instantly on entry (no transition sweep over the target), then drop
    // the guard so the later re-settles animate gently.
    root.classList.add("no-anim");
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        layout();
        requestAnimationFrame(() => root.classList.remove("no-anim"));
      }),
    );
    setTimeout(layout, 160);
    setTimeout(layout, 340);
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
    clearWait();
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", layout);
    window.removeEventListener("scroll", layout, true);
    if (root) {
      clearHole();
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
