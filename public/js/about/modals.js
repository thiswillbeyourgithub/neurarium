// The popups: one wireModal seam every modal goes through (so the URL can name the
// one on screen, see setModalToggle), the About / Legend / Sources popups, the image
// lightbox and the keyboard-shortcuts help.

const { t } = window.__I18N__;

/**
 * Keyboard-shortcuts help popup (#shortcuts-modal). Fills the key -> action rows
 * from the i18n catalogue (so each language reads right) and returns a small
 * controller; wireShortcuts opens it on `?` and closes it on Esc, the toolbar's
 * keyboard button opens it, and the ×, a backdrop click, or Esc close it.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
export function wireShortcutsHelp() {
  const modal = document.getElementById("shortcuts-modal");
  const list = document.getElementById("shortcuts-list");
  const noop = { open() {}, close() {}, get isOpen() { return false; } };
  if (!modal || !list) return noop;

  // One row per shortcut, mirroring the keys wired in wireShortcuts so the popup
  // can't drift from the actual bindings. The label is a localized action.
  const ROWS = [
    { keys: ["N"], desc: "shortcuts.names" },
    { keys: ["S"], desc: "shortcuts.spread" },
    { keys: ["L"], desc: "shortcuts.structures" },
    { keys: ["P"], desc: "shortcuts.projections" },
    { keys: ["K"], desc: "shortcuts.legend" },
    { keys: ["C"], desc: "shortcuts.seeInside" },
    { keys: ["R"], desc: "shortcuts.receptors" },
    { keys: ["M"], desc: "shortcuts.drugs" },
    { keys: ["F"], desc: "shortcuts.search" },
    { keys: ["Shift", "F"], desc: "shortcuts.findInPanel" },
    { keys: ["Tab"], desc: "shortcuts.tabs" },
    { keys: ["Esc"], desc: "shortcuts.close" },
  ];
  for (const r of ROWS) {
    const dt = document.createElement("dt");
    for (const k of r.keys) {
      const kbd = document.createElement("kbd");
      kbd.textContent = k;
      dt.appendChild(kbd);
    }
    const dd = document.createElement("dd");
    dd.textContent = t(r.desc);
    list.append(dt, dd);
  }

  return wireModal({ modalId: "shortcuts-modal", toggleId: "shortcuts-toggle", closeId: "shortcuts-close" });
}

// Run whenever ANY wireModal popup opens or closes, so the URL can name the one on
// screen. A module-level hook rather than a per-modal option because every popup goes
// through wireModal (js/changelog.js is handed the same function), so one seam covers
// them all; main() points it at the URL sync via setModalToggle.
let onModalToggle = () => {};
/** Point the popup open/close hook at `fn` (main() syncs the URL). */
export function setModalToggle(fn) {
  onModalToggle = fn;
}

/**
 * Shared wiring for a simple .modal-overlay popup (About / Legend / Sources &
 * provenance / the shortcuts help): a toggle button opens it, the × and a click on
 * the dimmed backdrop close it, and it exposes {open, close, isOpen} so
 * wireShortcuts can route Esc. `onOpen` (optional) runs just before it shows.
 * Returns a no-op controller when the modal element is absent.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
export function wireModal({ modalId, toggleId, closeId, onOpen }) {
  const modal = document.getElementById(modalId);
  const noop = { open() {}, close() {}, get isOpen() { return false; } };
  if (!modal) return noop;
  const close = () => { modal.hidden = true; onModalToggle(); };
  const open = () => { onOpen?.(); modal.hidden = false; onModalToggle(); };
  if (toggleId) document.getElementById(toggleId)?.addEventListener("click", open);
  if (closeId) document.getElementById(closeId)?.addEventListener("click", close);
  modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
  return { open, close, get isOpen() { return !modal.hidden; } };
}

/**
 * About popup (#about-modal): the project blurb + source / issues / licence /
 * attribution links. Opened by the toolbar's info button; the ×, a backdrop click,
 * or Esc close it. Its bottom links close this and open the #sourcing-modal or the
 * #changelog-modal (both passed in). Prose + hrefs live in the markup + wireControls.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean,
 *            openDataFiles:()=>void}}
 */
