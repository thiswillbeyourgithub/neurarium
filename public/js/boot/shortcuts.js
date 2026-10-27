// Keyboard shortcuts (the ? help overlay lists them).

/**
 * Global single-key shortcuts (no modifier), ignored while typing in a field.
 * Each maps to an existing control by clicking the same DOM element a mouse user
 * would (or nudging the Separate slider), so there is no duplicated behaviour:
 *   n  toggle all names            l  collapse / expand the Legend section
 *   s  spread fully / collapse     c  toggle "See inside"
 *   r  open Receptors & targets    m  open the Drugs (meds) section
 *   f  open search (bare-key Ctrl/Cmd+F)   Tab  cycle the detail tabs
 *   ?  open the shortcuts popup
 *   Esc  close popup, else close search + collapse any open Legend/Receptors/About
 * (Reset has no key: it is the centered toolbar button, so r is free for the
 * Receptors section, matching m for the Drugs section.)
 * Ctrl/Cmd+F (search) stays handled in wireToolbar; here `f` is its bare-key
 * twin. preventDefault on a handled key stops `f` typing into the search box it
 * just focused (and any other stray default). `help` is the shortcuts-popup
 * controller (wireShortcutsHelp): when its dialog is open Esc closes that first.
 * `selection` lets Esc clear an active focus (isolate / circuit / drug-or-receptor
 * dim) so the brain returns to its plain state, see the Escape case. `lightbox` is
 * the image popup: when it is open Esc closes it before anything else.
 */
