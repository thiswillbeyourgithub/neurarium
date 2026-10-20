#!/usr/bin/env python
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright>=1.40"]
# ///
"""Walk the guided tour end to end in headless Chromium, like a user would.

Serves ``public/`` (``shot.dev_server``), boots the viewer, starts the tour from the
About popup's replay button, then advances every step with real mouse input: Next when
it is enabled, otherwise the action the step waits for (tap the ringed target, close
the ringed popup, drag the brain, wheel the details panel). After the last step it
checks the tour really ended: overlay hidden, capture listeners gone (a click reaches
the app again), "seen" flag stored, search closed, explode slider back at 0.

    PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright uv run --with playwright==1.61.0 \\
        python tools/tour_walk.py [--lang en|fr] [--headed]

Exit 0 when every step was reached, the end state is clean and no console error fired.
Headless quirks it absorbs (see docs/RUNNING.md): the SDF Worker hangs (deleted before
load so the synchronous mesher runs), the intro never settles (so the tour is started
by hand, not via ``?tour=1``), rAF is throttled (positions are polled, not slept on).
"""
from __future__ import annotations

import argparse
import re
import sys
import time

from shot import GL_ARGS, dev_server

# One snapshot of the tour's visible state, read in the page.
STATE_JS = """() => {
  const q = (s) => document.querySelector(s);
  const vis = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
  const rect = (el) => { if (!vis(el)) return null; const r = el.getBoundingClientRect();
    return r.width && r.height ? [r.x, r.y, r.width, r.height] : null; };
  const root = q('#tour-root'), ring = q('.tour-ring'), next = q('.tour-next');
  // The ring's resting box: the left/top/width/height layoutStep writes, which is also
  // exactly the blocker's click-through hole. NOT its painted rect: the ring glides on
  // a CSS transition, and on a starved compositor (SwiftShader on a loaded host paints
  // one frame every 10-30 s) the paint can sit at the previous step's spot for many
  // seconds while the hole is already on the new target, so a tap aimed at the paint
  // lands on the blocker. The hole has no transition, so this box is what a tap hits.
  const ringBox = () => { if (!vis(ring)) return null; const s = ring.style;
    const b = [s.left, s.top, s.width, s.height].map(parseFloat);
    return b.every(Number.isFinite) && b[2] && b[3] ? b : null; };
  const target = (id) => { const el = q(id), r = ringBox();
    if (!el || !r) return false; const b = el.getBoundingClientRect();
    return b.left < r[0] + r[2] && b.right > r[0] && b.top < r[1] + r[3] && b.bottom > r[1]; };
  return {
    open: vis(root),
    step: (q('.tour-step') || {}).textContent || '',
    title: (q('.tour-title') || {}).textContent || '',
    nextRect: next && !next.hidden ? rect(next) : null,
    nextDisabled: !!(next && next.disabled),
    ring: ring && !ring.hidden ? ringBox() : null,
    ringInteractive: !!(ring && ring.classList.contains('interactive')),
    modalOpen: ['legend-modal', 'sourcing-modal'].some((id) => vis(q('#' + id))),
    onSlider: target('#explode'),
    pane: rect(q('#details-pane')),
  };
}"""

# What a click at (x, y) would land on: the topmost element, for a stuck-step report.
HIT_JS = """([x, y]) => { const el = document.elementFromPoint(x, y);
  return el ? el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
    + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').join('.') : '') : null; }"""

# The end state a finished tour must leave behind (tourFullReset + tour.stop()).
END_JS = """() => {
  const root = document.querySelector('#tour-root');
  const search = document.querySelector('#search');
  return {
    overlayHidden: !root || (root.hidden && root.getAttribute('aria-hidden') === 'true'),
    bubbleGone: [...document.querySelectorAll('.tour-bubble')].every((b) => b.getClientRects().length === 0),
    seen: localStorage.getItem('neurarium:tourSeen') !== null,
    searchClosed: !search || search.hidden,
    explodeZero: document.querySelector('#explode')?.value === '0',
  };
}"""


def step_no(state: dict) -> tuple[int, int]:
    """Parse "3 of 32" / "3 sur 32" into (3, 32); (0, 0) when no step shows."""
    nums = re.findall(r"\d+", state["step"])
    return (int(nums[0]), int(nums[1])) if len(nums) >= 2 else (0, 0)


def centre(r):
    return r[0] + r[2] / 2, r[1] + r[3] / 2


def settle(page, key: str, timeout: float = 4.0) -> dict:
    """Poll STATE_JS until ``state[key]`` reads the same twice (rAF is throttled)."""
    prev, deadline = None, time.time() + timeout
    while True:
        state = page.evaluate(STATE_JS)
        if (state[key] == prev and prev is not None) or time.time() > deadline:
            return state
        prev = state[key]
        page.wait_for_timeout(250)


# Points inside the ring a user would tap: the centre first, then a grid, skipping any
# that land on the tour's own bubble. Links are NOT skipped: a ring whose centre is a
# link (a visitor's natural tap opens it instead of doing the step) is reported by
# walk() as a problem, so a sloppy anchor fails here instead of being worked around.
TAP_POINTS_JS = """([x, y, w, h]) => {
  const pts = [[x + w / 2, y + h / 2]];
  for (const fy of [0.5, 0.25, 0.75]) for (const fx of [0.2, 0.4, 0.6, 0.8]) pts.push([x + w * fx, y + h * fy]);
  return pts.filter(([px, py]) => { const el = document.elementFromPoint(px, py);
    return el && !el.closest('.tour-bubble'); });
}"""
# Whether the ring centre lands on a link (see TAP_POINTS_JS).
CENTRE_LINK_JS = """([x, y, w, h]) => !!document.elementFromPoint(x + w / 2, y + h / 2)?.closest('a')"""