export function wireAboutModal(sourcing, changelog) {
  const ctrl = wireModal({ modalId: "about-modal", toggleId: "about-toggle", closeId: "about-close" });
  const jump = (id, target) =>
    document.getElementById(id)?.addEventListener("click", (event) => {
      event.preventDefault();
      ctrl.close();
      target?.open();
    });
  jump("about-open-sourcing", sourcing);
  jump("about-open-changelog", changelog);
  return {
    ...ctrl,
    get isOpen() { return ctrl.isOpen; },
    /**
     * Open the popup straight on its (collapsed) data-file dropdown, expanded and
     * scrolled to. The Data browser offers "the same data as files" and this is
     * where that list lives, so it points here instead of shipping a second copy of
     * the file links.
     */
    openDataFiles() {
      ctrl.open();
      const box = document.getElementById("about-data-files");
      if (!box) return;
      box.open = true;
      // After the popup is painted, or scrolling a hidden box is a no-op.
      requestAnimationFrame(() => box.scrollIntoView({ block: "center" }));
    },
  };
}

/**
 * Legend popup (#legend-modal): the static colour/symbol key (built by
 * buildLegendKey into #legend-body). Opened by the toolbar legend button or the k
 * key; the ×, a backdrop click, or Esc close it. Its bottom "Sources & provenance"
 * link closes this and opens the #sourcing-modal (passed in).
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
export function wireLegendModal(sourcing) {
  const ctrl = wireModal({ modalId: "legend-modal", toggleId: "legend-toggle", closeId: "legend-close" });
  document.getElementById("legend-open-sourcing")?.addEventListener("click", (event) => {
    event.preventDefault();
    ctrl.close();
    sourcing?.open();
  });
  return ctrl;
}

/**
 * Sources & provenance popup (#sourcing-modal): the grade key + coverage tally
 * (built by buildAboutSourcing into #about-sourcing). Opened by its own toolbar
 * button, from the Legend + About popups, and auto-shown over the loading overlay
 * on startup (see main()). The ×, a backdrop click, or Esc close it.
 * @returns {{open:()=>void, close:()=>void, isOpen:boolean}}
 */
export function wireSourcingModal() {
  return wireModal({ modalId: "sourcing-modal", toggleId: "sourcing-toggle", closeId: "sourcing-close" });
}

/**
 * Image lightbox (#image-lightbox): pops a clicked structure illustration or
 * molecule diagram up large over a dimmed backdrop. `open(src, alt, {invert})`
 * shows an image (`invert` mirrors the molecule line-art inversion so it reads on
 * the dark backdrop); the ×, a backdrop click, or Esc (routed by wireShortcuts)
 * close it. Reuses the shared .modal-overlay styling.
 * @returns {{open:(src:string, alt?:string, opts?:{invert?:boolean})=>void,
 *   close:()=>void, isOpen:boolean}}
 */
export function wireImageLightbox() {
  const overlay = document.getElementById("image-lightbox");
  const img = document.getElementById("image-lightbox-img");
  const closeBtn = document.getElementById("image-lightbox-close");
  const noop = { open() {}, close() {}, get isOpen() { return false; } };
  if (!overlay || !img) return noop;
  const MAX_UPSCALE = 4; // how far a small source may be blown up (readability > crispness)
  // Size the image to fill most of the viewport: enlarge a small thumbnail (the
  // point of the lightbox) but never past the viewport, and cap the upscale so a
  // tiny raster doesn't turn into a wall of blur. Vector SVGs scale crisply.
  const sizeToViewport = () => {
    const nw = img.naturalWidth, nh = img.naturalHeight;
    if (!nw || !nh) { img.style.width = img.style.height = ""; return; }
    const scale = Math.min(
      (window.innerWidth * 0.92) / nw, (window.innerHeight * 0.92) / nh, MAX_UPSCALE);
    img.style.width = Math.round(nw * scale) + "px";
    img.style.height = Math.round(nh * scale) + "px";
  };
  const close = () => {
    overlay.hidden = true;
    img.removeAttribute("src"); // drop the (possibly multi-MB) decode while closed
    img.style.width = img.style.height = "";
  };
  const open = (src, alt, { invert = false } = {}) => {
    if (!src) return;
    img.onload = sizeToViewport;
    img.src = src;
    img.alt = alt || "";
    img.classList.toggle("inverted", invert);
    overlay.hidden = false;
    if (img.complete && img.naturalWidth) sizeToViewport(); // cached: load won't refire
  };
  closeBtn?.addEventListener("click", close);
  // A click anywhere but the image itself (the dimmed backdrop / the ×) closes it.
  overlay.addEventListener("click", (event) => {
    if (event.target !== img) close();
  });
  return { open, close, get isOpen() { return !overlay.hidden; } };
}
