// Guided "take a tour" coach-marks. A small, app-agnostic overlay engine: it
// knows how to spotlight a DOM element (a dimmed backdrop with a cut-out ring)
// or float a caption over the live scene, and how to step Back / Skip through an
// ordered list. It knows NOTHING about the brain, three.js or the data: the
// caller (js/main.js) supplies the steps, each carrying its own `before()` hook
// that sets the scene up (spread the brain, open a section) so the tour can show
// real features live rather than static pictures.
//
// There is deliberately NO Next button (only Back + Skip): the user advances by
// acting on the step, so they cannot fast-forward past a hands-on demo and leave
// the UI half-set-up. How forward works depends on the step:
//   - passive / caption: a "click to continue" cue sits in the bubble, and a
//     click on the dim backdrop also advances (a live-scene step with no backdrop
//     advances via the cue only, keeping the scene draggable).
//   - interactive (`interactive:true`): the backdrop gets a click-through hole
//     over the target (a clip-path cut-out), so the user's real tap reaches the
//     highlighted control and drives the tour. The cue is hidden and every click
//     off the target is eaten, so the only way forward is the real tap: the user
//     cannot skip the hands-on action. Back/Skip (and Esc) stay the escapes.
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
  let elTitle, elBody, elCue, elStep, btnBack, btnSkip;
  let index = -1; // current step, -1 when inactive
  let active = false;
  let waitEl = null; // the element an interactive step is waiting on
  let waitFn = null; // its one-shot click handler (removed on leave)
  let observed = false; // a stayAfterTap step whose demo has been triggered
  let shownOnce = false; // false until the first step paints (snap it, don't fly in)
  let scrolling = false; // true while a scrollTo row is easing into view (see onScroll)

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
    // tap through to the real target and awaitingTap() is true, so a click that
    // lands on the blocker (off the target) is swallowed without advancing: the
    // user must act on the highlighted control. Never dismisses (no accidental exit).
    blocker.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!awaitingTap()) go(index + 1);
    });

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

    // The "click to continue" cue (there is no Next button). Shown on a step that
    // is not awaiting a real tap; clicking it advances. Hidden on an interactive
    // step, whose body already says which control to tap.
    elCue = document.createElement("div");
    elCue.className = "tour-cue";
    elCue.addEventListener("click", () => {
      if (!awaitingTap()) go(index + 1);
    });

    const foot = document.createElement("div");
    foot.className = "tour-foot";
    elStep = document.createElement("span");
    elStep.className = "tour-step";
    const actions = document.createElement("div");
    actions.className = "tour-actions";
    btnSkip = mkBtn("tour-skip", labels.skip, () => stop("skipped"));
    btnBack = mkBtn("tour-back", labels.back, () => go(index - 1));
    actions.append(btnSkip, btnBack);
    foot.append(elStep, actions);

    bubble.append(elTitle, elBody, elCue, foot);
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

  function layout() {
    if (index < 0) return;
    const step = steps[index];
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
      if (!scrolling) placeBubbleBy(box);
    } else {
      ring.hidden = true;
      clearHole();
      if (!scrolling) placeCaption(consumed ? "brain" : step.placement || "top");
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

  // True while the step's only way forward is a real tap on its highlighted
  // target: an interactive step whose target resolved and whose demo (if any)
  // has not fired yet. When true, the cue is hidden, the backdrop eats every
  // off-target click, and forward keys are inert, so the user cannot skip the
  // hands-on action. A stayAfterTap step drops out of "awaiting" once tapped
  // (its demo is playing) so the cue can offer "continue".
  function awaitingTap() {
    if (index < 0) return false;
    const step = steps[index];
    if (!step || !step.interactive || !waitEl) return false;
    return !(step.stayAfterTap && observed);
  }

  // Show/hide the "click to continue" cue for the current state. Hidden while a
  // real tap is required; otherwise a clickable cue ("Done" on the last step).
  function refreshCue() {
    if (index < 0) return;
    const wait = awaitingTap();
    elCue.hidden = wait;
    if (wait) return;
    elCue.textContent =
      index === steps.length - 1 ? labels.done : labels.continue;
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
    scrolling = false; // a fresh step always places its bubble (a prior scroll may not have settled)
    if (scrollTimer) { clearTimeout(scrollTimer); scrollTimer = null; }
    // The very first step snaps into place (no fly-in from the corner); every
    // later step glides from the previous one (smooth step-to-step transitions).
    setAnim(shownOnce);
    shownOnce = true;
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
    // (the app's own handler runs first; our listener is added after it). Next
    // stays visible as a fallback so a mis-tap can never trap the user.
    //   - default: the tap advances the tour (open a list, then move on).
    //   - stayAfterTap: the tap fires a live demo we want watched, so the tour
    //     stays put; the spotlight steps aside (see layout `consumed`) and Next
    //     proceeds when the user is ready.
    if (step.interactive) {
      const el = primaryTarget(step);
      if (el) {
        waitEl = el;
        waitFn = () => {
          if (step.stayAfterTap) {
            observed = true; // the demo is now playing: get the overlay out of its way
            layout();
            refreshCue(); // demo fired: offer "continue" now that no tap is pending
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

    // Smooth-scroll a scrollTo step's target into view (deferred to its own task;
    // see scrollStepIntoView for why inline would jump). onScroll keeps the ring
    // tracking the row as it slides.
    scrollStepIntoView(step);

    // Set the "click to continue" cue now that waitEl (if any) is attached.
    refreshCue();

    // Let the scene set-up (before()) and the new bubble text settle, then
    // measure + position. A scrolled-into-view row or a just-opened list can
    // still reflow a frame or two later (its final rect differs from the first),
    // so re-settle a couple of times: the bubble must track the target's final
    // spot, or it can end up covering the very control the user must tap.
    scheduleLayout();
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
      const want = c.scrollTop + (er.top - cr.top) - (c.clientHeight - er.height) / 2;
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

  // Follow the target while the page/panel scrolls (e.g. a row sliding into view,
  // or the user scrolling the list). Snap during the scroll so the ring tracks
  // tightly, then restore the smooth glide once it settles.
  let scrollTimer = null;
  function onScroll() {
    if (index < 0) return;
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
      if (!awaitingTap()) go(index + 1); // when a tap is required, keys can't skip it
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
    go(opts && opts.fromStep ? opts.fromStep : 0);
  }

  function stop(reason) {
    if (!active) return;
    active = false;
    index = -1;
    clearWait();
    if (scrollTimer) clearTimeout(scrollTimer);
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", layout);
    window.removeEventListener("scroll", onScroll, true);
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
