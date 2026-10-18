"""One closed species vocabulary for every corpus that records what an assay ran in.

Four corpora say which species a fact was measured in, each in its own spelling:

- GtoPdb tissue distribution (#7) and GtoPdb interactions (#11): ``"Rat"``, ``"Human"``
  on the quote node itself (``species``);
- PDSP Ki (#5): an upper-case column on the Ki source (``"GUINEA PIG"``, ``"? HUMAN"``)
  that sometimes names a cell line instead (``"N1E-115"`` is a mouse neuroblastoma);
- Europe PMC (#17): the record's MeSH species descriptors (``"Rats, Wistar"``,
  ``"Macaca mulatta"``), read once by ``fetch_europepmc.py --species`` into the committed
  ``tools/generated_cache/europepmc_species.json``, since the raw records are author-side.

:func:`species_key` folds any of those to one key of :data:`SPECIES` (or ``None`` when the
label is not a species we can name), so the derived ``animal_evidence`` flag
(``data_generators/quotes/uncertainty.py``) asks one question of every corpus: is any of a
claim's evidence human or primate? The viewer labels a key through ``species.<key>`` in
``js/i18n.js``, so a key added here needs both catalogue strings.

Built with the help of Claude Code.
"""
from __future__ import annotations

import re

# key -> is it human or a non-human primate (the evidence the flag never doubts).
SPECIES: dict[str, bool] = {
    "human": True, "monkey": True,
    "rat": False, "mouse": False, "guinea_pig": False, "hamster": False,
    "rabbit": False, "cat": False, "dog": False, "pig": False, "cow": False,
    "sheep": False, "ferret": False, "chicken": False, "opossum": False, "fish": False,
    "leech": False,
}

# Folded label (lower case, single spaces) -> key. Exact labels first; the word rules in
# _WORDS below catch the strain / qualifier variants ("Rats, Sprague-Dawley",
# "NEONATAL RAT", "Mice, Inbred C57BL").
_LABELS: dict[str, str] = {
    "? human": "human",
    # PDSP cell lines standing in for a species: HT-29 is a human colon line, COS-7 an
    # African green monkey kidney line, N1E-115 a mouse neuroblastoma, OK an opossum
    # kidney line.
    "ht29": "human", "c0s-7": "monkey", "cos-7": "monkey", "n1e-115": "mouse",
    "ok": "opossum",
    "theromyzon tessulatum": "leech",
    "calf": "cow", "beef": "cow", "bovine": "cow", "cattle": "cow",
    "swine": "pig", "chick": "chicken",
    "haplorhini": "monkey", "primates": "monkey", "saimiri": "monkey",
    "callithrix": "monkey", "papio": "monkey", "chlorocebus aethiops": "monkey",
    "cricetinae": "hamster", "mesocricetus": "hamster",
}
_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bhumans?\b"), "human"),
    (re.compile(r"\bmacaca\b|\bmonkeys?\b|\bmacaques?\b"), "monkey"),
    (re.compile(r"\brats?\b"), "rat"),
    (re.compile(r"\bmouse\b|\bmice\b"), "mouse"),
    (re.compile(r"\bguinea pigs?\b"), "guinea_pig"),
    (re.compile(r"\bhamsters?\b"), "hamster"),
    (re.compile(r"\brabbits?\b"), "rabbit"),
    (re.compile(r"\bcats?\b"), "cat"),
    (re.compile(r"\bdogs?\b"), "dog"),
    (re.compile(r"\bpigs?\b"), "pig"),
    (re.compile(r"\bsheep\b"), "sheep"),
    (re.compile(r"\bferrets?\b"), "ferret"),
    (re.compile(r"\bchickens?\b"), "chicken"),
    (re.compile(r"\bfish\b|\bzebrafish\b|\bflounders?\b"), "fish"),
)


def species_key(label: str | None) -> str | None:
    """The :data:`SPECIES` key a corpus's species label names, else ``None``."""
    folded = " ".join(str(label or "").lower().split())
    if not folded:
        return None
    if folded in _LABELS:
        return _LABELS[folded]
    if "guinea pig" in folded:          # before the bare "pig" rule below
        return "guinea_pig"
    for pattern, key in _WORDS:
        if pattern.search(folded):
            return key
    return None


def is_primate(key: str) -> bool:
    """True for human and non-human primate evidence (``KeyError`` on an unknown key)."""
    return SPECIES[key]
