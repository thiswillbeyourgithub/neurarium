// Unit tests for public/js/drug-map/site.js viewerUrl (where the map's links to the 3D
// viewer point), run by tools/tests/test_js_units.py via `node --test`.
import test from "node:test";
import assert from "node:assert/strict";
import { viewerUrl, NEURARIUM_URL } from "../../public/js/drug-map/site.js";

const at = (href) => {
  globalThis.location = new URL(href);
};

test("next to the viewer, the link is relative to the site root", () => {
  at("https://neurarium.olicorne.org/drugs-map?x=1#dmcat=ssri");
  assert.equal(viewerUrl(), "https://neurarium.olicorne.org/");
  at("http://localhost:8000/drugs-map.html");
  assert.equal(viewerUrl(), "http://localhost:8000/");
});

test("on the dedicated host, the link goes to the viewer's canonical address", () => {
  at("https://drugsmap.olicorne.org/#dmtgt=d2");
  assert.equal(viewerUrl(), NEURARIUM_URL);
  // Regression: the installed app launches at its start_url `drugs-map`, not `/`,
  // and the link then pointed at drugsmap.olicorne.org/, the map itself.
  at("https://drugsmap.olicorne.org/drugs-map");
  assert.equal(viewerUrl(), NEURARIUM_URL);
});
