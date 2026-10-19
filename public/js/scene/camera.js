// Camera: named view framing, the animated focus controller, and the ?params view
// keys (applyViewParams, used by tools/shot.py).

import * as THREE from "three";
import { EXPLODE_STRENGTH } from "./explode.js";
import { QUERY, isFramedView } from "../boot/query.js";

// Padding around the whole assembled brain when a load / the reset button frames it
// (createCameraFocus fitAll): 1 would touch the viewport edge.
const FIT_ALL_MARGIN = 1.15;

// Camera directions for `?view=` (unit vectors from the framed target back to
// the camera). World axes: x right, y up, z toward the viewer / anterior.
const VIEW_DIRS = {
  front: [0, 0, 1],
  back: [0, 0, -1],
  right: [1, 0, 0],
  left: [-1, 0, 0],
  top: [0, 1, 0],
  bottom: [0, -1, 0],
  iso: [1, 0.55, 1.2],
};

/**
 * Point the camera so the currently visible meshes fill the frame, from a named
 * direction. Used by the screenshot URL params (`?view=`, `?only=`) so a single
 * structure can be inspected from a canonical angle. No-op if nothing visible.
 * @param {{camera:THREE.PerspectiveCamera, controls:OrbitControls, meshes:THREE.Mesh[]}} bundle
 * @param {string} viewName  Key of VIEW_DIRS (defaults to "iso").
 */
function frameVisible({ camera, controls, meshes }, viewName, onlyIds = null) {
  // `onlyIds` (a comma-joined id string) restricts the framing box to those
  // meshes, used by the solo review view so the camera frames the studied
  // structure while its ghosted neighbours stay in shot as context.
  const keep = onlyIds ? new Set(onlyIds.split(",").map((s) => s.trim()).filter(Boolean)) : null;
  const box = new THREE.Box3();
  let any = false;
  for (const mesh of meshes) {
    if (mesh.visible && (!keep || keep.has(mesh.userData.id))) {
      box.expandByObject(mesh);
      any = true;
    }
  }
  if (!any) return;

  const center = box.getCenter(new THREE.Vector3());
  const radius = box.getBoundingSphere(new THREE.Sphere()).radius;
  const dir = new THREE.Vector3(...(VIEW_DIRS[viewName] || VIEW_DIRS.iso)).normalize();
  // Distance that fits the bounding sphere in the vertical FOV, plus margin.
  const dist = (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2)) * 1.3;

  camera.position.copy(center).addScaledVector(dir, dist);
  camera.near = Math.max(0.01, dist - radius * 2);
  camera.far = dist + radius * 4;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

/**
 * Smooth camera framing shared by double-click, the reset button and search.
 *
 * Tweens both the orbit pivot (`controls.target`) and the camera position so a
 * structure (or the whole brain) ends up centered and reasonably sized. The
 * current viewing direction (target -> camera) is preserved so only the pivot
 * and distance change, which is far less disorienting than also swinging the
 * angle. The tween is advanced one step per frame by `tick()` and is cancelled
 * the instant the user grabs the controls (so a drag always wins).
 * @param {{camera:THREE.PerspectiveCamera, controls:OrbitControls, meshes:THREE.Mesh[]}} bundle
 */
