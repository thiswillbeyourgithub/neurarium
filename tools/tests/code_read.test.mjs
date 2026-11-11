// allCodeRead (public/js/panel/format.js): a verified pill names the judge only when
// one ran, so a parser-copied quote (AGNP table row, PDSP row) must not claim one.
import { test } from "node:test";
import assert from "node:assert/strict";

globalThis.window = { __I18N__: { t: (k) => k, lang: "en" } };
const { allCodeRead } = await import("../../public/js/panel/format.js");

const pipelines = {
  page_code: ["page", "extract_code", "gate", "neurarium"],
  machine_judged: ["raw_data", "extract_code", "gate", "judge_llm", "neurarium"],
  page_llm_judged: ["page", "extract_llm", "gate", "judge_llm", "neurarium"],
};

test("every source code-copied and unjudged", () => {
  assert.equal(allCodeRead([{ pipeline: "page_code" }], pipelines), true);
});

test("one judged or LLM-picked source keeps the judge wording", () => {
  assert.equal(allCodeRead([{ pipeline: "page_code" }, { pipeline: "page_llm_judged" }], pipelines), false);
  assert.equal(allCodeRead([{ pipeline: "machine_judged" }], pipelines), false);
});

test("unknown pipeline or no source is not code-read", () => {
  assert.equal(allCodeRead([{ pipeline: "nope" }], pipelines), false);
  assert.equal(allCodeRead([{}], pipelines), false);
  assert.equal(allCodeRead([], pipelines), false);
  assert.equal(allCodeRead(null, pipelines), false);
});
