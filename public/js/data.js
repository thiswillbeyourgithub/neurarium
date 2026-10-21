// The brain dataset loader's public surface. The loader itself is split into
// stage modules under js/data/ (load.js orchestrates them); this module
// re-exports the names the viewer and tools/tests import, and holds the
// BrainData typedef the JSDoc `import("./data.js").BrainData` refs resolve to.

import { withFetched, rehydrateQuotes } from "./data/quotes.js";
import { affinityWeightOf, toneWeightOf, toneBySystem } from "./data/tone.js";
import { indexDrugsByTarget } from "./data/drug-index.js";
import { derivedUrl, loadSearchNames } from "./data/fetch.js";
import { loadBrainData } from "./data/load.js";

export {
  withFetched,
  rehydrateQuotes,
  affinityWeightOf,
  toneWeightOf,
  toneBySystem,
  indexDrugsByTarget,
  derivedUrl,
  loadSearchNames,
  loadBrainData,
};

/**
 * @typedef {Object} BrainData
 * @property {object[]} structures  Region records (from structures.jsonl), each
 *   augmented with a resolved `shape` payload from its data/shapes/<id>.json file.
 *   `name`/`base_name` are localized to plain strings (the full hemisphere name
 *   and the side-stripped legend label).
 * @property {object[]} projections Directed pathway records (from projections.jsonl),
 *   each augmented with a resolved `color` (from the kind->colour meta map) plus a
 *   `sign` (excitatory/inhibitory/modulatory) and its `signColor` for the coarse
 *   colour mode; its `label`/`description`/`neurotransmitter` are localized to
 *   plain strings.
 * @property {object[]} circuits    Named circuit records (from circuits.jsonl):
 *   `{id, name, structures:[structure ids]}` (localized `name`), plus an optional
 *   localized `description` + `sources`/`provenance`. The arrows belonging to a
 *   circuit are derived in the viewer (both endpoints among `structures`).
 * @property {object[]} projectionGroups  Projection-group records (from
 *   projection_groups.jsonl): one per legend pathway row, in both colour modes
 *   (`mode:"kind"|"sign"`, `key` the kind/sign). Each has a localized `name` +
 *   `description`, `sources`/`provenance`, optional `wikipedia`. Member pathways
 *   are derived in the viewer (the projections whose kind/sign matches `key`).
 * @property {Map<string,object>} projectionGroupsByKey  `${mode}:${key}` -> the
 *   projection-group record, so a legend row resolves its data by its grouping.
 * @property {object[]} receptors  Neurotransmitter receptor records (from
 *   receptors.jsonl). Each is augmented with localized `neurotransmitter` /
 *   `description`, a resolved `familyLabel` / `classLabel` / `signLabel` /
 *   `synapticLabel` and `signColor`, the concrete `structureIds` its `locations`
 *   bases expand to (every structure when `ubiquitous`), the side-stripped
 *   `locationNames`, and a `focusable` flag (false for the inert "stub" receptors).
 *   Its raw `classification` object passes through: one graded sub-claim per
 *   attribute (`family` / `receptor_class` / `sign` / `synaptic`), each with its own
 *   `grade` (+ optional `sources`), shown as that fact row's own provenance pill so
 *   an unsourced attribute reads honestly instead of borrowing a neighbour's grade.
 * @property {object[]} targets  The merged "Receptors & targets" browse list: one
 *   normalized, focusable entry per thing a drug acts on. Each carries `id`,
 *   `kind` ("receptor" or a non-receptor type: transporter / enzyme / ion_channel /
 *   vesicle_protein / receptor_group), `name`, `system` (grouping family, or null),
 *   `swatchColor`, `structureIds`, `focusable` + `keywords`. A "receptor" entry
 *   points back at its receptor record (`receptor`); a non-receptor one adds
 *   `typeLabel` / `systemLabel` / `wikipedia` / `locationNames` (+ the parallel
 *   `locationBases` base ids, so each panel region row can jump to its structure).
 * @property {Map<string, object[]>} targetsByStructure  The reverse expression index:
 *   region base id -> `{target, info, ubiquitous}` for every target expressed there,
 *   `info` being that region's own graded expression node (the same one the receptor
 *   panel's "Regional distribution" row shows). Lets a structure panel answer "what sits here?".
 * @property {object[]} drugs  Drug records (from drugs.jsonl, sourced from Stahl's
 *   Prescriber's Guide). Each is augmented with localized `description` / `nbn`,
 *   `categoryLabels` (+ primary `category`), and resolved `bindings` (each binding
 *   carrying `targetName`, `actionLabel`, net `effect` + `effectColor`/`effectLabel`,
 *   localized `note`, an `affinityWeight` (0.35..1, Ki-derived engagement) + signed
 *   `toneSign`, and the concrete `structureIds` it lights), the union
 *   `structureIds` the focus dims to, `flowSystems` (kind -> {direction, weight},
 *   the signed affinity-weighted per-system flow tone), a `focusable` flag and search `keywords`,
 *   plus a `structureImage` (the vendored molecular-structure SVG path, or null).
 * @property {object[]} enzymes  The Enzymes browse list: one entry per metabolic
 *   isoform some drug actually touches, `{id, label, wikipedia, rows, metabolites,
 *   keywords}` where `rows` are its `{drug, enzyme}` role pairs and `metabolites` its
 *   `{drug, metabolite, formedBy}` triples (the active metabolites it forms).
 *   Pharmacokinetics, so an entry has no anatomy and never lights the scene.
 * @property {object[]} effects  The Effects browse list (BETA): one entry per
 *   receptor_effect some target carries, `{id, label, name, owners, drugs, keywords}`,
 *   read from the build-time `derived/effects.json` (`readEffectIndex`,
 *   js/receptor-effects.js); `drugs` is derived, never stored. Empty when that fails to load.
 * @property {Map<string, object[]>} possibleEffectsByDrug  drug id -> its possible
 *   effects `{effect, label, via}` from the same file (the drug panel's derived section).
 * @property {Map<string, {drug: object, enzyme: object}[]>} drugsByEnzyme  Reverse
 *   index: enzyme id -> the drugs with a role at it, each paired with that role row.
 * @property {(drug: object) => {affects: object[], affectedBy: object[]}} pkInteractionsOf
 *   The drug -> drug pharmacokinetic edges implied by those roles (an inhibitor or
 *   inducer of an enzyme meets its substrates). Derived on demand, never authored;
 *   one entry per (other drug, direction), naming every enzyme the pair shares.
 * @property {Map<string, {drug: object, binding: object}[]>} drugsByTarget
 *   Reverse index: a target id (a receptor id or a drug_targets key, matching each
 *   `targets` entry's id) -> the drugs that act on it, each paired with its resolved
 *   binding (its net-effect colour + action), deduped to one row per (drug, target).
 *   Lets a receptor / target panel list its interacting drugs grouped by category.
 * @property {Map<string, {drug: object, binding: object}[]>} prodrugsByTarget
 *   Same shape, for a prodrug's borrowed bindings (`binding.viaMetabolite` set):
 *   listed in a target panel "via" their metabolite drug, never counted.
 * @property {object[]} addons  Addon records (from addons.jsonl): sourced
 *   annotations that carry their own insertion point, each `{id, ownerKind, owner,
 *   slot, display, tone, glyph, title, text, sources, provenance}` plus the resolved
 *   `ownerName` + `focus` ({nav, arg}) of the node it annotates. The claim is in
 *   `text`; `slot` says which panel hook draws it (see meta.addonSlots).
 * @property {Map<string, object[]>} addonsBySlot  Reverse index:
 *   `${ownerKind}:${owner}:${slot}` -> the addons a panel should splice in there.
 * @property {Map<string, object>} byId  structure id -> structure record.
 * @property {{projectionColors: Object<string,string>,
 *   groupLabels: Object<string,string>,
 *   kindLabels: Object<string,string>,
 *   systemFlowKinds: Object<string,string>,
 *   signColors: Object<string,string>,
 *   signLabels: Object<string,string>}} meta  Presentation maps emitted by the
 *   generator (kind->arrow colour, group->legend heading, kind->display label,
 *   transmitter-system->flow-overlay projection kind, and the excit/inhib sign
 *   colour + heading for the colour-mode toggle), so the dataset is self-describing
 *   rather than relying on hardcoded values in the viewer.
 *   `groupLabels`/`kindLabels`/`signLabels` are localized to plain strings.
 */
