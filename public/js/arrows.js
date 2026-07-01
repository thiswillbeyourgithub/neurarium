// Curved arrows representing directed neuron projections between structures.
//
// Each arrow is a thin curved tube (a quadratic Bezier bowing outward from the
// brain center, so arrows don't hide inside the blobs) capped with a cone head
// at the target end. Each end is attached to the point on the structure's
// *surface* nearest the other end (not its hidden center), so the shaft spans the
// gap between regions and the cone tip lands on a real arm of mass that stays
// visible instead of buried inside the blob. Because structures move when the
// explode slider changes, arrows expose an update() that re-fits their geometry
// to the *current* mesh positions each time the layout changes.

import * as THREE from "three";

// Module-level scratch for the per-end surface attach (see surfaceToward), so the
// per-frame re-fit allocates nothing; arrows are trimmed sequentially.
const _inv = new THREE.Matrix4();
const _localPt = new THREE.Vector3();

/**
 * Point on `mesh`'s surface nearest to `fromPoint` (the other arrow end), so the
 * arrow attaches to real surface mass instead of the structure's hidden
 * volumetric center.
 *
 * Why nearest-point and not a ray through the center: a concave region (most
 * egregiously the C-shaped caudate) has its volume centre sitting in a HOLLOW, so
 * a ray aimed through it threads the *opening* of the loop and the arrow lands on
 * empty space. The nearest surface point is on the mesh by construction, so it
 * always sits on a real arm of mass facing the other end. For the common convex
 * blob it coincides with the old centre-line hit, so those arrows don't move.
 *
 * Computed as the nearest geometry vertex, in the mesh's LOCAL space (transform
 * `fromPoint` once by the inverse world matrix, scan the raw vertices, map the
 * winner back to world). Working in local space (a single inverse-transform vs.
 * transforming every vertex) also makes it robust to the mirrored left-hemisphere
 * meshes, with none of a FrontSide raycast's winding sensitivity. Cheaper than the
 * old ray-vs-every-triangle intersection it replaces.
 * @param {THREE.Mesh} mesh
 * @param {THREE.Vector3} fromPoint  World point to attach toward (the other end).
 * @returns {THREE.Vector3|null}  Null only for an empty geometry.
 */
function surfaceToward(mesh, fromPoint) {
  // Positions may have just been changed by the explode logic; make sure the
  // world matrix is current before using it.
  mesh.updateMatrixWorld();
  const pos = mesh.geometry.attributes.position;
  if (!pos || pos.count === 0) return null;
  // Compare in local space: one inverse-transform of fromPoint beats transforming
  // every vertex out to world. (position is a plain stride-3 buffer for every
  // shape type we build, so the raw array is safe to walk directly.)
  _localPt.copy(fromPoint).applyMatrix4(_inv.copy(mesh.matrixWorld).invert());
  const arr = pos.array;
  const lx = _localPt.x, ly = _localPt.y, lz = _localPt.z;
  let bestI = 0, bestD = Infinity;
  for (let i = 0; i < arr.length; i += 3) {
    const dx = arr[i] - lx, dy = arr[i + 1] - ly, dz = arr[i + 2] - lz;
    const d = dx * dx + dy * dy + dz * dz;
    if (d < bestD) { bestD = d; bestI = i; }
  }
  return new THREE.Vector3(arr[bestI], arr[bestI + 1], arr[bestI + 2])
    .applyMatrix4(mesh.matrixWorld);
}

// Arrow colour per projection comes from the data: each projection record
// carries a resolved `color` (data.js fills it from the generator's kind->colour
// meta map). The viewer reads `projection.color` everywhere, so the palette has
// a single source (tools/generate_data.py) and the dataset is self-describing.

