#!/usr/bin/env python
"""Store a few primary-literature abstracts as corpus #17 (Europe PMC).

Some claims no textbook, label or encyclopedia article on disk states: lithium's brain
half-life being longer than its serum half-life is measured only in the 7Li magnetic
resonance spectroscopy literature. This corpus holds exactly those papers, one abstract
per page, so such a claim is quote-gated like any other instead of being authored from
memory. It is **not** a literature crawl: the papers are the hand-listed :data:`PAPERS`,
each with the claim it was added for, so the corpus never grows without a reason a
reader can see.

What it stores, per PubMed id:

* ``data_sources/europepmc/raw/<pmid>.json`` - the Europe PMC ``core`` search record as
  downloaded, kept so the page can be re-derived without re-fetching.
* ``data_sources/europepmc/pages/<pmid>.md`` - the quote-gate page: a provenance header
  (title, authors, journal, DOI, source URL, fetch date), then the abstract, one
  sentence per line. ``page`` on a quote is the PMID, which resolves to
  ``https://europepmc.org/article/MED/<pmid>``.

The abstract is what Europe PMC serves for every indexed paper (open access or not), and
a short verbatim sentence from it is a citation, like a quoted line of a book. **Open-access
full text** rides along where the record says so (``isOpenAccess: Y`` with a PMC id): the
``fullTextXML`` (JATS) is stored as ``raw/<pmid>.xml`` and flattened after the abstract,
under a ``## Full text`` marker (:func:`full_text_lines`): section headings, body
paragraphs one per line, figure captions, and every table as its caption line then one
``cell | cell | ...`` row per line (the Wikipedia table convention, so a measured Ki can be
quoted as a row), each table between blank lines. The licence comes from the record
(:func:`licence_of`, e.g. ``CC BY-NC``) and is stamped in the page header and on every
source quoting the full text, so it can be credited. Only Europe PMC's own OA copy is read:
never a publisher site. The abstract lines stay first, so a quote gated against an
abstract-only page still gates once the full text is appended. Like every other corpus
tree, ``data_sources/`` is gitignored and author-side: the quote gate is skipped with a
warning on a clone that lacks it.

Usage (from the repo root)::

    python tools/fetch/fetch_europepmc.py                 # every paper in PAPERS
    python tools/fetch/fetch_europepmc.py --only 7827213
    python tools/fetch/fetch_europepmc.py --refresh       # re-download stored records
    python tools/fetch/fetch_europepmc.py --species       # offline: MeSH species ledger

**Species** (``--species``, also run after every fetch): offline, it reads each stored
``raw/<pmid>.json`` record's MeSH species descriptors (``"Rats, Wistar"``, ``"Macaca
mulatta"``, folded by ``tools/species.py``) into the committed
``tools/generated_cache/europepmc_species.json`` (PMID -> sorted species keys, empty when
the record names none), which the generator reads for the ``animal_evidence`` flag since
``raw/`` is author-side.

Network (``www.ebi.ac.uk``), polite and resumable: a paper whose page is on disk is
skipped unless ``--refresh``. Stdlib only.

**The binding search mode, ``--binding-search``**, is the Europe PMC leg of the UNKNOWN search
(``tools/data_generators/unknown.py``): for every binding with no known direction it runs
one query (:func:`direction_query`: the ligand and the target, both required in the
abstract, plus a direction word), stores the top :data:`SEARCH_TOP` abstracts as pages
exactly like a hand-listed paper, and records the query, Europe PMC's hit count and the
PMIDs read in ``tools/generated_cache/europepmc_binding_search.json``. That ledger is the
reason each search-found page exists (the search key it answered), and it is what the
search log cites. Resumable: a binding already in the ledger is skipped unless
``--refresh``; ``--only <drug ids>`` scopes it::

    python tools/fetch/fetch_europepmc.py --binding-search

**``--effect-search``** is the Europe PMC leg of the receptor-effect UNKNOWN search: one
query per receptor with no ``receptor_effect`` node (:func:`effect_query`: the receptor
named in the abstract, plus an action word, an effect word and a human-study word), the top
:data:`EFFECT_SEARCH_TOP` abstracts stored, the query / hit count / PMIDs read recorded in
``tools/generated_cache/europepmc_effect_search.json`` (keyed ``receptor:<id>/effects``).
``tools/fetch/fetch_receptor_effects.py`` then offers their sentences as candidates::

    python tools/fetch/fetch_europepmc.py --effect-search

**The cited-paper mode, ``--ki-prose``**, follows a Wikipedia article's own citations to a
measured affinity its prose states but no table or database carries (viloxazine's
"K i = 3,900 nM and 6,400 nM" at 5-HT2B / 5-HT2C, PDSP and GtoPdb having nothing). For
every drug with a binding that has no Ki, it reads the drug's stored EN article
(``data_sources/wikipedia/raw/<slug>.html``, corpus #9), keeps each paragraph that states
an affinity (:func:`states_affinity`: a Ki / Kd and a concentration), stores the abstracts
of the PubMed ids that paragraph cites, and offers every abstract sentence that itself
states an affinity, with **no verdict**, in ``tools/generated_cache/ki_prose_worklist.json``.
The paragraph is the reason the page exists (it rides along as ``context``), never a
source: the Ki is quoted from the paper. One LLM pass answers by index, and
``tools/sourcing/apply_ki_prose.py`` gates and writes (see its docstring)::

    python tools/fetch/fetch_europepmc.py --ki-prose          # --only <drug ids> scopes

Built with the help of Claude Code.
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                                       # repo root
sys.path.insert(0, str(HERE))

sys.path.insert(0, str(HERE.parent))
from lib.page_file import page_path, read_page_file  # noqa: E402 (refuses a path-like page)
from lib import polite_http                                            # noqa: E402 (the one polite GET)
from lib.species import species_key                                # noqa: E402
from lib.io_atomic import atomic_write_json, atomic_write_text      # noqa: E402

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FULL_TEXT_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
# The line that separates the abstract from the appended open-access full text.
FULL_TEXT_MARKER = "## Full text"
ARTICLE_URL = "https://europepmc.org/article/MED/{pmid}"
RAW_DIR = ROOT / "data_sources" / "europepmc" / "raw"
PAGES_DIR = ROOT / "data_sources" / "europepmc" / "pages"

# PMID -> the claim it is stored for. Add a paper only for a claim nothing else on disk
# states, and say which.
PAPERS: dict[str, str] = {
    "7827213": "lithium: brain half-life (7Li MRS) longer than serum half-life "
               "(addon lithium_brain_half_life)",
    "10360127": "haloperidol: brain-tissue elimination half-life (post-mortem HPLC) far "
                "longer than the serum one (addon haloperidol_brain_half_life)",
    # Primate tract-tracing for the monoamine pathways the books never name (check_data
    # family 10, docs/SOURCING_GAPS.md "Innervation coverage"). Species in each line.
    "27028222": "raphe -> globus pallidus, serotonergic (primate review)",
    "6766111": "raphe + locus coeruleus -> internal pallidum (Macaca mulatta, HRP)",
    "6664490": "locus coeruleus -> caudate + putamen (Saimiri sciureus, retrograde)",
    "6315152": "locus coeruleus -> substantia nigra (Saimiri sciureus, retrograde)",
    "2896323": "VTA -> parietal cortex, dopaminergic (Macaca fascicularis, retrograde)",
    "2860583": "claustrum <-> insula connections (primate + human review)",
    # Transmitter / sign of the pathways no book sentence types (docs/SOURCING_GAPS.md
    # section 6). Species in each line; primate/human where one exists.
    "1374872": "frontal cortex -> pons: glutamatergic corticopontine fibres (review)",
    "173563": "frontal cortex -> pons: corticopontine excitation (cat)",
    "9133571": "pons -> cerebellum: excitatory mossy-fibre projection (rat)",
    "2422596": "pons -> cerebellum: glutamate in pontocerebellar fibres (rat)",
    "6147261": "cerebellum -> thalamus: glutamate in cerebellothalamic fibres (cat)",
    "15558250": "cerebellum -> thalamus: excitatory cerebellothalamic path (human)",
    "20421986": "entorhinal (temporal) -> hippocampus: glutamatergic perforant path (rat)",
    "1981215": "hippocampus -> fornix: excitatory hippocamposeptal fibres (rat)",
    "32019": "fornix -> mammillary body: glutamate/aspartate after fornix transection (rat)",
    "34015441": "subiculum (fornix) -> mammillary body: excitatory (mouse)",
    "19535593": "mammillary body -> anterior thalamus: glutamatergic (mouse)",
    "12576145": "mammillothalamic terminals: excitatory inputs (rat)",
    "2808769": "hippocampus -> lateral septum: excitatory fibres (rat)",
    "15740723": "accumbens -> ventral pallidum: GABAergic inhibitory input (rat)",
    "36642737": "lateral septum -> lateral hypothalamus: GABAergic (mouse)",
    "39150998": "lateral septum -> lateral hypothalamus: GABAergic inhibition (mouse)",
    "36653189": "amygdala -> accumbens: excitatory afferents (mouse)",
    "22357796": "frontal commissure: interhemispheric glutamatergic projections (human TMS)",
    "32769158": "sensory cortices: glutamatergic callosal projections (mouse)",
    "27335411": "raphe -> olfactory bulb: serotonergic innervation (mouse)",
    # Active-metabolite activity a stored article states only for the parent drug.
    "19890256": "sibutramine metabolites M1/M2 inhibit SERT + NET (human PET)",
    "15111248": "sibutramine metabolites inhibit dopamine reuptake (rat + mouse)",
    "34204205": "disulfiram -> diethyldithiocarbamate, its active metabolite (review)",
    # Receptor / transporter availability across age and sex (kind receptor_demographic):
    # human PET / SPECT only, what no book on disk measures.
    "28599217": "D1, D2, DAT decline with age, synthesis does not (meta-analysis, human PET)",
    "8684263": "D2 decline with age in thalamus + temporal cortex (human PET)",
    "8797238": "D2 decline with age, raclopride vs NMSP (human PET)",
    "7475891": "5-HT2 + D2 availability decline with age (human PET)",
    "11016537": "extrastriatal D2/D3 decline with age (human PET)",
    "9619148": "striatal D2 binding differs by sex (human PET)",
    "8053661": "DAT decline with age (human PET)",
    "7790941": "striatal DAT decline with age (human SPECT)",
    "10952500": "DAT decline with age, sex difference (human SPECT)",
    "21849982": "5-HT1A + 5-HT2A binding by age and sex (human PET)",
    "11282252": "5-HT1A decline with age (human PET)",
    "12414100": "5-HT1A by sex and age (human PET)",
    "18036835": "5-HT1A + SERT sex differences (human PET)",
    "10924762": "SERT decline with age (human SPECT)",
    "9330975": "MAO-B increase with age (human PET)",
    "10360121": "mu-opioid binding by age and sex (human PET)",
    "18077184": "CB1 binding increases with age, by sex (human PET)",
    "19728366": "NET availability with age (human PET)",
    # Found by the receptor-effect search (--effect-search), kept for the effect they back.
    "40992411": "5-HT1F agonism (lasmiditan) treats migraine (review)",
    "36879707": "ditans, 5-HT1F agonists, a migraine therapeutic class (review)",
    "41270648": "5-HT1F activation in the CNS mediates somnolence (dual-target design)",
    # Second source against a Wikipedia binding (CONTRADICTIONS).
    "12192085": "salvinorin A: selective kappa agonist, inactive at a receptor screen incl. D2 "
                "(Roth 2002, against the Wikipedia D2 partial agonism)",
}

SEARCH_LEDGER = ROOT / "tools" / "generated_cache" / "europepmc_binding_search.json"
SPECIES_LEDGER = ROOT / "tools" / "generated_cache" / "europepmc_species.json"
# Abstracts read per binding: enough to catch the paper that characterises the pair,
# few enough that a 700-binding search stays a few thousand short pages.
SEARCH_TOP = 5
DIRECTION_WORDS = ("agonist", "antagonist", '"inverse agonist"', "inhibitor", "blocker",
                   "modulator", "releaser")

_TAG = re.compile(r"<[^>]+>")
# A sentence ends at . ! ? followed by a space and a capital or digit; abbreviations
# like "hr." are rare enough in an abstract that a split line still holds the quote.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def record(pmid: str) -> dict | None:
    """The Europe PMC ``core`` record of one PubMed id, or None when not found."""
    query = urllib.parse.urlencode({"query": f"EXT_ID:{pmid} AND SRC:MED",
                                    "format": "json", "resultType": "core"})
    text = polite_http.fetch_or_none(f"{API}?{query}")
    if not text:
        return None
    hits = json.loads(text).get("resultList", {}).get("result") or []
    return hits[0] if hits else None


def licence_of(rec: dict) -> str | None:
    """The record's open-access licence, upper-cased (``"cc by-nc"`` -> ``"CC BY-NC"``).

    None for a paper Europe PMC holds no open-access copy of: only those get a full text.
    """
    if rec.get("isOpenAccess") != "Y" or not rec.get("pmcid"):
        return None
    lic = (rec.get("license") or "").strip()
    return lic.upper() if lic else "unstated"


# JATS elements whose text is not prose: LaTeX math (``tex-math``) and the alternative
# MathML copy would land as markup soup in a paragraph line; a nested table or figure is
# emitted as its own block after the paragraph that holds it.
_SKIP_INLINE = {"tex-math", "math", "alternatives", "table-wrap", "fig", "disp-formula"}


def _xml_text(el, skip=frozenset()) -> str:
    """An element's text, whitespace-collapsed, minus any subtree tagged in ``skip``."""
    parts = [el.text or ""]
    for child in el:
        if _local(child.tag) not in skip:
            parts.append(_xml_text(child, skip))
        parts.append(child.tail or "")
    return " ".join("".join(parts).split())


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _table_block(tw) -> list[str]:
    """One table: ``Table 3: caption``, then a ``cell | cell`` line per row, then notes."""
    label = tw.find("label")
    caption = tw.find("caption")
    lab = _xml_text(label) if label is not None else ""
    cap = _xml_text(caption, _SKIP_INLINE) if caption is not None else ""
    out = [f"{lab}: {cap}" if lab and cap else lab or cap or "Table"]
    for tr in tw.iter():
        if _local(tr.tag) == "tr":
            cells = [_xml_text(c, _SKIP_INLINE) for c in tr if _local(c.tag) in ("td", "th")]
            if any(cells):
                out.append(" | ".join(cells))
    for foot in tw.iter():
        if _local(foot.tag) == "table-wrap-foot":
            text = _xml_text(foot, _SKIP_INLINE)
            if text:
                out.append(f"Notes: {text}" if not text.lower().startswith("note") else text)
    return out


