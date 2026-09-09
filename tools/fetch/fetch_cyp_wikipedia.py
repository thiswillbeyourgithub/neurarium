#!/usr/bin/env python
"""Read one drug's stored English Wikipedia article for the ``drug_enzymes`` pass.

Corpus #9 keeps every drug's article author-side (see ``CLAUDE.local.md``), and this
module is the half of the CYP pipeline that knows how that store is shaped: which file
an article lives in, where a sentence ends in flowing prose, which lines are the
reference list rather than the text, and how the flattened drugbox prints its
``Metabolism`` row.

It states no claim of its own. ``fetch_cyp_worklist.py`` uses these to offer candidate
sentences, a model reads them, and ``tools/sourcing/apply_cyp_sources.py`` gates the
answer; nothing here decides whether a sentence supports a role, because prose is
exactly where a pattern cannot tell "is metabolized by CYP2D6" from "is not", or from a
sentence about the CYP2D6 inhibitors somebody takes alongside.

A library, not a script: import it, do not run it.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)

PAGES = os.path.join(REPO, "data_sources", "wikipedia", "pages")

# The isoform ids the dataset models (mirrors ENZYMES in data_generators/drugs.py; not
# imported because this module must load with only the repo's stdlib path set up).
KNOWN_ENZYMES = {"cyp1a2", "cyp2a6", "cyp2b6", "cyp2c8", "cyp2c9", "cyp2c19",
                 "cyp2d6", "cyp2e1", "cyp3a4", "cyp3a5", "adh", "ces1", "fmo3",
                 "ugt", "ugt1a4", "ugt1a9", "ugt2b7", "ugt2b15"}

# The flattened drugbox row. `pageimages`-style tables come through as "cell | cell",
# so the metabolism field is a line whose first cell is exactly "Metabolism".
INFOBOX_RE = re.compile(r"^\s*Metabolism\s*\|\s*(.+)$")

# A reference-list entry ("- ^ Gram LF ... 'Moclobemide, a substrate of CYP2C19 ...'").
# The cited paper's title states a role, but the article is not asserting it here, and
# a title is not a sentence about the drug: skip rather than quote a bibliography.
REFERENCE_RE = re.compile(r"^\s*-\s*\^|^\s*\^\s|\bdoi\s*:|\bPMID\b|\bISBN\b")

# Sentence split, deliberately crude: a period/semicolon/colon followed by whitespace
# and a capital or digit. Abbreviations ("e.g.", "vs.", "approx.") over-split, which
# only ever loses a candidate, never invents one.
SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9])")


def slug_of(url: str) -> str:
    """A stored page's filename stem for an article URL.

    Mirrors ``fetch_wikipedia_pharmacology.slugify`` (which names the files) without
    importing it: that script is a ``uv run`` module with third-party deps, and this
    one is stdlib-only so it runs alongside the offline generator.
    """
    title = urllib.parse.unquote(url.rsplit("/wiki/", 1)[-1])
    return re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")


# A drug whose article URL is a **redirect**: the store names the file after the
# resolved title, so the slug computed from our URL does not exist on disk. Listed
# rather than guessed, because a near-miss would silently read the wrong article.
PAGE_ALIASES: dict[str, str] = {
    "benztropine": "benzatropine",
    "brexanolone": "allopregnanolone",
    "caprylidene": "axona",
    "flupenthixol": "flupentixol",
    "lithium": "lithium_medication",
    "loflazepate": "ethyl_loflazepate",
    "thiothixene": "tiotixene",
    "dmt": "dimethyltryptamine",
    "lsd": "lsd",
}


def page_for(drug: dict) -> str | None:
    """The stored article path for a drug, or None when it was never fetched."""
    slug = PAGE_ALIASES.get(drug["id"]) or slug_of(drug.get("wikipedia") or "")
    if not slug:
        return None
    path = os.path.join(PAGES, f"{slug}.md")
    return path if os.path.exists(path) else None