def act(page, state: dict, attempt: int = 0) -> str:
    """Perform the one user action this step waits for; return its name.

    ``attempt`` counts retries on the same step, so a tap that missed moves on to the
    next candidate point instead of hitting the same dead spot forever.
    """
    if state["nextRect"] and not state["nextDisabled"]:
        page.mouse.click(*centre(state["nextRect"]))
        return "next"
    if state["ringInteractive"] or state["modalOpen"] or state["onSlider"]:
        # Tap only once the overlay faded in (pre-reveal holds the hole shut) and the
        # ring's box stopped tracking a row still scrolling in, or the click lands on
        # the blocker.
        page.wait_for_function("() => !document.querySelector('#tour-root.pre-reveal')")
        state = settle(page, "ring")
        if state["onSlider"]:
            r = state["ring"]  # off the thumb, so the click changes the value
            x, y = r[0] + r[2] * 0.7, r[1] + r[3] / 2
        else:
            if page.evaluate(CENTRE_LINK_JS, state["ring"]):
                # A ring still tracking a row mid-scroll can pass over the header
                # byline: only a centre that stays on a link once at rest counts.
                page.wait_for_timeout(1500)
                state = settle(page, "ring")
                if page.evaluate(CENTRE_LINK_JS, state["ring"]):
                    return "tap target (ring centre is a link)"
            pts = page.evaluate(TAP_POINTS_JS, state["ring"]) or [centre(state["ring"])]
            x, y = pts[attempt % len(pts)]
        page.mouse.click(x, y)
        return "tap target"
    if state["pane"]:
        page.mouse.move(*centre(state["pane"]))
        for _ in range(12):
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(80)
        return "scroll panel"
    w, h = page.viewport_size["width"], page.viewport_size["height"]
    page.mouse.move(w * 0.65, h * 0.5)
    page.mouse.down()
    page.mouse.move(w * 0.8, h * 0.45, steps=8)
    page.mouse.up()
    return "drag brain"


def boot(page, base: str, lang: str) -> None:
    page.add_init_script("delete window.Worker;")
    page.goto(f"{base}?lang={lang}", wait_until="load")
    page.wait_for_function("() => { const b = document.querySelector('#loading-start');"
                           " return b && !b.hidden; }")
    page.evaluate("document.querySelector('#loading-start').click()")
    page.wait_for_function("() => { const l = document.querySelector('#loading');"
                           " return !l || l.hidden || getComputedStyle(l).display === 'none'; }")
    # Late wiring straggles after the overlay hides: retry until the tour is up.
    for _ in range(40):
        page.evaluate("document.querySelector('#about-toggle')?.click();"
                      "document.querySelector('#about-tour')?.click()")
        page.wait_for_timeout(500)
        if page.evaluate(STATE_JS)["title"]:
            return
    raise RuntimeError("tour never started")


def walk(page, max_actions: int = 200) -> list[str]:
    """Advance to the end; return a list of problems (empty = clean run)."""
    problems, seen = [], set()
    total, stuck = 0, 0
    for _ in range(max_actions):
        state = page.evaluate(STATE_JS)
        if not state["open"]:
            break
        n, total = step_no(state)
        if n not in seen:
            seen.add(n)
            print(f"step {n}/{total}: {state['title']}")
        page.wait_for_timeout(400)  # let before() + the reveal timer run, like a reader
        what = act(page, page.evaluate(STATE_JS), stuck)
        if "is a link" in what:
            problems.append(f"step {n}: ring centre is a link, a centre tap opens it")
            break
        deadline = time.time() + 8
        while time.time() < deadline:
            after = page.evaluate(STATE_JS)
            if (not after["open"] or step_no(after)[0] != n
                    or (after["nextRect"] and not after["nextDisabled"] and what != "next")):
                break
            page.wait_for_timeout(200)
        else:
            s = page.evaluate(STATE_JS)
            hit = page.evaluate(HIT_JS, centre(s["ring"])) if s["ring"] else None
            print(f"  step {n}: '{what}' made no progress, retrying "
                  f"(ring={s['ring']}, next={s['nextRect']} disabled={s['nextDisabled']}, hit={hit})")
            stuck += 1
            if stuck >= 5:
                problems.append(f"stuck on step {n}")
                break
            continue
        stuck = 0
    else:
        problems.append("tour still open after max actions")
    missing = sorted(set(range(1, total + 1)) - seen)
    if missing:
        problems.append(f"steps never shown: {missing}")
    page.wait_for_timeout(800)
    end = page.evaluate(END_JS)
    print("end state:", end)
    problems += [f"end check failed: {k}" for k, ok in end.items() if not ok]
    # The capture-phase click guard must be gone: a click reaches the app again.
    page.evaluate("document.querySelector('#about-toggle').click()")
    page.wait_for_timeout(400)
    if not page.evaluate("!document.querySelector('#about-modal')?.hidden"):
        problems.append("a click after the tour did not reach the app (About did not open)")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", default="en", choices=["en", "fr"])
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    errors: list[str] = []
    with dev_server() as base, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed, args=GL_ARGS + ["--enable-webgl"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(180000)
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))
        boot(page, base, args.lang)
        problems = walk(page)
        browser.close()
    problems += [f"console error: {e}" for e in errors]
    for p in problems:
        print("FAIL:", p)
    print("OK: tour walked and ended cleanly" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