def _fig_line(fig) -> str:
    label = fig.find("label")
    caption = fig.find("caption")
    text = " ".join(x for x in (_xml_text(label) if label is not None else "",
                                _xml_text(caption, _SKIP_INLINE) if caption is not None else "")
                    if x)
    return text


def full_text_lines(xml_text: str) -> list[str]:
    """The article body of a JATS ``fullTextXML``, flattened for the quote gate.

    One line per section heading (``### title``), paragraph and figure caption, in
    document order; each table is a block between blank lines (see :func:`_table_block`).
    The reference list and front matter are left out: the abstract is already on the page.

    >>> full_text_lines('<article><body><sec><title>Results</title><p>Ki was '
    ...     '<italic>3.9</italic> uM.</p></sec></body></article>')
    ['### Results', 'Ki was 3.9 uM.']
    """
    import xml.etree.ElementTree as ET
    # The DOCTYPE names an external DTD ElementTree never fetches; entities it would
    # declare are not used by Europe PMC's export beyond the XML built-ins.
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    body = next((e for e in root.iter() if _local(e.tag) == "body"), None)
    out: list[str] = []
    if body is None:
        return out

    def blocks(el):
        tag = _local(el.tag)
        if tag == "table-wrap":
            out.extend([""] + _table_block(el) + [""])
            return
        if tag == "fig":
            line = _fig_line(el)
            if line:
                out.append(line)
            return
        if tag == "title":
            text = _xml_text(el, _SKIP_INLINE)
            if text:
                out.append(f"### {text}")
            return
        if tag == "p":
            text = _xml_text(el, _SKIP_INLINE)
            if text:
                out.append(text)
            for child in el.iter():
                if child is not el and _local(child.tag) in ("table-wrap", "fig"):
                    blocks(child)
            return
        for child in el:
            blocks(child)

    blocks(body)
    # Collapse runs of blank lines (a table right after another) and trim the ends.
    tidy: list[str] = []
    for ln in out:
        if ln or (tidy and tidy[-1]):
            tidy.append(ln)
    while tidy and not tidy[-1]:
        tidy.pop()
    return tidy


