// Hover/tap tooltips (the provenance pills, coverage bars, help icons): one bubble
// per trigger, mounted on <body> only while shown, and at most one open at a time.
// A tooltip's content may be a thunk, built on first open, so a panel with hundreds of
// pills pays for none of their bubbles until one is read.

import { extLink } from "./dom.js";

// Only one tooltip is pinned at a time across the whole UI: opening one closes
// whichever was open, so tapping a second pill / bar dismisses the first instead of
// stacking popups. Holds the open tip's `close` (so its scroll/resize listeners are
// torn down too, not just its `.show` class).
let _openTip = null;
// Each live tooltip bubble -> its `close`, for content inside a bubble that must
// dismiss it (see closeTip).
const tipClosers = new WeakMap();

/** Close the tooltip whose bubble is `tipEl` (a no-op for anything else). */
export function closeTip(tipEl) {
  const close = tipEl && tipClosers.get(tipEl);
  if (close) close();
}

/** Close whichever tooltip is open (pinned or hovered), if any. */
export function closeOpenTip() {
  if (_openTip) _openTip();
}

// The nearest ancestor that establishes a containing block for a position:fixed
// descendant (a transform / filter / backdrop-filter / perspective / will-change /
// paint-contain), or null if none (then fixed is viewport-relative). The panel
// #controls carries a backdrop-filter, so a fixed tooltip is offset by it; we walk
// this generically rather than hardcoding #controls.
function fixedContainingBlock(node) {
  for (let n = node.parentElement; n && n !== document.documentElement; n = n.parentElement) {
    const s = getComputedStyle(n);
    const bf = s.backdropFilter || s.webkitBackdropFilter;
    if ((s.transform && s.transform !== "none") ||
        (s.filter && s.filter !== "none") ||
        (bf && bf !== "none") ||
        (s.perspective && s.perspective !== "none") ||
        (s.willChange && /transform|filter|perspective/.test(s.willChange)) ||
        (s.contain && /paint|layout|strict|content/.test(s.contain))) {
      return n;
    }
  }
  return null;
}

/** Tooltip text as a fragment, every bare http(s) URL in it a live link (a source
 * line's resolved page, e.g. a paper's Europe PMC record), the rest plain text. */
export function linkifiedText(text) {
  const frag = document.createDocumentFragment();
  String(text ?? "").split(/(https?:\/\/\S+)/).forEach((part, i) => {
    if (i % 2 === 0) { if (part) frag.append(part); return; }
    frag.append(extLink(part, part));
  });
  return frag;
}

/**
 * Attach a hover/tap tooltip to `trigger`. The bubble is position:fixed just above
 * the trigger, clamped to the viewport, and lives on <body> while shown (so a dimmed
 * ancestor row can't bleed opacity into it, an overflow can't clip it, and you can
 * move onto the bubble to read/select its text). Shows on hover/focus (pointer +
 * keyboard) and is pinned on click/tap: on a touch screen `:hover` never fires, so
 * the click-toggle is the sole path (one tap shows, tap again or tap elsewhere
 * dismisses); on a pointer device a click pins it so its text stays selectable.
 *
 * Shared by the info panel's provenance pills (`opts.wrap` wraps the trigger in a
 * `.help-icon` span and returns that wrapper, so an inline pill anchors to itself)
 * and the sourcing coverage bars (block elements, attached in place with a raised
 * `opts.zIndex` so the bubble clears the #sourcing-modal backdrop).
 * @param {HTMLElement} trigger
 * @param {string|Node|(() => string|Node)} tipText the content, or a thunk building it
 * @returns {HTMLElement} the wrapper when `opts.wrap`, else `trigger` itself.
 */