export function createCameraFocus({ camera, controls, meshes, getFocusMeshes }) {
  const sphere = new THREE.Sphere();
  const box = new THREE.Box3();
  const tmpVec = new THREE.Vector3();
  // The in-progress tween, or null when idle.
  let anim = null;
  // The structure last centered via focusStructure (double-click / structure
  // search), or null. Kept so the explode slider can re-aim the camera at it as
  // it moves; cleared whenever we frame something else (a connection or the
  // whole brain) so we don't chase a structure the user has navigated away from.
  let focused = null;
  // Pivot-follow: while anything is focused, dragging the Separate slider keeps the
  // focused thing centered by easing the orbit pivot onto its (moving) center, and
  // recenters smoothly when the view didn't start on it. Enabled by reaimFocused()
  // (called from the explode handler), advanced in tick(), and turned off once it
  // settles (so an idle focus costs nothing per frame), when the user grabs the
  // camera (cancel), or when the focus clears.
  let trackPivot = false;
  const PIVOT_EASE = 0.3;        // per-frame approach fraction while off-center
  const PIVOT_SNAP_FRAC = 0.05;  // within this * brain radius, snap (exact tracking)
  // The explode amount last applied, so zoomForExplode() only ever applies the
  // *incremental* distance change and thus preserves whatever zoom the user has
  // dialed in. The layout scales linearly with this (applyExplode pushes each
  // region to base * (1 + amount * EXPLODE_STRENGTH)).
  let lastExplode = 0;
  const spreadScale = (a) => 1 + a * EXPLODE_STRENGTH;
  // A structure's own (fixed) radius in world units: its geometry bounding sphere
  // scaled by the mesh scale. Cached on first use (geometry never changes).
  const meshReach = (mesh) => {
    const g = mesh.geometry;
    if (!g.boundingSphere) g.computeBoundingSphere();
    const s = Math.max(mesh.scale.x, mesh.scale.y, mesh.scale.z);
    return g.boundingSphere.radius * s;
  };
  // The whole assembly's outer radius from the brain centre at a given explode
  // amount: the farthest structure surface = max over regions of
  // (|base| * spreadScale(amount)) + that region's own radius. zoomForExplode
  // scales the camera distance by the *ratio* of this (not spreadScale alone),
  // which keeps the WHOLE brain a constant apparent size as it spreads. Matching
  // spreadScale alone over-pulls the camera back (it ignores the fixed structure
  // radii), so the brain visibly shrinks while exploding; matching the true outer
  // radius holds the brain steady, so only the individual structures look like
  // they shrink apart, which is the intent.
  const boundingRadiusAt = (amount) => {
    const k = spreadScale(amount);
    let maxR = 0;
    for (const mesh of meshes) {
      const r = mesh.userData.base.length() * k + meshReach(mesh);
      if (r > maxR) maxR = r;
    }
    return maxR || 1;
  };
  // Render-time screen offset (fractions of the viewport: +x slides the rendered
  // brain right, +y up), eased toward `offsetTarget` each tick and baked into the
  // camera as a view offset. It is a projection shift, not a move of the orbit
  // target, so it survives rotation / zoom / framing and reverts cleanly. Used to
  // slide the brain out from under the expanded panel on a phone (see
  // setScreenOffset wiring in wireControls).
  const offset = { x: 0, y: 0 };
  const offsetTarget = { x: 0, y: 0 };
  const OFFSET_EPS = 0.0005;
  // Bake the current offset into the camera's view offset (or clear it). Reads
  // the live viewport size every call so a resize self-heals without extra
  // bookkeeping.
  const applyOffset = () => {
    if (Math.abs(offset.x) < OFFSET_EPS && Math.abs(offset.y) < OFFSET_EPS) {
      if (camera.view && camera.view.enabled) camera.clearViewOffset();
      return;
    }
    const w = window.innerWidth;
    const h = window.innerHeight;
    // offsetX < 0 slides content right; offsetY > 0 slides content up (see the
    // updateProjectionMatrix math in three's PerspectiveCamera).
    camera.setViewOffset(w, h, -offset.x * w, offset.y * h, w, h);
  };

  // Distance at which a bounding sphere of `radius` fits the vertical FOV,
  // padded by `margin` (a bigger margin leaves more context around the target).
  const fitDistance = (radius, margin) =>
    (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2)) * margin;

  // The present view direction (target -> camera, unit length).
  const viewDir = () => {
    const dir = camera.position.clone().sub(controls.target);
    if (dir.lengthSq() < 1e-6) dir.set(...VIEW_DIRS.iso);
    return dir.normalize();
  };

  // Whole-brain fit, seen along `dir` from `center`: the distance at which every
  // visible vertex lands inside the viewport on both axes, and inside the part the
  // expanded panel leaves clear (the screen offset slides the brain there, so only
  // that part counts), times `margin`; plus how far off-centre the silhouette sits
  // at that distance (`shiftX`/`shiftY`, world units along the screen axes). Exact
  // rather than a bounding sphere: the sphere around the brain's box is much wider
  // than the brain seen from any side, which left a desktop load framed far too
  // loosely. One pass over the vertices, only on a load / reset, never per frame.
  const measureFit = (center, dir, margin) => {
    const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const clearV = tanV * (1 - 2 * Math.abs(offsetTarget.y));
    const clearH = tanV * camera.aspect * (1 - 2 * Math.abs(offsetTarget.x));
    const right = new THREE.Vector3().crossVectors(camera.up, dir).normalize();
    const up = new THREE.Vector3().crossVectors(dir, right);
    const v = new THREE.Vector3();
    const pts = [];
    let dist = 0;
    for (const mesh of meshes) {
      if (!mesh.visible) continue;
      const pos = mesh.geometry.attributes.position;
      mesh.updateMatrixWorld();
      for (let i = 0; i < pos.count; i++) {
        v.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld).sub(center);
        const x = v.dot(right), y = v.dot(up), z = v.dot(dir);
        pts.push(x, y, z);
        dist = Math.max(dist, z + Math.abs(x) / clearH, z + Math.abs(y) / clearV);
      }
    }
    dist = Math.max(controls.minDistance, dist * margin);
    // Screen extents (as tangents) from that distance, mapped back to the pivot plane.
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < pts.length; i += 3) {
      const depth = dist - pts[i + 2];
      const sx = pts[i] / depth, sy = pts[i + 1] / depth;
      if (sx < minX) minX = sx;
      if (sx > maxX) maxX = sx;
      if (sy < minY) minY = sy;
      if (sy > maxY) maxY = sy;
    }
    return { dist, right, up, shiftX: ((minX + maxX) / 2) * dist, shiftY: ((minY + maxY) / 2) * dist };
  };

  // The center + distance framing the whole visible brain from the present view
  // direction, or null when nothing is visible. Shared by recenter + frameAllNow so
  // the reset button and a fresh load land on the same pose. Measured twice: once
  // about the box centre to find how far off-centre the silhouette sits, then again
  // about the silhouette's centre (the olfactory bulbs alone pull the box forward).
  const fitAll = () => {
    box.makeEmpty();
    for (const mesh of meshes) if (mesh.visible) box.expandByObject(mesh);
    if (box.isEmpty()) return null;
    const center = box.getCenter(new THREE.Vector3());
    const dir = viewDir();
    const first = measureFit(center, dir, FIT_ALL_MARGIN);
    center.addScaledVector(first.right, first.shiftX).addScaledVector(first.up, first.shiftY);
    return { center, dir, dist: measureFit(center, dir, FIT_ALL_MARGIN).dist };
  };

  // Begin a tween that looks at `center` and frames a sphere of `radius` (or sits
  // `dist` away when given), keeping the present view direction.
  function tweenTo(center, radius, margin, dist = null) {
    const dir = viewDir();
    if (dist == null) dist = Math.max(controls.minDistance, fitDistance(radius, margin));
    anim = {
      fromTarget: controls.target.clone(),
      toTarget: center.clone(),
      fromPos: camera.position.clone(),
      toPos: center.clone().addScaledVector(dir, dist),
      start: performance.now(),
      duration: 500,
    };
  }

  // The live center of whatever is currently focused (the dimmed-in set the viewer
  // reports via getFocusMeshes), written into `out`; returns false when nothing is
  // focused. Prefers the explicitly focused single structure while it is still part
  // of that set, so a searched / double-clicked structure tracks precisely;
  // otherwise the whole set's bounding-sphere center, so a receptor / drug / circuit
  // focus (spanning many regions) stays framed as it explodes. Only visible meshes
  // count, so it composes with "See inside".
  function focusCenter(out) {
    const sel = getFocusMeshes && getFocusMeshes();
    if (!sel || !sel.length) return false;
    if (focused && focused.visible && sel.indexOf(focused) !== -1) {
      focused.getWorldPosition(out);
      return true;
    }
    box.makeEmpty();
    let any = false;
    for (const m of sel) if (m && m.visible) { box.expandByObject(m); any = true; }
    if (!any) return false;
    box.getBoundingSphere(sphere);
    out.copy(sphere.center);
    return true;
  }

  return {
    /** Center on and frame a single structure mesh (double-click / search). */
    focusStructure(mesh) {
      box.setFromObject(mesh).getBoundingSphere(sphere);
      // A generous margin keeps the structure centered but in context, rather
      // than filling the frame (which would just clip into its neighbors).
      tweenTo(sphere.center, sphere.radius, 2.2);
      // Remember it so reaimFocused() can keep it centered as it explodes out.
      focused = mesh;
    },
    /**
     * Frame a connection by fitting both of its endpoint structures, so picking
     * a pathway in the search recenters on the two regions it links.
     * @param {import("./arrows.js").ProjectionArrow} arrow
     */
    focusConnection(arrow) {
      box.makeEmpty();
      box.expandByObject(arrow.fromMesh);
      box.expandByObject(arrow.toMesh);
      box.getBoundingSphere(sphere);
      tweenTo(sphere.center, sphere.radius, 1.8);
      // A connection isn't a single structure to track, so stop following one.
      focused = null;
    },
    /**
     * Frame an arbitrary set of structure meshes by fitting their combined
     * bounding sphere, used when a receptor is picked in search (it spans several
     * regions). Ignores hidden meshes; a no-op if none are visible. Doesn't track
     * a single structure (the set isn't one), so it clears `focused` like
     * focusConnection.
     * @param {THREE.Mesh[]} meshList
     */
    focusMeshes(meshList) {
      box.makeEmpty();
      let any = false;
      for (const m of meshList) {
        if (m && m.visible) { box.expandByObject(m); any = true; }
      }
      if (!any) return;
      box.getBoundingSphere(sphere);
      tweenTo(sphere.center, sphere.radius, 1.8);
      focused = null;
    },
    /** Recenter the pivot on the middle of the brain and frame the whole thing. */
    recenter() {
      const fit = fitAll();
      if (!fit) return;
      tweenTo(fit.center, 0, 0, fit.dist);
      focused = null;
    },
    /**
     * Instantly frame the whole visible brain (no tween), preserving the current
     * view direction. Used to seat the initial resting pose so a fresh load already
     * sits exactly where the reset button (recenter, same fitAll) would put it.
     */
    frameAllNow() {
      const fit = fitAll();
      if (!fit) return;
      controls.target.copy(fit.center);
      camera.position.copy(fit.center).addScaledVector(fit.dir, fit.dist);
      controls.update();
      focused = null;
    },
    /**
     * Called from the explode handler as the brain spreads: keep whatever is
     * focused (a single structure, or the multi-region set of a receptor / drug /
     * circuit / group focus) centered as it moves radially outward. It enables the
     * pivot-follow; tick() does the actual easing (gliding the orbit pivot in when
     * the view didn't start on the focus, then snapping to track the moving center
     * exactly). Only the pivot (controls.target) moves, so the camera rotates in
     * place, preserving the distance + angle the user set. A running framing tween
     * has its destination updated too so the two don't fight. Disabled when nothing
     * is focused.
     */
    reaimFocused() {
      trackPivot = focusCenter(tmpVec);
      if (trackPivot && anim) anim.toTarget.copy(tmpVec);
    },
    /**
     * Pull the camera back (or in) as the brain spreads, so the whole brain keeps
     * a *constant apparent size* (and the individual structures appear to shrink
     * as they separate) instead of overflowing or visibly shrinking. We scale the
     * camera->target distance by the ratio of the assembly's true outer radius
     * (boundingRadiusAt, which folds in the fixed structure radii) at the new vs
     * the last amount, so only the incremental change is applied and any manual
     * zoom the user has dialed in is preserved. OrbitControls' min/maxDistance
     * clamp the result on the next update. Call from the explode handler with the
     * slider's value.
     */
    zoomForExplode(amount) {
      const ratio = boundingRadiusAt(amount) / boundingRadiusAt(lastExplode);
      lastExplode = amount;
      if (Math.abs(ratio - 1) < 1e-6) return;
      tmpVec.copy(camera.position).sub(controls.target).multiplyScalar(ratio);
      camera.position.copy(controls.target).add(tmpVec);
    },
    /**
     * The factor by which the explode auto-zoom (zoomForExplode) has currently
     * pulled the camera back, relative to the assembled (amount 0) framing. So
     * `currentDistance / explodeZoom()` recovers the distance the user's own zoom
     * implies, with the spread's auto-pull divided out. The constant-width arrow
     * controller uses this so a spread (which auto-zooms) does not change arrow
     * width, only a genuine user zoom does.
     */
    explodeZoom() {
      return boundingRadiusAt(lastExplode) / boundingRadiusAt(0);
    },
    /**
     * Set the desired render-time screen offset (fractions of the viewport:
     * +x slides the brain right, +y up). Eased in/out by tick(). Pass 0,0 to
     * recenter. Survives rotation / zoom / framing (it's a projection shift).
     */
    setScreenOffset(x, y) {
      offsetTarget.x = x;
      offsetTarget.y = y;
    },
    /** Abort any running tween (used when the user starts interacting). */
    cancel() {
      anim = null;
      trackPivot = false; // a manual camera grab wins over the pivot-follow
    },
    /** Advance the active tween; call once per frame before controls.update().
     *  Returns true while a framing tween or the screen-offset ease is moving, so
     *  the on-demand render loop keeps drawing until both settle. */
    tick() {
      let active = false;
      if (anim) {
        const t = Math.min(1, (performance.now() - anim.start) / anim.duration);
        const e = t * t * (3 - 2 * t); // smoothstep ease in/out
        controls.target.lerpVectors(anim.fromTarget, anim.toTarget, e);
        camera.position.lerpVectors(anim.fromPos, anim.toPos, e);
        if (t >= 1) anim = null;
        active = true;
      } else if (trackPivot) {
        // No framing tween running: ease the orbit pivot toward the focused center.
        // Glide in when the view didn't start centered on it, then snap once close
        // so a slow spread tracks the (moving) center exactly with no lag. Turns
        // itself off once settled so an idle focus costs nothing per frame.
        if (focusCenter(tmpVec)) {
          const d = tmpVec.sub(controls.target); // tmpVec now = center - target
          const dist = d.length();
          if (dist > boundingRadiusAt(lastExplode) * PIVOT_SNAP_FRAC) {
            controls.target.addScaledVector(d, PIVOT_EASE);
            active = true;
          } else if (dist > 1e-4) {
            controls.target.add(d); // close enough: snap onto the center
            active = true;
          } else {
            trackPivot = false; // settled: stop following until the next spread
          }
        } else {
          trackPivot = false; // focus cleared
        }
      }
      // Ease the screen offset toward its target and (re)apply it. Runs every
      // frame independent of the framing tween, so the panel pan animates on its
      // own and a resize keeps the offset correctly scaled.
      if (
        Math.abs(offset.x - offsetTarget.x) > OFFSET_EPS ||
        Math.abs(offset.y - offsetTarget.y) > OFFSET_EPS
      ) {
        offset.x += (offsetTarget.x - offset.x) * 0.18;
        offset.y += (offsetTarget.y - offset.y) * 0.18;
        active = true;
      } else if (offset.x !== offsetTarget.x || offset.y !== offsetTarget.y) {
        offset.x = offsetTarget.x;
        offset.y = offsetTarget.y;
        active = true; // one last frame to apply the snap to target
      }
      applyOffset();
      return active;
    },
  };
}