def full_text_xml(rec: dict) -> str | None:
    """Europe PMC's open-access JATS full text of one record, or None (not OA / failed)."""
    if not licence_of(rec):
        return None
    return polite_http.fetch_or_none(FULL_TEXT_API.format(pmcid=rec["pmcid"]))


def page_text(rec: dict, full_text: list[str] | None = None) -> str:
    """The stored page: a provenance header, the abstract one sentence per line, then the
    open-access full text (when given) under :data:`FULL_TEXT_MARKER`."""
    journal = (rec.get("journalInfo") or {})
    abstract = html.unescape(_TAG.sub(" ", rec.get("abstractText") or ""))
    abstract = " ".join(abstract.split())
    head = [
        f"# {rec.get('title', '').strip()}",
        f"authors: {rec.get('authorString', '').strip()}",
        f"journal: {(journal.get('journal') or {}).get('title')} "
        f"{journal.get('volume')}({journal.get('issue')}):{rec.get('pageInfo')}, "
        f"{rec.get('pubYear')}",
        f"pmid: {rec.get('pmid')}",
        f"doi: {rec.get('doi')}",
        f"source: {ARTICLE_URL.format(pmid=rec.get('pmid'))}",
    ]
    if full_text:
        head += [f"pmcid: {rec.get('pmcid')}", f"licence: {licence_of(rec)}"]
    head += [f"fetched: {time.strftime('%Y-%m-%d')}", ""]
    lines = head + _SENTENCE.split(abstract)
    if full_text:
        lines += ["", f"{FULL_TEXT_MARKER} (open access, {licence_of(rec)}, "
                      f"{rec.get('pmcid')})", ""] + full_text
    return "\n".join(lines) + "\n"