export function attachTip(trigger, tipText, { wrap = false, zIndex = null } = {}) {
  const host = wrap ? document.createElement("span") : trigger;
  if (wrap) { host.className = "help-icon"; host.append(trigger); }
  const tip = document.createElement("span");
  tip.className = "help-tip";
  tip.setAttribute("role", "tooltip");
  // `tipText` is usually a string (set as textContent). It may instead be a Node
  // (e.g. a fragment carrying a clickable source link): appended live so the link
  // stays interactive. The node is consumed once; it then lives in this bubble
  // permanently, moving in/out of <body> with it on open/close. Or it is a thunk
  // returning either, called on the first open only.
  let filled = false;
  const fill = () => {
    if (filled) return;
    filled = true;
    const content = typeof tipText === "function" ? tipText() : tipText;
    if (content instanceof Node) tip.appendChild(content);
    else tip.appendChild(linkifiedText(content));
  };
  if (zIndex != null) tip.style.zIndex = String(zIndex);
  if (!wrap) trigger.style.cursor = "help";
  let pinned = false, hideTimer = 0;
  const place = () => {
    const r = trigger.getBoundingClientRect();
    const m = 6, gap = 4;
    // Choose the vertical side (above default, matching the arrow-less convention),
    // then cap the bubble to that side's free space so a long tooltip scrolls inside
    // itself (overflow-y:auto) instead of running off-screen and being cropped.
    tip.style.maxHeight = "none";            // measure the natural height first
    const natural = tip.offsetHeight;
    // Free space each side, capped to the viewport (a partly-scrolled trigger can push
    // r.top/r.bottom past the edges, which would otherwise let maxHeight exceed the
    // screen and re-crop a long tooltip).
    const vLimit = window.innerHeight - 2 * m;
    const spaceAbove = Math.min(r.top - m - gap, vLimit);
    const spaceBelow = Math.min(window.innerHeight - r.bottom - m - gap, vLimit);
    let below;
    if (natural <= spaceAbove) below = false;        // fits above -> above
    else if (natural <= spaceBelow) below = true;    // else fits below -> below
    else below = spaceBelow > spaceAbove;            // fits neither -> roomier side (scrolls)
    const avail = Math.max(0, Math.floor(below ? spaceBelow : spaceAbove));
    tip.style.maxHeight = `${avail}px`;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = r.left + r.width / 2 - tw / 2;
    left = Math.max(m, Math.min(left, window.innerWidth - tw - m));
    let top = below ? r.bottom + gap : r.top - th - gap;
    top = Math.max(m, Math.min(top, window.innerHeight - th - m)); // never off-screen
    // With the bubble in <body> there is normally no fixed-positioning containing
    // block (offsets zero), but keep the generic subtraction in case a transformed /
    // filtered ancestor ever forms one.
    const cb = fixedContainingBlock(tip);
    const cbRect = cb ? cb.getBoundingClientRect() : null;
    const ox = cb ? cbRect.left - cb.scrollLeft : 0;
    const oy = cb ? cbRect.top - cb.scrollTop : 0;
    tip.style.left = `${Math.round(left - ox)}px`;
    tip.style.top = `${Math.round(top - oy)}px`;
  };
  const reposition = () => {
    if (!trigger.isConnected) { close(); return; }
    if (tip.classList.contains("show")) place();
  };
  // A scroll INSIDE the bubble (reading a long, height-capped tooltip) must not
  // reposition it: place() re-measures the natural height, which would fight the
  // user's scroll. Only an outside scroll (the page/panel moving) repositions.
  const onScroll = (e) => {
    if (e.target === tip || (e.target instanceof Node && tip.contains(e.target))) return;
    reposition();
  };
  const onDocPointer = (e) => {
    if (host.contains(e.target) || tip.contains(e.target)) return;
    close();
  };
  const open = () => {
    clearTimeout(hideTimer);
    if (_openTip && _openTip !== close) _openTip(); // close any other open tip
    _openTip = close;
    fill();
    if (!tip.isConnected) document.body.appendChild(tip);
    tip.classList.add("show");
    place();
    // Re-place after this frame: tapping a button can focus-scroll it into view
    // *after* the click handler runs, which would otherwise strand the bubble.
    requestAnimationFrame(place);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", reposition);
    document.addEventListener("pointerdown", onDocPointer, true);
  };
  const close = () => {
    clearTimeout(hideTimer);
    pinned = false;
    if (_openTip === close) _openTip = null;
    tip.classList.remove("show");
    tip.remove();
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("resize", reposition);
    document.removeEventListener("pointerdown", onDocPointer, true);
  };
  // Exposed so an interactive element *inside* the bubble (e.g. a provenance pill's
  // "Click for details" cue) can dismiss it cleanly before opening a popup.
  tipClosers.set(tip, close);
  const scheduleHide = () => {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (pinned || trigger.matches(":hover") || tip.matches(":hover")) return;
      close();
    }, 160);
  };
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    if (pinned) close(); else { pinned = true; open(); }
  });
  const canHover = !window.matchMedia ||
    window.matchMedia("(hover: hover)").matches;
  if (canHover) {
    trigger.addEventListener("mouseenter", open);
    trigger.addEventListener("mouseleave", scheduleHide);
    trigger.addEventListener("focus", open);
    trigger.addEventListener("blur", scheduleHide);
    tip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
    tip.addEventListener("mouseleave", scheduleHide);
  }
  return host;
}
