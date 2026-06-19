#!/usr/bin/env python
"""Tiny static dev server that forbids the browser from caching responses.

Why this exists: Neurarium is a no-build static site whose JavaScript is loaded
as ES modules (``<script type="module">`` + relative ``import``s). The stock
``python -m http.server`` sends no ``Cache-Control`` header, so the browser falls
back to *heuristic* caching and may serve a stale module (say an old
``js/labels.js``) next to a freshly fetched one. A mismatched pair like that
crashes in confusing ways, e.g. a new ``main.js`` calling
``createLabels(meshes, arrows, parentEl)`` against an old two-argument
``createLabels(meshes, parentEl)`` throws ``parentEl.appendChild is not a
function`` (the ``arrows`` array lands in the ``parentEl`` slot). A normal reload
does not reliably fix it because only some files get revalidated.

Serving every response with ``Cache-Control: no-store`` makes the browser refetch
each module on every load, so a plain reload always runs the code currently on
disk. Use this instead of ``python -m http.server`` while developing.

Stdlib-only on purpose (like ``generate_data.py``): it must run with a bare
``python`` interpreter and no third-party packages.

Usage
-----
    python tools/serve.py                 # serve public/ on http://localhost:8000/
    python tools/serve.py --port 9000     # different port
    python tools/serve.py --root .        # serve a different directory
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    """A static file handler that disables all client-side caching.

    ``end_headers`` is the single choke point every response passes through, so
    adding the no-cache headers there covers static files, directory listings and
    error pages alike, without having to override each ``do_*`` method.
    """

    def end_headers(self) -> None:
        # no-store: never write to the cache; the belt-and-suspenders Pragma /
        # Expires cover older heuristics so no proxy or browser holds a copy.
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main() -> None:
    """Parse ``--port`` / ``--root`` and serve until interrupted (Ctrl-C)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to listen on (default: 8000)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        # Default to the served site (public/); this file lives in tools/.
        default=Path(__file__).resolve().parent.parent / "public",
        help="Directory to serve (default: the public/ site root).",
    )
    args = parser.parse_args()

    # `directory` is bound per-handler so the server can serve any root without
    # chdir'ing the whole process.
    handler = partial(NoCacheHandler, directory=str(args.root))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(
        f"Serving {args.root} at http://localhost:{args.port}/ "
        "with caching disabled (Ctrl-C to stop)."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
