// The seam between the Drugs list and the drug map: the list's per-section "map" links
// call openDrugMap(patch) without importing the popup (which is built later in boot,
// js/main.js); the map registers itself here once it exists.

let opener = null;

/** Called by js/drug-map/view.js with the function that opens the map on a view. */
export function setDrugMapOpener(fn) {
  opener = fn;
}

/** Open the drug map pre-filtered by `patch` (e.g. `{cats: new Set(["antipsychotic_atypical"])}`). */
export function openDrugMap(patch) {
  opener?.(patch);
}