def target_terms(target: str, aliases: dict, genes: dict) -> list[str]:
    """The ASCII names a target goes by in an abstract: our aliases plus its genes."""
    terms = [a for a in aliases.get(target, []) if a.isascii()] + sorted(genes.get(target, []))
    out = []
    for term in terms:
        if term.lower() not in {o.lower() for o in out}:
            out.append(term)
    return out


def direction_query(ligand: str, terms: list[str]) -> str:
    """The Europe PMC query for one (ligand, target): both named in the abstract, plus
    one direction word anywhere."""
    names = " OR ".join(f'ABSTRACT:"{t}"' for t in terms)
    return (f'ABSTRACT:"{ligand}" AND ({names}) AND ({" OR ".join(DIRECTION_WORDS)}) '
            f"AND SRC:MED AND HAS_ABSTRACT:y")


def search(query: str, size: int = SEARCH_TOP) -> tuple[int, list[dict]] | None:
    """Europe PMC's hit count + its top ``size`` core records, or None on an HTTP error."""
    params = urllib.parse.urlencode({"query": query, "format": "json",
                                     "resultType": "core", "pageSize": size})
    text = polite_http.fetch_or_none(f"{API}?{params}")
    if not text:
        return None
    body = json.loads(text)
    return body.get("hitCount", 0), body.get("resultList", {}).get("result") or []


