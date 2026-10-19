#!/usr/bin/env python
"""The Dockerfile `api` stage runs with only the files it COPYs.

render_api.py is rendered in a bare python image from a hand-listed set of
COPYs, under `python -I` (no script dir, no PYTHONPATH). An import of a module
the stage does not copy passes every local run and fails only `docker compose
build` on the deploy host. This replays the stage: its COPYs (filtered by
.dockerignore, as the build context is) into a scratch root, then its RUN.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_dockerignore import _rules, ignored

REPO = Path(__file__).resolve().parents[2]


def api_stage() -> tuple[list[tuple[str, str]], list[str]]:
    """(COPY src, dest) pairs and the RUN command words of the `api` stage."""
    copies, run, inside = [], "", False
    lines = (REPO / "docker" / "Dockerfile").read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        while line.endswith("\\") and i + 1 < len(lines):
            i += 1
            line = line[:-1] + " " + lines[i].strip()
        words = line.split()
        if words[:1] == ["FROM"]:
            inside = words[-1] == "api"
        elif inside and words[:1] == ["COPY"]:
            copies.append((words[1], words[2]))
        elif inside and words[:1] == ["RUN"] and "render_api.py" in line:
            run = line
        i += 1
    return copies, shlex.split(run)[1:]


class DockerApiStageTest(unittest.TestCase):
    def test_stage_renders_from_its_own_copies(self):
        copies, cmd = api_stage()
        self.assertTrue(copies and cmd, "api stage COPY / RUN not found")
        rules = _rules()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for src, dest in copies:
                path = REPO / src
                files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
                for f in files:
                    rel = f.relative_to(REPO).as_posix()
                    if ignored(rel, rules):
                        continue
                    target = root / dest.lstrip("/")
                    if path.is_dir():
                        target = target / f.relative_to(path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(f, target)
            args = [str(root / w.lstrip("/")) if w.startswith("/") else w for w in cmd]
            self.assertEqual(args[0], "python")
            proc = subprocess.run([sys.executable, *args[1:]], capture_output=True, text=True, cwd=root)
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
