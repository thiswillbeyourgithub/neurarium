// The panel's scroll areas show their scrollbar thumb only while in use: a
// scroll, or the pointer moving over the scrollbar gutter, adds `.scroll-active`
// (css/controls.css paints the thumb only then) and it drops after IDLE_MS of
// quiet, so an idle panel shows no bar catching the eye.
const IDLE_MS = 1500;
// Pointer within this many px of the right edge counts as reaching for the bar.
const GUTTER_PX = 16;

/**
 * @param {Iterable<HTMLElement|null>} els the scroll containers
 */
export function autohideScrollbars(els) {
  for (const el of els) {
    if (!el) continue;
    let timer = 0;
    const wake = () => {
      el.classList.add("scroll-active");
      clearTimeout(timer);
      timer = setTimeout(() => el.classList.remove("scroll-active"), IDLE_MS);
    };
    el.addEventListener("scroll", wake, { passive: true });
    el.addEventListener("pointermove", (e) => {
      if (e.pointerType === "mouse" && el.getBoundingClientRect().right - e.clientX < GUTTER_PX) wake();
    }, { passive: true });
  }
}
