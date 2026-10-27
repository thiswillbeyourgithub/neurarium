// The launch: the guided tour and its auto-start gates, the one-shot "What's new"
// at launch, the assemble intro, and the loading overlay's dismissal coupled to it.

import { animSettings } from "../anim-settings.js";
import { applyExplode } from "../scene/explode.js";
import { createIntroAnimation } from "../scene/intro.js";
import { createViewerTour } from "./tour-steps.js";
import { AUTOMATED_VIEW, HAS_EXPLODE, TOUR_FORCED } from "./query.js";

/**
 * @param {object} deps the scene (arrows, camera, controls, meshes, meshById, focus,
 *   selection, autoSpread, arrowRetrim), the focus functions the tour drives, the
 *   popups (aboutModal, changelog, legendModal, sourcingModal), tabs, toolbar, the
 *   loading screen, and the Data browser (NODES_TAB_KEY, showNodeBrowser, setNo3d,
 *   the last possibly late-bound)
 * @returns {{intro: object}} the assemble intro (a focused deep link cancels it)
 */
export function launchScene({
  aboutModal, arrowRetrim, arrows, autoSpread, camera, changelog, controls, data, focus,
  focusDrug, focusProjectionGroup, focusTarget, legendModal, loading, meshById, meshes,
  NODES_TAB_KEY, selection, selectStructure, setNo3d, showNodeBrowser, sourcingModal, tabs,
  toolbar,
}) {
  const {
    tour, tourEl,
  } = createViewerTour({
    arrows, autoSpread, controls, data, focus, focusDrug,
    focusProjectionGroup, focusTarget, legendModal, meshById, meshes, NODES_TAB_KEY,
    selection, selectStructure, setNo3d, showNodeBrowser, sourcingModal, tabs, toolbar,
  });
  // Auto-start only on a genuinely fresh view: not a screenshot / deep-link mode,
  // and nothing already focused (a hash deep link, or a click during the intro).
  const tourEligible = () =>
    !AUTOMATED_VIEW && !tabs.activeKey() && !selection.getSelected();
  // Replay from the About popup (close it first so the tour isn't behind it).
  tourEl("about-tour")?.addEventListener("click", () => {
    aboutModal.close();
    tour.start();
  });
  // Auto-start waits for the assemble intro to settle, and declines to stack on an
  // open popup (Sources, or the "What's new" notes that now open at launch): the
  // Sources one no longer opens on launch, but a visitor could open it manually
  // during the intro, so if either is up we defer and the observer retries the moment
  // it closes. (Mid-tour the observer is a no-op: maybeAutoStart/start bail when the
  // tour is already active, so the sourcing open / close steps can't restart it.)
  // Two gates, not one. `sceneSettled` means the launch is over however it ended;
  // `introCompleted` means the assemble reached its natural end, which the tour
  // requires so it never starts over a user's own action.
  let sceneSettled = false;
  let introCompleted = false;
  let tourForcedStarted = false; // one-shot guard for the ?tour=1 forced start
  const tourGateEls = ["sourcing-modal", "changelog-modal"].map(tourEl).filter(Boolean);
  const tourGateOpen = () => tourGateEls.some((el) => !el.hidden);
  const tryAutoTour = () => {
    if (!sceneSettled || tourGateOpen()) return;
    if (TOUR_FORCED) {
      // Forced: ignore the seen gate + eligibility, but never re-trigger.
      if (!tourForcedStarted) { tourForcedStarted = true; tour.start(); }
    } else if (introCompleted) {
      tour.maybeAutoStart(tourEligible());
    }
  };
  /** The launch is over; `completed` says the assemble reached its natural end. */
  const settleScene = (completed) => {
    sceneSettled = true;
    if (completed) introCompleted = true;
    tryAutoTour();
  };
  for (const el of tourGateEls) {
    new MutationObserver(tryAutoTour)
      .observe(el, { attributes: true, attributeFilter: ["hidden"] });
  }
  /**
   * "What's new" at LAUNCH, not at settle: release notes are about the build, not
   * about the scene, so a returning visitor reads them the moment they click through
   * the overlay rather than several seconds later once the assemble has finished.
   * (It used to ride the tour's settle gate, which is what made it wait, and which
   * also lost it entirely on a load where the intro was cancelled.) Fire-and-forget
   * and one-shot: it decides for itself whether there is anything to show, and the
   * tour gates on its popup above so the two never stack.
   */
  let changelogTried = false;
  const showChangelogOnce = () => {
    if (changelogTried) return;
    changelogTried = true;
    changelog.showIfUnseen();
  };

  // Auto-play the "assemble" intro on a plain load. Grabbing the explode slider
  // cancels it so a manual drag wins. Skipped when ?explode= is pinned (deep
  // links / headless screenshots) so the requested static amount is honored.
  const explodeSlider = document.getElementById("explode");
  const intro = createIntroAnimation(
    { meshes, arrows, slider: explodeSlider, camera, controls, focus,
      // The assemble re-fits the arrows in `fast` mode, so it borrows the same
      // deferred precise re-trim the manual spread uses.
      retrim: arrowRetrim,
      // Once the assemble settles, offer the tour (once per visitor, and not while
      // the Sources popup is open: see tryAutoTour). Fires on a cancel too, with
      // completed=false, which settles the scene without earning the tour.
      onSettle: settleScene });
  explodeSlider.addEventListener("input", () => intro.cancel());
  // The launch (assemble intro, or an instant settle when animations are off) is
  // wrapped so it can fire exactly when the loading overlay is dismissed below.
  const beginScene = () => {
    if (!HAS_EXPLODE) {
      // Seat the resting pose on the exact framing the reset button produces, so a
      // fresh load already appears centered (not a hardcoded distance that only
      // roughly matched). Done first, so the DEV-banner nudge + intro capture build
      // on the centered pose.
      focus.frameAllNow();
      // The assemble intro is a decorative animation, so honor the Animations toggle:
      // when off, present the brain already whole (explode 0) instead of playing it in.
      if (animSettings.enabled) {
        intro.start();
      } else {
        applyExplode(meshes, 0, arrows);
        // No assemble intro to finish (so onSettle never fires); settle after a short
        // beat. It counts as completed: there was no animation for the user to cut
        // short, so the tour is as welcome here as after a full assemble.
        setTimeout(() => settleScene(true), 500);
      }
    } else if (TOUR_FORCED) {
      // ?explode= pinned: the intro block above is skipped, so onSettle never fires.
      // A forced tour still wants to run, so settle the gate condition after a beat.
      setTimeout(() => settleScene(false), 500);
    }
  };
  // Dismiss the loading overlay, coupled to the launch. An automated view (headless
  // ui=0, or an ?explode= deep-link / screenshot) drops it at once so a capture is
  // never trapped behind the overlay; a normal interactive load keeps it up showing
  // the "Start exploring" button (so the tagline + invite can be read) and launches
  // on the click, the assemble intro playing as the overlay fades.
  if (AUTOMATED_VIEW) {
    // An automated view (headless capture, deep-link screenshot) is not a visit, so it
    // launches with no release notes over the shot.
    loading.done();
    beginScene();
  } else {
    loading.waitForStart().then(() => {
      beginScene();
      showChangelogOnce();
    });
  }

  return { intro };
}
