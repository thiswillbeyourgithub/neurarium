#!/usr/bin/env python
"""Unit tests for tools/check_js.py, the viewer's free-variable check.

The regression at the bottom is the one that matters: a search entry called
`focusEnzyme` from `wireToolbar`, while `focusEnzyme` was a `const` inside `main()`,
a sibling scope. The file parsed, `node --check` passed, and the browser only raised
when somebody searched for an enzyme. Every other test here exists to keep the checker
quiet enough that it stays switched on: a lint with false positives gets ignored, so
"reports nothing" is asserted far more often than "reports something".

Built with the help of Claude Code.
"""
import os
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import check_js as C  # noqa: E402


def names(src):
    return sorted(n for _, n in C.analyse(src))


class QuietOnOrdinaryCodeTest(unittest.TestCase):
    """Everything here is correct code, so every assertion is "says nothing"."""

    def test_a_parameter_binds_inside_its_body(self):
        self.assertEqual(names("function f(a, b) { return a + b; }"), [])

    def test_a_destructured_parameter_binds_each_name(self):
        self.assertEqual(names("function f({ a, b: c, d = 1 }, [e]) "
                               "{ return a + c + d + e; }"), [])

    def test_an_arrow_binds_its_parameters_both_ways(self):
        self.assertEqual(names("const f = x => x + 1; const g = (y) => { return y; };"),
                         [])

    def test_a_property_is_not_a_reference(self):
        # `.somethingUndefined` is a lookup on an object, not a free variable, and the
        # optional form has to be seen too or every `a?.b` becomes a false report.
        self.assertEqual(names("const o = {}; o.whatever; o?.alsoWhatever;"), [])

    def test_an_object_key_is_not_a_reference_but_shorthand_is(self):
        self.assertEqual(names("const a = 1; const o = { key: a, a };"), [])
        self.assertEqual(names("const o = { key: 1, missing };"), ["missing"])

    def test_a_function_may_be_used_above_its_declaration(self):
        # Declarations hoist, so a top-down walk that reported this would be wrong
        # about ordinary code, which is most of the file.
        self.assertEqual(names("start(); function start() { return 1; }"), [])

    def test_a_var_escapes_the_block_it_was_written_in(self):
        self.assertEqual(names("function f() { if (1) { var v = 2; } return v; }"), [])

    def test_a_const_does_not_escape_its_block(self):
        self.assertEqual(names("function f() { if (1) { const v = 2; } return v; }"),
                         ["v"])

    def test_imports_bind_what_they_bring_in(self):
        self.assertEqual(names('import * as THREE from "three";\n'
                               'import { a, b as c } from "./x.js";\n'
                               'THREE.Mesh; a; c;'), [])

    def test_a_template_substitution_is_real_code(self):
        self.assertEqual(names("const a = 1; const s = `x${a}y`;"), [])
        self.assertEqual(names("const s = `x${missing}y`;"), ["missing"])

    def test_a_template_brace_is_not_a_block(self):
        # `${` ... `}` must not close the scope it sits in, or every binding after a
        # template in a function would look out of scope.
        self.assertEqual(names("function f(a) { const s = `${a}`; return a + s; }"), [])

    def test_a_regex_body_is_not_code(self):
        self.assertEqual(names("const re = /notAVariable/g; re.test('x');"), [])

    def test_a_getter_name_is_not_a_reference(self):
        self.assertEqual(names("const o = { get active() { return 1; }, "
                               "set active(v) { this.x = v; } };"), [])

    def test_a_class_binds_its_own_name(self):
        self.assertEqual(names("export class Thing { constructor(a) { this.a = a; } }\n"
                               "new Thing(1);"), [])

    def test_a_catch_binds_its_parameter(self):
        self.assertEqual(names("try { null; } catch (err) { err.message; }"), [])

    def test_a_condition_is_references_not_bindings(self):
        # `if (x)` looks exactly like a parameter list; reading it as one would bind
        # `x` and hide the bug.
        self.assertEqual(names("if (nope) { 1; }"), ["nope"])

    def test_a_for_of_binds_its_loop_variable(self):
        self.assertEqual(names("const xs = []; for (const x of xs) { x; }"), [])


class SiblingScopeRegressionTest(unittest.TestCase):
    """The shipped bug: a handler defined in one function, called from its sibling."""

    SRC = """
        function wireToolbar({ focusDrug, %s }) {
          return [{ select: () => focusDrug(1) },
                  { select: () => focusEnzyme(2) }];
        }
        async function main() {
          const focusDrug = (d) => d;
          const focusEnzyme = (e) => e;
          wireToolbar({ focusDrug, focusEnzyme });
        }
        main();
    """

    def test_the_missing_parameter_is_reported(self):
        self.assertEqual(names(self.SRC % ""), ["focusEnzyme"])

    def test_adding_the_parameter_silences_it(self):
        self.assertEqual(names(self.SRC % "focusEnzyme"), [])

    def test_the_report_carries_the_line_the_browser_would(self):
        found = C.analyse(self.SRC % "")
        self.assertEqual(len(found), 1)
        line, name = found[0]
        self.assertEqual(name, "focusEnzyme")
        self.assertIn("focusEnzyme(2)", self.SRC.splitlines()[line - 1])


class TheShippedViewerIsCleanTest(unittest.TestCase):
    """The load-bearing one: every file the browser actually loads, right now."""

    def test_no_file_the_browser_loads_has_a_free_variable(self):
        bad = []
        for path in C.targets():
            with open(path, encoding="utf-8") as fh:
                for line, name in C.analyse(fh.read()):
                    bad.append(f"{os.path.relpath(path, C.ROOT)}:{line}: {name}")
        self.assertEqual(bad, [], "these would raise a ReferenceError in the browser "
                                  "the moment that line runs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
