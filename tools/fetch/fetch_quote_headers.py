#!/usr/bin/env python
"""Where in the book does a quote sit? (Heading resolution for the book corpora.)

A quote source stores a passage and a page number. That is enough to *check* the
quote, but not enough to *read* it: "Blocking muscarinic cholinergic receptors can
cause dry mouth" reads very differently under **How the Drug Works** (a mechanism
the book attributes to the drug) than under **How Drug Causes Side Effects** (a
rule the book prints without a subject). The reader gets that context in the source
tooltip, and an LLM judge gets it in its prompt, only if we store it.

This resolves, for every stored quote from a paged **book** corpus, the breadcrumb
**trail** of headings the passage sits under, and writes them to the committed
``tools/generated_cache/quote_headers.json``, which ``data_generators/quote_table.py``
merges onto the quote nodes by id (exactly like ``quote_llm.json``: a derived
annotation applied uniformly, never authored per site).

A trail is a plain list of strings, outermost first (``["CLOZAPINE", "Side effects",
"How Drug Causes Side Effects"]``), capped to its ``MAX_TRAIL`` deepest levels. A
list rather than named levels because the books do not share a shape: Stahl is a
drug monograph with two heading levels, Kandel a part/chapter/section hierarchy,
Nieuwenhuys a flat list of chapters. The viewer just joins it.

Two resolvers, picked per corpus:

* **Stahl** (corpus #1) has no usable PDF outline, but its pages are regular, so the
  trail is read off the page text itself: the monograph title from the generated
  ``INDEX.md``, then the section > subsection headings above the quote's offset.
  Why not simply "the nearest heading above"? The PDF extraction drops ~30 of the
  158 section headings, and the nearest surviving one then leaks in from the
  previous section (or, at a monograph boundary, from the previous *drug*). But
  Stahl's subsection vocabulary is closed and stable: ``Class`` is under THERAPEUTICS
  in all 158 monographs, ``Pharmacokinetics`` under DOSING AND USE. So the section
  comes from a ``subsection -> section`` majority vote over the whole book, falling
  back to the positional answer only for a subsection too rare to vote on.
* **Every other book** (Kandel, Stahl Essential, Carlat, Nieuwenhuys) ships a real
  PDF outline, already extracted into its ``INDEX.md`` as an indented list of
  ``- [Title](pages/N.md)`` rows. The trail is that outline's ancestor chain for the
  deepest entry starting at or before the cited page. Page-level precision is out of
  reach there (the outline knows chapters, not paragraphs), which is honest: the
  trail says which chapter, and does not pretend to know which paragraph.

Run it from the repo root, author-side (it needs the uncommitted page trees, see
CLAUDE.local.md), after ``generate_data.py`` has emitted the quote table:

    python tools/fetch/fetch_quote_headers.py            # rewrite the cache
    python tools/fetch/fetch_quote_headers.py --dry-run  # report, write nothing

Then re-run ``generate_data.py`` to bake the headings into the emitted quotes.
Deterministic and offline (it only reads files), so a re-run with unchanged pages
rewrites an identical cache. A corpus whose book is absent from this checkout keeps
whatever the cache already holds for it, so running on a partial clone never
silently drops another machine's work. Written with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

import check_data  # noqa: E402  (reuse the quote gate's normalizer + INDEX parser)

STAHL = "stahl"
META = os.path.join(REPO, "public", "data", "meta.json")
QUOTES = os.path.join(REPO, "public", "data", "quotes.jsonl")
CACHE = os.path.join(REPO, "tools", "generated_cache", "quote_headers.json")

# The deepest levels of a trail worth showing. Kandel nests book > part > chapter >
# section: the book title is not a location, and a four-part breadcrumb is a wall.
MAX_TRAIL = 3

_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_HYPHEN_BREAK = re.compile(r"-\s*\n\s*")
# An INDEX.md outline row, two spaces of indentation per outline level.
_OUTLINE_ROW = re.compile(r"^(\s*)-\s+\[(.+)\]\(pages/(\d+)\.md\)")

# Stahl's closed set of monograph sections, in the order the book prints them.
# Matched **case-sensitively** inside a heading, which is what separates the
# section "SIDE EFFECTS" from the subsection "How Drug Causes Side Effects": the
# book prints a section in caps and a subsection in title case, so a case-blind
# substring test (the first thing tried) mislabels four subsections per monograph.
SECTIONS = (
    "THE ART OF PSYCHOPHARMACOLOGY",
    "THE ART OF SWITCHING",
    "SAFETY AND TOLERABILITY",
    "SPECIAL POPULATIONS",
    "DEPOT FORMULATIONS",
    "SUGGESTED READING",
    "DOSING AND USE",
    "SIDE EFFECTS",
    "THERAPEUTICS",
)

# A subsection name seen fewer times than this across the 158 monographs is not
# voted on (it is either monograph-specific or an OCR artifact); its section falls
# back to the positional answer.
MIN_VOTES = 3


def book_corpora() -> dict[str, str]:
    """``corpus -> absolute pages dir``, for the paged corpora that are books.

    A book is exactly a paged corpus whose page tree has a generated ``INDEX.md``
    sibling, which is what tells chapters from the flat page stores (GtoPdb, Allen,
    Wikipedia) where "the heading above this quote" has no meaning.
    """
    with open(META, encoding="utf-8") as fh:
        corpora = json.load(fh).get("source_corpora", {})
    out = {}
    for name, entry in corpora.items():
        pages = entry.get("pages_dir")
        if not pages:
            continue
        pages = os.path.join(REPO, pages)
        if os.path.exists(os.path.join(os.path.dirname(pages), "INDEX.md")):
            out[name] = pages
    return out


def _clean(text: str) -> str:
    """A heading line stripped of markdown/OCR decoration, whitespace collapsed.

    A ``~~struck~~`` span is dropped **whole**: the extraction wraps the fragments
    it read off the page furniture that way (``## ~~Co~~ **THERAPEUTICS**``), and
    keeping the letters would leave "Co" glued to the heading name."""
    text = re.sub(r"~~.*?~~", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[*_#~\[\]|]", " ", text)).strip()


def _subsection(text: str) -> str:
    """A subsection heading trimmed of the content the extraction merged into it
    (``Brands • Ingrezza`` -> ``Brands``)."""
    return re.split(r"\s*•\s*", text)[0].strip(" :-")


def classify(text: str, drug_names: set[str]) -> tuple[str, str | None, str | None]:
    """Classify one cleaned heading -> ``(kind, name, trailing subsection)``.

    ``kind`` is ``section`` (name = the canonical section), ``drug`` (a monograph
    title, which ends the previous monograph's headings), ``sub`` (a subsection) or
    ``noise`` (a stray page number or extraction fragment).
    """
    for section in SECTIONS:
        at = text.find(section)
        if at >= 0:
            # "DOSING AND USE Usual Dosage Range" merges a section + its first
            # subsection onto one line; "LEE DOSING AND USE" is OCR spill before it.
            tail = _subsection(_clean(text[at + len(section):]))
            return "section", section, (tail or None)
    if check_data.normalize_for_match(text) in drug_names:
        return "drug", text, None
    letters = re.sub(r"[^A-Za-z]", "", text)
    if not letters or letters.isupper():
        return "noise", None, None
    return "sub", _subsection(text), None


class StahlPages:
    """The Stahl page tree, indexed once: headings + normalized text per page.

    Callers outside this script (a worklist builder wanting to hand an LLM judge the
    section a candidate quote sits in) should use :meth:`locate`.
    """

    def __init__(self, pages_dir: str) -> None:
        self.pages_dir = pages_dir
        ranges = check_data.stahl_monograph_ranges()
        self.ok = bool(ranges) and os.path.isdir(pages_dir)
        self.drug_names: set[str] = set()
        self.page_drug: dict[int, str] = {}
        self.page_span: dict[int, tuple[int, int]] = {}
        self._pages: dict[int, tuple[list, str]] = {}
        self._section_of: dict[str, str] | None = None
        if not self.ok:
            return
        for title, lo, hi in check_data.stahl_index_rows():
            self.drug_names.add(check_data.normalize_for_match(title))
            for page in range(lo, hi + 1):
                self.page_drug[page] = title
                self.page_span[page] = (lo, hi)

    def page(self, page: int) -> tuple[list, str]:
        """``([(offset, kind, name, tail)], normalized page text)``.

        The offsets index the same normalized string the quote gate matches
        against, so "which heading is above this quote" is a plain comparison.
        The one normalization rule that spans lines (joining a hyphenated line
        break) is applied to the whole page first, which keeps the reconstruction
        byte-identical to ``normalize_for_match`` over the whole file.
        """
        if page not in self._pages:
            path = os.path.join(self.pages_dir, f"{page}.md")
            if not os.path.exists(path):
                self._pages[page] = ([], "")
                return self._pages[page]
            with open(path, encoding="utf-8") as fh:
                raw = _HYPHEN_BREAK.sub("", fh.read())
            marks, parts, offset = [], [], 0
            for line in raw.splitlines():
                head = _HEADING.match(line)
                body = check_data.normalize_for_match(
                    head.group(1) if head else line)
                if head:
                    marks.append((offset,) + classify(_clean(head.group(1)),
                                                      self.drug_names))
                if body:
                    parts.append(body)
                    offset += len(body) + 1
            self._pages[page] = (marks, " ".join(parts))
        return self._pages[page]

    @property
    def section_of(self) -> dict[str, str]:
        """``subsection -> section``, by majority vote over every monograph."""
        if self._section_of is None:
            votes: dict[str, collections.Counter] = collections.defaultdict(
                collections.Counter)
            for lo, hi in set(self.page_span.values()):
                section = None
                for page in range(lo, hi + 1):
                    for _off, kind, name, tail in self.page(page)[0]:
                        if kind == "section":
                            section = name
                            if tail:
                                votes[tail][section] += 1
                        elif kind == "sub" and section:
                            votes[name][section] += 1
            self._section_of = {
                sub: counter.most_common(1)[0][0]
                for sub, counter in votes.items()
                if sum(counter.values()) >= MIN_VOTES
            }
        return self._section_of

    def locate(self, page: int, quote: str) -> list[str]:
        """``[drug, section, subsection]`` for a quote on ``page``, or ``[]``.

        Only the levels it can actually resolve are present (always in that order,
        so the drug leads): a heading it cannot pin down is **omitted**, never
        guessed, so a reader never sees a confidently wrong breadcrumb.
        """
        if not self.ok:
            return []
        marks, text = self.page(page)
        at = text.find(check_data.normalize_for_match(quote))
        if at < 0:
            return []
        sub = positional = None
        for offset, kind, name, tail in marks:
            if offset > at:
                break
            if kind == "drug":
                sub = positional = None
            elif kind == "section":
                positional, sub = name, tail
            elif kind == "sub":
                sub = name
        lo, _hi = self.page_span.get(page, (page, page))
        back = page - 1
        while sub is None and back >= lo:      # a page opening mid-section, but
            for _off, kind, name, tail in self.page(back)[0]:   # never out of the
                if kind == "drug":                              # monograph
                    sub, positional = None, None
                elif kind == "section":
                    positional, sub = name, tail or sub
                elif kind == "sub":
                    sub = name
            back -= 1
        section = self.section_of.get(sub) if sub else None
        if section is None and sub is None:
            section = positional      # no subsection to vote with; take the page's
        # Sentence-cased here rather than in the viewer: the book prints a section
        # in caps for layout, which reads as shouting inside a breadcrumb, and the
        # trail should be renderable by a plain join wherever it is shown.
        return [part for part in (self.page_drug.get(page),
                                  section.capitalize() if section else None,
                                  sub) if part]


class OutlineIndex:
    """A book's ``INDEX.md`` outline, read as ``page -> ancestor chain``.

    The outline rows are contiguous by construction (the PDF's own table of
    contents), so the entry a page belongs to is the deepest one starting at or
    before it, and its ancestors are the enclosing chapter/part.
    """

    def __init__(self, index_path: str) -> None:
        self.entries: list[tuple[int, list[str]]] = []   # (start page, chain)
        stack: list[str] = []
        try:
            with open(index_path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            self.ok = False
            return
        for line in lines:
            row = _OUTLINE_ROW.match(line)
            if not row:
                continue
            level = len(row.group(1)) // 2
            del stack[level:]
            stack.append(self._title(row.group(2)))
            self.entries.append((int(row.group(3)), list(stack)))
        self.ok = bool(self.entries)

    @staticmethod
    def _title(text: str) -> str:
        """One outline title, tidied for display.

        Nieuwenhuys' outline is a list of the per-chapter PDFs it was assembled
        from ("15.Telencephalon Neocortex.pdf"), so drop the extension and give the
        chapter number its space back; every other book's titles come through
        untouched."""
        text = re.sub(r"\.pdf$", "", text.strip(), flags=re.I)
        return re.sub(r"^(\d+)\.(?=\S)", r"\1. ", text).strip()

    def locate(self, page: int, quote: str = "") -> list[str]:
        """The heading trail for ``page``, deepest ``MAX_TRAIL`` levels."""
        if not self.ok:
            return []
        chain: list[str] = []
        for start, entry in self.entries:
            if start > page:
                break
            chain = entry
        return chain[-MAX_TRAIL:]


def resolver(corpus: str, pages_dir: str):
    """The locator for one book corpus, or ``None`` if its material is absent."""
    if corpus == STAHL:
        pages = StahlPages(pages_dir)
        return pages if pages.ok else None
    index = OutlineIndex(os.path.join(os.path.dirname(pages_dir), "INDEX.md"))
    return index if index.ok else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be written, change nothing")
    args = ap.parse_args()

    if not os.path.exists(QUOTES):
        print(f"{QUOTES} missing; run tools/generate_data.py first.")
        return 1
    books = book_corpora()
    if not books:
        print("no book page trees in this checkout (author-side material, see "
              "CLAUDE.local.md); nothing to do.")
        return 1

    quotes = []
    with open(QUOTES, encoding="utf-8") as fh:
        for line in fh:
            q = json.loads(line)
            if q.get("corpus") in books and q.get("page") is not None:
                quotes.append(q)

    try:
        with open(CACHE, encoding="utf-8") as fh:
            previous = json.load(fh)
    except (OSError, ValueError):
        previous = {}
    kept = previous.get("quotes") or {}

    resolved, sections = {}, previous.get("sections") or {}
    for corpus, pages_dir in sorted(books.items()):
        mine = [q for q in quotes if q["corpus"] == corpus]
        if not mine:
            continue
        loc = resolver(corpus, pages_dir)
        if loc is None:
            carried = {q["id"]: kept[q["id"]] for q in mine if q["id"] in kept}
            resolved.update(carried)
            print(f"{corpus}: page material absent; kept the {len(carried)} cached "
                  f"trail(s) of its {len(mine)} quotes")
            continue
        if isinstance(loc, StahlPages):
            sections = dict(sorted(loc.section_of.items()))
        found = unresolved = 0
        for q in mine:
            trail = loc.locate(q["page"], q.get("quote") or "")
            if trail:
                resolved[q["id"]] = trail
                found += 1
            else:
                unresolved += 1
                if unresolved <= 3:
                    print(f"  unresolved  {corpus} p.{q['page']}  "
                          f"{(q.get('quote') or '')[:60]!r}")
        depth = collections.Counter(len(resolved[q["id"]]) for q in mine
                                    if q["id"] in resolved)
        print(f"{corpus}: {found}/{len(mine)} quotes located "
              f"(trail depth " +
              ", ".join(f"{n} level(s): {c}" for n, c in sorted(depth.items())) +
              (f"; {unresolved} unresolved)" if unresolved else ")"))

    payload = {
        "_readme": ("Derived by tools/fetch/fetch_quote_headers.py from the "
                    "author-side book page trees; applied onto the quote nodes by "
                    "data_generators/quote_table.py. Do not hand-edit."),
        "sections": sections,
        "quotes": {qid: resolved[qid] for qid in sorted(resolved)},
    }
    if args.dry_run:
        print("--dry-run: cache not written")
        return 0
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")
    print(f"wrote {CACHE} ({len(resolved)} trails)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
