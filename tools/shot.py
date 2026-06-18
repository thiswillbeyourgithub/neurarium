#!/usr/bin/env python
"""Render the brain viewer headlessly and save a PNG screenshot.

Purpose: let a developer (or Claude Code) actually *see* the rendered output
without a manual browser. It serves the repository over a throwaway local HTTP
server, drives a headless Chrome/Chromium to load ``index.html`` with optional
view parameters, captures a screenshot, then shuts the server down.

The view parameters are the URL query keys parsed by ``js/main.js``
(``applyViewParams``), so the same flags that deep-link a view also drive the
screenshot. The most useful for inspecting one structure at a time:

    only=<id[,id2,...]>   show only these structures (hide the rest + arrows)
    view=front|back|left|right|top|bottom|iso   frame from a canonical angle
    explode=<0..1>        blow-out amount      transparency=<0..1>
    names=all             show every label     autorotate=1

Stdlib-only (argparse/http.server/subprocess/...) so it matches
``generate_data.py`` and runs offline. It needs a Chrome/Chromium binary: it
auto-detects common ones, or set ``$CHROME`` / pass ``--browser`` to point at a
specific binary (e.g. a Playwright ``chrome-headless-shell``).

Headed mode (``--headed``): when headless WebGL comes back blank (no GPU, flaky
software rendering), this instead opens a *real* browser window on ``$DISPLAY``
where WebGL renders for real, and grabs that window. It needs an X session plus
``xdotool`` and ImageMagick ``import`` (or ``maim``). This is the reliable way to
visually verify the scene from this repo.

Examples
--------
    python tools/shot.py --out /tmp/brain.png
    python tools/shot.py --params "only=putamen_R&view=iso" --out /tmp/putamen.png
    python tools/shot.py --headed --params "explode=0.5&view=iso" --out /tmp/brain.png
    CHROME=/path/to/chrome-headless-shell python tools/shot.py --out /tmp/brain.png
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import os
import shutil
import signal
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# Repo root = parent of this tools/ directory; served as the web root.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Browser binaries tried in order when neither $CHROME nor --browser is given.
# brave/chrome with a real GPU come first for --headed (they render WebGL for
# real); chrome-headless-shell is last (it is headless-only).
BROWSER_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "brave-browser",
    "brave",
    "chromium",
    "chromium-browser",
    "chrome",
    "chrome-headless-shell",
)


def find_browser(explicit: str | None) -> str:
    """Resolve a Chrome/Chromium executable.

    Parameters
    ----------
    explicit
        Value of ``--browser`` (or ``None``). May be a bare command name on
        ``PATH`` or an absolute path.

    Returns
    -------
    str
        A runnable path/command for the browser.

    Raises
    ------
    SystemExit
        If no usable browser is found, with guidance on how to point at one.
    """
    for candidate in (explicit, os.environ.get("CHROME"), os.environ.get("CHROMIUM")):
        if candidate:
            resolved = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
            if resolved:
                return resolved
            sys.exit(f"Specified browser not found: {candidate!r}")

    for name in BROWSER_CANDIDATES:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    sys.exit(
        "No Chrome/Chromium found. Install one, or set $CHROME / pass --browser "
        "with a path to a chrome / chromium / chrome-headless-shell binary."
    )


def start_server(root: Path, port: int) -> tuple[socketserver.TCPServer, int]:
    """Start a background HTTP server serving ``root``.

    Parameters
    ----------
    root
        Directory to serve (the repo root).
    port
        Port to bind, or ``0`` to let the OS pick a free one.

    Returns
    -------
    (server, port)
        The running server (serving on a daemon thread) and the actual port.
    """
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(root)
    )
    # Allow quick re-binds between runs; serve on a daemon thread.
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def capture(
    *,
    browser: str,
    url: str,
    out: Path,
    width: int,
    height: int,
    wait_ms: int,
) -> None:
    """Drive the headless browser to screenshot ``url`` into ``out``.

    Uses SwiftShader (software WebGL) so it works on headless hosts without a
    GPU. ``--virtual-time-budget`` lets the page finish its fetches and a few
    render frames before the shot is taken.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    # Isolated profile dir so concurrent/!repeated runs never hit a profile lock.
    with tempfile.TemporaryDirectory(prefix="brainwebviz-shot-") as profile:
        cmd = [
            browser,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            "--enable-unsafe-swiftshader",
            "--use-gl=angle",
            "--use-angle=swiftshader",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            f"--virtual-time-budget={wait_ms}",
            f"--screenshot={out}",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
    if not out.exists():
        sys.stderr.write(result.stderr[-2000:] + "\n")
        sys.exit(f"Browser did not produce {out} (exit {result.returncode}).")


def capture_headed(
    *,
    browser: str,
    url: str,
    out: Path,
    width: int,
    height: int,
    wait_ms: int,
) -> None:
    """Screenshot ``url`` from a *real, on-screen* browser window (not headless).

    Headless Chrome here can't get a GPU and software WebGL has been unreliable,
    so this opens a normal browser window on the user's X display (``$DISPLAY``)
    where WebGL renders for real, then grabs that window's pixels. It needs an X
    session plus ``xdotool`` (to find the window by its page title) and ImageMagick
    ``import`` (or ``maim``) to capture it; it raises a clear error if any are
    missing. The browser is launched in ``--app`` mode (no tabs/URL bar) with an
    isolated profile and torn down afterwards.
    """
    if not os.environ.get("DISPLAY"):
        sys.exit("--headed needs an X display: $DISPLAY is not set.")
    xdotool = shutil.which("xdotool")
    if not xdotool:
        sys.exit("--headed needs xdotool (to locate the browser window).")
    grabber = shutil.which("import") or shutil.which("maim")
    if not grabber:
        sys.exit("--headed needs ImageMagick `import` or `maim` to capture.")

    out.parent.mkdir(parents=True, exist_ok=True)
    # ignore_cleanup_errors: a just-terminated browser can still be flushing its
    # profile when we tear the dir down, which otherwise raises a spurious
    # "Directory not empty" *after* the shot was already captured.
    with tempfile.TemporaryDirectory(
        prefix="brainwebviz-shot-", ignore_cleanup_errors=True
    ) as profile:
        cmd = [
            browser,
            f"--app={url}",
            f"--window-size={width},{height}",
            "--window-position=40,40",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--disable-features=Translate",
            # Fall back to software WebGL only if the real GPU is unavailable, so
            # the shot still renders instead of coming back blank.
            "--enable-unsafe-swiftshader",
        ]
        def windows_named():
            """Set of window ids whose title matches the page <title>."""
            return set(
                subprocess.run(
                    [xdotool, "search", "--name", "BrainWebViz"],
                    capture_output=True, text=True,
                ).stdout.split()
            )

        # Windows already titled like our page *before* we launch (e.g. the user
        # has the same site open in another browser); ours is whatever is new.
        before = windows_named()

        # New session so we can tear down the whole browser process tree after.
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            # Wait for the page (the window's title is the page <title>), then let
            # it fetch its data + render a few frames before grabbing it.
            subprocess.run(
                [xdotool, "search", "--sync", "--name", "BrainWebViz"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            )
            time.sleep(wait_ms / 1000)
            # Our window is the one that appeared since `before`. Fall back to the
            # newest match if the diff is somehow empty (single-browser case).
            new = windows_named() - before
            wid = sorted(new) or sorted(windows_named())
            if not wid:
                sys.exit("Could not find the browser window (xdotool).")
            win = wid[-1]  # newest match
            # Raise/focus our window first: a compositor can leave an occluded
            # window without a readable backing pixmap, which makes the grab fail
            # with "Resource temporarily unavailable" (common when other windows,
            # e.g. another browser, are open on the same display).
            for action in ("windowactivate", "windowraise"):
                subprocess.run(
                    [xdotool, action, win],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            time.sleep(0.4)
            grab = (
                [grabber, "-window", win, str(out)]
                if Path(grabber).name == "import"
                else [grabber, "-i", win, str(out)]
            )
            # Even raised, the grab can fail transiently on a busy live X session;
            # retry a few times before giving up.
            for _ in range(5):
                if subprocess.run(
                    grab, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                ).returncode == 0:
                    break
                time.sleep(0.6)
            else:
                sys.exit("Headed capture failed to grab the window after retries.")
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)
    if not out.exists():
        sys.exit(f"Headed capture did not produce {out}.")


def main() -> None:
    """CLI entry point: parse flags, render, and report the output path."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--out", type=Path, default=Path("/tmp/brainwebviz.png"),
        help="Output PNG path (default: /tmp/brainwebviz.png).",
    )
    parser.add_argument(
        "--params", default="",
        help="URL query string for the view, e.g. 'only=putamen_R&view=iso'.",
    )
    parser.add_argument("--width", type=int, default=1280, help="Viewport width.")
    parser.add_argument("--height", type=int, default=800, help="Viewport height.")
    parser.add_argument(
        "--wait", type=int, default=8000,
        help="Virtual-time budget in ms before the shot (default: 8000).",
    )
    parser.add_argument(
        "--port", type=int, default=0,
        help="HTTP port to serve on (default: 0 = pick a free one).",
    )
    parser.add_argument(
        "--browser", default=None,
        help="Path/name of a Chrome/Chromium binary (else $CHROME or autodetect).",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Render in a real on-screen browser window (uses the GPU for WebGL) "
             "and grab it, instead of headless. Needs $DISPLAY + xdotool + "
             "ImageMagick `import` (or maim). Use when headless WebGL comes back "
             "blank. --wait is then real milliseconds, not a virtual-time budget.",
    )
    args = parser.parse_args()

    browser = find_browser(args.browser)
    server, port = start_server(REPO_ROOT, args.port)
    try:
        query = args.params.lstrip("?")
        url = f"http://127.0.0.1:{port}/" + (f"?{query}" if query else "")
        run = capture_headed if args.headed else capture
        run(
            browser=browser,
            url=url,
            out=args.out.resolve(),
            width=args.width,
            height=args.height,
            wait_ms=args.wait,
        )
    finally:
        server.shutdown()
        server.server_close()

    print(args.out.resolve())


if __name__ == "__main__":
    main()
