// The bottom-left panel's detail-tab strip (one tab per opened node, plus the Data
// browser and Simulation tabs) and the helper that opens a collapsed controls section.

import { panelSectionKey } from "./dom.js";

const { t } = window.__I18N__;

/**
 * Expand the collapsed control panel, the bare DOM half of it. Several places need
 * to reveal something that lives inside the panel body (a detail tab, the search
 * box, the reading mode), so the two lines live here once; `wireControls` wraps
 * this with the pan-aside recompute + URL sync and hands that wrapper around.
 * @returns {boolean} whether it actually expanded (false = already open).
 */
export function openControlsBody(toggle, body) {
  if (toggle.getAttribute("aria-expanded") === "true") return false;
  toggle.setAttribute("aria-expanded", "true");
  body.hidden = false;
  return true;
}

/**
 * Browser-style detail tabs at the top of the bottom-left panel. The first tab,
 * **Settings**, is pinned (always first, never scrolled away) and shows the
 * controls pane; every other tab is one opened detail (a structure / connection /
 * receptor / target / drug), shown in the Details pane. The bar ships hidden and
 * appears once the first detail is opened.
 *
 * This controller only owns the *tab strip + which pane shows*; it does NOT know
 * how to render a detail or apply its 3D focus. `openDetail({key,title,reopen})`
 * registers/activates a tab (called by the select* layer after it has rendered +
 * focused), and clicking a tab calls its `reopen()` (which re-renders #info-body
 * and re-applies the focus, then calls openDetail again to mark it active). So a
 * detail's content + scene state always match the active tab, with no duplicated
 * render logic.
 *
 * Interactions: click a tab to activate it, click its × to close it, long-press a
 * tab then drag to reorder it; the strip scrolls (wheel on desktop, touch-drag on
 * mobile) when the tabs overflow the narrow panel. The strip is touch-action:none
 * so a tab's long-press can't be hijacked by the browser's native pan (which would
 * fire pointercancel mid-hold and kill the reorder on touch); the drag-scroll for a
 * swipe-before-hold is therefore driven here in JS. Closing the active tab falls
 * back to its neighbour (re-applying that one's focus) or, if it was the last
 * detail, to Settings + `onEmpty()` (which clears the 3D selection).
 * @returns {{openDetail:Function, showSettings:()=>void, setOnEmpty:Function,
 *            setOnChange:Function, keys:()=>string[], activate:(key:string)=>void}}
 */
