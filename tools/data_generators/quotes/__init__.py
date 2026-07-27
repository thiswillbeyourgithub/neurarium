"""data_generators.quotes: verified quote registries split out of generate_data.py.

Each module groups the quote registries by source corpus:
- ``kandel``: PROJECTION_QUOTES + STRUCTURE_QUOTES (Kandel / Nieuwenhuys anatomy).
- ``stahl_essential``: the receptor/target classification, per-attribute and tone
  polarity registries (Stahl's Essential Psychopharmacology).
- ``metabolism``: which enzyme forms each active metabolite (Stahl + Wikipedia; the one
  enzyme registry that is hand-curated rather than grepped, see the module docstring).

Dependency chain stays acyclic: provenance <- connectivity <- quotes <- generate_data.
"""
from data_generators.quotes.kandel import (
    PROJECTION_QUOTES,
    STRUCTURE_QUOTES,
)
from data_generators.quotes.metabolism import (
    METABOLITE_ENZYME_QUOTES,
)
from data_generators.quotes.stahl_essential import (
    CLASSIFICATION_ATTRS,
    RECEPTOR_ATTR_QUOTES,
    RECEPTOR_CLASSIFICATION_COVERAGE,
    STAHL_ESSENTIAL_RECEPTOR_QUOTES,
    STAHL_ESSENTIAL_TARGET_QUOTES,
    TARGET_POLARITY_QUOTES,
)

__all__ = [
    "METABOLITE_ENZYME_QUOTES",
    "PROJECTION_QUOTES",
    "STRUCTURE_QUOTES",
    "CLASSIFICATION_ATTRS",
    "RECEPTOR_ATTR_QUOTES",
    "RECEPTOR_CLASSIFICATION_COVERAGE",
    "STAHL_ESSENTIAL_RECEPTOR_QUOTES",
    "STAHL_ESSENTIAL_TARGET_QUOTES",
    "TARGET_POLARITY_QUOTES",
]
