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
from typing import Any

# Accumulated quote nodes: quote_id -> {"id", "corpus", "page", "quote", "species"?}.
QUOTES: dict[str, dict[str, Any]] = {}

# The excerpt-identity fields (hash input + what the quote node carries). ``provenance``
# is deliberately excluded: it grades the claim, not the quote (see module docstring).
_IDENTITY_FIELDS = ("corpus", "page", "quote", "species")


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
        for k in _IDENTITY_FIELDS:
            if k in obj:
                entry[k] = obj[k]
        existing = QUOTES.get(qid)
        if existing is not None and existing != entry:
            raise ValueError(
                f"quote id collision: {qid} maps to both {existing!r} and {entry!r}"
            )
        QUOTES[qid] = entry
        ref: dict[str, Any] = {"quote_id": qid}
        for k, v in obj.items():
            if k not in _IDENTITY_FIELDS:
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
