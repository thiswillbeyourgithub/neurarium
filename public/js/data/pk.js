// Pharmacokinetics (no anatomy, never lights the scene): a drug's enzyme roles +
// CPIC rows, the Enzymes browse list and the derived drug -> drug PK edges.

import { groupBy } from "../util.js";
import { localize } from "./localize.js";
import { strongestGrade, mapSources, mapUncertainty, mapClaims } from "./sources.js";

/** The metabolizer-variability normalizer, closed over meta's phenotype vocab. */
export function makeVariabilityEntry(metaRecord) {
  /**
   * Normalize one enzyme's metabolizer-status profile (PharmFreq, corpus #13).
   *
   * Reshapes `{group: {phenotype: frequency}}` into the render order the emitted
   * vocabularies define, so the panel iterates data rather than a hardcoded list of
   * phenotype letters. Each group's row is the frequencies **in phenotype order**
   * (slowest clearance first), which is what makes the stacked bars comparable down
   * the column: the same colour sits at the same end of every bar.
   *
   * Returns null when the isoform has no published profile, which the panel shows as
   * a gap rather than inventing a flat "does not vary".
   */
  const variabilityEntry = (variability) => {
    if (!variability || !variability.profile) return null;
    const order = Object.keys(metaRecord.metabolizer_phenotypes || {});
    const groups = [];
    for (const key of Object.keys(metaRecord.metabolizer_groups || {})) {
      const row = variability.profile[key];
      if (!row) continue;
      groups.push({
        key,
        label: localize(metaRecord.metabolizer_groups[key]) || key,
        cells: order.filter((p) => row[p] != null).map((p) => {
          const def = metaRecord.metabolizer_phenotypes[p] || {};
          return {
            phenotype: p,
            freq: row[p],
            label: def.label ? localize(def.label) : p,
            note: def.note ? localize(def.note) : "",
          };
        }),
      });
    }
    if (!groups.length) return null;
    return {
      gene: variability.gene,
      groups,
      provenance: strongestGrade(variability.sources),
      sources: mapSources(variability.sources),
    };
  };
  return variabilityEntry;
}

/** Resolve one drug's enzyme rows, CPIC rows and auto-modulation in place. */
export function resolveDrugMetabolism(d, v, metaRecord, variabilityEntry) {
  const { enzymeDefs, enzymeRoles, enzymeStrengths } = v;
  // Metabolism: which enzymes handle this drug, or are inhibited/induced by it.
  // Pharmacokinetics, so unlike a binding it lights nothing in the 3D scene; it
  // feeds the panel's Metabolism list, the Enzymes browse section, and the derived
  // drug -> drug interaction edges below. Labels come from meta.enzymes* so no
  // isoform name is hardcoded here.
  d.enzymes = (d.enzymes || []).map((e) => {
    const def = enzymeDefs[e.enzyme] || {};
    const role = enzymeRoles[e.role] || {};
    return {
      ...e,
      label: def.label || e.enzyme,
      wikipedia: def.wikipedia || null,
      roleLabel: role.label ? localize(role.label) : e.role,
      // The drug panel's group heading over this role's rows ("Substrate of").
      roleHeading: role.heading ? localize(role.heading) : (role.label ? localize(role.label) : e.role),
      // What the drug does to that enzyme's throughput: +1 inhibits (a substrate
      // co-prescribed with it accumulates), -1 induces (it is cleared faster), 0
      // for a substrate, which sets no tone of its own.
      direction: role.direction || 0,
      strengthLabel: enzymeStrengths[e.strength]
        ? localize(enzymeStrengths[e.strength]) : null,
        sources: mapSources(e.sources),
      provenance: strongestGrade(e.sources),
      // Another corpus denies this row (quotes/contradictions.py): the pill goes
      // orange and its tooltip leads with the denial, then shows this row's own
      // quote. Empty for all but the handful of contradicted rows.
      uncertainty: mapUncertainty(e.uncertainty),
      // How much of the clearing this isoform does is its own graded claim.
      claims: mapClaims(e.claims),
    };
  });
  // CPIC's prescribing guidance for this drug (corpus #15), one node per (gene,
  // phenotype) row. The one place this dataset carries a clinical action, and the
  // only one that needs a *second* dataset to be read at all: each row is paired
  // here with how common that phenotype is per population group (corpus #13, on the
  // enzyme), because "poor metabolizer" means nothing to a reader until they know
  // whether that is 1 patient in 20 or 1 in 1000. A gene with no profile cannot
  // reach this point (generate_data refuses it), so `groups` is always populated.
  d.pgx = (d.pgx || []).map((block) => {
    const variability = variabilityEntry((enzymeDefs[block.enzyme] || {}).variability);
    const freqs = new Map((variability ? variability.groups : [])
      .map((g) => [g.key, new Map(g.cells.map((c) => [c.phenotype, c]))]));
    return {
      ...block,
      label: (enzymeDefs[block.enzyme] || {}).label || block.gene,
      population: block.population ? localize(block.population) : null,
      // The population groups the frequency table offers, so the picker lists what
      // can actually be answered rather than a fixed continent list.
      groups: (variability ? variability.groups : []).map((g) => ({
        key: g.key, label: g.label,
      })),
      rows: (block.rows || []).map((row) => {
        const def = (metaRecord.metabolizer_phenotypes || {})[row.phenotype] || {};
        return {
          ...row,
          label: def.label ? localize(def.label) : row.phenotype,
          note: def.note ? localize(def.note) : "",
          // group key -> {freq, label}: what the panel reads once the user picks a
          // group. A phenotype the gene has no row for is absent here rather than
          // zero, because nobody measured it at 0%.
          freqByGroup: new Map([...freqs].map(([key, cells]) =>
            [key, cells.get(row.phenotype) || null])),
          sources: mapSources(row.sources),
          provenance: strongestGrade(row.sources),
        };
      }),
    };
  });
  // Derived, never stored (like pkInteractionsOf below): the isoforms this drug
  // is BOTH a substrate of and a modulator of, so it changes its own clearance
  // (autoinhibition, or autoinduction for an inducer) and its dose/level relation
  // is not a straight line. No single enzyme row above can say this: each states
  // one role, and it is their coincidence on one isoform that is the claim. An
  // inference off graded rows, so the panel words it conditionally and shows no
  // pill of its own (the rows it reads carry theirs).
  d.autoModulation = d.enzymes.filter((e) => e.direction !== 0
    && d.enzymes.some((o) => o.enzyme === e.enzyme && o.role === "substrate"));
}

