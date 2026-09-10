#!/usr/bin/env python
"""Scope-aware "is this name actually reachable from here?" check over the viewer's JS.

There is no build step and no package manager here (see CLAUDE.md "Conventions"), so
there is no linter either, and the one bug class that costs a *runtime* crash in a file
that parses perfectly is a free variable: a name referenced in a scope where nothing
binds it. `node --check` cannot see it (the syntax is valid), and the browser only
raises when that exact line runs, so a search entry nobody clicked shipped broken.

So this walks each file's scope tree the way the engine would and reports every
identifier reference that no enclosing scope binds.

    python tools/check_js.py            # public/js/*.js + public/*.js
    python tools/check_js.py a.js b.js  # just these

Exit status is 1 when something is unbound, so it can gate a push.

It is a *lint*, not a parser: it tokenizes rather than building an AST, and every
judgement call is biased toward silence. When it cannot tell whether a name is a
binding or a reference it calls it a binding, and when it cannot tell whether a name is
a reference or a property key it calls it a key. That direction is deliberate: a checker
that cries wolf gets switched off, while one that misses an exotic case still catches
the ordinary one. Consequences worth knowing before "fixing" a miss:

  - a `var` is bound at the nearest function scope, everything else at its block, and
    no temporal-dead-zone rule is applied (using a `const` above its line is legal here);
  - a name in a parameter list is a binding, including one that only appears in a
    default value;
  - `x ? a : b` loses `a` as a reference, because `a:` is how an object key looks.

Built with the help of Claude Code.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Reserved words plus the contextual ones that would otherwise read as free variables
# (`async` sits exactly where a callee sits, `of` exactly where an operand does).
KEYWORDS = {
    "await", "async", "break", "case", "catch", "class", "const", "continue",
    "debugger", "default", "delete", "do", "else", "enum", "export", "extends",
    "false", "finally", "for", "function", "get", "if", "import", "in", "instanceof",
    "let", "new", "null", "of", "return", "set", "static", "super", "switch", "this",
    "throw", "true", "try", "typeof", "var", "void", "while", "with", "yield",
}

# A `(` right after one of these opens a condition, not a parameter list, so what is
# inside is references to bind against, not bindings. `catch` is the exception: its
# parenthesis really does introduce a binding for the block that follows.
CONTROL = {"if", "for", "while", "switch", "with", "do", "return"}

# The ambient names. Not a curated minimum: anything the platform hands a module for
# free belongs here, because a missing entry reads as a bug in the code under check.
GLOBALS = set("""
AbortController AbortSignal ArrayBuffer Array Atomics Audio BigInt BigInt64Array
BigUint64Array Blob Boolean BroadcastChannel CSS CustomEvent DataTransfer DataView
Date DOMParser DOMMatrix Element Error EvalError Event EventSource EventTarget File
FileReader Float32Array Float64Array FormData Function Headers History HTMLElement
HTMLCanvasElement HTMLImageElement Image ImageBitmap ImageData Infinity Int16Array
Int32Array Int8Array Intl JSON Map Math MessageChannel MessagePort MutationObserver
NaN Node NodeList Notification Number Object OffscreenCanvas Path2D Performance
PointerEvent Promise Proxy RangeError ReferenceError Reflect RegExp Request Response
ResizeObserver IntersectionObserver Set SharedArrayBuffer String Symbol SyntaxError
Text TextDecoder TextEncoder TouchEvent TypeError Uint16Array Uint32Array Uint8Array
Uint8ClampedArray URIError URL URLSearchParams WeakMap WeakRef WeakSet WebAssembly
WebSocket Window Worker XMLHttpRequest KeyboardEvent MouseEvent WheelEvent
alert atob btoa caches cancelAnimationFrame clearInterval clearTimeout clients close
confirm console crypto decodeURI decodeURIComponent devicePixelRatio document
encodeURI encodeURIComponent eval fetch getComputedStyle globalThis history
indexedDB innerHeight innerWidth isFinite isNaN localStorage location matchMedia
navigator open parseFloat parseInt performance postMessage prompt queueMicrotask
registration requestAnimationFrame requestIdleCallback screen scrollTo self
sessionStorage setInterval setTimeout structuredClone undefined window
arguments importScripts skipWaiting
""".split())

# Longest first: `=` must not win over `=>` or `===`.
PUNCT = sorted([
    ">>>=", "...", "===", "!==", "**=", "<<=", ">>=", ">>>", "&&=", "||=", "??=",
    "=>", "==", "!=", "<=", ">=", "&&", "||", "??", "?.", "**", "++", "--", "+=",
    "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<", ">>",
    "{", "}", "(", ")", "[", "]", ";", ",", "<", ">", "+", "-", "*", "/", "%", "&",
    "|", "^", "!", "~", "?", ":", "=", ".", "#", "@",
], key=len, reverse=True)

NAME_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
NUM_RE = re.compile(r"(?:0[xXbBoO][0-9a-fA-F_]+|(?:\d[\d_]*)?\.?\d[\d_]*(?:[eE][+-]?\d+)?)n?")

# A `/` is a division only after something a value can end with. Anywhere else it opens
# a regex. The tie is broken toward "regex" on purpose: reading a regex as division
# spills its body into the token stream as identifiers, which invents free variables,
# while reading a division as a regex only swallows a few real ones.
DIV_AFTER = {")", "]", "++", "--"}


class Tok:
    __slots__ = ("kind", "val", "line")

    def __init__(self, kind, val, line):
        self.kind, self.val, self.line = kind, val, line

    def __repr__(self):
        return f"{self.kind}:{self.val}"


def tokenize(src):
    """Flatten source to name/num/str/punct tokens, comments and literal text dropped.

    A template literal's `${...}` becomes a plain parenthesised group, so the braces
    inside a template never look like a block to the scope walk.
    """
    toks = []
    i, n, line = 0, len(src), 1
    depth = 0            # brace nesting, to know which `}` closes a `${`
    subst = []           # brace depth at each open `${`
    in_tpl = []          # True while scanning template text rather than code

    def prev():
        return toks[-1] if toks else None

    while i < n:
        if in_tpl and in_tpl[-1]:
            # Template text: only `\`` and `${` mean anything.
            if src[i] == "\\":
                line += src[i:i + 2].count("\n")
                i += 2
                continue
            if src[i] == "`":
                in_tpl.pop()
                i += 1
                continue
            if src.startswith("${", i):
                toks.append(Tok("punct", "(", line))
                subst.append(depth)
                in_tpl[-1] = False
                i += 2
                continue
            if src[i] == "\n":
                line += 1
            i += 1
            continue

        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r\f\v ﻿":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += src[i:j].count("\n")
            i = j
            continue
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            line += src[i:j].count("\n")
            toks.append(Tok("str", src[i:j + 1], line))
            i = j + 1
            continue
        if c == "`":
            in_tpl.append(True)
            i += 1
            continue
        if c == "/":
            p = prev()
            divides = p is not None and (
                p.kind in ("num", "str")
                or (p.kind == "name" and p.val not in KEYWORDS)
                or (p.kind == "punct" and p.val in DIV_AFTER))
            if not divides:
                j, cls = i + 1, False
                while j < n:
                    ch = src[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        cls = True
                    elif ch == "]":
                        cls = False
                    elif ch == "/" and not cls:
                        break
                    elif ch == "\n":
                        break
                    j += 1
                if j < n and src[j] == "/":
                    j += 1
                    while j < n and src[j].isalpha():
                        j += 1
                    toks.append(Tok("regex", src[i:j], line))
                    i = j
                    continue
        m = NAME_RE.match(src, i)
        if m:
            toks.append(Tok("name", m.group(), line))
            i = m.end()
            continue
        m = NUM_RE.match(src, i)
        if m:
            toks.append(Tok("num", m.group(), line))
            i = m.end()
            continue
        if c == "}" and subst and depth == subst[-1]:
            subst.pop()
            in_tpl[-1] = True
            toks.append(Tok("punct", ")", line))
            i += 1
            continue
        for p in PUNCT:
            if src.startswith(p, i):
                if p == "{":
                    depth += 1
                elif p == "}":
                    depth -= 1
                toks.append(Tok("punct", p, line))
                i += len(p)
                break
        else:
            i += 1
    return toks


class Scope:
    __slots__ = ("parent", "names", "is_fn")

    def __init__(self, parent, is_fn):
        self.parent, self.names, self.is_fn = parent, set(), is_fn

    def declare(self, name, hoist=False):
        s = self
        while hoist and not s.is_fn and s.parent is not None:
            s = s.parent
        s.names.add(name)

    def resolve(self, name):
        s = self
        while s is not None:
            if name in s.names:
                return True
            s = s.parent
        return False


def _match_brackets(toks):
    """index of `(`/`[`/`{` -> index of its partner, and back."""
    pair, stack = {}, []
    for i, t in enumerate(toks):
        if t.kind != "punct":
            continue
        if t.val in "([{":
            stack.append(i)
        elif t.val in ")]}" and stack:
            j = stack.pop()
            pair[i] = j
            pair[j] = i
    return pair


def _is_name(t):
    return t is not None and t.kind == "name" and t.val not in KEYWORDS


def _pattern_names(toks, a, b):
    """-> [(index, name)] a binding pattern (parameter list, destructuring target) introduces.

    Generous on purpose: a name that only appears in a default value is collected too.
    An extra binding can only silence a report, never invent one.
    """
    out = []
    for j in range(a, b):
        t = toks[j]
        if not _is_name(t):
            continue
        prv = toks[j - 1] if j > a else None
        nxt = toks[j + 1] if j + 1 < b else None
        if prv is not None and prv.kind == "punct" and prv.val in (".", "?."):
            continue          # a property path, not a binding
        if nxt is not None and nxt.kind == "punct" and nxt.val == ":":
            continue          # `{ key: bound }`, the key names nothing
        out.append((j, t.val))
    return out


def _decl_names(toks, i):
    """-> ([(index, name)], end) for the `var`/`let`/`const` declaration at index `i`.

    Walks the declarator list, collecting inside patterns and skipping initialisers,
    which are expressions and so hold references rather than bindings.
    """
    names, j, d, init = [], i + 1, 0, False
    while j < len(toks):
        t = toks[j]
        if t.kind == "punct":
            if t.val in "([{":
                d += 1
            elif t.val in ")]}":
                d -= 1
                if d < 0:
                    break
            elif d == 0 and t.val == ";":
                break
            elif d == 0 and t.val == "=":
                init = True
            elif d == 0 and t.val == ",":
                init = False
        elif t.kind == "name" and t.val in ("of", "in") and d == 0:
            break
        elif _is_name(t) and not init:
            prv, nxt = toks[j - 1], toks[j + 1] if j + 1 < len(toks) else None
            if not (prv.kind == "punct" and prv.val in (".", "?.")) and \
               not (nxt is not None and nxt.kind == "punct" and nxt.val == ":"):
                names.append((j, t.val))
        j += 1
    return names, j


def analyse(src):
    """-> [(line, name)] for every reference no enclosing scope binds."""
    toks = tokenize(src)
    pair = _match_brackets(toks)
    n = len(toks)

    module = Scope(None, True)
    scope_of = [module] * n
    params_at = {}        # index of a body `{` -> names its parameter list binds
    defname = set()       # indices of names that *are* a definition, not a use
    skip = set()          # indices inside an import statement

    # Pass 1: build the scope tree and every binding in it, so a reference may point
    # at a declaration further down its own scope (a hoisted function, mostly).
    cur = module
    i = 0
    while i < n:
        t = toks[i]
        scope_of[i] = cur

        if t.kind == "name" and t.val == "import" and (
                i + 1 < n and not (toks[i + 1].kind == "punct"
                                   and toks[i + 1].val in (".", "("))):
            j = i
            while j < n and not (toks[j].kind == "punct" and toks[j].val == ";"):
                j += 1
            for k in range(i, min(j + 1, n)):
                skip.add(k)
                scope_of[k] = cur
                if _is_name(toks[k]) and toks[k].val not in ("from", "as"):
                    cur.declare(toks[k].val)
            i = j + 1
            continue

        if t.kind == "name" and t.val in ("function", "class") and _is_name(
                toks[i + 1] if i + 1 < n else None):
            # `class Foo {` never reaches the parameter-list rule below (it has no
            # parameter list), and `function foo` is named the same way, so both are
            # bound here: the name belongs to the scope AROUND the body, not inside it.
            defname.add(i + 1)
            cur.declare(toks[i + 1].val, hoist=True)

        if t.kind == "name" and t.val in ("var", "let", "const"):
            names, end = _decl_names(toks, i)
            for k, name in names:
                defname.add(k)
                cur.declare(name, hoist=(t.val == "var"))
            i += 1
            continue

        if t.kind == "punct" and t.val == "(" and i in pair:
            close = pair[i]
            nxt = toks[close + 1] if close + 1 < n else None
            arrow = nxt is not None and nxt.kind == "punct" and nxt.val == "=>"
            body = nxt is not None and nxt.kind == "punct" and nxt.val == "{"
            prv = toks[i - 1] if i else None
            guard = (prv is not None and prv.kind == "name"
                     and prv.val in CONTROL)
            if arrow or (body and not guard):
                names = _pattern_names(toks, i + 1, close)
                defname.update(k for k, _ in names)
                names = [v for _, v in names]
                if arrow and not (close + 2 < n and toks[close + 2].kind == "punct"
                                  and toks[close + 2].val == "{"):
                    # A concise arrow body has no block of its own, so its parameters
                    # go in the scope around it. Wider than the engine, never narrower.
                    for name in names:
                        cur.declare(name)
                else:
                    brace = close + 1 if body else close + 2
                    params_at[brace] = names
                if _is_name(prv) and body:
                    defname.add(i - 1)
                    kind = toks[i - 2] if i >= 2 else None
                    if kind is not None and kind.kind == "name" and \
                            kind.val in ("function", "class"):
                        cur.declare(prv.val, hoist=True)

        if t.kind == "punct" and t.val == "=>":
            prv = toks[i - 1] if i else None
            if _is_name(prv) and not (i >= 2 and toks[i - 2].kind == "punct"
                                      and toks[i - 2].val == ")"):
                defname.add(i - 1)
                names = [prv.val]
                nxt = toks[i + 1] if i + 1 < n else None
                if nxt is not None and nxt.kind == "punct" and nxt.val == "{":
                    params_at[i + 1] = params_at.get(i + 1, []) + names
                else:
                    cur.declare(prv.val)

        if t.kind == "punct" and t.val == "{":
            params = params_at.get(i)
            cur = Scope(cur, params is not None)
            for name in params or ():
                cur.declare(name)
            scope_of[i] = cur
        elif t.kind == "punct" and t.val == "}":
            if cur.parent is not None:
                cur = cur.parent
            scope_of[i] = cur
        i += 1

    # Pass 2: every name that reads as a reference must resolve.
    bad = []
    seen = set()
    for i, t in enumerate(toks):
        if i in skip or i in defname or not _is_name(t):
            continue
        prv = toks[i - 1] if i else None
        nxt = toks[i + 1] if i + 1 < n else None
        if prv is not None and prv.kind == "punct" and prv.val in (".", "?.", "#"):
            continue                                   # property access
        if prv is not None and prv.kind == "name" and \
                prv.val in ("break", "continue", "function", "class", "var", "let",
                            "const", "get", "set"):
            continue                                   # a label or a declared name
        if nxt is not None and nxt.kind == "punct" and nxt.val == ":":
            continue                                   # object key, label, case
        if _is_name(nxt):
            continue                                   # modifier, e.g. `get active`
        if t.val in GLOBALS or scope_of[i].resolve(t.val):
            continue
        key = (t.val, t.line)
        if key not in seen:
            seen.add(key)
            bad.append((t.line, t.val))
    return bad


def targets():
    out = []
    for d in (os.path.join(ROOT, "public", "js"), os.path.join(ROOT, "public")):
        for name in sorted(os.listdir(d)):
            path = os.path.join(d, name)
            if name.endswith(".js") and os.path.isfile(path):
                out.append(path)
    return out


def main(argv):
    paths = argv[1:] or targets()
    total = 0
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        rel = os.path.relpath(path, ROOT)
        if rel.startswith(".."):
            rel = path          # given from outside the repo, so show it as given
        for line, name in analyse(src):
            print(f"{rel}:{line}: {name!r} is not defined in any enclosing scope")
            total += 1
    if total:
        print(f"\n{total} unbound reference(s) in {len(paths)} file(s)")
        return 1
    print(f"check_js: {len(paths)} file(s), no unbound references")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
