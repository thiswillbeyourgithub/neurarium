"""The corpus #9 store: fetch, write and read one drug's English Wikipedia article.

Corpus #9 keeps every drug's article author-side (see ``CLAUDE.local.md``), and this
module is the one place that knows how that store is shaped (``fetch_page`` +
``store_page`` write it, ``stored_meta`` reads a raw page's header back): which file
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

import datetime
import json
import os
import re
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(REPO, "data_sources", "wikipedia")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PAGES_DIR = os.path.join(DATA_DIR, "pages")
META_PATH = os.path.join(REPO, "public", "data", "meta.json")

from lib.page_file import page_path  # noqa: E402 (refuses a path-like page)
from lib import polite_http  # noqa: E402  (the one polite GET + User-Agent)
from data_generators.drugs import ENZYMES  # noqa: E402  (stdlib-only module)

# The isoform ids the dataset models: ENZYMES itself, so a newly modeled isoform is
# offered to the judge with no second list to keep in step.
KNOWN_ENZYMES = frozenset(ENZYMES)

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


def title_slug(title: str) -> str:
    """A stored page's filename stem for an article title (the one slug rule).

    ``store_page`` (which names the files) delegates here, so
    the writer and every stdlib reader agree. Greek letters are spelled out first, or
    "δ-opioid receptor" and "κ-opioid receptor" would both collapse to ``opioid_receptor``.
    """
    from lib.target_aliases import GREEK_TO_LATIN  # lazy: only a slug needs the map
    t = title.strip()
    for greek, latin in GREEK_TO_LATIN.items():
        t = t.replace(greek, latin)
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def slug_of(url: str) -> str:
    """A stored page's filename stem for an article URL (see :func:`title_slug`)."""
    return title_slug(urllib.parse.unquote(url.rsplit("/wiki/", 1)[-1]))


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
    path = page_path(PAGES_DIR, slug)
    return path if os.path.exists(path) else None


def load_valid_ids() -> set[str]:
    with open(META_PATH, encoding="utf-8") as f:
        return set(json.load(f)["drug_targets"].keys())


def fetch_page(title: str, lang: str = "en") -> dict:
    """Fetch the rendered article (action=parse) pinned to its current revision.

    `lang` selects the Wikipedia edition (en/fr/...); `langlinks` is returned so a
    caller can hop to the same article on another edition (EN -> FR for brand names).
    """
    api = f"https://{lang}.wikipedia.org/w/api.php"
    q = urllib.parse.urlencode({
        "action": "parse", "page": title, "prop": "text|revid|displaytitle|langlinks",
        "format": "json", "redirects": 1, "formatversion": 2})
    req = polite_http.request(f"{api}?{q}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "error" in data:
        raise SystemExit(f"Wikipedia API error for {title!r} ({lang}): {data['error']}")
    p = data["parse"]
    real = p["title"]
    return {
        "title": real,
        "lang": lang,
        "revid": p["revid"],
        "html": p["text"],
        "langlinks": p.get("langlinks", []),
        "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(real.replace(' ', '_'))}",
        "oldid_url": f"https://{lang}.wikipedia.org/w/index.php?oldid={p['revid']}",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
                      .replace(microsecond=0).isoformat(),
    }


def store_page(page: dict, page_text: str,
               pages_dir: str = PAGES_DIR, raw_dir: str = RAW_DIR) -> tuple[str, str]:
    """Write raw/<slug>.html + pages/<slug>.md, both header-stamped. Returns paths.

    `pages_dir`/`raw_dir` default to the EN store; the FR brand pass points them at
    the FR sibling (pages_fr/, raw_fr/) so each edition keeps its own quote-gate tree.
    """
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(pages_dir, exist_ok=True)
    slug = title_slug(page["title"])
    header = (f"source: {page['url']}\nrevision: {page['revid']}\n"
              f"permalink: {page['oldid_url']}\nfetched_at: {page['fetched_at']}\n")
    raw_path = page_path(raw_dir, slug, ".html")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(f"<!--\n{header}-->\n{page['html']}")
    pages_path = page_path(pages_dir, slug)
    with open(pages_path, "w", encoding="utf-8") as f:
        f.write(f"<!-- {page['title']} -->\n" + header.replace("\n", " | ") + "\n\n"
                + page_text)
    return raw_path, pages_path


HEADER_RE = re.compile(r"revision:\s*(\S+).*?permalink:\s*(\S+)", re.S)


def stored_meta(raw_html: str) -> tuple[str, str]:
    """(revid, permalink) from the header comment we stamped into raw/<slug>.html."""
    m = HEADER_RE.search(raw_html[:400])
    return (m.group(1), m.group(2)) if m else ("", "")
