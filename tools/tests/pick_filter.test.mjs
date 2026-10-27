// hoverMesh / isPickableMesh (public/js/scene/pick-filter.js): with "See inside" on, a
// cortical shell faded to glass must not take the hover label from the solid structure
// behind it (it used to: hover checked only `visible`, while click skipped the glass).
import { test } from "node:test";
import assert from "node:assert/strict";
import { hoverMesh, isPickableMesh } from "../../public/js/scene/pick-filter.js";

const mesh = (name, { visible = true, insideFade } = {}) => ({ name, visible, userData: { insideFade } });
const hits = (...meshes) => meshes.map((object) => ({ object }));

test("a see-inside glass shell is skipped, the solid structure behind it is named", () => {
  const lobe = mesh("frontal_lobe", { insideFade: 0.15 });
  const caudate = mesh("caudate");
  assert.equal(isPickableMesh(lobe), false);
  assert.equal(hoverMesh(hits(lobe, caudate), null), caudate);
});

test("a shell mid-fade still counts while mostly solid", () => {
  const lobe = mesh("frontal_lobe", { insideFade: 0.8 });
  assert.equal(hoverMesh(hits(lobe, mesh("caudate")), null), lobe);
});

test("hidden meshes are skipped and an all-glass ray names nothing", () => {
  assert.equal(hoverMesh(hits(mesh("a", { visible: false }), mesh("b", { insideFade: 0.1 })), null), null);
});

test("a focused region wins over a nearer one, but not when it is glass", () => {
  const lobe = mesh("temporal_lobe");
  const amygdala = mesh("amygdala");
  assert.equal(hoverMesh(hits(lobe, amygdala), new Set([amygdala])), amygdala);
  const glassFocus = mesh("parietal_lobe", { insideFade: 0.15 });
  assert.equal(hoverMesh(hits(glassFocus, amygdala), new Set([glassFocus])), amygdala);
});
