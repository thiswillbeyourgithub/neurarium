"""Atomic file writes for every committed artifact the tools produce.

``Path.write_text`` truncates the target first and then streams into it, so an
interrupt (Ctrl-C mid-apply, a full disk, a killed container) leaves a half-written
``drugs_data.jsonl`` or cache behind, and the next run reads that truncation as the
real data. Writing to a sibling temp file and ``os.replace``-ing it over the target
makes the swap atomic on POSIX: a reader (``tools/serve.py`` serving the effect
index, a concurrent generator run) sees the old file or the new one, never a torn
one.

Stdlib only, so ``generate_data.py`` stays runnable offline.

Built with the help of Claude Code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically, creating parent directories.

    Parameters
    ----------
    path : str or Path
        Target file. The temp file sits beside it (``<name>.tmp``) so the final
        ``os.replace`` never crosses a filesystem boundary, which would not be atomic.
    text : str
        Full file contents.
    encoding : str, optional
        Text encoding, UTF-8 by default.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        # Only reached with the temp file still present when the write or the
        # replace raised: never leave a stray `.tmp` beside a committed file.
        if tmp.exists():
            tmp.unlink()


def atomic_write_json(path: str | Path, obj: Any, *, trailing_newline: bool = True,
                      **dumps_kw: Any) -> None:
    """``json.dumps(obj, **dumps_kw)`` written atomically (see ``atomic_write_text``).

    ``ensure_ascii`` defaults to False (every committed cache keeps its accents
    readable); pass it explicitly to override. A trailing newline is added by
    default so the file ends the way an editor would leave it.
    """
    dumps_kw.setdefault("ensure_ascii", False)
    text = json.dumps(obj, **dumps_kw)
    atomic_write_text(path, text + ("\n" if trailing_newline else ""))