/** The Enzymes browse list, its reverse index and pkInteractionsOf. */
export function indexEnzymes({ drugs, metaRecord, v }) {
  const { enzymeDefs } = v;
  const variabilityEntry = makeVariabilityEntry(metaRecord);
  // The Enzymes browse list + its reverse index, the metabolism mirror of `targets` /
  // `drugsByTarget` above. One entry per isoform any drug actually touches (an isoform
  // in meta.enzymes that nothing references would be an empty panel), each carrying
  // the drugs split by role so the panel can head them "Substrates / Inhibitors /
  // Inducers" without re-scanning the corpus.
  const drugsByEnzyme = groupBy(
    drugs.flatMap((d) => d.enzymes.map((e) => ({ drug: d, enzyme: e }))),
    (r) => r.enzyme.enzyme);
  // The same index for the OTHER metabolism relation: which active metabolites this
  // isoform forms. Kept apart from the role rows because it is a different claim (the
  // enzyme is the maker, not the handler) and the enzyme panel heads it separately.
  const metabolitesByEnzyme = groupBy(
    drugs.flatMap((d) => d.metabolites.flatMap((m) => (m.formedBy || [])
      .map((f) => ({ drug: d, metabolite: m, formedBy: f })))),
    (r) => r.formedBy.enzyme);
  const enzymes = [...new Set([...drugsByEnzyme.keys(), ...metabolitesByEnzyme.keys()])]
    .map((id) => ({
      id,
      label: (enzymeDefs[id] || {}).label || id,
      wikipedia: (enzymeDefs[id] || {}).wikipedia || null,
      rows: drugsByEnzyme.get(id) || [],
      metabolites: metabolitesByEnzyme.get(id) || [],
      // How fast people clear a drug through this isoform, per population group
      // (PharmFreq, corpus #13). One graded node for the whole profile, like an
      // expression density profile; absent for an isoform the source does not cover,
      // which the panel renders as a gap rather than as "does not vary".
      variability: variabilityEntry((enzymeDefs[id] || {}).variability),
      keywords: [id, (enzymeDefs[id] || {}).label || id].join(" ").toLowerCase(),
    }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));

  /**
   * The pharmacokinetic interactions implied by the enzyme nodes, for one drug.
   *
   * Derived, never authored, exactly like `flowSystems` and circuit membership: an
   * inhibitor (or inducer) of an enzyme meets every substrate of that same enzyme.
   * Recomputing it here means it can never drift from the nodes it comes from.
   *
   * `direction` is what happens to the OTHER drug's blood level: +1 when this drug
   * inhibits an enzyme the other is a substrate of (the other accumulates), -1 when
   * it induces one (the other is cleared faster). A drug that is only a substrate
   * has no effect of its own, but is still *affected* by others, so both sides are
   * returned. This is a flag to check, never a contraindication: the panel says so.
   * @param {object} drug
   * @returns {{affects: object[], affectedBy: object[]}}
   */
  function pkInteractionsOf(drug) {
    // Keyed by (other drug, direction), not by enzyme: two drugs often meet at more
    // than one isoform (fluoxetine inhibits both CYP2D6 and CYP3A4, aripiprazole is
    // a substrate of both), and listing that pair twice reads as a rendering bug.
    // One row per pair, naming every enzyme they share.
    const merge = (map, other, enzymeRow, direction) => {
      if (other.id === drug.id) return;
      const key = `${other.id}:${direction}`;
      const hit = map.get(key);
      if (hit) {
        if (!hit.enzymes.some((x) => x.enzyme === enzymeRow.enzyme)) {
          hit.enzymes.push(enzymeRow);
        }
        return;
      }
      map.set(key, { drug: other, enzymes: [enzymeRow], direction, key });
    };
    const affects = new Map();
    const affectedBy = new Map();
    for (const e of drug.enzymes) {
      const rows = drugsByEnzyme.get(e.enzyme) || [];
      if (e.direction !== 0) {
        // This drug modulates the enzyme: it moves every substrate of it.
        for (const r of rows) {
          if (r.enzyme.role === "substrate") merge(affects, r.drug, e, e.direction);
        }
      }
      if (e.role === "substrate") {
        // This drug rides the enzyme: every modulator of it moves this drug.
        for (const r of rows) {
          if (r.enzyme.direction !== 0) {
            merge(affectedBy, r.drug, r.enzyme, r.enzyme.direction);
          }
        }
      }
    }
    return { affects: [...affects.values()], affectedBy: [...affectedBy.values()] };
  }
  return { enzymes, drugsByEnzyme, pkInteractionsOf };
}