def store(rec: dict, refresh: bool = False, full_text: bool = False) -> bool:
    """Write one record's raw + page (skipped when on disk); False with no abstract.

    ``full_text`` also stores the open-access full text when the record has one (see
    :func:`licence_of`); a page stored abstract-only is then re-written once to add it.
    """
    pmid = rec.get("pmid")
    if not pmid or not rec.get("abstractText"):
        return False
    page = page_path(PAGES_DIR, pmid)
    want_full = full_text and licence_of(rec) is not None
    if page.exists() and not refresh and (
            not want_full or FULL_TEXT_MARKER in read_page_file(page)):
        return True
    page_path(RAW_DIR, pmid, ".json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    body = None
    if want_full:
        xml = full_text_xml(rec)
        if xml:
            page_path(RAW_DIR, pmid, ".xml").write_text(xml, encoding="utf-8")
            body = full_text_lines(xml) or None
        else:
            print(f"[warn] {pmid}: open access but no full text served", file=sys.stderr)
    page.write_text(page_text(rec, body), encoding="utf-8")
    return True


KI_PROSE_WORKLIST = ROOT / "tools" / "generated_cache" / "ki_prose_worklist.json"
WIKI_RAW = ROOT / "data_sources" / "wikipedia" / "raw"
# A measured affinity named in text: Ki / Kd (the subscript flattens to "K i") or their
# log forms, next to a concentration or a pK value. IC50 / EC50 are not affinities (a
# functional potency), so they never make a sentence a candidate on their own.
_AFFINITY = re.compile(r"\bp?K\s?[iIdD]\b")
_CONC = re.compile(r"\d\s*(?:nM|pM|μM|µM|uM|microM|[nµμ]mol/[lL]|(?:nano|micro|pico)molar)\b"
                   r"|\bpK\s?[iIdD]\b\D{0,12}\d")
_PARAGRAPH = re.compile(r"<p[ >].*?</p>", re.S)
# MediaWiki escapes the note ids ("cite&#95;note-Pinder&#95;1977-2"), so both ends of a
# citation link are unescaped before they are matched.
_REF_ITEM = re.compile(r'<li id="(cite(?:_|&#95;)note-[^"]+)"[^>]*>(.*?)</li>', re.S)
_REF_LINK = re.compile(r'href="#(cite(?:_|&#95;)note-[^"]+)"')
_PUBMED = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)|ncbi\.nlm\.nih\.gov/pubmed/(\d+)")


def _plain(fragment: str) -> str:
    """An HTML fragment as one line of text."""
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def states_affinity(text: str) -> bool:
    """Whether a sentence or paragraph states a measured affinity with its value.

    >>> states_affinity("affinity for 5-HT 2B (K i = 3,900 nM)")
    True
    >>> states_affinity("an IC 50 of 40 nM"), states_affinity("a high K i at NET")
    (False, False)
    """
    return bool(_AFFINITY.search(text) and _CONC.search(text))


def cited_affinity_pmids(raw_html: str) -> list[tuple[str, list[str]]]:
    """``(paragraph text, PubMed ids it cites)`` for every article paragraph stating an
    affinity and citing at least one paper Europe PMC can resolve."""
    refs = {html.unescape(rid): [a or b for a, b in _PUBMED.findall(body)]
            for rid, body in _REF_ITEM.findall(raw_html)}
    out = []
    for para in _PARAGRAPH.findall(raw_html):
        text = _plain(para)
        if not states_affinity(text):
            continue
        pmids = sorted({pm for rid in _REF_LINK.findall(para)
                        for pm in refs.get(html.unescape(rid), [])})
        if pmids:
            out.append((text, pmids))
    return out


def affinity_candidates(page: str) -> list[dict]:
    """Every line of a stored page that could carry a measured affinity, no verdict.

    A prose line (an abstract sentence or a full-text paragraph) is offered when it
    states one itself (:func:`states_affinity`). A table row rarely names the constant
    (its column header or caption does), so a full-text table is judged as a whole:
    when its caption, header or notes state an affinity, every row holding a number is
    offered, with the caption and header row riding along as ``table`` so the picker
    can read which column is a Ki. The provenance header is never offered.

    >>> page = "# T\\npmid: 1\\n\\nA sentence.\\nKi = 3 nM at D2.\\n\\n## Full text\\n\\n" \\
    ...        "Table 1: Ki values (nM)\\nTarget | Ki\\n5-HT2B | 3900\\n"
    >>> [(c["line"], c.get("table")) for c in affinity_candidates(page)]
    [('Ki = 3 nM at D2.', None), ('5-HT2B | 3900', 'Table 1: Ki values (nM) || Target | Ki')]

    (A caption stating the values, ``Table 3: ... Ki of 3900 nM``, is offered too.)
    """
    parts = page.split("\n\n", 1)
    body = parts[1] if len(parts) > 1 else ""
    abstract, _, full = body.partition(FULL_TEXT_MARKER)
    out = [{"line": ln} for ln in abstract.splitlines() if ln.strip() and states_affinity(ln)]
    for chunk in full.split("\n\n"):
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        rows = [ln for ln in lines[1:] if " | " in ln]
        if len(lines) > 1 and rows and all(" | " in ln or ln.startswith("Notes")
                                           for ln in lines[1:]):
            notes = " ".join(ln for ln in lines[1:] if " | " not in ln)
            if states_affinity(lines[0]):
                out.append({"line": lines[0]})      # a caption can state the values
            if _AFFINITY.search(" ".join([lines[0], rows[0], notes])):
                table = f"{lines[0]} || {rows[0]}"
                out += [{"line": r, "table": table} for r in rows[1:]
                        if re.search(r"\d", r)]
            continue
        out += [{"line": ln} for ln in lines
                if not ln.startswith(("## ", "### ")) and states_affinity(ln)]
    return out


