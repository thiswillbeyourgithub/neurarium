// The tour's overlay DOM: the click-eating blocker, the spotlight ring, the bubble
// (title / body / Skip-Back-Next foot, drag-repositionable), the scroll arrow and
// the pooled veils. Built once, lazily, into the shared tour state `st`.

import { MARGIN, clamp, resolveTargets } from "./layout.js";

/**
 * Build the overlay into `st` (root, blocker, ring, bubble, scrollArrow and the
 * bubble's text/button elements) and mount it on <body>. No-op once built.
 * @param {object} st  shared tour state
 * @param {object} labels  the createTour labels
 * @param {{onBlocker:()=>void, onSkip:()=>void, onBack:()=>void, onNext:()=>void}} on
 */
export function buildOverlay(st, labels, on) {
  if (st.root) return;
  const root = document.createElement("div");
  root.id = "tour-root";
  root.setAttribute("aria-hidden", "true");

  const blocker = document.createElement("div");
  blocker.className = "tour-blocker";
  // Eat clicks so a mis-click on the page behind doesn't fire mid-tour. On a
  // passive/caption step a click on the dim backdrop is "continue" (there is no
  // Next button). On an interactive step a clip-path hole (see setHole) lets the
  // tap through to the real target and awaiting() is true, so a click that
  // lands on the blocker (off the target) is swallowed without advancing: the
  // user must act on the highlighted control. Never dismisses (no accidental exit).
  blocker.addEventListener("click", (e) => {
    e.stopPropagation();
    on.onBlocker();
  });

  const ring = document.createElement("div");
  ring.className = "tour-ring";

  const bubble = document.createElement("div");
  bubble.className = "tour-bubble";
  bubble.setAttribute("role", "dialog");
  bubble.setAttribute("aria-modal", "true");
  if (labels.aria) bubble.setAttribute("aria-label", labels.aria);
  enableBubbleDrag(st, bubble);

  const elTitle = document.createElement("div");
  elTitle.className = "tour-title";
  const elBody = document.createElement("div");
  elBody.className = "tour-body";

  const foot = document.createElement("div");
  foot.className = "tour-foot";
  const elStep = document.createElement("span");
  elStep.className = "tour-step";
  const actions = document.createElement("div");
  actions.className = "tour-actions";
  const btnSkip = mkBtn("tour-skip", labels.skip, on.onSkip);
  const btnBack = mkBtn("tour-back", labels.back, on.onBack);
  // The Next button is the sole forward affordance (no "click to continue" link).
  // On a hands-on step it stays disabled until the required action is done (see
  // awaiting()); clicking it advances, or finishes on the last step.
  const btnNext = mkBtn("tour-next", labels.next, on.onNext);
  actions.append(btnSkip, btnBack, btnNext);
  foot.append(elStep, actions);

  // The scroll arrow (see updateScrollArrow). Three nested elements on purpose:
  // the outer one is positioned, the middle one bobs, the inner chevron rotates
  // for the "up" direction, so none of the three transforms fights the others.
  const scrollArrow = document.createElement("div");
  scrollArrow.className = "tour-scroll-arrow";
  scrollArrow.hidden = true;
  if (labels.scrollHint) scrollArrow.setAttribute("aria-label", labels.scrollHint);
  const bob = document.createElement("span");
  bob.className = "tour-arrow-bob";
  bob.innerHTML = '<svg viewBox="0 0 32 32" aria-hidden="true">'
    + '<path d="M6 11l10 11 10-11" /></svg>';
  scrollArrow.appendChild(bob);

  bubble.append(elTitle, elBody, foot);
  root.append(blocker, ring, scrollArrow, bubble);
  document.body.appendChild(root);
  Object.assign(st, {
    root, blocker, ring, bubble, scrollArrow,
    elTitle, elBody, elStep, btnSkip, btnBack, btnNext,
  });
}

// Let the user drag the bubble out of the way (touch or mouse) so it can be
// moved off anything it happens to occlude. Once dragged, the bubble stays put
// for the rest of the step (layout() stops auto-placing it); a step change
// (go()) resets it. A press that starts on a button or a link is left alone so
// those keep working; a tiny jitter under the threshold still counts as a click.
function enableBubbleDrag(st, bubble) {
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
    if (moved) st.bubbleDragged = true; // stop auto-placing it for the rest of this step
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

// A translucent "veil" over specific elements (e.g. the controls panel) so a step
// can dim just those while leaving the 3D scene fully interactive. The veils are
// pointer-events:none (purely visual: the veiled UI still works), pooled in
// `st.veilEls`, and re-sized every layout(). `step.veil` is a selector, an element,
// a resolver, or an array of those (resolved like a target).
export function applyVeil(st, step) {
  const els = resolveTargets(step, "veil");
  while (st.veilEls.length < els.length) {
    const v = document.createElement("div");
    v.className = "tour-veil";
    st.root.appendChild(v);
    st.veilEls.push(v);
  }
  for (let k = 0; k < st.veilEls.length; k++) {
    const v = st.veilEls[k];
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
export function removeVeils(st) {
  for (const v of st.veilEls) v.remove();
  st.veilEls = [];
}