/**
 * Apply screenshot/deep-link view parameters from the URL query string so the
 * headless renderer (tools/shot.py) can capture a specific view without any
 * interaction. Supported keys:
 *   explode, transparency : numbers (also move the sliders so the UI matches)
 *   autorotate            : truthy -> spin
 *   names=all             : force every structure label on
 *   only=id[,id2,...]     : show only these structures (others + all arrows hidden)
 *   view=front|back|left|right|top|bottom|iso : frame the visible meshes
 * The first three are ordinary UI state, so they are handed to the very url-state
 * views the fragment uses (js/url-state.js) rather than re-implemented here; what
 * stays below is the screenshot-only half, which describes no shareable UI state.
 * Called after wireControls so the initial slider-driven layout is in place.
 * @param {object} bundle  { scene, camera, controls, meshes, arrows, labels, urlState }
 */
export function applyViewParams(bundle) {
  const q = QUERY;
  if (!isFramedView(q)) return;
  const { camera, controls, meshes, arrows, urlState } = bundle;

  const autorotate = document.getElementById("autorotate");

  // Translate the query's (older, screenshot-facing) spellings onto the registry keys.
  const shared = new URLSearchParams();
  for (const key of ["explode", "transparency"]) {
    if (q.has(key)) shared.set(key, q.get(key));
  }
  if (q.get("names") === "all") shared.set("names", "1");
  urlState.apply(shared);
  // Auto-rotate is on by default for a live visit, but a deep link / screenshot
  // wants its exact framed view to hold still, so set it explicitly here (off
  // unless the param asks for it) instead of letting the default keep spinning.
  // Unlike the keys above this is NOT the registry's "a missing key changes nothing"
  // rule: any VIEW key (boot/query.js VIEW_KEYS) means a framed view, hence a still
  // one; a query holding only startup flags (`?lang=`, `?tour=`) returned above.
  if (autorotate) {
    autorotate.checked = q.has("autorotate") && q.get("autorotate") !== "0";
    autorotate.dispatchEvent(new Event("change"));
  }
  // ?ui=0 hides the control panel (which now nests the toolbar, legend and the
  // detail/info pane) for clean, uncluttered shots (e.g. reviewing a shape).
  if (q.get("ui") === "0") {
    const el = document.getElementById("controls");
    if (el) el.style.display = "none";
  }

  if (q.has("only")) {
    const keep = new Set(q.get("only").split(",").map((s) => s.trim()).filter(Boolean));
    for (const mesh of meshes) mesh.visible = keep.has(mesh.userData.id);
    // Arrows are about relationships, not form; hide them all in isolated views.
    for (const arrow of arrows) arrow.setVisible(false);
    // Drop labels of now-hidden meshes (in case names=all was already applied).
    bundle.labels.refresh();
  }

  // `solo=id[,id2]`: the in-context shape-review view. Keep the whole brain
  // visible but render only the solo set solidly while the rest is ghosted to a
  // faint translucency (override the amount with `ghost=0..1`), so a structure's
  // fit against its neighbours can be judged. Used by tools/sculpt_shot.py; the
  // framing below targets the solo set. Arrows hidden (form, not relationships).
  if (q.has("solo")) {
    const solo = new Set(q.get("solo").split(",").map((s) => s.trim()).filter(Boolean));
    // A non-numeric `ghost` falls back to the default (never a NaN opacity); a number is clamped to [0, 1].
    const ghostRaw = Number(q.get("ghost"));
    const ghost = q.has("ghost") && Number.isFinite(ghostRaw) ? Math.min(1, Math.max(0, ghostRaw)) : 0.06;
    for (const mesh of meshes) {
      const isSolo = solo.has(mesh.userData.id);
      mesh.material.transparent = !isSolo;
      mesh.material.opacity = isSolo ? 1 : ghost;
      mesh.material.depthWrite = isSolo;
    }
    for (const arrow of arrows) arrow.setVisible(false);
    bundle.labels.refresh();
  }

  // Frame whenever a view angle is requested, or a subset is isolated. With a
  // solo set, frame on it (the rest is only ghosted context, not framed).
  if (q.has("view") || q.has("only") || q.has("solo")) {
    frameVisible(bundle, q.get("view") || "iso", q.has("solo") ? q.get("solo") : null);
  }
}
