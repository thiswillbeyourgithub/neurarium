// Curved arrows representing directed neuron projections between structures.
//
// Each arrow is a thin curved tube (a quadratic Bezier bowing outward from the
// brain center, so arrows don't hide inside the blobs) capped with a cone head
// at the target end. The two ends are trimmed to the structure *surfaces* (not
// their centers) by raycasting from one center toward the other, so the shaft
// spans the gap between regions and the cone tip lands on the target surface
// where it stays visible instead of buried inside the blob. Because structures
// move when the explode slider changes, arrows expose an update() that re-fits
// their geometry to the *current* mesh positions each time the layout changes.

import * as THREE from "three";

// Reused for the per-end surface trimming (see surfaceToward). One instance is
// plenty since arrows are updated sequentially.
const _ray = new THREE.Raycaster();

const _sphere = new THREE.Sphere();

/**
 * Point on `mesh`'s surface that faces `fromPoint` (the other arrow end): the
 * first face hit when shooting from just outside the mesh, on the side toward
 * `fromPoint`, back toward its center. Used to trim an arrow end to the visible
 * surface instead of its hidden center.
 *
 * The ray starts *outside* the mesh's bounding sphere on purpose: at low explode
 * the deep nuclei overlap, so the other structure's center is often inside this
 * mesh. A ray cast from there would stay inside and never cross a face, leaving
 * the tip stuck at the center. Starting outside the bounding sphere and shooting
 * inward always crosses the near face first. Returns null only for a degenerate
 * (coincident) pair so the caller can fall back to the center.
 * @param {THREE.Mesh} mesh
 * @param {THREE.Vector3} fromPoint  World point to look from (the other end).
 * @returns {THREE.Vector3|null}
 */
function surfaceToward(mesh, fromPoint) {
  // Positions may have just been changed by the explode logic; make sure the
  // world matrix the raycaster uses is current before intersecting.
  mesh.updateMatrixWorld();
  const geo = mesh.geometry;
  if (!geo.boundingSphere) geo.computeBoundingSphere();
  _sphere.copy(geo.boundingSphere).applyMatrix4(mesh.matrixWorld);

  const dir = fromPoint.clone().sub(_sphere.center); // center -> other end
  const len = dir.length();
  if (len < 1e-6) return null;
  dir.divideScalar(len);
  const reach = _sphere.radius + 0.05; // just clear of the surface
  // Start outside on the far-facing side, shoot back through the center; the
  // first hit is the surface looking at `fromPoint`.
  const origin = _sphere.center.clone().addScaledVector(dir, reach);
  _ray.set(origin, dir.clone().negate());
  _ray.far = 2 * reach;
  const hits = _ray.intersectObject(mesh, false);
  _ray.far = Infinity;
  return hits.length ? hits[0].point.clone() : null;
}

// Arrow colour per projection comes from the data: each projection record
// carries a resolved `color` (data.js fills it from the generator's kind->colour
// meta map). The viewer reads `projection.color` everywhere, so the palette has
// a single source (tools/generate_data.py) and the dataset is self-describing.

const TUBE_RADIUS = 0.1;
const CONE_LENGTH = 0.4;
const CONE_RADIUS = 0.22;
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
    // Arrows are not transparency-controlled with the structures: they should
    // stay readable, so they use a flat, lit-independent material.
    this.material = new THREE.MeshBasicMaterial({ color });

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

    this.update();
  }

  /**
   * Re-fit the tube and cone to the current source/target mesh positions.
   * Call this after the structures have been (re)positioned for a new explode
   * amount. Cheap enough to also call every frame if needed.
   */
  update() {
    const srcCenter = this.fromMesh.position;
    const tgtCenter = this.toMesh.position;

    // Trim each end from the (hidden) center to the structure surface that faces
    // the other end, so the arrow spans the gap between regions and the cone tip
    // lands on the target surface. Fall back to the center if a ray misses.
    const start = surfaceToward(this.fromMesh, tgtCenter) || srcCenter.clone();
    const end = surfaceToward(this.toMesh, srcCenter) || tgtCenter.clone();

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
    const tangentEnd = curve.getTangent(1).normalize(); // points into the target
    const coneBaseEnd = end.clone().addScaledVector(tangentEnd, -CONE_LENGTH);

    // A bidirectional arrow also caps the source end: its apex sits on the source
    // surface and the shaft starts one cone-length in along the outgoing tangent.
    const tangentStart = curve.getTangent(0).normalize(); // points away from start
    const shaftStart = this.coneStart
      ? start.clone().addScaledVector(tangentStart, CONE_LENGTH)
      : start.clone();
    const shaftCurve = new THREE.QuadraticBezierCurve3(shaftStart, mid, coneBaseEnd);

    this.tube.geometry.dispose();
    this.tube.geometry = this.tentative
      ? dashedTubeGeometry(shaftCurve, TUBE_RADIUS)
      : new THREE.TubeGeometry(shaftCurve, 24, TUBE_RADIUS, 8, false);

    // Pick proxy spans the whole arc (start -> end) at the fat PICK_RADIUS so the
    // entire arrow, heads included, is comfortably clickable.
    this.pick.geometry.dispose();
    this.pick.geometry = new THREE.TubeGeometry(curve, 24, PICK_RADIUS, 6, false);

    // Halo tube tracks the same arc one notch fatter than the visible tube, so
    // the glow hugs the whole arrow as it explodes.
    this.halo.geometry.dispose();
    this.halo.geometry = new THREE.TubeGeometry(curve, 24, HALO_RADIUS, 8, false);

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

  /** Toggle the whole arrow's visibility. */
  setVisible(visible) {
    this.group.visible = visible;
  }

  /**
   * Fade the whole arrow, used by the isolate/focus mode to dim pathways that
   * don't touch a selected structure. The tube + cone(s) share `this.material`,
   * so one set covers them all; the invisible pick proxy is untouched. A faded
   * arrow stops writing depth so it doesn't occlude the structures behind it.
   * @param {number} opacity  1 = fully opaque (the default), lower = dimmer.
   */
  setOpacity(opacity) {
    this.material.transparent = opacity < 1;
    this.material.opacity = opacity;
    this.material.depthWrite = opacity >= 1;
  }

  /** Show/hide the selection glow around this arrow (picked via click/search). */
  setHalo(on) {
    this.halo.visible = on;
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
