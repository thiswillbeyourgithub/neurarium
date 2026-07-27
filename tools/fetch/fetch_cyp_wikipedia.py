#!/usr/bin/env python
"""Extract cytochrome-P450 roles from a drug's English Wikipedia article (corpus #9).

The complement to ``fetch_cyp.py``, which reads Stahl's Pharmacokinetics block and so
covers only Stahl's 158-drug roster. 149 of our 235 drugs have no Stahl enzyme line at
all: the European benzodiazepines, the barbiturates, the recreational agents, and
everything else the roster pass added. Their English Wikipedia articles are already
stored author-side under ``data_sources/wikipedia/pages/`` (fetched for corpus #9's
binding tables), so this pass reads pages that are already on disk.

Like ``fetch_cyp.py`` this needs **no LLM**, because it leans on the one part of a
Wikipedia drug article that is as regular as a Stahl bullet: the **drugbox
``Metabolism`` row**, flattened into the stored page as a single ``Metabolism | ...``
line::

    Metabolism | Liver , mostly CYP2D6 -mediated
    Metabolism | Liver ( CYP1A2 )
    Metabolism | Primary: CYP1A2 Minor: CYP2E1 , CYP3A4 , CYP2C8 , CYP2C9

That row states what metabolises the drug, so every isoform in it is a ``substrate``
claim, and the row itself is the verbatim quote. Article **prose** is read too, but
under three constraints Stahl's terse bullets never needed, because a Wikipedia
paragraph is long and talks about other molecules constantly:

* **sentence granularity.** The stored page keeps a whole paragraph on one line, so a
  paragraph is split into sentences first. Matching a paragraph pairs an unrelated
  "metabolized by" with an unrelated isoform three sentences away (amitriptyline's
  absorption paragraph, haloperidol's protein-binding one).
* **the drug must be named before the verb.** Not merely present: "Smoking induces
  CYP1A2 enzyme activity, which accelerates the metabolism of clozapine" names
  clozapine, and reading it as clozapine inducing CYP1A2 inverts the claim.
* **a negation veto.** Wikipedia states the absence of a route as often as its
  presence ("metabolized in the liver by hydrolysis, without involvement of CYP2D6"),
  and a pattern match cannot see the "without".

Precision over yield, same as the Stahl pass. On top of the three rules above: a
sentence about *other* drugs acting on this one is vetoed (``VICTIM_RE``, imported);
a reference-list line is skipped (a cited paper's title names roles it does not
assert *here*); an isoform our ``ENZYMES`` vocabulary does not carry is skipped
(midazolam's row names the obsolete CYP3A3), so the cache never proposes a row the
build would reject; and every accepted line is re-confirmed **verbatim** on the
stored page with ``check_data``'s own normalizer, so ``check_data.py``'s gate passes
unchanged.

Stahl still wins: ``generate_data.py`` merges this cache **after** the Stahl one and
keeps the existing row for any (enzyme, role) pair Stahl already states.

Output: ``tools/generated_cache/drug_enzymes_wikipedia.json``, committed and read at
build time, so the emitted data stays reproducible on a clone with no author-side tree.

Usage (from the repo root):
    python tools/fetch/fetch_cyp_wikipedia.py            # rewrite the cache
    python tools/fetch/fetch_cyp_wikipedia.py --dry-run  # report only
    python tools/fetch/fetch_cyp_wikipedia.py --verbose  # also list every dropped line

Built with the help of Claude Code.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)

import check_data  # noqa: E402  (reuse the quote gate's normalizer, one definition)
import drugs_io  # noqa: E402
from fetch_cyp import (  # noqa: E402  (one definition of each shared rule)
    CYP_RE,
    ROLE_PATTERNS,
    ROLE_STRENGTHS,
    STRENGTH_RE,
    VICTIM_RE,
    isoforms,
)

PAGES = os.path.join(REPO, "data_sources", "wikipedia", "pages")
OUT = os.path.join(REPO, "tools", "generated_cache", "drug_enzymes_wikipedia.json")

# The isoform ids the dataset models (mirrors ENZYMES in data_generators/drugs.py; not
# imported because this script must run with only the repo's stdlib path set up).
KNOWN_ENZYMES = {"cyp1a2", "cyp2a6", "cyp2b6", "cyp2c8", "cyp2c9", "cyp2c19",
                 "cyp2d6", "cyp2e1", "cyp3a4", "cyp3a5"}

# The flattened drugbox row. `pageimages`-style tables come through as "cell | cell",
# so the metabolism field is a line whose first cell is exactly "Metabolism".
INFOBOX_RE = re.compile(r"^\s*Metabolism\s*\|\s*(.+)$")

# Wikipedia states the *absence* of a route as often as its presence, which a
# subject-is-the-drug pattern cannot see. Vetoes the whole line.
NEGATION_RE = re.compile(
    r"\bwithout\b|\bnot\s+(?:a\s+)?(?:metaboli|substrate|inhibit|induc|appear|"
    r"believed|thought|significantly|extensively)|\bno\s+(?:significant\s+)?"
    r"(?:involvement|inhibition|induction|effect)|\bnegligible\b|\bunlikely\b|"
    r"\bdoes not\b|\bdo not\b|\bindependent of\b|\brather than\b|\bfree of\b",
    re.I)

# A drugbox row qualifier -> the substrate tier it states. Checked against the text
# preceding the first isoform only, exactly like the Stahl pass, so "primarily via
# CYP2D6" is major while "Primary: CYP1A2 Minor: CYP2E1" (which qualifies each half
# separately) yields no tier at all rather than the wrong one on the wrong isoform.
INFOBOX_STRENGTH = [
    ("major", re.compile(r"\bprimar(?:y|ily)|mainly|mostly|major|extensiv", re.I)),
    ("minor", re.compile(r"\bminor\b|\bpartly\b|\bin part\b", re.I)),
]

# A reference-list entry ("- ^ Gram LF ... 'Moclobemide, a substrate of CYP2C19 ...'").
# The cited paper's title states a role, but the article is not asserting it here, and
# a title is not a sentence about the drug: skip rather than quote a bibliography.
REFERENCE_RE = re.compile(r"^\s*-\s*\^|^\s*\^\s|\bdoi\s*:|\bPMID\b|\bISBN\b")

# Sentence split, deliberately crude: a period/semicolon/colon followed by whitespace
# and a capital or digit. Abbreviations ("e.g.", "vs.", "approx.") over-split, which
# only ever loses a candidate, never invents one.
SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9])")

# The victim frames `VICTIM_RE` (written for Stahl's terse bullets) does not carry,
# all seen misfiring on real Wikipedia prose: a sentence about the *class* of drugs an
# isoform handles ("may interact with medications that are metabolized by CYP3A4"), or
# about what this drug does to another one's level ("increase serum concentrations of
# mirtazapine, which is mainly metabolized by CYP1A2").
WIKI_VICTIM_RE = re.compile(
    r"concentrations of|\b(?:drugs|medications|substrates|agents)\b"
    r"(?:\s+\S+){0,4}?\s*metaboli|\bis formed from\b|\bformed from\b", re.I)

# Between the drug's name and the verb, any of these means the verb's real subject is
# something else the sentence introduced in between: a relative clause ("mirtazapine,
# which is mainly metabolized by ..."), a parenthetical ("dextromethorphan (a drug
# that is mainly metabolized by CYP2D6)"), or an apposition ("interacts with the
# antibiotic erythromycin, a strong inhibitor of CYP3A4"). A genuine subject-verb
# pair has none of them in between: "Buprenorphine is metabolized by ...".
HEAD_BREAK_RE = re.compile(r"\bwhich\b|\bthat\b|\(|,", re.I)


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


def qualifier(text: str, table: list, allowed: set[str]) -> str | None:
    """The single strength tier a line states before its first isoform, else None."""
    first = CYP_RE.search(text)
    head = text[: first.start()] if first else text
    present = {s for s, pat in table if s in allowed and pat.search(text)}
    if len(present) != 1:
        return None
    tier = present.pop()
    return tier if dict(table)[tier].search(head) else None


def subject_names(drug: dict, page: str) -> list[re.Pattern]:
    """The tokens that count as "this drug" as a sentence's subject, as \\b patterns.

    Its dataset name and its article slug, both lowercased, so "Dextroamphetamine is
    metabolized ..." counts for the drug we call ``amphetamine_d``. A combo drug's
    name ("A + B") contributes each constituent.

    Word-bounded on purpose: a metabolite's name usually *contains* its parent's
    ("N-desmethylclobazam"), and a plain substring test would read a sentence about
    the metabolite as a sentence about the drug.
    """
    names = {page.replace("_", " ").lower()}
    for part in re.split(r"\s*\+\s*", drug.get("name") or ""):
        part = part.strip().lower()
        if len(part) >= 5:
            names.add(part)
    return [re.compile(r"\b" + re.escape(n) + r"\b")
            for n in sorted(names) if len(n) >= 5]


def claims(text: str, names: list[re.Pattern]) -> list[tuple[str, str, str | None]]:
    """Every (quote, role, strength) claim a page states about the drug itself."""
    out: list[tuple[str, str, str | None]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not CYP_RE.search(line):
            continue
        infobox = INFOBOX_RE.match(line)
        if infobox:
            # The drugbox metabolism field: what metabolises the drug, so substrate.
            # No subject check needed, the row's subject is the article's own drug.
            if not NEGATION_RE.search(line):
                out.append((line, "substrate",
                            qualifier(infobox.group(1), INFOBOX_STRENGTH,
                                      {"major", "minor"})))
            continue
        if REFERENCE_RE.search(line):
            continue
        for sentence in SENTENCE_SPLIT.split(line):
            sentence = sentence.strip()
            if not CYP_RE.search(sentence) or NEGATION_RE.search(sentence):
                continue
            if VICTIM_RE.search(sentence) or WIKI_VICTIM_RE.search(sentence):
                continue
            hits = [(pat.search(sentence), role) for role, pat in ROLE_PATTERNS]
            hits = [(m, role) for m, role in hits if m]
            # A sentence stating two roles at once ("a weak inducer of CYP3A4 and a
            # weak inhibitor of CYP2C19") cannot be split by isoform without guessing
            # which half owns which, so it is dropped rather than half-attributed.
            if len(hits) != 1:
                continue
            hit, role = hits[0]
            # The drug must be named BEFORE the verb, with nothing in between that
            # hands the verb a different subject.
            head = sentence[: hit.start()].lower()
            ends = [m.end() for pat in names for m in pat.finditer(head)]
            if not ends or HEAD_BREAK_RE.search(head[max(ends):]):
                continue
            out.append((sentence, role,
                        qualifier(sentence, STRENGTH_RE, ROLE_STRENGTHS[role])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--verbose", action="store_true", help="list dropped lines too")
    args = ap.parse_args()

    if not os.path.isdir(PAGES):
        print(f"missing author-side Wikipedia tree ({PAGES}); see CLAUDE.local.md")
        return 1

    out: dict[str, list[dict]] = {}
    stats: collections.Counter = collections.Counter()
    dropped = []
    for drug in drugs_io.load_drugs():
        path = page_for(drug)
        if path is None:
            stats["drug: no stored article"] += 1
            continue
        text = open(path, encoding="utf-8").read()
        page = os.path.splitext(os.path.basename(path))[0]
        normalized = check_data.normalize_for_match(text)
        rows: dict[tuple[str, str], dict] = {}
        for line, role, strength in claims(text, subject_names(drug, page)):
            if check_data.normalize_for_match(line) not in normalized:
                stats["line: quote not verbatim on the page"] += 1
                dropped.append((drug["id"], "gate", line))
                continue
            for enzyme in isoforms(line):
                if enzyme not in KNOWN_ENZYMES:
                    stats[f"line: isoform not modeled ({enzyme})"] += 1
                    continue
                key = (enzyme, role)
                if key in rows:                # same claim twice: keep the first quote
                    continue
                row = {"enzyme": enzyme, "role": role}
                if strength:
                    row["strength"] = strength
                row["sources"] = [{"corpus": "wikipedia_pharm", "page": page,
                                   "quote": line, "provenance": "verified"}]
                rows[key] = row
                stats[f"node: {role}"] += 1
        if rows:
            out[drug["id"]] = [rows[k] for k in sorted(rows)]

    print(f"{len(out)} drugs, {sum(len(v) for v in out.values())} enzyme nodes")
    for key, n in sorted(stats.items()):
        print(f"  {key:<44} {n}")
    iso = collections.Counter(r["enzyme"] for v in out.values() for r in v)
    print("  isoforms:", ", ".join(f"{k}={n}" for k, n in iso.most_common()))
    if args.verbose:
        print("\ndropped lines:")
        for did, why, line in dropped:
            print(f"  [{why}] {did}: {line[:110]}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"\nwrote {os.path.relpath(OUT, REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
