// The Settings pane wiring: explode / see-inside / quality sliders, the accordion
// sections, and the scene + camera URL keys they own.

import * as THREE from "three";
import { LIST_SEP } from "../url-state.js";
import { animSettings } from "../anim-settings.js";
import { applyExplode, createArrowRetrim, createAutoSpread } from "../scene/explode.js";
import { openControlsBody } from "../panel/tabs.js";
import { isWebUrl } from "../web-url.js";

// url-state priorities (a higher number is applied later, see js/url-state.js). The
// default 0 carries the focus views; scene state that a focus would otherwise override
// comes next, and the camera last, so an explicit `cam=` in a link wins over the
// framing the focused node imposes.
const SCENE_URL_PRIORITY = 5;
const CAMERA_URL_PRIORITY = 10;

// A slider drag fires per frame: write its value to the URL once it has been still
// this long, so one drag costs one history write.
const SLIDER_SETTLE_MS = 300;

/** Wire the DOM controls to the scene behaviors. */
export function wireControls({ camera, controls, meshes, arrows, labels, focus, selection, projVis, seeThrough, urlState }) {
  const autorotate = document.getElementById("autorotate");
  const seeInside = document.getElementById("see-inside");
  const toggleAnimations = document.getElementById("toggle-animations");
  const explode = document.getElementById("explode");
  const transparency = document.getElementById("transparency");
  const toggleNames = document.getElementById("toggle-names");
  const toggleProjections = document.getElementById("toggle-projections");
  const controlsToggle = document.getElementById("controls-toggle");
  const controlsBody = document.getElementById("controls-body");
  const controlsSettingsToggle = document.getElementById("controls-settings-toggle");
  const controlsSettingsBody = document.getElementById("controls-settings-body");
  const structuresToggle = document.getElementById("structures-toggle");
  const structuresBody = document.getElementById("structures-body");
  const projectionsToggle = document.getElementById("projections-toggle");
  const projectionsBody = document.getElementById("projections-body");
  const receptorsToggle = document.getElementById("receptors-toggle");
  const receptorsBody = document.getElementById("receptors-body");
  const drugsToggle = document.getElementById("drugs-toggle");
  const drugsBody = document.getElementById("drugs-body");
  const enzymesToggle = document.getElementById("enzymes-toggle");
  const enzymesBody = document.getElementById("enzymes-body");
  const effectsToggle = document.getElementById("effects-toggle");
  const effectsBody = document.getElementById("effects-body");

  // One collapse-header behaviour shared by the panel, the Controls section and
  // the accordion sections: toggle aria-expanded + the body's hidden flag. The
  // panel + Controls ship expanded, the accordion sections collapsed (their markup
  // sets the initial aria-expanded / hidden).
  // `onToggle(open)` runs after a click so callers can react (accordion below).
  const setSection = (toggle, body, open) => {
    toggle.setAttribute("aria-expanded", String(open));
    body.hidden = !open;
  };
  const wireCollapse = (toggle, body, onToggle) => {
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      setSection(toggle, body, open);
      onToggle?.(open);
    });
  };
  // The panel covers the centered brain, so while it is expanded we push the
  // rendered brain clear of it (a render-time camera view offset, see
  // createCameraFocus.setScreenOffset; collapsing it restores the centered view,
  // eased in focus.tick):
  //   - portrait: the panel spans the full width but only the bottom half (see
  //     the @media rule in css/controls.css), so push the brain straight UP into the
  //     clear top section. The shove is half the panel's height fraction, so the
  //     brain ends up centered in the space above the panel whatever its height.
  //   - landscape: the panel is a full-height left sidebar (up to 25% wide), so
  //     push the brain RIGHT by half the panel's width fraction, so it centres in
  //     the clear space beside the sidebar whatever the sidebar's width.
  const controlsPanel = document.getElementById("controls");
  const portrait = window.matchMedia("(orientation: portrait)");
  const updatePanelPan = () => {
    const open = controlsToggle.getAttribute("aria-expanded") === "true";
    // `offsetHeight` is 0 only when the panel is display:none (the ?ui=0 shots);
    // it stays correct for a position:fixed element, unlike `offsetParent`
    // (which is always null for fixed, so it can't be used as a visibility test).
    const visible = controlsPanel.offsetHeight > 0;
    if (!open || !visible) {
      focus.setScreenOffset(0, 0);
    } else if (portrait.matches) {
      // From the panel's top edge, so its bottom margin counts as covered too.
      const frac =
        1 - controlsPanel.getBoundingClientRect().top / window.innerHeight;
      focus.setScreenOffset(0, Math.min(0.4, frac / 2));
    } else {
      // To the panel's right edge, so its left margin counts as covered too.
      const frac =
        controlsPanel.getBoundingClientRect().right / window.innerWidth;
      focus.setScreenOffset(Math.min(0.3, frac / 2), 0);
    }
  };
  wireCollapse(controlsToggle, controlsBody, updatePanelPan);
  // Expanding the panel from elsewhere (opening search, entering the reading mode)
  // goes through here rather than poking the DOM directly, so the pan-aside and the
  // shareable link end up exactly where a header click would have left them.
  const expandPanel = () => {
    if (!openControlsBody(controlsToggle, controlsBody)) return;
    updatePanelPan();
    urlState.sync();
  };
  // Recompute when the orientation flips, and whenever the panel's own size
  // changes (collapsing/expanding, or opening the Legend/About accordion, which
  // changes how far the brain must move). The ResizeObserver also fires once on
  // observe, so the initial expanded panel is handled on load.
  portrait.addEventListener("change", updatePanelPan);
  new ResizeObserver(updatePanelPan).observe(controlsPanel);

  // Controls (the sliders + global scene toggles) is a collapsible section like
  // the others but deliberately NOT part of the accordion below: it toggles
  // independently, so opening it leaves an open content section open (and vice
  // versa) and you can tweak a slider without losing your place. The
  // ResizeObserver above re-runs the pan-aside when its height changes.
  if (controlsSettingsToggle && controlsSettingsBody) {
    wireCollapse(controlsSettingsToggle, controlsSettingsBody);
  }

  // Structures, Projections, Receptors and Drugs behave as an accordion among
  // themselves: only one open at a time (Controls, above, is exempt; the Legend,
  // Sources & provenance and About are now popups, not sections). The panel top
  // (language switch + reset/search row) stays visible throughout; the open section grows to
  // fill the tall sidebar via the :has(...) CSS in css/controls.css, so no JS layout
  // class is needed here anymore.
  // Order mirrors the on-screen section order (Drugs / Receptors / Structures /
  // Projections, set by the markup in index.html). This array only drives the
  // single-open accordion + keyboard nav, so it is order-agnostic, but keeping it
  // aligned avoids surprises when reading the two together. The Data browser row
  // sits with them in the markup but is NOT here: it opens a detail tab instead of
  // expanding in place (wired in main()).
  const sections = [
    { toggle: drugsToggle, body: drugsBody },
    { toggle: receptorsToggle, body: receptorsBody },
    { toggle: enzymesToggle, body: enzymesBody },
    { toggle: effectsToggle, body: effectsBody },
    { toggle: structuresToggle, body: structuresBody },
    { toggle: projectionsToggle, body: projectionsBody },
  ];
  for (const s of sections) {
    if (!s.toggle || !s.body) continue;
    wireCollapse(s.toggle, s.body, (open) => {
      // Opening one section closes the others (single-open accordion).
      if (open) {
        for (const other of sections) {
          if (other !== s && other.toggle && other.body) {
            setSection(other.toggle, other.body, false);
          }
        }
      }
    });
  }

  // About: point the "Source code" link at the configured sourceUrl (from
  // app-config.js, default the public site). Drop the row if it isn't a valid
  // http(s) url, so a broken/empty config never shows a dead link.
  const aboutSource = document.getElementById("about-source");
  const sourceUrl = String((window.__APP_CONFIG__ || {}).sourceUrl || "").trim();
  const sourceIsUrl = isWebUrl(sourceUrl);
  if (aboutSource) {
    if (sourceIsUrl) aboutSource.href = sourceUrl;
    else document.getElementById("about-source-row")?.remove();
  }

  // The same source-repo link inside the About "data files" dropdown: point it at
  // sourceUrl too, dropping its row when the config isn't a valid http(s) url (no
  // repo/username hardcoded; the data-file links beside it are same-origin so they
  // always work regardless of this).
  const aboutSource2 = document.getElementById("about-source2");
  if (aboutSource2) {
    if (sourceIsUrl) aboutSource2.href = sourceUrl;
    else document.getElementById("about-source2-row")?.remove();
  }

  // "open an issue" link (embedded in the about.issues paragraph by i18n): point
  // it at the source repo's issues page (sourceUrl + "/issues"), deriving it from
  // the same env-configured sourceUrl so no repo/username is hardcoded. Only do
  // this when sourceUrl points *into* a repository (has a path beyond the host):
  // the committed default is the bare public-site domain, where "/issues" would
  // 404, so there we drop the whole row instead of shipping a dead link. The repo
  // URL is set via the SOURCE_URL env var in the container (see app-config.js).
  const aboutIssues = document.getElementById("about-issues");
  if (aboutIssues) {
    let issuesUrl = "";
    if (sourceIsUrl) {
      try {
        const u = new URL(sourceUrl);
        if (u.pathname.replace(/\/+$/, "") !== "") { // a repo path, not a bare domain
          issuesUrl = `${sourceUrl.replace(/\/+$/, "")}/issues`;
        }
      } catch { /* malformed url: leave the row removed below */ }
    }
    if (issuesUrl) aboutIssues.href = issuesUrl;
    else document.getElementById("about-issues-row")?.remove();
  }

  controls.autoRotate = autorotate.checked;
  controls.autoRotateSpeed = 1.5;
  autorotate.addEventListener("change", () => {
    controls.autoRotate = autorotate.checked;
  });

  // "See inside": hide the near hemisphere so the deep structures show through.
  seeThrough.setEnabled(seeInside.checked);
  seeInside.addEventListener("change", () => seeThrough.setEnabled(seeInside.checked));

  // "Animations": the checkbox reflects the persisted animSettings state (default
  // on for desktop, off for a phone / reduced-motion). Flipping it flows through
  // animSettings, whose subscribers (in main()) stop/allow the decorative motion.
  toggleAnimations.checked = animSettings.enabled;
  toggleAnimations.addEventListener("change", () =>
    animSettings.setEnabled(toggleAnimations.checked));

  // Apply an explode `amount`: spread the regions, keep a focused structure
  // centered (re-aim), and pull the camera to hold the apparent size. Shared by the
  // slider handler and the auto-spread tween so both behave identically.
  // Re-trim arrows precisely once the spread settles (the per-frame updates below
  // are cheap/approximate; see createArrowRetrim). Advanced by its tick() in the
  // render loop.
  const arrowRetrim = createArrowRetrim(arrows);
  const applyExplodeAmount = (amount) => {
    applyExplode(meshes, amount, arrows, true); // fast: reuse cached surface trims
    // Keep a double-clicked / searched structure centered as it blows outward,
    // by re-aiming (rotating) the camera rather than translating it.
    focus.reaimFocused();
    // Pull the camera back as the regions spread (and zoom back in as they
    // reassemble) so the exploded layout stays framed.
    focus.zoomForExplode(amount);
    arrowRetrim.markDirty(); // schedule the precise re-trim for when the spread stops
  };
  const onExplode = () => applyExplodeAmount(parseFloat(explode.value));
  explode.addEventListener("input", onExplode);

  // Auto-spread: focusing a deep (non-lobe) structure from search / a detail panel
  // blows the brain fully apart so the structure isn't buried under the cortex.
  // A manual slider grab cancels it (so the user always wins).
  const autoSpread = createAutoSpread({ slider: explode, apply: applyExplodeAmount });
  explode.addEventListener("input", () => autoSpread.cancel());
  // True when a focused set contains anything that isn't an outer lobe, i.e. a
  // structure that would otherwise sit hidden inside the assembled brain.
  const hasDeep = (meshList) =>
    meshList.some((m) => m && m.userData.structure && m.userData.structure.group !== "lobe");
  const autoSpreadIfDeep = (meshList) => {
    if (hasDeep(meshList)) autoSpread.spreadTo(1);
  };

  // Shift + wheel drives the Separate slider instead of zooming the camera. The
  // capture-phase window listener runs *before* OrbitControls' own wheel handler
  // on the canvas, so swallowing the event here (preventDefault + stopPropagation)
  // stops OrbitControls from also zooming. We dispatch the slider's "input" event
  // rather than calling onExplode directly, so its other listeners fire too
  // (notably the intro-animation cancel). A plain wheel (no shift) is ignored here
  // and falls through to OrbitControls zoom as usual.
  window.addEventListener(
    "wheel",
    (e) => {
      if (!e.shiftKey) return;
      e.preventDefault();
      e.stopPropagation();
      const current = parseFloat(explode.value);
      const step = (e.deltaY < 0 ? 1 : -1) * 0.06; // scroll up = more separation
      const next = Math.min(1, Math.max(0, current + step));
      if (next === current) return; // already at an end stop
      explode.value = String(next);
      explode.dispatchEvent(new Event("input"));
    },
    { capture: true, passive: false }
  );

  // Opacity is owned by the selection controller so the slider value and the
  // isolate-mode dimming compose into one final opacity per structure/arrow.
  const onTransparency = () =>
    selection.setBaseOpacity(parseFloat(transparency.value));
  transparency.addEventListener("input", onTransparency);

  // Button that forces structure labels on/off at once (vs. hover, which shows
  // just one). When something is selected (an isolated region, a circuit, a
  // halo'd structure/arrow), it names only the selection rather than every
  // structure, so the focus isn't drowned in labels; with nothing selected it
  // names everything. aria-pressed + an .active class reflect the state.
  // "Show all names" checkbox (next to Auto-rotate): force every structure label
  // on at once (vs. hover, one at a time). When something is selected it names only
  // the selection rather than every structure, so the focus isn't drowned in
  // labels; with nothing selected it names everything. The checkbox's own `checked`
  // is the state (no separate flag).
  const showAllScoped = () => {
    const on = toggleNames.checked;
    const sel = on ? selection.getSelected() : null;
    labels.setShowAll(on, sel?.meshes ?? null, sel?.arrows ?? null);
  };
  toggleNames.addEventListener("change", showAllScoped);
  // Keep the named set tracking the selection while show-all is on, so adding /
  // removing an isolated region (or clearing it) updates which names show.
  selection.onIsolate(showAllScoped);

  // "Show projections" checkbox (next to Auto-rotate): show/hide every projection
  // arrow at once. UNCHECKED by default: all ~100 at once bury the anatomy, and the
  // arrows a focus lights are exempt from the hiding (see createProjectionVisibility),
  // so a circuit / drug / structure focus still draws its own pathways.
  // projVis refreshes the connection labels (which key off group.visible) and the
  // pick helpers skip hidden groups. Composes with the legend's "Hypothetical
  // pathways" toggle through projVis: hiding wins, and re-showing restores the
  // tentative arrows only if that section is toggled on.
  projVis.setAllHidden(!toggleProjections.checked);
  selection.onIsolate((_isolated, _pinned, focusArrows) =>
    projVis.setFocusArrows(focusArrows));
  toggleProjections.addEventListener("change", () => {
    projVis.setAllHidden(!toggleProjections.checked);
  });

  // Apply initial slider values so the scene matches the UI on load.
  onExplode();
  onTransparency();

  // ---- URL views owned by this panel ---------------------------------------------
  // Each control hands the js/url-state.js registry a {read, write} pair, so the
  // fragment describes it and a link reproduces it. `read` returns null while the
  // control sits at its shipped default, keeping a plain link short; `write` drives
  // the control through its own event, so every side effect runs exactly as a click
  // or a drag would (no second implementation of what the control does).
  // Each also carries `reset` (back to `dflt`), which the toolbar's reset button runs
  // through urlState.resetAll.
  const checkboxView = (input, dflt) => {
    const write = (v) => {
      const on = v !== "0";
      if (input.checked === on) return;
      input.checked = on;
      input.dispatchEvent(new Event("change"));
    };
    return {
      read: () => (input.checked === dflt ? null : input.checked ? "1" : "0"),
      write,
      reset: () => write(dflt ? "1" : "0"),
    };
  };
  const sliderView = (input, dflt) => {
    const write = (v) => {
      if (!Number.isFinite(parseFloat(v))) return;
      input.value = v;
      input.dispatchEvent(new Event("input"));
    };
    return {
      read: () => {
        const value = parseFloat(input.value);
        return value === dflt ? null : String(value);
      },
      write,
      reset: () => write(String(dflt)),
    };
  };
  // Register a view AND let the control's own events refresh the URL, so the address
  // bar tracks it live. A slider fires `input` per frame while dragged, so its sync is
  // debounced and lands once on the settled value (see url-state.js sync).
  const registerControl = (key, input, view, event = "change", delay = 0, priority = 0) => {
    urlState.register(key, view, priority);
    input.addEventListener(event, () => urlState.sync(delay));
  };
  // Explode applies AFTER the focus views: focusing a deep structure auto-spreads the
  // brain, and a link that states an explode amount must win over that (setting the
  // slider cancels the auto-spread, see its `input` listener above).
  registerControl("explode", explode, sliderView(explode, 0), "input", SLIDER_SETTLE_MS,
    SCENE_URL_PRIORITY);
  registerControl("transparency", transparency, sliderView(transparency, 1), "input", SLIDER_SETTLE_MS);
  // Apply-only keys: still applied from a link (and reset by the toolbar), never written,
  // because the address bar would only carry noise. A still view always writes `cam=`,
  // whose apply stops the spin by itself, so `rotate=0` would be redundant beside it.
  const writeOnlyView = (view) => ({ ...view, read: () => null });
  registerControl("rotate", autorotate, writeOnlyView(checkboxView(autorotate, true)));
  registerControl("names", toggleNames, checkboxView(toggleNames, false));
  registerControl("arrows", toggleProjections, checkboxView(toggleProjections, false));
  registerControl("inside", seeInside, checkboxView(seeInside, false));
  // Animations are a persisted personal preference (js/prefs.js), not part of what is
  // on screen, so a shared link does not impose the sender's choice: apply-only too.
  registerControl("anim", toggleAnimations,
    writeOnlyView(checkboxView(toggleAnimations, animSettings.defaultEnabled)));

  // Panel layout: whether the panel body is collapsed, whether the Controls sub-section
  // is open, and which browse section the accordion has open. Written through the same
  // setSection the headers use, then the pan-aside recomputed as their click does.
  urlState.register("collapsed", {
    read: () => (controlsToggle.getAttribute("aria-expanded") === "true" ? null : "1"),
    write: (v) => {
      setSection(controlsToggle, controlsBody, v === "0");
      updatePanelPan();
    },
  });
  if (controlsSettingsToggle && controlsSettingsBody) {
    urlState.register("settings", {
      read: () => (controlsSettingsToggle.getAttribute("aria-expanded") === "true" ? null : "0"),
      write: (v) => setSection(controlsSettingsToggle, controlsSettingsBody, v !== "0"),
    });
  }
  const sectionId = (s) => s.toggle.id.replace(/-toggle$/, "");
  urlState.register("section", {
    read: () => {
      const open = sections.find(
        (s) => s.toggle && s.toggle.getAttribute("aria-expanded") === "true");
      return open ? sectionId(open) : null;
    },
    // An empty value closes them all, which is the accordion's own resting state.
    write: (v) => {
      for (const s of sections) {
        if (s.toggle && s.body) setSection(s.toggle, s.body, sectionId(s) === v);
      }
    },
  });
  for (const s of [{ toggle: controlsToggle }, { toggle: controlsSettingsToggle }, ...sections]) {
    s.toggle?.addEventListener("click", () => urlState.sync());
  }

  // `cam=<azimuth>,<polar>,<distance>[,<tx>,<ty>,<tz>]`: the orbit as degrees around
  // the pivot plus the camera's distance from it, and the pivot itself when a focus has
  // moved it off the brain centre. Rounded: "approximately this view" is what a shared
  // link means, and full precision would only churn the address bar.
  //
  // Written only while auto-rotate is OFF. A spinning view has no fixed orientation to
  // capture, and rewriting one every frame would churn history for nothing; so applying
  // a `cam` also stops the spin (and any running framing tween), or the link's view
  // would immediately drift off it.
  const camRound = (n, digits) => Number(n.toFixed(digits));
  const camOffset = new THREE.Vector3();
  urlState.register("cam", {
    read: () => {
      if (autorotate.checked) return null;
      const parts = [
        camRound(THREE.MathUtils.radToDeg(controls.getAzimuthalAngle()), 1),
        camRound(THREE.MathUtils.radToDeg(controls.getPolarAngle()), 1),
        camRound(controls.getDistance(), 2),
      ];
      if (controls.target.lengthSq() > 1e-4) {
        parts.push(camRound(controls.target.x, 2), camRound(controls.target.y, 2),
          camRound(controls.target.z, 2));
      }
      return parts.join(LIST_SEP);
    },
    write: (v) => {
      const n = v.split(LIST_SEP).map(Number);
      if (n.length < 3 || n.some((x) => !Number.isFinite(x))) return;
      if (autorotate.checked) {
        autorotate.checked = false;
        autorotate.dispatchEvent(new Event("change"));
      }
      focus.cancel(); // a framing tween would otherwise drag the view off the link's
      autoSpread.cancel(); // as would a still-running auto-spread's zoom
      controls.target.set(n[3] || 0, n[4] || 0, n[5] || 0);
      camOffset.setFromSphericalCoords(
        n[2], THREE.MathUtils.degToRad(n[1]), THREE.MathUtils.degToRad(n[0]));
      camera.position.copy(controls.target).add(camOffset);
      controls.update();
    },
  }, CAMERA_URL_PRIORITY);
  // The camera moves continuously while orbiting, so record the settled value: "end"
  // fires when a drag / wheel / pinch finishes.
  controls.addEventListener("end", () => urlState.sync());

  // Hand the auto-spread back to the caller: the focus helpers (selectStructure,
  // focusDrug, ...) live in the main scope and call autoSpreadIfDeep, and the
  // render loop advances autoSpread.tick() + arrowRetrim.tick().
  return { autoSpread, autoSpreadIfDeep, arrowRetrim, expandPanel };
}