export function createPanelTabs() {
  const bar = document.getElementById("panel-tabs");
  const tabSettings = document.getElementById("tab-settings");
  const strip = document.getElementById("detail-tabs");
  const settingsPane = document.getElementById("settings-pane");
  const detailsPane = document.getElementById("details-pane");
  const controlsToggle = document.getElementById("controls-toggle");
  const controlsBody = document.getElementById("controls-body");

  const MAX_TABS = 12; // bound the strip; the oldest inactive tab drops past this
  const LONG_PRESS_MS = 450; // hold this long (roughly still) to start a reorder
  const MOVE_CANCEL = 8; // px of movement before the long-press fires => a scroll

  let openTabs = []; // [{ key, title, reopen }], left-to-right order
  let activeKey = null; // active detail key, or null when Settings is shown
  let onEmpty = () => {}; // run when the last detail tab is closed (clears the 3D)
  // Run when the user hand-picks the Settings tab while a detail was active (the
  // detail tabs stay in the strip; only the scene focus they applied is dropped).
  let onSettings = () => {};
  // Run after ANY change to the strip (opened / closed / activated / reordered), so
  // the URL can mirror it. render() below is the one choke point every such change
  // funnels through, which is why the hook hangs off it rather than off each caller.
  let onChange = () => {};
  let press = null; // in-flight pointer press (long-press / reorder bookkeeping)
  let suppressClick = false; // a reorder drag must not also activate the tab

  // Where each tab was left scrolled to, so coming back to it resumes reading
  // instead of jumping to the top. Necessary because a tab switch re-runs the whole
  // show*(), and createInfoPanel's clearBody() zeroes the pane on every render.
  const scrollByKey = new Map(); // key -> scrollTop
  // key -> keys of the panel sections open in that tab (panel/dom.js panelSectionKey).
  // Like the scroll offset: a return to the tab (activate) re-opens them, a fresh open
  // of a node (a new drug, or the same one picked again) starts with all folded.
  const sectionsByKey = new Map();
  let pendingSections = null; // single-shot, set by activate(), used by openDetail()
  const openSectionKeys = () => [...detailsPane.querySelectorAll("details.panel-sec")]
    .filter((d) => d.open).map(panelSectionKey);
  // Kept current from the toggles themselves (a click, a tour step, a flashRow jump),
  // read off the live pane so it always matches what the reader sees. Capture phase:
  // toggle does not bubble. A detached panel's late toggle never reaches the pane.
  detailsPane.addEventListener("toggle", (e) => {
    if (activeKey === null || !e.target.classList?.contains("panel-sec")) return;
    sectionsByKey.set(activeKey, openSectionKeys());
  }, true);
  let pendingRestore = null; // single-shot offset, set by activate(), used by openDetail()
  // Record the live offset while a detail is shown: one hook covers every leave path
  // (a tab click, the Settings tab, a close, the Tab-key cycle).
  detailsPane.addEventListener("scroll", () => {
    if (activeKey !== null && pendingRestore === null) {
      scrollByKey.set(activeKey, detailsPane.scrollTop);
    }
  }, { passive: true });

  // Put the pane back where this tab was left. Applied on the next frame (the panel
  // is rebuilt synchronously, so its height is only final after layout), then once
  // more shortly after: a panel keeps growing as its live Wikipedia lead and lazy
  // illustration land, which would otherwise clamp the restore short. The re-apply
  // bows out the moment the offset is no longer ours, so it never fights the user.
  const restoreScroll = (top) => {
    const apply = () => {
      const max = Math.max(0, detailsPane.scrollHeight - detailsPane.clientHeight);
      detailsPane.scrollTop = Math.min(top, max);
      return detailsPane.scrollTop;
    };
    requestAnimationFrame(() => {
      const settled = apply();
      setTimeout(() => {
        if (Math.abs(detailsPane.scrollTop - settled) < 2 && settled < top) apply();
      }, 250);
    });
  };

  // Show the Settings or Details pane and keep the bar's visibility + the pinned
  // Settings tab's active state in sync. The bar hides entirely with no detail
  // tabs open (back to the plain Settings view).
  const showPane = (details) => {
    settingsPane.hidden = details;
    detailsPane.hidden = !details;
    bar.hidden = openTabs.length === 0;
    tabSettings.classList.toggle("active", !details);
    tabSettings.setAttribute("aria-selected", String(!details));
  };

  // The detail must be visible, so make sure the panel body is expanded (the
  // ResizeObserver in wireControls then re-runs the small-screen pan-aside).
  const expandPanel = () => openControlsBody(controlsToggle, controlsBody);

  // Rebuild the detail-tab buttons from openTabs (the array is the source of
  // truth). Cheap: a handful of tabs at most.
  const render = () => {
    strip.textContent = "";
    for (const tab of openTabs) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "detail-tab" + (tab.key === activeKey ? " active" : "");
      btn.dataset.key = tab.key;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", String(tab.key === activeKey));
      const label = document.createElement("span");
      label.className = "detail-tab-label";
      label.textContent = tab.title;
      label.title = tab.title; // full name on hover (the label is ellipsized)
      const close = document.createElement("span");
      close.className = "detail-tab-close";
      close.textContent = "×";
      close.setAttribute("aria-label", t("panel.closeTab"));
      btn.append(label, close);
      strip.appendChild(btn);
    }
    bar.hidden = openTabs.length === 0;
    tabSettings.classList.toggle("active", activeKey === null);
    onChange();
  };

  const scrollActiveIntoView = () => {
    const el = strip.querySelector(".detail-tab.active");
    if (el) el.scrollIntoView({ inline: "nearest", block: "nearest" });
  };

  // Re-show a tab's detail: its reopen() re-renders + re-applies the 3D focus and
  // calls openDetail(key), which marks it active and shows the Details pane. Arm the
  // scroll restore here, not in openDetail: coming BACK to a tab resumes where it was
  // left, while a fresh open (or a jump from a link inside a panel) still starts at
  // the top, and flashRow's deliberate scroll is left alone.
  const activate = (key) => {
    const tab = openTabs.find((tb) => tb.key === key);
    if (!tab) return;
    pendingRestore = scrollByKey.get(key) || 0;
    pendingSections = sectionsByKey.get(key) || [];
    tab.reopen();
  };

  const closeTab = (key) => {
    const idx = openTabs.findIndex((tb) => tb.key === key);
    if (idx === -1) return;
    openTabs.splice(idx, 1);
    scrollByKey.delete(key); // reopening it later is a fresh open, so start at the top
    sectionsByKey.delete(key);
    if (key !== activeKey) { render(); return; } // 3D unchanged; just drop the chip
    if (openTabs.length) {
      // Fall back to the neighbour that slid into this slot (or the new last one),
      // re-applying its focus so the scene matches the now-active tab.
      activate(openTabs[Math.min(idx, openTabs.length - 1)].key);
    } else {
      activeKey = null;
      showPane(false);
      onEmpty(); // nothing left selected: clear the 3D focus
      render();
    }
  };

  // ----- strip interactions (event-delegated on the scroll container) -----
  // Click: the × closes, anywhere else activates (unless a reorder just ran).
  strip.addEventListener("click", (e) => {
    if (suppressClick) { suppressClick = false; return; }
    const btn = e.target.closest(".detail-tab");
    if (!btn) return;
    if (e.target.closest(".detail-tab-close")) closeTab(btn.dataset.key);
    else activate(btn.dataset.key);
  });

  // Long-press a tab to lift it into a reorder drag; a move before the press
  // fires is a scroll instead, so we bow out and let the strip scroll natively.
  strip.addEventListener("pointerdown", (e) => {
    const btn = e.target.closest(".detail-tab");
    if (!btn || e.target.closest(".detail-tab-close")) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    press = { key: btn.dataset.key, btn, x: e.clientX, y: e.clientY,
      pointerId: e.pointerId, dragging: false, moved: false };
    press.timer = setTimeout(() => {
      if (!press) return;
      press.dragging = true;
      press.btn.classList.add("dragging");
      // Take the pointer + stop the browser scrolling so the drag is ours.
      strip.style.touchAction = "none";
      try { press.btn.setPointerCapture(press.pointerId); } catch (_) {}
    }, LONG_PRESS_MS);
  });
  strip.addEventListener("pointermove", (e) => {
    if (!press) return;
    if (!press.dragging) {
      // Moved before the long-press fired: a swipe, so scroll the strip ourselves
      // (it is touch-action:none, so the browser no longer pans it natively, which
      // is exactly what used to fire pointercancel mid-hold and kill the reorder on
      // touch). Capture the pointer so the moves keep coming as tabs slide under it.
      if (!press.scrolling &&
          Math.hypot(e.clientX - press.x, e.clientY - press.y) > MOVE_CANCEL) {
        clearTimeout(press.timer);
        press.scrolling = true;
        press.lastX = e.clientX;
        try { press.btn.setPointerCapture(press.pointerId); } catch (_) {}
      }
      if (press.scrolling) {
        strip.scrollLeft -= e.clientX - press.lastX;
        press.lastX = e.clientX;
        press.moved = true;
        e.preventDefault();
      }
      return;
    }
    e.preventDefault();
    press.moved = true;
    // Insert the dragged chip before the first sibling whose midpoint is right of
    // the pointer (the canonical drag-to-reorder move); the element keeps its
    // identity + capture, so we reorder the DOM live and sync the array on drop.
    const after = [...strip.querySelectorAll(".detail-tab:not(.dragging)")].find(
      (s) => {
        const r = s.getBoundingClientRect();
        return e.clientX < r.left + r.width / 2;
      });
    if (after) strip.insertBefore(press.btn, after);
    else strip.appendChild(press.btn);
  });
  const endPress = () => {
    if (!press) return;
    clearTimeout(press.timer);
    if (press.dragging) {
      press.btn.classList.remove("dragging");
      strip.style.touchAction = "";
      try { press.btn.releasePointerCapture(press.pointerId); } catch (_) {}
      // Reorder openTabs to match the live DOM order, then rebuild cleanly.
      const order = [...strip.querySelectorAll(".detail-tab")].map((b) => b.dataset.key);
      openTabs.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
      if (press.moved) {
        // The browser fires a synthetic click on the dragged tab right after this
        // pointerup; swallow only THAT click, then clear the flag on the next tick
        // so a later, unrelated tab click is never eaten.
        suppressClick = true;
        setTimeout(() => { suppressClick = false; }, 0);
      }
      render();
    } else if (press.scrolling) {
      try { press.btn.releasePointerCapture(press.pointerId); } catch (_) {}
      // A drag-scroll on a tab must not also activate it on the trailing click.
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 0);
    }
    press = null;
  };
  strip.addEventListener("pointerup", endPress);
  strip.addEventListener("pointercancel", endPress);

  // Wheel over the strip scrolls it horizontally (the desktop "scroll through
  // tabs"); touch gets native horizontal scroll via touch-action: pan-x (CSS).
  strip.addEventListener("wheel", (e) => {
    if (!e.deltaY) return;
    strip.scrollLeft += e.deltaY;
    e.preventDefault();
  }, { passive: false });

  // Return to the pinned Settings tab (active = none), keeping every detail tab.
  // `user` marks the two ways a *person* leaves a detail behind (the Settings chip,
  // the Tab-key cycle landing on it): those also drop the 3D focus via onSettings, so
  // a drug's animation does not keep playing behind the controls. The programmatic
  // showSettings() (search, the tour) leaves the scene alone.
  const selectSettings = ({ user = false } = {}) => {
    activeKey = null;
    showPane(false);
    render();
    if (user) onSettings();
  };
  tabSettings.addEventListener("click", () => selectSettings({ user: true }));

  return {
    /**
     * Register (or re-activate) the tab for a detail. Called by the select* layer
     * after it has rendered #info-body + applied the 3D focus. `key` dedupes (one
     * tab per thing), `title` is the chip label, `reopen` re-runs that select* so
     * clicking the tab restores both the panel and the scene.
     */
    openDetail({ key, title, reopen }) {
      let tab = openTabs.find((tb) => tb.key === key);
      if (tab) {
        tab.title = title;
        tab.reopen = reopen;
      } else {
        tab = { key, title, reopen };
        openTabs.push(tab);
        if (openTabs.length > MAX_TABS) {
          const drop = openTabs.findIndex((tb) => tb.key !== key && tb.key !== activeKey);
          if (drop !== -1) {
            const dropped = openTabs.splice(drop, 1)[0].key;
            scrollByKey.delete(dropped);
            sectionsByKey.delete(dropped);
          }
        }
      }
      activeKey = key;
      // Sections: a return re-opens what was open in this tab, a fresh open forgets it
      // (the panel was just rendered all folded). Before the scroll restore, which
      // needs the re-opened heights.
      const reopenSections = pendingSections;
      pendingSections = null;
      if (reopenSections) {
        const want = new Set(reopenSections);
        for (const d of detailsPane.querySelectorAll("details.panel-sec"))
          if (want.has(panelSectionKey(d))) d.open = true;
      } else {
        sectionsByKey.delete(key);
      }
      expandPanel();
      showPane(true);
      render();
      scrollActiveIntoView();
      // Consume the offset activate() armed (single-shot, so only a return to a tab
      // resumes; a first open lands at the top like any freshly rendered panel).
      const resume = pendingRestore;
      pendingRestore = null;
      if (resume !== null) restoreScroll(resume);
    },
    /**
     * Switch to the pinned Settings tab without closing any detail tabs (they stay
     * in the strip as history). Used by search (its box lives in the Settings
     * pane) and by an empty-space click / deselect.
     */
    showSettings() {
      selectSettings();
    },
    /**
     * Close the currently active detail tab (falling back to a neighbour or
     * Settings, like its × button). Returns true when a detail was active and got
     * closed, false when Settings was active (nothing to close) so the caller (Esc)
     * can fall through to other behaviour.
     */
    closeActive() {
      if (activeKey === null) return false;
      closeTab(activeKey);
      return true;
    },
    /**
     * Close one detail tab by key, wherever it sits in the strip. Returns whether
     * it was open. Used by a legend row that toggles its own focus off but has no
     * 3D state for `selection.clear()` to unwind (the Enzymes section).
     */
    close(key) {
      if (!openTabs.some((tb) => tb.key === key)) return false;
      closeTab(key);
      return true;
    },
    /**
     * Cycle the active tab one step (`+1` next, `-1` previous) through the pinned
     * Settings tab plus the open detail tabs, wrapping around. Landing on a detail
     * re-applies its 3D focus (same as clicking it); landing on Settings returns
     * to the controls. Returns false (nothing to cycle) when only Settings exists,
     * so the caller can leave the Tab key's default focus move intact.
     */
    cycle(dir) {
      if (openTabs.length === 0) return false;
      const keys = [null, ...openTabs.map((tb) => tb.key)]; // Settings first, then details
      const at = keys.indexOf(activeKey);
      const target = keys[(at + dir + keys.length) % keys.length];
      if (target === null) selectSettings({ user: true });
      else activate(target);
      return true;
    },
    /** Close every open detail tab, returning to Settings (fires onEmpty once the
     *  last one goes, clearing the 3D focus + the URL hash). No-op when none open. */
    closeAll() {
      if (!openTabs.length) return false;
      // Drop them all, then let the shared close path settle the empty state.
      openTabs.length = 0;
      activeKey = null;
      showPane(false);
      onEmpty();
      render();
      return true;
    },
    /** Set the callback run when the last detail tab is closed (clears the 3D). */
    setOnEmpty(fn) { onEmpty = fn; },
    /** Set the callback run when the user returns to the Settings tab by hand while
     *  a detail was active (drops the 3D focus; the tabs themselves stay open). */
    setOnSettings(fn) { onSettings = fn; },
    /** Set the callback run after ANY strip change (open / close / activate /
     *  reorder), so the URL can mirror the whole strip, not just the active tab. */
    setOnChange(fn) { onChange = fn; },
    /** The active detail tab's key (`<kind>:<id>`), or null when Settings is shown.
     *  Used to build the shareable deep link that mirrors the focus into the URL. */
    activeKey() { return activeKey; },
    /** The open tabs' keys, in strip order (which the user can drag to change), so
     *  the URL can reproduce both the set and its order. */
    keys() { return openTabs.map((tb) => tb.key); },
    /** Re-show one open tab by key (re-applying its 3D focus), as clicking it does.
     *  No-op for a key that is not open. */
    activate(key) { activate(key); },
  };
}
