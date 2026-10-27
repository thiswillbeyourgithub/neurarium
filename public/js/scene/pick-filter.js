// Which raycast hits a pick may land on. Kept free of three.js (it only reads mesh
// fields) so node tests can import it (tools/tests/pick_filter.test.mjs).

/** A structure a click / hover can land on: shown, and not faded to glass by "See
 *  inside" (js/scene/see-inside.js writes `userData.insideFade`), so a deep nucleus is
 *  picked through the near cortex in front of it. */
export const isPickableMesh = (mesh) =>
  mesh.visible && (mesh.userData.insideFade ?? 1) > 0.5;

/**
 * The structure a hover names, from the raycast hits sorted near to far. A focused
 * region the ray passes through wins even when a non-focused one sits nearer, so the
 * thing you focused names *itself* rather than whatever occludes it (an isolated deep
 * nucleus behind the dimmed cortex); otherwise the nearest pickable structure. Both
 * passes skip see-inside's glass shells, so the hover names the solid structure under
 * the cursor, the same one a click would select.
 * @param {{object: object}[]} hits
 * @param {Set<object>|null|undefined} focusMeshes
 * @returns {object|null} the mesh, or null
 */
export function hoverMesh(hits, focusMeshes) {
  if (focusMeshes && focusMeshes.size) {
    for (const hit of hits) {
      if (isPickableMesh(hit.object) && focusMeshes.has(hit.object)) return hit.object;
    }
  }
  for (const hit of hits) if (isPickableMesh(hit.object)) return hit.object;
  return null;
}
