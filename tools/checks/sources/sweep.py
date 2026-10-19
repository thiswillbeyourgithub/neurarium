"""Family 5's coverage sweeps: every stored quote, whoever walks it.

The node walks (``walk_drugs``, ``walk_receptors``, ...) gate the quotes of the node
kinds they know, so a quote reaches the page check only if some walk visits its kind,
and a quote that is committed but not emitted (a cache entry for an owner the data no
longer has) reaches no walk at all. These two sweeps close both holes, for every
corpus ``meta.source_corpora`` gives a ``pages_dir`` (no hand list):

* :func:`sweep_quote_table` looks every row of ``quotes.jsonl`` (the one table every
  emitted quote lives in) up on its page;
* :func:`sweep_committed_caches` does the same for every quote-shaped source
  (``{corpus, page, quote}``) committed under ``tools/generated_cache/*.json`` and
  ``tools/data/*.jsonl``, the inputs the generator merges.

Same normalizer and the same skip rule as the walks (``QuoteGate.on_page``): skipped +
warned only when a corpus's page tree is absent (a clone).

Part of the ``tools/check_data.py`` checker (see docs/DATA_CHECKS.md).
"""

import json

# The committed inputs a quote can sit in before (or instead of) being emitted.
CACHE_GLOBS = ("tools/generated_cache/*.json", "tools/data/*.jsonl")


def sweep_quote_table(gate, quotes_by_id):
    """Look every ``quotes.jsonl`` row up on its page. Returns the number found."""
    found = 0
    for qid in sorted(quotes_by_id):
        q = quotes_by_id[qid]
        if isinstance(q.get("quote"), str) and q.get("page") is not None:
            found += bool(gate.on_page(f"quotes.jsonl {qid}", q.get("corpus"),
                                       q["page"], q["quote"]))
    return found


def quote_sources(node, path=""):
    """Yield ``(path, source)`` for every quote-shaped dict nested in ``node``."""
    if isinstance(node, dict):
        if (isinstance(node.get("corpus"), str) and isinstance(node.get("quote"), str)
                and node["quote"] and node.get("page") is not None):
            yield path, node
        for key, value in node.items():
            yield from quote_sources(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from quote_sources(value, f"{path}[{i}]")


def _load(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def sweep_committed_caches(gate, globs=CACHE_GLOBS):
    """Look every committed cache's quote-shaped source up on its page. A source
    naming a corpus the registry does not know is left to the generator (a cache can
    hold worklist candidates of any shape). Returns the number found."""
    found = 0
    for pattern in globs:
        for path in sorted(gate.root.glob(pattern)):
            rel = path.relative_to(gate.root).as_posix()
            for where, src in quote_sources(_load(path)):
                if src["corpus"] in gate.corpora:
                    found += bool(gate.on_page(f"{rel}{where}", src["corpus"],
                                               src["page"], src["quote"]))
    return found