const TUBE_RADIUS = 0.1;
const CONE_LENGTH = 0.4;
const CONE_RADIUS = 0.22;
// Arrows never render fully opaque: even undimmed they cap here, so a projection
// always reads as a translucent overlay on the anatomy (the brain shows through)
// rather than a hard solid tube. setOpacity() clamps to this, so the isolate/focus
// "full" state (setOpacity(1)) lands at this cap and dimming still fades below it.
const ARROW_MAX_OPACITY = 0.8;
// Radius of the selection-halo tube: a fatter additive glow drawn around the
// whole arc when the arrow is picked, mirroring the structures' halo shells.
const HALO_RADIUS = 0.22;
// Radius of the invisible pick tube: much fatter than the visible TUBE_RADIUS so
// a click/tap that lands near (not exactly on) a thin arrow still selects it.
const PICK_RADIUS = 0.32;
// Shared invisible material for every arrow's pick tube: never rendered
// (visible:false) but still raycast, since Mesh.raycast tests triangles
// regardless of material visibility. One instance is enough (no per-arrow state).
const PICK_MATERIAL = new THREE.MeshBasicMaterial({ visible: false });
// How far the curve's midpoint bows away from the brain center, as a fraction
// of the straight-line distance between the two endpoints.
const BOW_FACTOR = 0.25;
// Sideways offset of the midpoint (fraction of the span), perpendicular to both
// the line and the outward bow. Its sign is keyed off the endpoint id ordering
// so a reciprocal pair (A->B and B->A) splits to opposite sides instead of
// drawing two arrows on the exact same arc (e.g. the indirect-pathway
// GPe<->STN loop, or striatonigral vs nigrostriatal between the same nuclei).
const SIDE_FACTOR = 0.16;

// Tentative (speculative) pathways are drawn as a *dotted* tube instead of a
// solid one, so they read as "maybe" rather than fact. The dotting is pure
// geometry (gaps in the tube), so the same material / halo / picking as a solid
// arrow apply unchanged. DASH_COUNT periods span the shaft; DASH_ON is the solid
// fraction of each period (the rest is a gap).
const DASH_COUNT = 9;
const DASH_ON = 0.55;

/**
 * Concatenate several indexed BufferGeometries (position + normal + index) into
 * one. A tiny local stand-in for three/addons BufferGeometryUtils.mergeGeometries
 * (not vendored), enough for merging the dash segments of a dotted tube. UVs are
 * dropped: the arrows use a flat solid-colour material that doesn't sample them.
 * @param {THREE.BufferGeometry[]} geoms  All must be indexed with position+normal.
 * @returns {THREE.BufferGeometry}
 */
function mergeIndexedGeometries(geoms) {
  let vertexCount = 0;
  let indexCount = 0;
  for (const g of geoms) {
    vertexCount += g.attributes.position.count;
    indexCount += g.index.count;
  }
  const position = new Float32Array(vertexCount * 3);
  const normal = new Float32Array(vertexCount * 3);
  const index = new Uint32Array(indexCount);
  let vOffset = 0;
  let iOffset = 0;
  for (const g of geoms) {
    position.set(g.attributes.position.array, vOffset * 3);
    normal.set(g.attributes.normal.array, vOffset * 3);
    const gi = g.index.array;
    for (let i = 0; i < gi.length; i++) index[iOffset + i] = gi[i] + vOffset;
    vOffset += g.attributes.position.count;
    iOffset += gi.length;
  }
  const merged = new THREE.BufferGeometry();
  merged.setAttribute("position", new THREE.BufferAttribute(position, 3));
  merged.setAttribute("normal", new THREE.BufferAttribute(normal, 3));
  merged.setIndex(new THREE.BufferAttribute(index, 1));
  return merged;
}

/**
 * A dotted tube along `curve`: DASH_COUNT short tube segments with gaps between
 * them, merged into one geometry (same radius as a solid tube so a dotted arrow
 * reads as the same pathway, just uncertain).
 * @param {THREE.Curve} curve
 * @param {number} radius
 * @returns {THREE.BufferGeometry}
 */
function dashedTubeGeometry(curve, radius) {
  const segments = [];
  for (let i = 0; i < DASH_COUNT; i++) {
    const t0 = i / DASH_COUNT;
    const t1 = (i + DASH_ON) / DASH_COUNT;
    const pts = [];
    for (let s = 0; s <= 3; s++) pts.push(curve.getPoint(t0 + (t1 - t0) * (s / 3)));
    segments.push(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 3, radius, 6, false));
  }
  const merged = mergeIndexedGeometries(segments);
  for (const g of segments) g.dispose();
  return merged;
}

