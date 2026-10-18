// Anatomy stages: hemisphere mirroring, projection / structure / circuit / group
// display fields, shape files, and the structure indexes later stages key by.

import { mirrorId, stripSide } from "../util.js";
import { fetchOrThrow } from "./fetch.js";
import { localize } from "./localize.js";
import { strongestGrade } from "../grades.js";

/** Reflect every `mirror: true` projection to the other hemisphere, in place. */
export function mirrorProjections(projections) {
  // A symmetric pathway is stored once carrying `mirror: true` (the emitted file
  // authors only the right-hemisphere record, avoiding a duplicate row per
  // pathway; see generate_data.py _projection_records). Reflect each such record
  // to the other hemisphere here (flip `_R` <-> `_L` on both endpoints) so the
  // rest of the viewer sees the full bilateral connectome as if both rows had
  // been emitted. A midline endpoint is left unchanged, so a half-midline pathway
  // mirrors only its lateralized end. Done before any downstream use (colours,
  // circuit membership, legends), so every consumer sees both hemispheres.
  for (const p of projections.slice()) {
    if (!p.mirror) continue;
    delete p.mirror;
    projections.push({ ...p, from: mirrorId(p.from), to: mirrorId(p.to) });
  }
}

/**
 * Resolve projection colours + every anatomy display string; returns the
 * projection groups indexed by `${mode}:${key}`.
 */
export function resolveAnatomy({ projections, structures, circuits, projectionGroups, v }) {
  const { projectionColors, kindSigns, signColors } = v;
  // Resolve each projection's colours from its kind (kept as the raw key, since it
  // indexes the colour/label maps): `color` is the per-transmitter colour (default
  // mode), `sign`/`signColor` the coarse excitatory/inhibitory view the colour
  // toggle switches to. Localize the display fields so the viewer reads plain
  // strings. `provenance` is the strongest grade among its `sources`, which colours
  // the summary source pill shown on a structure panel's connection row (the same
  // pill the binding rows use), so a pathway's source shows on both endpoints'
  // panels (null when it has no source).
  for (const p of projections) {
    p.color = projectionColors[p.kind] || "#ffffff";
    p.sign = kindSigns[p.kind] || "modulatory";
    p.signColor = signColors[p.sign] || "#ffffff";
    p.label = localize(p.label);
    p.description = localize(p.description);
    p.neurotransmitter = localize(p.neurotransmitter);
    p.provenance = strongestGrade(p.sources);
    // Reasons the quote does not actually state THIS pathway (the orange "uncertain"
    // badge a blanket sweep sentence earns, derived in quotes/uncertainty.py). Same
    // bullet shape a drug binding carries; always an array so the panel can test
    // `.length` without a guard. The bullets' sources stay raw, like `p.sources`, and
    // so do those of its per-claim split (`p.claims`, transmitter + sign): every
    // pathway source is read raw here, so normalizing one of them would be the odd
    // one out.
    p.uncertainty = p.uncertainty || [];
  }

  // Localize the structure + circuit display strings (the geometry/ids stay as
  // language-neutral keys).
  for (const s of structures) {
    s.name = localize(s.name);
    s.base_name = localize(s.base_name);
    // Hot-linked Wikipedia hero image for the structure panel (null when none was
    // fetched), mirroring a drug's molecule image. Not localized (raster art).
    s.structureImage = s.structure_image || null;
    // Further gif/svg from the structure's EN+FR articles, revealed by the panel's
    // "show more" (always an array, so the viewer can test .length).
    s.structureImageGallery = s.structure_image_gallery || [];
  }
  for (const c of circuits) {
    c.name = localize(c.name);
    // A circuit carries a baked description (offline fallback) plus an optional
    // Wikipedia link; its panel live-fetches the current lead like a structure. The
    // raw `wikipedia` field passes through untouched for appendReference to consume.
    c.description = c.description ? localize(c.description) : "";
    c.provenance = strongestGrade(c.sources);
    // Hot-linked Wikipedia illustration (hero + gallery), same shape as a structure's,
    // so the circuit panel reuses appendWikiImages.
    c.structureImage = c.structure_image || null;
    c.structureImageGallery = c.structure_image_gallery || [];
  }

  // Projection groups: the legend's per-pathway rows promoted to a sourced data
  // structure (one record per group, in both colour modes; see
  // generate_data.py PROJECTION_GROUPS). Localize the display strings and resolve
  // the source grade, exactly like a projection / circuit. The member pathways are
  // derived in the viewer (the projections whose kind/sign matches), so they are
  // not stored here. Indexed by `${mode}:${key}` so a legend row can find its
  // record by the grouping it stands for.
  const projectionGroupsByKey = new Map();
  for (const g of projectionGroups) {
    g.name = localize(g.name);
    g.description = g.description ? localize(g.description) : "";
    g.provenance = strongestGrade(g.sources);
    projectionGroupsByKey.set(`${g.mode}:${g.key}`, g);
  }
  return projectionGroupsByKey;
}

/** Fetch every shape file (deduplicated by url) onto its structure. */
export async function loadShapes(structures, onProgress) {
  // Fetch all shape files in parallel and attach them to their structure. Report
  // progress per file (these are the bulk of the load, especially on a slow link)
  // so the startup loading bar can advance.
  //
  // Deduplicated by url: a symmetric structure's two hemispheres share ONE shape
  // file (the right-side form, which `structure.mirror` flips for the left), so
  // 46 structures resolve to 26 files. Fetching per structure meant 20 redundant
  // requests, which on a phone is 20 extra round trips, and handed the mesher two
  // distinct-but-identical specs to build twice (see js/main.js `sdfItems`). The
  // parsed spec is then SHARED between the twins, which is safe because nothing
  // downstream mutates it: `buildGeometry` only reads, and the mesh budget's
  // `adjust` returns a copy.
  let loaded = 0;
  const total = structures.length;
  onProgress?.({ stage: "shapes", loaded, total });
  const byUrl = new Map();
  await Promise.all(
    structures.map(async (s) => {
      let shape = byUrl.get(s.shape_file);
      if (!shape) {
        shape = fetchOrThrow(s.shape_file).then((r) => r.json());
        byUrl.set(s.shape_file, shape);
      }
      s.shape = await shape;
      onProgress?.({ stage: "shapes", loaded: (loaded += 1), total });
    }),
  );
}

/**
 * The structure indexes the later stages key by: id -> record, base id -> side-
 * stripped name, and every concrete structure id (a ubiquitous target lights all).
 */
export function indexStructures(structures) {
  const byId = new Map(structures.map((s) => [s.id, s]));
  const baseName = new Map();
  for (const s of structures) baseName.set(stripSide(s.id), s.base_name);
  const allIds = structures.map((s) => s.id);
  return { byId, baseName, allIds };
}
