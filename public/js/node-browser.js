// Data browser: one flat, searchable list of every graded knowledge node.
//
// The Sources & provenance popup answers "how well sourced is the dataset?" with
// bars and one example node per kind; this section answers the next question the
// bars provoke, "which ones?", by listing every node behind them. Same nodes, same
// grades, same navigation callbacks: only the presentation differs, so the two must
// never drift apart (collectNodes below is the enumeration, kinds.js exampleRow
// picks the Sources popup's representative from these very rows).
//
// It doubles as a sourcing workbench, which is why the default sort is weakest-grade
// first: the unsourced claims surface on top rather than being buried under the
// verified majority.
//
// No three.js here: rows navigate through the `nav` callbacks the boot wiring
// (js/boot/views.js) hands in, so this module never touches the scene.
//
// Split: node-browser/collect.js (the pure enumeration, collectNodes) and
// node-browser/view.js (the UI, createNodeBrowser); this module re-exports both.

import { collectNodes } from "./node-browser/collect.js";
import { createNodeBrowser } from "./node-browser/view.js";

export { collectNodes, createNodeBrowser };
