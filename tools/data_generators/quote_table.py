"""data_generators.quote_table: serialization-time quote externalization.

Every sourceable node embeds its provenance **source** inline. A quote-bearing
source is an object like ``{"corpus", "page", "quote", "provenance"}`` (location
sources also carry ``"species"``). The same verbatim quote is frequently cited by
many nodes (e.g. one Stahl side-effect line backs all four alpha-1 subtype
bindings), so embedding the text inline duplicates it.

This pass mirrors the i18n :func:`externalize` pass: at SERIALIZATION time every
quote-bearing source is collapsed to a reference ``{"quote_id", "provenance"}``
and the immutable excerpt ``{"id", "corpus", "page", "quote", "species"?}`` is
collected once into :data:`QUOTES`, written out as ``public/data/quotes.jsonl``.
The viewer + ``check_data.py`` rehydrate it back in memory, so nothing downstream
sees the dehydrated shape.

The id is a **deterministic content hash** of the excerpt identity
(corpus + page + quote + species), so identical excerpts dedupe to one entry and
the id never churns across regenerations (the emitted data is committed and we
want minimal diffs). ``provenance`` is a per-*claim* grade, not part of the quote,
so it stays on the referencing node. Made with the help of Claude Code.
"""
import hashlib
import json
import os
from typing import Any

# Accumulated quote nodes: quote_id -> {"id", "corpus", "page", "quote", "species"?, "llm"?}.
QUOTES: dict[str, dict[str, Any]] = {}

# Central quote_id -> sourcing-llm overrides, written by tools/sourcing/recheck_quotes.py
# (a Sonnet recheck that confirmed the quote is present + supports its claim). Applied
# uniformly by id in externalize_quotes, so one recheck pass stamps every kind of quote
# without editing each authoring site. An override WINS over a source-level ``llm`` (it is
# the most recent verification); a quote absent from the map keeps its source llm, else
# reads as unknown. Loaded once from the committed generated_cache (best-effort: absent = {}).
_LLM_OVERRIDES: dict[str, str] = {}


def _load_llm_overrides() -> dict[str, str]:
    path = os.path.join(
        os.path.dirname(__file__), "..", "generated_cache", "quote_llm.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {qid: v for qid, v in data.items() if isinstance(v, str)}
    except (FileNotFoundError, ValueError):
        return {}


_LLM_OVERRIDES = _load_llm_overrides()

# The excerpt-identity fields (hash input + what the quote node carries). ``provenance``
# is deliberately excluded: it grades the claim, not the quote (see module docstring).
_IDENTITY_FIELDS = ("corpus", "page", "quote", "species")

# Non-identity metadata carried onto the quote node but excluded from the id hash: ``llm``
# names the model that sourced the quote (see provenance.SOURCING_LLMS). Kept off the hash
# so re-attributing a quote's sourcing model doesn't churn its id (the excerpt identity is
# the text, not who found it); a genuine llm disagreement on one excerpt is a hard error below.
_METADATA_FIELDS = ("llm",)


def reset_quotes() -> None:
    """Clear the accumulated quote table (call once per generation)."""
    QUOTES.clear()


def _is_quote_source(obj: object) -> bool:
    """True for a source object carrying a verbatim ``quote`` string.

    Ki sources (``{corpus, ki_id, value_nm, ...}``) and bare wikipedia provenance
    (``{provenance}``) have no ``quote`` field, so they pass through untouched.
    """
    return isinstance(obj, dict) and isinstance(obj.get("quote"), str)


def quote_id(source: dict[str, Any]) -> str:
    """Deterministic ``q_<12 hex>`` id from the excerpt identity fields."""
    identity = json.dumps(
        {k: source.get(k) for k in _IDENTITY_FIELDS},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"q_{digest}"


def externalize_quotes(obj):
    """Recursively replace every quote-bearing source with a ``{quote_id, ...}`` ref.

    Registers the excerpt into :data:`QUOTES` (a content-hash collision on two
    genuinely different excerpts is a hard error). The reference keeps
    ``provenance`` (the per-claim grade) and any unexpected sibling keys; recurses
    through plain dicts and lists; other values pass through.
    """
    if _is_quote_source(obj):
        qid = quote_id(obj)
        entry = {"id": qid}
        for k in _IDENTITY_FIELDS + _METADATA_FIELDS:
            if k in obj:
                entry[k] = obj[k]
        # A recheck override wins over any source-level llm (uniform by id -> no collision).
        if qid in _LLM_OVERRIDES:
            entry["llm"] = _LLM_OVERRIDES[qid]
        existing = QUOTES.get(qid)
        if existing is not None and existing != entry:
            raise ValueError(
                f"quote id collision: {qid} maps to both {existing!r} and {entry!r}"
            )
        QUOTES[qid] = entry
        ref: dict[str, Any] = {"quote_id": qid}
        for k, v in obj.items():
            if k not in _IDENTITY_FIELDS and k not in _METADATA_FIELDS:
                ref[k] = externalize_quotes(v)
        return ref
    if isinstance(obj, dict):
        return {k: externalize_quotes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [externalize_quotes(v) for v in obj]
    return obj


def quote_lines() -> list[str]:
    """The accumulated quote table as JSON lines, sorted by id for stable diffs."""
    return [
        json.dumps(QUOTES[qid], ensure_ascii=False)
        for qid in sorted(QUOTES)
    ]
