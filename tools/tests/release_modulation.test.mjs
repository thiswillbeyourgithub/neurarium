// Unit tests for public/js/release-modulation.js: the drug panel's derived release
// changes flip with an antagonist, keep with an agonist, and ignore affinity_only.
// Run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { resolveModulation, activationSign, deriveReleaseChanges, transmitterVars }
  from "../../public/js/release-modulation.js";

const modes = {
  agonism: { actions: ["agonist", "partial_agonist", "pam"] },
  antagonism: { actions: ["antagonist", "inverse_agonist", "nam", "blocker"] },
  inhibition: { actions: ["reuptake_inhibitor"] },
};
const vocab = {
  kinds: { autoreceptor: "Autoreceptor", heteroreceptor: "Heteroreceptor" },
  cells: { gaba_interneuron: "GABA interneurons", presynaptic_terminal: "terminals" },
  transmitters: { dopamine: { label: "dopamine" }, histamine: { label: "histamine" },
                  norepinephrine: { label: "norepinephrine" } },
};
const node = (modulates, effect, structure = null, cell = "gaba_interneuron") => ({
  kind: "heteroreceptor", site: { structure, cell }, modulates,
  effect_of_activation: effect, grade: "verified" });
const nodes = {
  "5ht2c": resolveModulation([node("dopamine", "decrease", "vta"),
                              node("norepinephrine", "decrease")], vocab),
  h3: resolveModulation([{ ...node("histamine", "decrease", null, "presynaptic_terminal"),
                           kind: "autoreceptor" }], vocab),
  d3: resolveModulation([node("dopamine", "decrease", "vta")], vocab),
  a2a: resolveModulation([
    { ...node("norepinephrine", "decrease", null, "cell_body"), kind: "autoreceptor" },
    { ...node("norepinephrine", "decrease", null, "presynaptic_terminal"),
      kind: "autoreceptor" }], vocab),
};
const modsOf = (t) => nodes[t] || [];

test("resolveModulation labels every field", () => {
  const r = nodes["5ht2c"][0];
  assert.deepEqual([r.kindLabel, r.cellLabel, r.transmitterLabel, r.structure, r.effect,
                    r.provenance],
                   ["Heteroreceptor", "GABA interneurons", "dopamine", "vta", "decrease",
                    "verified"]);
});

test("activationSign reads the receptor_effect modes", () => {
  assert.equal(activationSign("partial_agonist", modes), 1);
  assert.equal(activationSign("inverse_agonist", modes), -1);
  assert.equal(activationSign("reuptake_inhibitor", modes), 0);
  assert.equal(activationSign(null, modes), 0);
});

test("an antagonist flips the effect of activation", () => {
  const out = deriveReleaseChanges([{ target: "h3", action: "antagonist" }], modsOf, modes);
  assert.deepEqual(out.map((e) => [e.modulates, e.direction]), [["histamine", "increase"]]);
});

test("an agonist keeps it", () => {
  const out = deriveReleaseChanges([{ target: "5ht2c", action: "agonist" }], modsOf, modes);
  assert.deepEqual(out.map((e) => [e.modulates, e.direction, e.structure]),
                   [["dopamine", "decrease", "vta"], ["norepinephrine", "decrease", null]]);
});

test("affinity_only bindings contribute nothing", () => {
  assert.deepEqual(deriveReleaseChanges([{ target: "h3", action: null, affinityOnly: true }],
                                        modsOf, modes), []);
});

test("two receptors converging on one change share a line", () => {
  const out = deriveReleaseChanges(
    [{ target: "5ht2c", action: "antagonist" }, { target: "d3", action: "antagonist" }],
    modsOf, modes);
  const da = out.find((e) => e.modulates === "dopamine");
  assert.equal(da.direction, "increase");
  assert.deepEqual(da.via.map((v) => v.binding.target), ["5ht2c", "d3"]);
});

test("one receptor reaching a change through two of its nodes is one chip", () => {
  const out = deriveReleaseChanges([{ target: "a2a", action: "antagonist" }], modsOf, modes);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0].via.map((v) => v.binding.target), ["a2a"]);
});

test("transmitterVars passes the label through the language's article", () => {
  const ofNoun = (w) => (/^[aeiouh]/i.test(w) ? `d'${w}` : `de ${w}`);
  assert.deepEqual(transmitterVars("histamine", ofNoun), { transmitter: "d'histamine" });
  assert.deepEqual(transmitterVars("histamine", (w) => w), { transmitter: "histamine" });
});

test("the parent and its active metabolite on one receptor are two chips", () => {
  const out = deriveReleaseChanges([
    { target: "h3", action: "antagonist" },
    { target: "h3", action: "antagonist", viaMetabolite: "Norfoo" },
  ], modsOf, modes);
  assert.deepEqual(out.map((e) => e.via.map((v) => v.binding.viaMetabolite || null)),
                   [[null, "Norfoo"]]);
});