def ki_prose(only: set | None, refresh: bool) -> int:
    """The ``--ki-prose`` worklist (see the module docstring)."""
    sys.path.insert(0, str(ROOT / "tools"))
    from lib import drugs_io  # noqa: E402
    from lib import target_aliases as ta  # noqa: E402
    from lib import worklist_io  # noqa: E402
    from lib.corpora.wikipedia import page_for  # noqa: E402 (drug -> stored article)

    names = ta.target_names()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    drugs, failed = {}, 0
    for d in drugs_io.load_drugs():
        if only is not None and d["id"] not in only:
            continue
        # A Ki this pass wrote itself (apply_ki_prose.py) still counts as missing, so a
        # rebuild keeps offering the candidate the applier re-applies on every run.
        missing = sorted({b["target"] for b in d.get("bindings", [])
                          if (b.get("ki") or {}).get("source", {}).get("corpus", "europepmc")
                          == "europepmc"})
        path = page_for(d) if missing else None
        raw = page_path(WIKI_RAW, Path(path).stem, ".html") if path else None
        if not raw or not raw.exists():
            continue
        paragraphs = cited_affinity_pmids(raw.read_text("utf-8"))
        cands = []
        for pmid in sorted({pm for _, pms in paragraphs for pm in pms}):
            page = page_path(PAGES_DIR, pmid)
            raw_rec = page_path(RAW_DIR, pmid, ".json")
            # The full text is what a table row lives in: an abstract-only page whose
            # stored record says open access is re-stored once to add it.
            rec = (json.loads(raw_rec.read_text("utf-8"))
                   if raw_rec.exists() and not refresh else None)
            if (not page.exists() or refresh or rec is None or (
                    licence_of(rec) and FULL_TEXT_MARKER not in read_page_file(page))):
                rec = rec if rec is not None and not refresh else record(pmid)
                if not rec or not store(rec, refresh, full_text=True):
                    failed += rec is None
                    continue
            cands += [{"corpus": "europepmc", "page": pmid, **c}
                      for c in affinity_candidates(read_page_file(page))]
        if cands:
            drugs[d["id"]] = {"name": d["name"],
                              "missing": {t: names.get(t, t) for t in missing},
                              "context": [text for text, _ in paragraphs],
                              "candidates": cands}
            print(f"{d['id']}: {len(cands)} candidate sentence(s)")
    built = {"drugs": drugs}
    if only is not None and KI_PROSE_WORKLIST.exists():
        built = worklist_io.merge_scoped(json.loads(KI_PROSE_WORKLIST.read_text("utf-8")),
                                         built, "drugs")
    worklist_io.write(KI_PROSE_WORKLIST, built)
    print(f"{len(drugs)} drug(s) with candidates -> "
          f"{KI_PROSE_WORKLIST.relative_to(ROOT)}; {failed} failed request(s)")
    return 1 if failed else 0


def _alias_gene_maps() -> tuple[dict, dict]:
    """``(aliases, genes)``: every target's prose aliases and its HGNC gene symbols."""
    sys.path.insert(0, str(ROOT / "tools"))
    from lib import target_aliases as ta                             # noqa: E402
    from fetch_gtopdb_ki import owner_genes                 # noqa: E402 (gene map)
    aliases = ta.aliases_by_target()
    genes: dict[str, set] = {}
    for gene, owners in owner_genes(set(aliases)).items():
        for owner in owners:
            genes.setdefault(owner, set()).add(gene)
    return aliases, genes


def binding_search(only: set | None, refresh: bool) -> int:
    """The UNKNOWN search's Europe PMC leg (see the module docstring)."""
    sys.path.insert(0, str(ROOT / "tools"))
    from lib import drugs_io                                         # noqa: E402
    from data_generators import unknown                     # noqa: E402
    aliases, genes = _alias_gene_maps()
    rows = [(r["site"], lambda r=r: direction_query(
                 r["ligand"], target_terms(r["target"], aliases, genes)))
            for r in unknown.affinity_only_bindings(drugs_io.load_drugs(),
                                                    drugs_io.load_metabolites())
            if only is None or r["drug"] in only]
    return ledger_search(rows, SEARCH_LEDGER, refresh)