/**
 * A single projection arrow. Holds its own meshes (tube + one or two cones)
 * grouped under one Object3D and recomputes them from the live source/target
 * centers. Carries its source `projection` record so the picking/search UI can
 * read the connection's metadata back off a ray hit.
 */
export class ProjectionArrow {
  /**
   * @param {THREE.Mesh} fromMesh  Source structure mesh.
   * @param {THREE.Mesh} toMesh    Target structure mesh.
   * @param {object} projection    The projection record (from/to/kind/label/...).
   * @param {string} colorHex      Arrow color (the projection's resolved `color`).
   */
  constructor(fromMesh, toMesh, projection, colorHex) {
    this.fromMesh = fromMesh;
    this.toMesh = toMesh;
    this.projection = projection;
    // Speculative pathways draw a dotted shaft instead of a solid tube.
    this.tentative = Boolean(projection.tentative);
    this.group = new THREE.Group();
    // Stable side for the lateral offset: reverse the sign when the endpoints
    // swap, so the two directions of a reciprocal pair take opposite arcs.
    this.side = projection.from < projection.to ? 1 : -1;

    const color = new THREE.Color(colorHex);
    // Flat, lit-independent material so arrows stay readable. Created
    // `transparent: true` from the start (like the structure material): toggling
    // `transparent` at runtime would need a material recompile (needsUpdate) to
    // take visual effect, so setOpacity() below only ever changes
    // `opacity`/`depthWrite` and the isolate-mode dimming actually shows. Its
    // resting opacity is ARROW_MAX_OPACITY (never fully opaque, so the anatomy
    // always shows through the arrows); the global Transparency slider leaves this
    // alone (it never calls setOpacity), only the isolate/circuit focus fades them.
    this.material = new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: ARROW_MAX_OPACITY, depthWrite: false });

    // Tube geometry is rebuilt on every update(); start with a placeholder.
    this.tube = new THREE.Mesh(new THREE.BufferGeometry(), this.material);
    this.cone = new THREE.Mesh(
      new THREE.ConeGeometry(CONE_RADIUS, CONE_LENGTH, 12),
      this.material,
    );
    this.group.add(this.tube, this.cone);
    // Reciprocal/commissural pathways (e.g. the corpus callosum) draw a head at
    // the source end too, so the arrow reads as connecting both ways.
    this.coneStart = null;
    if (projection.bidirectional) {
      this.coneStart = new THREE.Mesh(
        new THREE.ConeGeometry(CONE_RADIUS, CONE_LENGTH, 12),
        this.material,
      );
      this.group.add(this.coneStart);
    }

    // Invisible, deliberately fat tube used only for picking, so the thin
    // visible arrow is still easy to click/tap. Rebuilt in update() along the
    // full curve; never drawn.
    this.pick = new THREE.Mesh(new THREE.BufferGeometry(), PICK_MATERIAL);
    this.group.add(this.pick);

    // Selection halo: a fatter additive tube along the whole arc, hidden until
    // the arrow is picked (click/search). Lightened toward white so it reads as
    // a glow, like the structures' halo shells. Rebuilt with the curve each
    // update(); pure decoration, so it never intercepts a raycast.
    this.haloMaterial = new THREE.MeshBasicMaterial({
      color: color.clone().lerp(new THREE.Color(0xffffff), 0.4),
      transparent: true,
      opacity: 0.5,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    this.halo = new THREE.Mesh(new THREE.BufferGeometry(), this.haloMaterial);
    this.halo.visible = false;
    this.halo.raycast = () => {};
    this.group.add(this.halo);

    // Pickable meshes, each tagged so a raycast hit maps back to this arrow. The
    // fat pick tube comes first so it dominates the thin visible parts.
    this.meshes = [this.pick, this.tube, this.cone, this.coneStart].filter(Boolean);
    for (const m of this.meshes) m.userData.arrow = this;

    // Anchor at the arc midpoint that a floating connection label can ride on
    // (see js/labels.js). update() keeps it on the live curve so the label
    // tracks the arrow as the regions explode. Added to the group so it inherits
    // visibility with the rest of the arrow.
    this.labelAnchor = new THREE.Object3D();
    this.group.add(this.labelAnchor);

    // Width multiplier applied to the shaft radius + the cone cross-section, so
    // arrows can be kept a constant *apparent* width as the camera zooms (a
    // zoomed-in arrow would otherwise balloon and clutter the view). 1 = the
    // authored TUBE_RADIUS. Driven by setWidthScale(); update() honours it so the
    // width survives every explode rebuild. The live shaft curve is cached so a
    // pure width change can rebuild the tube without recomputing the arc.
    this._widthScale = 1;
    this._shaftCurve = null;

    this.update();
  }

  /**
   * Re-fit the arrow (tube + cone) to its (possibly just-moved) endpoints. Call
   * after the structures have been (re)positioned for a new explode amount.
   * @param {boolean} [fast]  Skip the per-end nearest-surface scans and the
   *   pick/halo rebuilds, reusing the cached trim offsets. Used during a
   *   continuous spread (the scans are ~90% of this call's cost); a deferred
   *   precise re-trim corrects the small attach drift once the spread settles.
   */
  update(fast = false) {
    const srcCenter = this.fromMesh.position;
    const tgtCenter = this.toMesh.position;

    // Attach each end to the structure-surface point nearest the other end, so the
    // arrow spans the gap between regions and the cone tip lands on real surface
    // mass. Fall back to the center only for an empty geometry.
    //
    // The attach point is cached as a world OFFSET from the region's center
    // (`_trimFrom`/`_trimTo`). Regions only translate as they spread (never rotate
    // or scale), so that offset stays a valid surface point as the region moves;
    // a `fast` update reuses it and skips the scans. The offset still reflects the
    // OLD attach direction, so a precise pass (default) refreshes it.
    let start, end;
    if (fast && this._trimFrom && this._trimTo) {
      start = srcCenter.clone().add(this._trimFrom);
      end = tgtCenter.clone().add(this._trimTo);
    } else {
      start = surfaceToward(this.fromMesh, tgtCenter) || srcCenter.clone();
      end = surfaceToward(this.toMesh, srcCenter) || tgtCenter.clone();
      this._trimFrom = start.clone().sub(srcCenter);
      this._trimTo = end.clone().sub(tgtCenter);
    }

    const mid = start.clone().add(end).multiplyScalar(0.5);
    const dist = start.distanceTo(end);
    // Bow the midpoint outward (away from the brain center at the origin) so the
    // arc arcs over the surface rather than cutting through other regions.
    const outward = mid.clone();
    if (outward.lengthSq() < 1e-6) outward.set(0, 1, 0);
    outward.normalize();
    mid.addScaledVector(outward, dist * BOW_FACTOR);
    // Push the midpoint sideways (perpendicular to the line and the outward bow)
    // so reciprocal pairs separate onto two arcs instead of overlapping. The
    // direction flips with `side`, which is opposite for A->B vs B->A.
    const lineDir = end.clone().sub(start);
    if (lineDir.lengthSq() > 1e-6) {
      lineDir.normalize();
      const lateral = new THREE.Vector3().crossVectors(lineDir, outward);
      if (lateral.lengthSq() > 1e-6) {
        lateral.normalize();
        mid.addScaledVector(lateral, dist * SIDE_FACTOR * this.side);
      }
    }

    // The cone's *apex* sits exactly on the target surface (`end`); its base is
    // one cone-length back along the incoming tangent, and the shaft runs from
    // the source surface to that base. Placing the apex directly (rather than
    // approximating via a curve parameter) guarantees the head touches the
    // surface and never overshoots inside the structure.
    const curve = new THREE.QuadraticBezierCurve3(start.clone(), mid, end.clone());
    // Expose the live source->target arc so external animators (the circuit
    // traveling-pulse, js/circuit-anim.js) can ride a bead along it. Rebuilt here
    // every update(), so sampling it always reflects the current explode layout.
    this.curve = curve;
    const tangentEnd = curve.getTangent(1).normalize(); // points into the target
    const coneBaseEnd = end.clone().addScaledVector(tangentEnd, -CONE_LENGTH);

    // A bidirectional arrow also caps the source end: its apex sits on the source
    // surface and the shaft starts one cone-length in along the outgoing tangent.
    const tangentStart = curve.getTangent(0).normalize(); // points away from start
    const shaftStart = this.coneStart
      ? start.clone().addScaledVector(tangentStart, CONE_LENGTH)
      : start.clone();
    const shaftCurve = new THREE.QuadraticBezierCurve3(shaftStart, mid, coneBaseEnd);
    // Cache the arc so a pure width change (setWidthScale) can rebuild the shaft
    // tube at a new radius without redoing the trim/bow math (the endpoints don't
    // move on a zoom).
    this._shaftCurve = shaftCurve;

    const tubeRadius = TUBE_RADIUS * this._widthScale;
    this.tube.geometry.dispose();
    this.tube.geometry = this.tentative
      ? dashedTubeGeometry(shaftCurve, tubeRadius)
      : new THREE.TubeGeometry(shaftCurve, 24, tubeRadius, 8, false);
    // The cones share a fixed ConeGeometry; their cross-section (x/z, not the
    // axial y) scales with the width so the heads track the shaft. The apex sits
    // on the y axis (x = z = 0), so scaling x/z leaves it exactly on the surface.
    this.cone.scale.set(this._widthScale, 1, this._widthScale);
    if (this.coneStart) this.coneStart.scale.set(this._widthScale, 1, this._widthScale);

    // Pick hull (invisible, fat) + halo tube. Both ride the full start->end arc
    // (`this.curve`) and are only consulted on a click (pick) or while selected
    // (halo), so a `fast` update defers them: it marks the pick stale
    // (ensurePickGeometry rebuilds it before the next raycast) and rebuilds the
    // halo only while it is visible. A precise update rebuilds both now.
    if (fast) {
      this._pickDirty = true;
      if (this.halo.visible) this._rebuildHalo();
      else this._haloDirty = true;
    } else {
      this._rebuildPick();
      this._rebuildHalo();
    }

    // Target cone center is half a length behind the apex so the apex lands on
    // `end`, pointing in the direction of travel.
    this.cone.position.copy(end).addScaledVector(tangentEnd, -CONE_LENGTH / 2);
    this.cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangentEnd);

    if (this.coneStart) {
      // Source cone points back out of the source surface (-tangentStart).
      const axis = tangentStart.clone().negate();
      this.coneStart.position.copy(start).addScaledVector(axis, -CONE_LENGTH / 2);
      this.coneStart.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis);
    }

    // Keep the label anchor on the (live) arc midpoint so the connection label
    // sits on the arrow wherever it is after an explode.
    this.labelAnchor.position.copy(curve.getPoint(0.5));
  }

  /** (Re)build the fat invisible pick hull from the current arc. */
  _rebuildPick() {
    this.pick.geometry.dispose();
    this.pick.geometry = new THREE.TubeGeometry(this.curve, 24, PICK_RADIUS, 6, false);
    this._pickDirty = false;
  }

  /** (Re)build the halo glow tube from the current arc (tracking the width). */
  _rebuildHalo() {
    this.halo.geometry.dispose();
    this.halo.geometry = new THREE.TubeGeometry(
      this.curve, 24, HALO_RADIUS * this._widthScale, 8, false);
    this._haloDirty = false;
  }

  /**
   * Set the width multiplier (1 = the authored radius) and rebuild just the
   * visible width: the shaft tube (from the cached arc) and the cone(s)'
   * cross-section. The endpoints/curve are unchanged (a zoom doesn't move the
   * regions), so this skips the trim raycasts and the bow math entirely, which is
   * what makes a per-zoom-step width refresh cheap. The fat pick hull is left at
   * its constant world radius on purpose, so a thin (zoomed-in) arrow stays an
   * easy click target.
   * @param {number} scale
   * @returns {boolean} whether the width actually changed.
   */
  setWidthScale(scale) {
    if (scale === this._widthScale) return false;
    this._widthScale = scale;
    if (this._shaftCurve) {
      const tubeRadius = TUBE_RADIUS * scale;
      this.tube.geometry.dispose();
      this.tube.geometry = this.tentative
        ? dashedTubeGeometry(this._shaftCurve, tubeRadius)
        : new THREE.TubeGeometry(this._shaftCurve, 24, tubeRadius, 8, false);
    }
    this.cone.scale.set(scale, 1, scale);
    if (this.coneStart) this.coneStart.scale.set(scale, 1, scale);
    // The halo hugs the (now thinner/fatter) tube while visible; a hidden halo is
    // marked stale and rebuilt on demand by setHalo().
    if (this.halo.visible) this._rebuildHalo();
    else this._haloDirty = true;
    return true;
  }

  /**
   * Rebuild the pick hull if a `fast` update left it stale. Call before any
   * raycast that includes the pick mesh (the deferred rebuild is what keeps the
   * spread cheap), so a click still hits the up-to-date hull.
   */
  ensurePickGeometry() {
    if (this._pickDirty) this._rebuildPick();
  }

  /** Toggle the whole arrow's visibility. */
  setVisible(visible) {
    this.group.visible = visible;
  }

  /**
   * Fade the whole arrow, used by the isolate/focus mode to dim pathways that
   * don't touch a selected structure. The tube + cone(s) share `this.material`,
   * so one set covers them all; the invisible pick proxy is untouched. A faded
   * arrow stops writing depth so it doesn't occlude the structures behind it.
   * The material is already `transparent: true` (see the constructor), so we
   * never toggle that flag here, only the opacity + depth-write.
   * @param {number} opacity  the requested opacity; clamped to ARROW_MAX_OPACITY,
   *   so the undimmed "full" state (1) lands at the cap and never fully opaque.
   */
  setOpacity(opacity) {
    const o = Math.min(opacity, ARROW_MAX_OPACITY);
    this.material.opacity = o;
    // Arrows never reach full opacity now, so they never write depth (a
    // translucent overlay blends rather than occluding the arrows behind it).
    this.material.depthWrite = o >= 1;
  }

  /** Show/hide the selection glow around this arrow (picked via click/search). */
  setHalo(on) {
    this.halo.visible = on;
    // A fast spread defers the halo rebuild while it is hidden; refresh it now if
    // it is being shown stale, so a selection made right after a spread glows on
    // the current arc.
    if (on && this._haloDirty) this._rebuildHalo();
  }

  /**
   * Recolour the arrow, for the panel's colour-mode toggle (per-transmitter vs.
   * excitatory/inhibitory sign). The tube + cone(s) share `this.material`; the
   * halo tracks the same hue, lightened toward white like at construction.
   * @param {string} hex  The new arrow colour.
   */
  setColor(hex) {
    const color = new THREE.Color(hex);
    this.material.color.copy(color);
    this.haloMaterial.color.copy(color).lerp(new THREE.Color(0xffffff), 0.4);
  }
}

/**
 * Build one ProjectionArrow per projection record, skipping any whose endpoints
 * are missing (and logging that, so a typo in the data is obvious in eruda).
 * @param {object[]} projections  Projection records from the dataset.
 * @param {Map<string, THREE.Mesh>} meshById  structure id -> its mesh.
 * @returns {ProjectionArrow[]}
 */
export function buildArrows(projections, meshById) {
  const arrows = [];
  for (const proj of projections) {
    const fromMesh = meshById.get(proj.from);
    const toMesh = meshById.get(proj.to);
    if (!fromMesh || !toMesh) {
      console.warn(`Skipping projection ${proj.from} -> ${proj.to}: missing structure`);
      continue;
    }
    const color = proj.color || "#ffffff";
    arrows.push(new ProjectionArrow(fromMesh, toMesh, proj, color));
  }
  return arrows;
}