export function wireShortcuts(help, tabs, selection, lightbox, aboutModal, legendModal, sourcingModal, changelog) {
  const click = (id) => document.getElementById(id)?.click();
  const isTyping = (el) =>
    !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA"
      || el.tagName === "SELECT" || el.isContentEditable);

  // Separate slider: fully spread if collapsed, else back to assembled. Dispatch
  // "input" (not a direct call) so its other listeners fire too (the intro
  // cancel, the camera re-aim + explode zoom), like the shift+wheel handler.
  const toggleSpread = () => {
    const explode = document.getElementById("explode");
    if (!explode) return;
    explode.value = parseFloat(explode.value) > 0 ? "0" : "1";
    explode.dispatchEvent(new Event("input"));
  };

  // Esc closes the in-panel search and collapses any open accordion section, by
  // clicking the same toggles a user would so the existing wiring runs. (The
  // Legend is a Controls sub-panel, not an accordion peer, so Esc leaves it be.)
  const collapseOpen = () => {
    const search = document.getElementById("search");
    if (search && !search.hidden) click("search-toggle");
    for (const id of ["drugs-toggle", "receptors-toggle", "enzymes-toggle", "effects-toggle",
                      "structures-toggle", "projections-toggle"]) {
      const tg = document.getElementById(id);
      if (tg && tg.getAttribute("aria-expanded") === "true") tg.click();
    }
    sectionNav.reset(); // a closed section keeps no stale keyboard highlight
  };

  // Open search only (never toggle it back off), matching Ctrl/Cmd+F.
  const openSearch = () => {
    const search = document.getElementById("search");
    if (search && search.hidden) click("search-toggle");
  };

  // "k": toggle the Legend popup (its colour/symbol key). It is now a modal, so a
  // press opens it and a second press closes it.
  const toggleLegend = () => {
    if (!legendModal) return;
    if (legendModal.isOpen) legendModal.close();
    else legendModal.open();
  };

  // Roving keyboard navigation inside the currently-open accordion section: once
  // a section is open (e.g. after `l` opens the Legend), ArrowDown / ArrowUp move
  // a highlight (`.kbd-active`) through that section's interactive rows (its
  // action buttons + every `.clickable` row/heading) and Enter activates the
  // highlighted one (a plain click, so it isolates / focuses / opens its detail
  // tab exactly as a mouse click would). Rows are recomputed on each key (the
  // legend rebuilds, the drug filter hides rows), and the highlight is dropped
  // when the open section changes or closes. No-op when no section is open, so
  // the arrow/Enter keys keep their default behaviour elsewhere.
  const sectionNav = (() => {
    const BODIES = [
      ["drugs-toggle", "drugs-body"],
      ["receptors-toggle", "receptors-body"],
      ["enzymes-toggle", "enzymes-body"],
      ["effects-toggle", "effects-body"],
      ["structures-toggle", "structures-body"],
      ["projections-toggle", "projections-body"],
    ];
    let activeEl = null;
    let lastBody = null;
    const openBody = () => {
      for (const [tid, bid] of BODIES) {
        const tg = document.getElementById(tid);
        if (tg && tg.getAttribute("aria-expanded") === "true") {
          return document.getElementById(bid);
        }
      }
      return null;
    };
    const rows = (body) =>
      [...body.querySelectorAll("button, .clickable")]
        .filter((el) => el.offsetParent !== null && !el.disabled);
    const setActive = (el, list) => {
      for (const r of list) r.classList.toggle("kbd-active", r === el);
      activeEl = el || null;
      if (el) el.scrollIntoView({ block: "nearest" });
    };
    return {
      handle(key) {
        const body = openBody();
        if (body !== lastBody) {
          // Section changed or closed: drop the stale highlight on the old body.
          if (lastBody) {
            for (const r of lastBody.querySelectorAll(".kbd-active")) {
              r.classList.remove("kbd-active");
            }
          }
          activeEl = null;
          lastBody = body;
        }
        if (!body) return false;
        const list = rows(body);
        if (list.length === 0) return false;
        if (key === "Enter") {
          if (activeEl && list.includes(activeEl)) { activeEl.click(); return true; }
          return false; // nothing highlighted yet: leave Enter alone
        }
        let idx = list.indexOf(activeEl);
        if (key === "ArrowDown") idx = idx < 0 ? 0 : (idx + 1) % list.length;
        else idx = idx <= 0 ? list.length - 1 : idx - 1; // ArrowUp, wraps
        setActive(list[idx], list);
        return true;
      },
      // Drop any highlight everywhere (called when a section is toggled via the
      // keyboard, so opening/closing/switching a section never leaves a stale
      // outline behind on a now-hidden body).
      reset() {
        for (const [, bid] of BODIES) {
          const body = document.getElementById(bid);
          if (body) {
            for (const r of body.querySelectorAll(".kbd-active")) {
              r.classList.remove("kbd-active");
            }
          }
        }
        activeEl = null;
        lastBody = null;
      },
    };
  })();

  window.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return; // leave combos alone
    if (isTyping(event.target)) return; // let the field keep the key (Esc self-handles)
    // With any popup open, Esc just closes it (and nothing else fires). The image
    // lightbox is checked first so it wins when stacked over another (it can be
    // opened from a panel behind a modal). Only one popup is open at a time.
    if (event.key === "Escape") {
      const search = document.getElementById("search");
      if (search && !search.hidden) {
        click("search-toggle");
        event.preventDefault();
        return;
      }
      for (const modal of [lightbox, help, changelog, aboutModal, legendModal, sourcingModal]) {
        if (modal?.isOpen) {
          modal.close();
          event.preventDefault();
          return;
        }
      }
    }
    // Tab / Shift+Tab cycle the detail tabs (incl. the pinned Settings tab). Only
    // swallow the key when there is something to cycle, so with no detail open
    // Tab keeps its default focus-move behaviour.
    if (event.key === "Tab") {
      if (tabs && tabs.cycle(event.shiftKey ? -1 : 1)) event.preventDefault();
      return;
    }
    // Arrow keys / Enter browse + activate the rows of the open accordion section
    // (Legend / Receptors / Drugs); only swallowed when a section actually handled
    // them, so they keep their default behaviour with no section open.
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter") {
      if (sectionNav.handle(event.key)) event.preventDefault();
      return;
    }
    switch (event.key) {
      case "?": help?.open(); break;
      case "n": case "N": click("toggle-names"); break;
      case "s": case "S": toggleSpread(); break;
      case "l": case "L": sectionNav.reset(); click("structures-toggle"); break;
      case "p": case "P": sectionNav.reset(); click("projections-toggle"); break;
      case "k": case "K": toggleLegend(); break;
      case "c": case "C": click("see-inside"); break;
      case "r": case "R": sectionNav.reset(); click("receptors-toggle"); break;
      case "m": case "M": sectionNav.reset(); click("drugs-toggle"); break;
      case "f": case "F": openSearch(); break;
      // Esc peels one layer at a time, prioritizing a return to the plain brain:
      // (1) close the active detail tab (which clears its dim when it is the last
      // tab), else (2) clear any active focus/isolate/circuit so the brain is
      // un-dimmed with nothing hidden, else (3) close search / collapse an open
      // section. So a focus made from a legend row (a circuit / projection-group /
      // structure isolate that opens no tab) is also cleared by Esc, not just a
      // drug/receptor detail tab.
      case "Escape":
        if (tabs && tabs.closeActive()) break;
        if (selection && selection.getSelected()) { selection.clear(); break; }
        collapseOpen();
        break;
      default: return; // unhandled key: leave its default intact
    }
    event.preventDefault();
  });
}