def ledger_search(rows: list, ledger_path: Path, refresh: bool,
                  size: int = SEARCH_TOP) -> int:
    """Run one query per ``(site, make_query)`` row, store the top ``size`` abstracts
    and record ``{query, hits, read, searched}`` per site in the ledger at
    ``ledger_path``. Resumable: a site already in the ledger is skipped unless
    ``refresh``. Shared by the two UNKNOWN search legs (bindings, receptor effects)."""
    ledger = json.loads(ledger_path.read_text("utf-8")) if ledger_path.exists() else {}
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0
    for i, (site, make_query) in enumerate(rows, 1):
        if site in ledger and not refresh:
            continue
        query = make_query()
        got = search(query, size)
        if got is None:
            failed += 1
            continue
        hits, recs = got
        pmids = [r["pmid"] for r in recs if store(r, refresh)]
        ledger[site] = {"query": query, "hits": hits, "read": pmids,
                        "searched": time.strftime("%Y-%m-%d")}
        print(f"[{i}/{len(rows)}] {site}: {hits} hit(s), read {len(pmids)}")
        if i % 25 == 0:
            atomic_write_json(ledger_path, ledger, indent=1, sort_keys=True, ensure_ascii=True)
    atomic_write_json(ledger_path, ledger, indent=1, sort_keys=True, ensure_ascii=True)
    print(f"ledger: {len(ledger)} site(s); {failed} failed request(s)")
    return 1 if failed else 0


EFFECT_SEARCH_LEDGER = ROOT / "tools" / "generated_cache" / "europepmc_effect_search.json"
# Abstracts read per receptor: an effect search is one query per owner (a few dozen),
# so it can afford more than a binding's five.
EFFECT_SEARCH_TOP = 10
# What an abstract stating a clinical / physiological effect of acting on a receptor
# says, folded from the closed vocabulary (data_generators.receptor_effects) into the
# stems Europe PMC's wildcard search takes. Recall over precision: the pick step
# discards a weak hit.
EFFECT_WORDS = ("sedat*", "somnolen*", '"weight gain"', "appetite", "hypotension",
                "dizziness", "hallucinat*", "prolactin", "extrapyramidal", "dyskinesia",
                "akathisia", "cognit*", "memory", "nausea", "vomiting", "sexual",
                "insomnia", "anxi*", "euphori*", "dysphori*", '"respiratory depression"',
                "seizure*", "convuls*", "psychosis", "psychotic", '"heart rate"',
                '"blood pressure"', "valvulopath*", "antiemetic", "anticonvulsant",
                "antidepressant", "antipsychotic", "parkinson*", "analges*", "pain",
                "migraine", "sleep", "circadian", "wakefulness", "hypotherm*",
                "bradycardia", "bronchodilat*", '"gastric acid"', "vasoconstrict*",
                "vasodilat*", "bladder", "motility")
HUMAN_WORDS = ("human", "humans", "patients", "volunteers", '"healthy subjects"')
# An effect node is about ACTING on the receptor in a mode, so the abstract must name an
# action too (a DRD4 repeat-polymorphism association study states none).
MODE_WORDS = DIRECTION_WORDS + ("agonism", "antagonism", "blockade", "activation",
                                "stimulation")
# Names the alias table (``target_aliases``) lacks because no drug-binding prose uses
# them, but a paper does. An alias the table already has (GABA-C) is never repeated here.
EFFECT_EXTRA_TERMS: dict[str, tuple[str, ...]] = {
    "gaba_a_rho": ("GABAA-rho receptor", "GABA rho receptor"),
    "nachr_muscle": ("muscle nicotinic receptor", "muscle-type nicotinic",
                     "neuromuscular nicotinic"),
}


def effect_terms(owner: str, aliases: dict, genes: dict) -> list[str]:
    """The ASCII names a receptor goes by, made specific enough for a literature query:
    its genes, then each alias as ``"<alias> receptor"`` (a bare "D4" or "glycine" is
    a word in any abstract; an alias already ending in "receptor" is kept as it is),
    plus the alias alone when it already names the receptor (has a digit and is at
    least four characters: ``mGluR5``, ``5-HT1E``), then :data:`EFFECT_EXTRA_TERMS`.

    >>> effect_terms("gaba_a_rho", {"gaba_a_rho": ["GABA-C", "GABAC receptor"]}, {})
    ['GABA-C receptor', 'GABAC receptor', 'GABAA-rho receptor', 'GABA rho receptor']
    """
    out: list[str] = []
    for term in target_terms(owner, aliases, genes):
        if term in genes.get(owner, set()) or term.lower().endswith(" receptor"):
            forms = [term]
        else:
            forms = [f"{term} receptor"] + (
                [term] if re.search(r"\d", term) and len(term) >= 4 else [])
        for form in forms:
            if form.lower() not in {o.lower() for o in out}:
                out.append(form)
    for form in EFFECT_EXTRA_TERMS.get(owner, ()):
        if form.lower() not in {o.lower() for o in out}:
            out.append(form)
    return out


