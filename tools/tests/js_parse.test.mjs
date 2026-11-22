// Every viewer script parses as an ES module. tools/check_js.py is a lint that
// resolves identifiers and the unit suites import only some modules, so a syntax
// error in an untested module (a doc comment left unterminated by an edit, as
// baked-meshes.js once was) shipped a blank page with every test green.
// Run: node --test tools/tests/js_parse.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import vm from "node:vm";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = new URL("../../public/", import.meta.url).pathname;

function* jsFiles(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (name === "vendor" || name === "data") continue;
    if (statSync(p).isDirectory()) yield* jsFiles(p);
    else if (name.endsWith(".js")) yield p;
  }
}

// The module parser needs --experimental-vm-modules; under a plain `node --test` the
// file re-runs itself with the flag and reports the child's list.
export function unparsable() {
  const bad = [];
  for (const file of jsFiles(ROOT)) {
    try {
      new vm.SourceTextModule(readFileSync(file, "utf8"), { identifier: file });
    } catch (e) {
      if (e instanceof SyntaxError) bad.push(`${file.slice(ROOT.length)}: ${e.message}`);
    }
  }
  return bad;
}

if (process.env.JS_PARSE_CHILD) {
  process.stdout.write(JSON.stringify(unparsable()));
} else {
  test("every public/**/*.js parses", () => {
    if (vm.SourceTextModule) return assert.deepEqual(unparsable(), []);
    const r = spawnSync(process.execPath, ["--experimental-vm-modules", "--no-warnings",
      fileURLToPath(import.meta.url)], { env: { ...process.env, JS_PARSE_CHILD: "1" },
      encoding: "utf8" });
    assert.deepEqual(JSON.parse(r.stdout || "null"), [], r.stderr);
  });
}
