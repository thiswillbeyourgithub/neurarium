"""Shared plumbing for every check family: the report, the loaders, the mirroring of
symmetric projections, and the small helpers two or more families use.

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[2] / "public" / "data"
# Repo root, used to resolve a source corpus's author-side ``pages_dir`` (e.g.
# ``data_sources/books/stahl/pages``) for the quote-in-page check (see check_sources).
REPO_ROOT = DATA_DIR.parent.parent
def flip_hemisphere(structure_id):
    """Flip a structure id to the other hemisphere; midline ids unchanged."""
    if structure_id.endswith("_R"):
        return structure_id[:-2] + "_L"
    if structure_id.endswith("_L"):
        return structure_id[:-2] + "_R"
    return structure_id


def expand_mirrored(projections):
    """Reflect ``mirror: true`` projections into the full bilateral connectome.

    A symmetric pathway is emitted once carrying ``mirror: true`` (the file stores
    only the right-hemisphere record; see generate_data.py ``_projection_records``).
    The reachability + connectivity checks reason over the logical connectome, so
    expand each flagged record into its hemisphere-flipped twin here, exactly as
    ``js/data.js`` does at load, before any check runs."""
    out = []
    for proj in projections:
        record = {k: v for k, v in proj.items() if k != "mirror"}
        out.append(record)
        if proj.get("mirror"):
            out.append({**record,
                        "from": flip_hemisphere(record.get("from")),
                        "to": flip_hemisphere(record.get("to"))})
    return out


class Report:
    """Collects errors/warnings while printing each section as it runs.

    A third level, ``review``, is for the per-item lines of an eyeball list whose
    flags are mostly intended (family 8's presynaptic-tone vs. postsynaptic-block
    split, family 7's drugs without a Ki): counted and summarized, but listed only
    under ``--verbose``, so the default run's warnings stay few enough to be read."""

    def __init__(self, verbose=False):
        self.errors = 0
        self.warnings = 0
        self.reviews = 0
        self.verbose = verbose

    def header(self, title):
        print(f"\n{title}\n{'-' * len(title)}")

    def ok(self, msg):
        print(f"  [ok]    {msg}")

    def error(self, msg):
        self.errors += 1
        print(f"  [ERROR] {msg}")

    def warn(self, msg):
        self.warnings += 1
        print(f"  [warn]  {msg}")

    def review(self, msg):
        self.reviews += 1
        if self.verbose:
            print(f"  [review] {msg}")


def normalize(value):
    """Lowercase and keep only alphanumeric characters (Unicode-aware, so a
    Greek receptor name like ``α1A`` collapses to ``α1a`` rather than vanishing).
    Two strings that normalize equal are "the same entry" for the dup check."""
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def display_name(name):
    """A display name. The emitted data is English-only, so it is normally a
    plain string; the legacy ``{en, fr}`` object is still handled defensively
    (use the English text). French lives in data/translations.fr.json."""
    if isinstance(name, dict):
        return name.get("en")
    return name


def load_jsonl(report, name):
    path = DATA_DIR / f"{name}.jsonl"
    records = []
    if not path.exists():
        report.error(f"missing data file: {path}")
        return records
    for lineno, line in enumerate(path.open(encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            report.error(f"{name}.jsonl:{lineno}: invalid JSON ({exc})")
    return records


def load_meta(report):
    path = DATA_DIR / "meta.json"
    if not path.exists():
        report.error(f"missing data file: {path}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(f"meta.json: invalid JSON ({exc})")
        return {}


def walk_strings(obj, path):
    """Yield ``(json_path, string_value)`` for every string anywhere in ``obj``,
    so the TODO scan can both find placeholders and tell *where* they sit."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk_strings(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk_strings(value, f"{path}[{index}]")
    elif isinstance(obj, str):
        yield path, obj
