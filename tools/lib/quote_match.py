"""The quote gate's canonical text matcher, shared by every script that checks a
quote against a page file: ``normalize_for_match`` (the one normalizer) and
``emitted_page_dirs`` (the corpus -> page-tree registry read off the emitted meta).

Built with the help of Claude Code.
"""

import json
import re
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "public" / "data"


def normalize_for_match(text):
    """Canonicalize prose for the quote-in-page substring check (see check_sources).

    The PDF->Markdown extraction of the source pages introduces artifacts the raw
    quote will not match verbatim: hard-wrapped lines (a word hyphenated across a
    line break), markdown emphasis/bullets, curly quotes, en/em dashes, accents.
    This folds all of that away deterministically: join hyphenated line breaks,
    NFKD-decompose (so an accent becomes a strippable combining mark), lowercase,
    then collapse every run of non-alphanumerics to a single space. The result is
    still compared with an **exact** substring test, only on a canonical form: no
    fuzzy / similarity matching, which would manufacture false confidence. A miss
    is therefore a real miss to investigate, not a threshold to tune."""
    text = re.sub(r"-\s*\n\s*", "", text)            # join hyphenated line breaks
    # A soft hyphen (U+00AD) is a typesetting break hint, never text: a table cell
    # wrapped at one ("Brexpi­\nprazole") is one word, so it joins like a
    # hyphenated break instead of splitting the word in two.
    text = re.sub("­\\s*", "", text)
    # Inline markup the Markdown split keeps (`<u>` underline in a table cell,
    # `<sup>` around a reference number) is formatting: dropping only the tag keeps
    # its content, so `<u>CYP1A2</u>` reads as the word, not "u cyp1a2 u".
    # A tag INSIDE a word ("9-hydroxyrisperi<u>done)</u>", where the PDF underline
    # starts mid-word) is dropped outright, so the word stays one word.
    text = re.sub(r"(?<=\w)</?(?:u|b|i|em|strong)>(?=\w)", "", text)
    text = re.sub(r"</?(?:u|b|i|em|strong|sup|sub)>", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)          # drops combining marks too
    return " ".join(text.split())


def emitted_page_dirs() -> dict[str, str]:
    """``corpus -> author-side page directory`` (repo-relative), read from the emitted
    ``meta.source_corpora``: the trees the quote gate checks. The one reader of that
    registry for the author-side scripts (recheck / demote / heading resolution), so a
    corpus added to the generator reaches them all at once."""
    corpora = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8")).get(
        "source_corpora", {})
    return {name: entry["pages_dir"] for name, entry in corpora.items()
            if entry.get("pages_dir")}
