// Draw-order tier for the additive decorations that sit on a structure's surface
// (the gem-dot clouds, the wash shells, the selection halos).
//
// Why this exists: the structure materials are `transparent: true` at `opacity: 1`
// (so the transparency slider can fade them), which puts every region in three.js's
// transparent pass. That pass is sorted back-to-front by each object's **geometry
// bounding-sphere centre**, not by the object's own position, so a decoration whose
// geometry is not its parent's own gets a *different* sort depth: a gem-dot cloud is
// a sparse sample of the surface, so its centre sits off the mesh's centre, and past
// some camera azimuth it sorts BEFORE the region it decorates. The region is then
// painted straight over its own glow at full opacity and the dots vanish, abruptly,
// at whatever angle flips the comparison.
//
// Pinning the decorations one tier above the structures makes the layering explicit
// instead of a by-product of that sort (three compares `renderOrder` before depth,
// so they always draw last). Occlusion is unaffected: the structures still write
// depth and the decorations still depth-test, so a dot on the far side of a region
// stays hidden.
//
// Structures (and everything else) stay at the default 0.
export const DECOR_RENDER_ORDER = 1;