def effect_query(terms: list[str]) -> str:
    """The Europe PMC query for one receptor: named in the abstract, plus an effect word
    and a human-study word, so an abstract can state what acting on it does in people."""
    names = " OR ".join(f'ABSTRACT:"{t}"' for t in terms)
    return (f'({names}) AND ({" OR ".join(MODE_WORDS)}) AND ({" OR ".join(EFFECT_WORDS)}) '
            f'AND ({" OR ".join(HUMAN_WORDS)}) AND SRC:MED AND HAS_ABSTRACT:y')


def effect_search(only: set | None, refresh: bool) -> int:
    """The receptor-effect UNKNOWN search's Europe PMC leg: one query per receptor with
    no ``receptor_effect`` node (``--only`` names owners, a target included)."""
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(HERE))
    import fetch_receptor_effects as fre                    # noqa: E402 (owner roster)
    from data_generators import receptor_effects, unknown  # noqa: E402
    aliases, genes = _alias_gene_maps()
    cache = receptor_effects.load_cache()
    rows = []
    for oid, owner in sorted(fre.owners().items()):
        if oid in fre.SKIP_OWNERS:
            continue
        if (only is not None and oid not in only) or (
                only is None and (owner["kind"] != "receptor" or cache.get(oid))):
            continue
        rows.append((unknown.effects_site(owner["kind"], oid),
                     lambda oid=oid: effect_query(effect_terms(oid, aliases, genes))))
    return ledger_search(rows, EFFECT_SEARCH_LEDGER, refresh, EFFECT_SEARCH_TOP)


# A cited paper whose record carries no MeSH species (not yet indexed, or tagged only
# "Animals"), read off its abstract by hand. Only for a PMID a shipped quote cites.
SPECIES_OVERRIDES: dict[str, list[str]] = {
    "6664490": ["monkey"],      # "in squirrel monkeys (Saimiri sciureus)"
    "32019": ["rat"],           # fornix transection in the rat
    "26170874": ["mouse"],      # "writhing assay in mice"
}


def species_of(rec: dict) -> list[str]:
    """Sorted species keys a record names: its MeSH headings, else the hand override."""
    heads = (rec.get("meshHeadingList") or {}).get("meshHeading") or []
    keys = {k for h in heads if (k := species_key(h.get("descriptorName"))) is not None}
    return sorted(keys) or SPECIES_OVERRIDES.get(str(rec.get("pmid")), [])


def write_species_ledger() -> int:
    """Rewrite :data:`SPECIES_LEDGER` from every stored ``raw/<pmid>.json``."""
    ledger = {}
    for raw in sorted(RAW_DIR.glob("*.json")):
        ledger[raw.stem] = species_of(json.loads(raw.read_text("utf-8")))
    atomic_write_text(SPECIES_LEDGER,
        "{\n" + ",\n".join(f"{json.dumps(k)}: {json.dumps(v)}"
                             for k, v in sorted(ledger.items())) + "\n}\n")
    print(f"species: {len(ledger)} record(s), "
          f"{sum(1 for v in ledger.values() if v)} naming a species")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated PMIDs (default: all of PAPERS); "
                                   "drug ids with --binding-search")
    ap.add_argument("--refresh", action="store_true", help="re-download stored records")
    ap.add_argument("--binding-search", action="store_true",
                    help="search every direction-less binding (the UNKNOWN search)")
    ap.add_argument("--effect-search", action="store_true",
                    help="search every receptor with no receptor_effect node (the "
                         "receptor-effect UNKNOWN search); --only names owner ids")
    ap.add_argument("--ki-prose", action="store_true",
                    help="store the papers Wikipedia cites for a Ki its prose states, "
                         "and write the ki_prose worklist")
    ap.add_argument("--species", action="store_true",
                    help="offline: rewrite the MeSH species ledger from raw/ and exit")
    args = ap.parse_args()
    if args.species:
        return write_species_ledger()
    if args.binding_search or args.ki_prose or args.effect_search:
        only = {d.strip() for d in args.only.split(",")} if args.only else None
        code = (binding_search if args.binding_search else effect_search
                if args.effect_search else ki_prose)(only, args.refresh)
        write_species_ledger()
        return code
    pmids = [p.strip() for p in args.only.split(",")] if args.only else list(PAPERS)
    unknown = [p for p in pmids if p not in PAPERS]
    if unknown:
        print(f"[error] not in PAPERS (add it with its reason first): {unknown}",
              file=sys.stderr)
        return 1
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0
    for pmid in pmids:
        page = page_path(PAGES_DIR, pmid)
        if page.exists() and not args.refresh:
            print(f"[skip] {pmid}: page on disk")
            continue
        rec = record(pmid)
        if not rec or not store(rec, refresh=True, full_text=True):
            print(f"[warn] {pmid}: no record / no abstract", file=sys.stderr)
            failed += 1
            continue
        print(f"[ok] {pmid}: {page.relative_to(ROOT)}")
    write_species_ledger()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
