"""The registry of drug-level effect kinds (``data_generators.drug_effects.DrugEffectKind``).

Order is the drug panel's section order. Every consumer loops over :data:`KINDS`, so a new
kind is its vocabulary module plus one line here.

Built with the help of Claude Code.
"""
from __future__ import annotations

from . import seizure_threshold

KINDS = (seizure_threshold.KIND,)
BY_FIELD = {k.field: k for k in KINDS}
