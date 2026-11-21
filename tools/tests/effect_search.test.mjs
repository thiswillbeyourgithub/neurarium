// The effect search keywords (public/js/data/effects.js effectKeywords, fed by the build's
// meta.receptor_effect_search): a search for a word no label holds still finds the effect,
// and an effect's opposite is listed alongside it.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { effectKeywords } from "../../public/js/data/effects.js";
import { rankMatch } from "../../public/js/search-rank.js";
import { foldText } from "../../public/js/search/query.js";

const meta = JSON.parse(readFileSync(new URL("../../public/data/meta.json", import.meta.url)));
const labels = meta.receptor_effect_labels;

/** Effect ids a query finds, as the search box ranks them. */
const found = (query) => Object.keys(labels).filter((id) => rankMatch(
  foldText(labels[id]), foldText(effectKeywords(id, meta)), foldText(query)) !== null);

test("'saliv' finds dry mouth and hypersalivation", () => {
  const hits = found("saliv");
  assert.ok(hits.includes("dry_mouth"), hits);
  assert.ok(hits.includes("hypersalivation"), hits);
});

test("an effect's opposite is listed with it", () => {
  assert.ok(found("mydriasis").includes("miosis"));
  assert.ok(found("miosis").includes("mydriasis"));
});

test("an effect with no extra keywords keeps its id words", () => {
  assert.equal(effectKeywords("ataxia", {}), "ataxia");
});
