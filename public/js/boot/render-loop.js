// On-demand render loop: render a frame only when something animated, the camera
// moved, or invalidate() fired; idle, the canvas holds its last frame.

import { animSettings } from "../anim-settings.js";
import { setRepaint } from "../scene/setup.js";
import { createAdaptiveQuality } from "../scene/quality.js";

/**
 * Set up the repaint triggers now (so controls wired next can call `invalidate`);
 * `start` installs the frame callback once every per-frame controller exists.
 * @param {{renderer: object, baseDpr: number, controls: object, circuitAnim: object}} deps
 * @returns {{invalidate: () => void, start: (frame: object) => void}}
 */
export function createRenderLoop({ renderer, baseDpr, controls, circuitAnim }) {
  // On-demand rendering: a mostly-static brain has no reason to repaint at 60fps,
  // which only burns battery / spins fans / throttles phones. We render a frame
  // only when something actually changed: an animation is running (each tick()
  // below reports whether it is active), the controls moved (OrbitControls.update
  // returns true while damping settles or auto-rotate spins), or `invalidate()`
  // was called. `invalidate` is wired to every user input below as a catch-all so
  // no interaction is ever missed, and the controls' own `change` event covers
  // every camera move (drag / wheel / pinch / programmatic). When truly idle (no
  // input, no animation) the loop calls only the cheap tick/update checks and
  // skips the render + CSS2D passes entirely, holding the last drawn frame.
  let needsRender = true;
  const invalidate = () => { needsRender = true; };
  // Hand the render loop to everything wired before it existed (the theme's scene
  // repaint); see the `repaint` hook in scene/setup.js.
  setRepaint(invalidate);
  controls.addEventListener("change", invalidate);
  window.addEventListener("resize", invalidate);

  // Adaptive rendering (Task): lower the pixel ratio + animation detail when frames
  // drop, raise it back when they recover. Fed once per frame below with whether an
  // animated render actually happened.
  const adaptive = createAdaptiveQuality({ renderer, baseDpr });

  // Toggling the Animations checkbox flips animSettings; react to it here (where the
  // decorative controllers live): repaint once so a static frame draws, and when
  // turning OFF, halt the circuit traveling pulse (its beads persist otherwise; the
  // gem/wash controllers freeze themselves in their own tick()s). Turning back ON
  // resumes motion on the next focus.
  animSettings.subscribe(() => {
    if (!animSettings.enabled) circuitAnim.stop();
    invalidate();
  });
  // Belt-and-suspenders: any user input repaints, so adding a new control never
  // needs to remember to call invalidate. Capture phase + passive so this only
  // observes (it never preventDefaults, leaving the real handlers untouched).
  for (const ev of ["pointerdown", "pointermove", "pointerup", "wheel",
                    "keydown", "input", "change", "click"]) {
    window.addEventListener(ev, invalidate, { capture: true, passive: true });
  }

  /**
   * Install the frame callback. Each controller's tick() returns whether it animated.
   * @param {{scene: object, camera: object, labels: object, urlState: object,
   *          intro: object, autoSpread: object, arrowRetrim: object, focus: object,
   *          receptorMarkers: object, drugAnim: object, arrowWidth: object,
   *          seeThrough: object, no3dOn: () => boolean, updateSpeedRow: () => void}} frame
   */
  const start = ({
    scene, camera, labels, urlState, intro, autoSpread, arrowRetrim, focus,
    receptorMarkers, drugAnim, arrowWidth, seeThrough, no3dOn, updateSpeedRow,
  }) => {
    // A framing tween (focusing a node, recentering, the explode re-aim) moves the
    // camera over several frames, so the URL's `cam` is only right once it settles:
    // record it on the tween's falling edge rather than per frame.
    let camWasMoving = false;

    renderer.setAnimationLoop(() => {
      // Panel-only mode: the scene (canvas + label overlay) is display:none, so skip
      // the ticks and the render entirely. Animations freeze in place and resume when
      // 3D returns, repainted by setNo3d's invalidate().
      if (no3dOn()) return;
      // Advance the intro + any focus/recenter tween before controls.update()
      // reads the target + camera position for this frame. Each tick() returns
      // whether it animated this frame; controls.update() returns whether the
      // camera moved (damping / auto-rotate). Any true keeps us rendering.
      let active = false;
      if (intro.tick()) active = true;
      if (autoSpread.tick()) active = true;
      if (arrowRetrim.tick()) active = true;
      const camMoving = focus.tick();
      if (camMoving) active = true;
      else if (camWasMoving) urlState.sync(); // tween done: the settled view is the link's
      camWasMoving = camMoving;
      if (circuitAnim.tick()) active = true;
      if (receptorMarkers.tick()) active = true;
      if (drugAnim.tick()) active = true;
      if (controls.update()) active = true;
      // After controls.update() so it reads this frame's settled camera distance.
      if (arrowWidth.tick()) active = true;
      // After controls.update() so the fade reads this frame's camera + target.
      if (seeThrough.tick()) active = true;
      if (active) needsRender = true;
      const rendered = needsRender;
      // Adaptive quality watches the frame time of actually-rendered animated frames
      // and may step the pixel ratio down/up; a level change forces one more repaint.
      if (adaptive.tick(rendered && active)) needsRender = true;
      if (!needsRender) return; // idle: skip the render + label passes this frame
      needsRender = false;
      // Reveal/hide the speed slider from the live animation state. Cheap + guarded to a
      // no-op when unchanged; a stop always triggers one final render here, so it can't
      // stay stuck visible after the focus clears.
      updateSpeedRow();
      renderer.render(scene, camera);
      // CSS2D labels render as a separate DOM pass after the WebGL frame.
      labels.render(scene, camera);
    });
  };

  return { invalidate, start };
}
