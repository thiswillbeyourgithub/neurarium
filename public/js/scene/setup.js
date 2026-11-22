// Scene setup: renderer, camera, lights and OrbitControls, plus the module-level
// repaint hook the on-demand render loop fills in (setRepaint).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createTheme } from "../theme.js";

// The render loop is built in main.js, long after the scene, so
// anything up here that needs a repaint goes through this hook, which `invalidate`
// replaces once it exists. A no-op before then is right: nothing has been drawn yet.
// It sits at module scope because its two ends live in different functions: the theme
// fires it from initThree(), the loop fills it in from the boot path.
let repaint = () => {};
/** Install the render loop's `invalidate` as the repaint hook. */
export function setRepaint(fn) {
  repaint = fn;
}

/** Ask the on-demand loop for one frame (e.g. after an async mesh landed). */
export function requestRepaint() {
  repaint();
}

/** Build scene, camera, renderer and controls. @returns {object} the bundle. */
export function initThree() {
  const canvas = document.getElementById("scene");
  const scene = new THREE.Scene();
  // Set below by the theme, whose token block owns the colour; the literal is only
  // what the canvas holds for the instant before the first apply() runs.
  scene.background = new THREE.Color("#0e1116");
  // Light/dark. The palette is CSS tokens (see css/tokens.css); the WebGL canvas is not
  // CSS, so the resolved page background is handed back here and painted into the
  // scene. See js/theme.js for who decides which theme is on.
  const theme = createTheme((_name, pageBg) => {
    if (pageBg) scene.background = new THREE.Color(pageBg);
    repaint();
  });

  const camera = new THREE.PerspectiveCamera(
    50,
    window.innerWidth / window.innerHeight,
    0.1,
    1000,
  );
  // Pulled back from the old (9, 4.5, 13): the default view was a touch too
  // zoomed in, so the resting framing leaves a little more room around the brain.
  camera.position.set(11, 5.5, 16);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  // Cap the device pixel ratio at 2 (a retina phone can report 3+, which quadruples
  // the pixel work for no visible gain). This is the *base* ratio; the adaptive
  // quality controller (see createAdaptiveQuality) scales it down transiently when
  // it detects dropped frames, then this same base is the ceiling it recovers to.
  const baseDpr = Math.min(window.devicePixelRatio, 2);
  renderer.setPixelRatio(baseDpr);
  renderer.setSize(window.innerWidth, window.innerHeight);

  // Soft, even lighting so colors read true and the blobs keep visible relief.
  scene.add(new THREE.HemisphereLight(0xffffff, 0x33373d, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 0.8);
  key.position.set(6, 10, 8);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xbfd4ff, 0.35);
  fill.position.set(-8, -4, -6);
  scene.add(fill);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.rotateSpeed = 0.9;
  controls.minDistance = 4;
  // Comfortably beyond the fully-separated spread so the intro's zoom-out (the
  // resting distance times the explode spread factor) isn't clamped mid-greeting.
  controls.maxDistance = 75;
  // Pan in screen space so a two-finger drag slides the brain across the view
  // (rather than along world axes), which feels natural on touch.
  controls.enablePan = true;
  controls.screenSpacePanning = true;
  // Touch mapping: one finger rotates, two fingers pan AND pinch-zoom together
  // (DOLLY_PAN). Pinned here so it survives future control tweaks.
  controls.touches = {
    ONE: THREE.TOUCH.ROTATE,
    TWO: THREE.TOUCH.DOLLY_PAN,
  };

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  return { scene, camera, renderer, controls, baseDpr, theme };
}
