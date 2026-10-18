"""data_generators.corpora: ``SOURCE_CORPORA``, the registry of every source corpus.

Pure data (one record per corpus a quote-level source may cite), split out of
data_generators.provenance verbatim so the grading logic stays readable. Emitted as
``meta.source_corpora``; ``provenance.load_external_registries`` adds the PharmFreq /
CPIC export pins to it in place at build time.
"""

from __future__ import annotations

from . import clinpgx, cpic, pharmfreq


# Source corpora that the *per-claim* drug sources cite, keyed by a short id. A
# claim's source is ``{corpus, page, quote, provenance}``: ``quote`` is the
# verbatim snippet supporting the claim, ``page`` locates it inside the corpus,
# and ``tools/check_data.py`` confirms (when the corpus's pages are present) that
# the quote really appears on that page, which is what makes a ``"verified"``
# grade trustworthy. The design is source-agnostic: Stahl is the first corpus,
# more can be added here without touching the schema. ``pages_dir`` is an
# author-side path (relative to the repo root) holding one ``<page>.md`` per page
# (see ``data_sources/books/stahl/`` in CLAUDE.local.md); it is emitted into ``meta.json`` so the
# checker is data-driven, and is simply absent on a checkout without that
# (uncommitted, large) source material, in which case the quote-in-page check is
# skipped while the structural checks still run. ``url`` is the corpus's landing page
# (a book's DOI, else its ISBN on WorldCat), the link a cited page falls back to when
# neither a ``page_url`` template (``{page}`` filled in) nor a per-page ``page_urls``
# entry (data_generators/page_links.py, added at emit time) names that exact page. ``editable`` marks a corpus
# whose pages can change upstream (a wiki, a live database): each of its cited pages
# carries its download date and must be refetched within a year (see
# data_generators/freshness.py); a book omits the key.
# GtoPdb's "How to cite" page (guidetopharmacology.org/citing.jsp, read 2026-10-12
# from its 2026-07-31 snapshot while the live site was down for maintenance) asks a
# general citation of its current Nucleic Acids Research database paper, plus the
# relevant section of the Concise Guide to PHARMACOLOGY for work on target data, and
# its contents are CC BY-SA 4.0. Shared by corpora #7, #11 and #12 as
# ``required_citations``: a corpus's own request to be cited, which the viewer prints
# under its source pills + in the Sources popup and the README lists under its table.
GTOPDB_NAR_CITATION = (
    "Harding SD, Armstrong JF, Faccenda E, Southan C, Alexander SPH, Davenport AP, "
    "Spedding M, Davies JA. The IUPHAR/BPS Guide to PHARMACOLOGY in 2026. Nucleic "
    "Acids Res. 2026;54(D1):D1446-D1456. doi:10.1093/nar/gkaf1067. PMID 41160876.")
GTOPDB_CONCISE_GUIDE_CITATION = (
    "Alexander SPH, Davenport AP, Kelly E, et al. The Concise Guide to PHARMACOLOGY "
    "2025/26: G protein-coupled receptors. Br J Pharmacol. 2025;182:S24-S151 (and the "
    "matching 2025/26 chapter for each other target family).")
GTOPDB_LICENCE = ("IUPHAR/BPS Guide to PHARMACOLOGY content licensed under CC BY-SA 4.0 "
                  "(database ODbL).")
GTOPDB_TARGET_CITATIONS = [GTOPDB_NAR_CITATION, GTOPDB_CONCISE_GUIDE_CITATION, GTOPDB_LICENCE]
GTOPDB_LIGAND_CITATIONS = [GTOPDB_NAR_CITATION, GTOPDB_LICENCE]


SOURCE_CORPORA: dict[str, dict] = {
    "stahl": {
        # Label for the per-claim tooltip ref ("<ref>, p. N"). The full book title
        # + edition, not a bare "Stahl", so a page citation is unambiguous on its
        # own (which Stahl, which edition) without needing the full bibliographic
        # citation below.
        "ref": "Prescriber's Guide: Stahl's Essential Psychopharmacology, 8th ed.",
        "citation": "Stahl SM. Prescriber's Guide: Stahl's Essential "
                    "Psychopharmacology. 8th ed. Cambridge University Press; 2024.",
        "url": "https://doi.org/10.1017/9781009464772",
        "pages_dir": "data_sources/books/stahl/pages",
    },
    "kandel": {
        # Anatomy/pathway corpus (the projection claims, currently LLM-only, are
        # quote-verified against this). Full title + edition so a page citation is
        # unambiguous on its own.
        "ref": "Kandel, Principles of Neural Science, 6th ed.",
        "citation": "Kandel ER, Koester JD, Mack SH, Siegelbaum SA, eds. "
                    "Principles of Neural Science. 6th ed. McGraw Hill; 2021.",
        # No DOI: the print ISBN 978-1-25-964223-4, via WorldCat.
        "url": "https://search.worldcat.org/search?q=bn:9781259642234",
        "pages_dir": "data_sources/books/eric_kandel/pages",
    },
    "stahl_essential": {
        # Mechanism/receptor corpus: the receptor + non-receptor-target
        # classification claims are quote-verified against this.
        "ref": "Stahl's Essential Psychopharmacology: Neuroscientific Basis, "
               "5th ed.",
        "citation": "Stahl SM. Stahl's Essential Psychopharmacology: "
                    "Neuroscientific Basis and Practical Applications. 5th ed. "
                    "Cambridge University Press; 2021.",
        "url": "https://doi.org/10.1017/9781108975292",
        "pages_dir": "data_sources/books/stahl_essential_pharmacology/pages",
    },
    "carlat": {
        # Second drug corpus: cross-sources drug bindings Stahl did not state.
        "ref": "Carlat Medication Fact Book for Psychiatric Practice, 7th ed.",
        "citation": "Carlat DJ. The Carlat Medication Fact Book for Psychiatric "
                    "Practice. 7th ed. Carlat Publishing; 2024.",
        # No DOI: the print ISBN 979-8-9873354-8-2, via WorldCat.
        "url": "https://search.worldcat.org/search?q=bn:9798987335482",
        "pages_dir": "data_sources/books/carlat_medication/pages",
    },
    "nieuwenhuys": {
        # Systematic neuroanatomy/connectivity corpus: backs region-anatomy +
        # projection claims Kandel does not state in prose (the claustrum, the
        # fornix, commissures). Page numbers are the PDF's 1-based pages (the .md
        # file names), which run a few ahead of the printed page numbers.
        "ref": "Nieuwenhuys, Voogd & van Huijzen, The Human Central Nervous "
               "System, 4th ed.",
        "citation": "Nieuwenhuys R, Voogd J, van Huijzen C. The Human Central "
                    "Nervous System. 4th ed. Springer; 2008.",
        "url": "https://doi.org/10.1007/978-3-540-34686-9",
        "pages_dir": "data_sources/books/nieuwenhuys_atlas/pages",
    },
    "gtopdb": {
        # Expression/localization corpus: the IUPHAR/BPS Guide to Pharmacology
        # per-target "Tissue Distribution" statements, backing a receptor/target
        # expression-region claim ("R is found in region B"). Fetched from the GtoPdb
        # web service (tools/fetch/fetch_gtopdb.py) and cached author-side as one page per
        # target id: each `location_sources` quote is a verbatim `tissue` string and
        # its `page` is the GtoPdb target id, so the normal verbatim-quote gate
        # applies unchanged. Many entries are rat/mouse, so each source carries a
        # `species` (the viewer flags a non-human claim; see _quote_sources).
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), tissue distribution",
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_TARGET_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages",
        "machine": True,
        "editable": True,
        "page_kind": "target",
        "page_url": "https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId={page}",
    },
    "pdsp_ki": {
        # Binding-affinity corpus: measured Ki (nM) values backing a drug binding's
        # `ki` annotation. Unlike the book corpora this is a single CSV of assay
        # rows, not paged text, so it has no `pages_dir`; check_data confirms a
        # cited Ki id/value against the `csv` file instead (author-side, skipped on
        # a clone without it, like the quote gate). See tools/fetch/fetch_ki.py +
        # data_sources/books/pdsp_ki/README.md.
        "ref": "PDSP Ki Database (NIMH PDSP)",
        "citation": "NIMH Psychoactive Drug Screening Program (PDSP) Ki Database, "
                    "directed by Bryan L. Roth, University of North Carolina at "
                    "Chapel Hill.",
        "url": "https://pdspdb.unc.edu/databases/kidb.php",
        "csv": "data_sources/books/pdsp_ki/KiDatabase.csv",
        "machine": True,
        "editable": True,
        "page_kind": "row",
    },
    "allen_ahba": {
        # Expression corpus: the Allen Human Brain Atlas microarray, backing a
        # receptor/target expression-region claim ("X is found in region B") the
        # GtoPdb tissue comments could not reach (esp. the non-receptor targets +
        # the deep nuclei). tools/fetch/fetch_allen.py aggregates Allen's PACall
        # present/absent boolean per (gene, region) across the 6 donors and writes one
        # cached page per gene (`page` = the HGNC gene symbol): each `location_sources`
        # quote is a verbatim presence line, so the normal verbatim-quote gate applies
        # unchanged. All 6 donors are human, so every quote carries `species: Human`.
        # Licence: copyright-reserved, non-commercial research use with required
        # citation; we vendor only the cited slice, never the atlas.
        "ref": "Allen Human Brain Atlas, microarray (Hawrylycz et al. 2012)",
        "citation": "Hawrylycz MJ, Lein ES, Guillozet-Bongaarts AL, et al. An "
                    "anatomically comprehensive atlas of the adult human brain "
                    "transcriptome. Nature. 2012;489(7416):391-399. "
                    "human.brain-map.org.",
        "url": "https://human.brain-map.org/",
        "pages_dir": "data_sources/allen/pages",
        "machine": True,
        "editable": True,
        "page_kind": "gene",
    },
    "wikipedia_pharm": {
        # Corpus #9: a drug's English Wikipedia article, stored whole (article text +
        # every table flattened to rows), so one corpus backs three different claims:
        # a binding `ki` where PDSP (corpus #5) has none (a fallback, never overriding
        # a measured assay), an active metabolite's own bindings, and a drug's
        # metabolising-enzyme roles for the 149 drugs outside Stahl's roster. It also
        # backs a drug's originator (its own article) and that company's country and
        # current name (the company's own article, same pages/ tree).
        # tools/fetch/fetch_wikipedia_pharmacology.py fetches the article pinned to a
        # revision id and writes the whole page as author-side text; a source's `page`
        # is the article slug and its `quote` is a verbatim line of it (a table row, a
        # prose sentence, the drugbox metabolism row), so the normal verbatim-quote
        # gate applies unchanged (author-side, skipped on a clone lacking
        # data_sources/wikipedia/, like the book corpora). Wikipedia is a tertiary
        # source citing the primary literature: the grade attests the quote is really
        # on the page, and this corpus label makes the source's tier explicit.
        "ref": "Wikipedia (English), drug article (pharmacology sections)",
        "citation": "Wikipedia contributors. Pharmacology sections of the cited drug "
                    "article. Wikipedia, The Free Encyclopedia. "
                    "en.wikipedia.org (revision pinned per citation).",
        "url": "https://en.wikipedia.org/",
        "pages_dir": "data_sources/wikipedia/pages",
        "editable": True,
        "page_kind": "article",
    },
    "wikipedia_fr": {
        # Brand-name corpus #10: the French Wikipedia article, the source for a drug's
        # European / French commercial brands (`eu`/`fr` region). The FR infobox carries
        # only chemistry, so the trade names live in the prose ("commercialisée sous les
        # noms Xeroquel, Seroquel..."); tools/fetch/fetch_brand_names.py stores the whole
        # FR article author-side (pinned to a revision id) and an LLM reads the candidate
        # sentences, apply_brand_names.py quote-gating each returned brand verbatim on the
        # page. A brand source's `page` is the FR article slug, its `quote` the brand name,
        # so the normal verbatim-quote gate applies (author-side, skipped on a clone lacking
        # data_sources/wikipedia/pages_fr, like the book corpora). Tertiary source: the
        # grade attests the name is really on the page, the label makes the tier explicit.
        "ref": "Wikipedia (French), drug article (commercial names)",
        "citation": "Wikipedia contributors. Commercial names of the cited drug article. "
                    "Wikipedia, l'encyclopedie libre. fr.wikipedia.org (revision pinned "
                    "per citation).",
        "url": "https://fr.wikipedia.org/",
        "pages_dir": "data_sources/wikipedia/pages_fr",
        "editable": True,
        "page_kind": "article",
    },
    "gtopdb_ki": {
        # Binding corpus #11: GtoPdb's *other* half. Where corpus #7 uses its tissue
        # API for expression regions, this uses its hand-curated ligand-interaction
        # table, which carries a measured affinity, a curated direction and a PubMed
        # id per row. It complements PDSP (#5) where a radioligand panel structurally
        # cannot reach: targets PDSP does not assay (GABA-A benzodiazepine site,
        # MAO-A/B, acetylcholinesterase, orexin, melatonin, SV2A) and the *direction*
        # of an affinity_only binding. PDSP still wins on a Ki both have.
        # tools/fetch/fetch_gtopdb_ki.py flattens each matched compound's rows into
        # one author-side page (`page` = the GtoPdb ligand slug, `quote` = one verbatim
        # row line), so the normal verbatim-quote gate applies unchanged (skipped on a
        # clone lacking data_sources/gtopdb/pages_ki, like the book corpora).
        # Licence: contents CC BY-SA 4.0, database ODbL; both need attribution, which
        # the citation below carries into every pill tooltip.
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), ligand interactions",
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_LIGAND_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_ki",
        "machine": True,
        "editable": True,
        "page_kind": "ligand",
    },
    "gtopdb_class": {
        # Classification corpus #12: GtoPdb's third slice (after #7 tissue distribution
        # and #11 ligand interactions). Two structured fields per target back a
        # *mechanism* node no book prose states uniformly: its `type` (gpcr / lgic /
        # vgic / enzyme), which is a receptor's `receptor_class` and a non-receptor
        # target's `type`; and its transduction table (transducer family + effectors),
        # from which a GPCR's `sign` is mapped under the narrow, confirm-only rule in
        # tools/sourcing/apply_classification_sources.py (GtoPdb states the
        # transduction, never a sign, so the quote carried into the pill is the
        # transduction line itself and the reader can see what backs it).
        # tools/fetch/fetch_gtopdb_class.py flattens both into one author-side page per
        # target id (`page` = the GtoPdb target id, `quote` = one verbatim line), so the
        # normal verbatim-quote gate applies unchanged (skipped on a clone lacking
        # data_sources/gtopdb/pages_class, like every other pages*/). GtoPdb has no
        # pre/post-synaptic field, so `synaptic` is out of this corpus's reach.
        # Licence: contents CC BY-SA 4.0, database ODbL, as for #7 and #11.
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), target classification",
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_TARGET_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_class",
        "machine": True,
        "editable": True,
        "page_kind": "target",
        "page_url": "https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId={page}",
    },
    "gtopdb_function": {
        # Function corpus #23: GtoPdb's fourth slice, the curated per-target prose of
        # three target-page sections, "Physiological Functions", "Clinically-Relevant
        # Mutations and Pathophysiology" and "Physiological Consequences of Altering
        # Gene Expression" (+ their comments), backing receptor_effect nodes.
        # tools/fetch/fetch_gtopdb_function.py flattens them into one author-side page
        # per target id (`page`), one statement per line naming its section and the
        # species GtoPdb records; a row with a stated non-human species is never offered
        # as a candidate. An LLM picks the line (not `machine`), so a judge must follow.
        # Licence: contents CC BY-SA 4.0, database ODbL, as #7 / #11 / #12.
        "ref": "IUPHAR/BPS Guide to Pharmacology (GtoPdb), target function",
        "citation": GTOPDB_NAR_CITATION,
        "required_citations": GTOPDB_TARGET_CITATIONS,
        "url": "https://www.guidetopharmacology.org/",
        "pages_dir": "data_sources/gtopdb/pages_function",
        "editable": True,
        "page_kind": "target",
        "page_url": "https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId={page}",
    },
    "pharmfreq": {
        # Enzyme variability corpus #13: how fast people clear a drug through one
        # enzyme, and how common each speed is per population group. The only corpus
        # here whose subject is *people* rather than molecules or anatomy, which is
        # why it backs its own node kind (`enzyme_variability`) instead of grading an
        # existing one: nothing else this dataset states about CYP2D6 varies by who
        # is taking the drug.
        # tools/fetch/fetch_pharmfreq.py reshapes the hand-downloaded "Metabolizer
        # status tool" export (`page` = the HGNC gene symbol, `quote` = the one line
        # carrying the whole profile, as in the Allen density profiles), so the gate
        # covers the numbers a reader judges the claim by. Deterministic, no judge:
        # PharmFreq publishes the aggregate and we only reshape it.
        # The one corpus with `tsv_dir` and no `pages_dir`, for two reasons that go
        # together. Its export is small and freely redistributable, so it is COMMITTED
        # rather than kept author-side, and the gate therefore runs on every clone
        # instead of being skipped-and-warned. And the sentence we quote is one we
        # compose out of that table, so looking for it on a page we also wrote would
        # be circular: `check_data.py` instead pins each file by sha256 and rebuilds
        # the sentence from it (see data_generators/pharmfreq.py).
        # Two isoforms this dataset leans on hardest, CYP3A4 and CYP1A2, have no
        # profile in the tool, so their absence is a gap in the source, not a claim
        # that they do not vary.
        "ref": "PharmFreq, metabolizer status by population",
        "citation": "PharmFreq: a global genetic variation database for "
                    "pharmacogenomics. pharmfreq.com, metabolizer status tool.",
        "url": "https://pharmfreq.com",
        "tsv_dir": pharmfreq.EXPORT_DIR,
        "export_sha256": {},  # filled by load_external_registries()
        "machine": True,
        "editable": True,
        "page_kind": "gene",
    },
    "dailymed": {
        # Pharmacokinetics corpus #14: the US prescribing label (DailyMed / NLM
        # Structured Product Labels). It exists for one fact the roster could not
        # otherwise source: a drug's time to peak plasma concentration, which the
        # already-stored corpora state for only a third of the drugs (Wikipedia prose
        # 102, Stahl 13, 190 nowhere) while a label's section 12.3 states it for
        # essentially every oral drug marketed in the US.
        # tools/fetch/fetch_dailymed.py picks ONE label per drug (plain-oral forms
        # preferred: a modified-release product states a real Tmax for a different
        # product) and stores its pharmacokinetics sections as an author-side page;
        # `page` is the label's **setid**, which is a stable public identifier, so a
        # citation resolves to dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=<page>.
        # The quote is a verbatim line of that page, gated exactly like a book page
        # (author-side, skipped on a clone lacking data_sources/dailymed/, like every
        # other pages*/). A primary regulatory source, unlike the tertiary #9.
        # Licence: SPL content is submitted by manufacturers and published by the US
        # National Library of Medicine as a government work under no copyright
        # restriction; the citation below carries the attribution it asks for.
        "ref": "DailyMed (U.S. NLM), prescribing label, clinical pharmacology",
        "citation": "U.S. National Library of Medicine. DailyMed Structured Product "
                    "Label, Pharmacokinetics section of the cited label. "
                    "dailymed.nlm.nih.gov (label set id pinned per citation).",
        "url": "https://dailymed.nlm.nih.gov/",
        "pages_dir": "data_sources/dailymed/pages",
        "editable": True,
        "page_kind": "setid",
        "page_url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={page}",
    },
    "bdpm": {
        # Pharmacokinetics + brand corpus #16: the French public drug database (ANSM
        # "Base de donnees publique des medicaments"), the French counterpart of #14. Its
        # summary of product characteristics (RCP) section 5.2 states a time to peak and
        # an elimination half-life for most products authorised in France, including the
        # European-only drugs no US label exists for, and its product table names every
        # French commercial brand.
        # tools/fetch/fetch_bdpm.py joins each drug to its single-active products through
        # the French INN (exact, accent-folded, stereo-aware via tools/chirality.py) and
        # picks ONE plain-oral RCP per drug (a prolonged-release "LP" product states a
        # different product's peak, the Seroquel XR gotcha). `page` is the product's CIS
        # code, a stable public identifier, so a citation resolves to
        # base-donnees-publique.medicaments.gouv.fr/medicament/<page>/extrait.
        # Tmax / half-life quotes are French sentences picked by a model and judged like
        # any prose (four-step pipeline); a brand quote is the denomination's brand word,
        # copied by code from the product table (`extraction: "code"`, no judge), and its
        # page is that product's header page; a current French holder is that header's
        # `holder:` line, copied the same way. Author-side pages, like #14.
        # Licence: Licence Ouverte / Open Licence (Etalab); the citation names the source
        # and the database as the licence asks.
        "ref": "Base de données publique des médicaments (ANSM), RCP",
        "citation": "ANSM / Ministère de la Santé. Base de données publique des "
                    "médicaments, résumé des caractéristiques du produit (RCP) of the "
                    "cited product, section 5.2. base-donnees-publique.medicaments.gouv.fr "
                    "(Licence Ouverte; CIS code pinned per citation).",
        "url": "https://base-donnees-publique.medicaments.gouv.fr/",
        "pages_dir": "data_sources/bdpm/pages",
        "editable": True,
        "page_kind": "cis",
        "page_url": "https://base-donnees-publique.medicaments.gouv.fr/extrait.php?specid={page}",
    },
    "bdpm_rcp": {
        # Workup corpus #24: the same official French RCPs as #16, read for sections
        # 4.2 / 4.3 / 4.4 (posology, contraindications, warnings and precautions):
        # the tests the label asks for before starting a drug and while it is taken
        # (kind drug_workup, data_generators/workup.py). A sibling corpus rather than
        # more lines on #16's pages because a corpus has ONE pages_dir keyed by `page`:
        # the same CIS is cited by both (Teralithe's 5.2 half-life and its 4.4 workup)
        # with different text and a different download date, and the quote gate and
        # the freshness ledger both resolve `<pages_dir>/<page>.md`.
        # tools/fetch/fetch_bdpm_rcp.py builds one page per chosen product (princeps
        # first) from an RCP copy already on disk (#16's own download, or the
        # justelesRCP re-scrape of the live ANSM site), the freshest copy winning; the
        # page header names the copy and how its date was read. `page` = the CIS, or
        # for a drug with no French product at all the EMA product number of its EPAR
        # found by name (`EMEA-H-C-003759`, fetch_ema_epar.py), linked at EMA's SmPC
        # PDF through page_links. An LLM picks the line (not `machine`), so a judge
        # must follow.
        # Licence: Licence Ouverte / Open Licence (Etalab), as #16; an EMA SmPC is
        # "reproduction authorised, source acknowledged".
        "ref": "Base de données publique des médicaments (ANSM) or EMA EPAR, RCP sections 4.2-4.4",
        "citation": "ANSM / Ministère de la Santé. Base de données publique des "
                    "médicaments, résumé des caractéristiques du produit (RCP) of the "
                    "cited product, sections 4.2, 4.3 and 4.4. "
                    "base-donnees-publique.medicaments.gouv.fr (Licence Ouverte; CIS "
                    "code pinned per citation). For a centrally authorised product, the "
                    "European Medicines Agency's EPAR product information (SmPC, French "
                    "version), ema.europa.eu (EMA product number pinned per citation).",
        "url": "https://base-donnees-publique.medicaments.gouv.fr/",
        "pages_dir": "data_sources/bdpm/pages_rcp4",
        "editable": True,
        "page_kind": "product",
        "page_url": "https://base-donnees-publique.medicaments.gouv.fr/medicament/{page}/extrait",
    },
    "cpic": {
        # Pharmacogenomic guidance corpus #15: what a metabolizer phenotype *means* for
        # one prescription. The third layer over #13 (how common each clearance speed
        # is) and the enzyme nodes (which isoform clears the drug), and the only corpus
        # here that states a clinical action rather than a fact about a molecule.
        # tools/fetch/fetch_cpic.py pulls CPIC's structured recommendation rows for the
        # gene-drug pairs this roster covers; `page` is the guideline's ClinPGx id, so a
        # citation resolves to clinpgx.org/guideline/<page>. Two quotes per node (the
        # implication, then the recommendation): one claim, two sentences, both CPIC's
        # own words. Deterministic, no judge, `extraction: "code"`.
        # Committed with the repo like #13 (CC0 content, 64 KB) and pinned by sha256
        # instead of kept author-side, so the gate runs on every clone; unlike #13 the
        # quote is not one we compose, so it is checked verbatim against the export.
        # Scope limits that are gaps in the source, not judgements: only genes with a
        # metabolizer-frequency profile here (so HLA-B with carbamazepine, SCN1A, and
        # the urea-cycle genes with valproate are out), only CPIC's `general`/`adults`/
        # treatment-naive populations, and only phenotypes a frequency exists for.
        # Licence: CPIC curated content is CC0 1.0; the citation below carries the
        # attribution CPIC's terms ask of an API consumer (primary source, guideline
        # publication, version, date accessed).
        "ref": "CPIC, clinical pharmacogenetics dosing guideline",
        "citation": "Clinical Pharmacogenetics Implementation Consortium (CPIC®). "
                    "Gene-drug recommendation, cited guideline. clinpgx.org (CC0 1.0); "
                    "guideline content is subject to update, so the export is dated.",
        "url": "https://cpicpgx.org/",
        "tsv_dir": cpic.EXPORT_DIR,
        "export_sha256": {},  # filled by load_external_registries()
        "machine": True,
        "editable": True,
        "page_kind": "guideline",
        "page_url": "https://www.clinpgx.org/guidelineAnnotation/{page}",
    },
    "europepmc": {
        # Primary-literature corpus #17: paper abstracts for the claims only a study
        # measures (lithium's brain half-life, from 7Li MRS, being longer than its serum
        # one: no book, label or article on disk says so), plus Europe PMC's own
        # open-access full text where the record has one (a Ki that lives only in a
        # paper's table: viloxazine's 5-HT2B / 5-HT2C). tools/fetch/fetch_europepmc.py
        # stores one page per paper (abstract one sentence per line, then the OA body and
        # every table as `cell | cell` rows, licence in the header); `page` is the PubMed
        # id, so a citation resolves to europepmc.org/article/MED/<page>. Papers are
        # hand-listed (PAPERS, each with its claim) or a Wikipedia-cited paper the Ki
        # pass followed, so the corpus never grows into a crawl. Quotes are picked by a
        # model and judged like any other (no `extraction: "code"`). Author-side pages
        # like #14/#16 (a short verbatim sentence is a citation, the page is never
        # shipped); a full-text Ki source carries the paper's `licence` for credit.
        "ref": "Europe PMC, journal article",
        "citation": "Europe PMC (EMBL-EBI). Abstract, or open-access full text, of the "
                    "cited journal article, PubMed id pinned per citation. europepmc.org.",
        "url": "https://europepmc.org/",
        "pages_dir": "data_sources/europepmc/pages",
        "page_kind": "pmid",
        "page_url": "https://europepmc.org/article/MED/{page}",
        # Not editable: a published abstract does not change under a citation, so
        # its pages carry no freshness deadline (see data_generators/freshness.py).
        "editable": False,
    },
    "drugsfda": {
        # Regulatory register corpus #18: Drugs@FDA, the FDA's own list of approved
        # applications, read from openFDA's bulk drug/drugsfda export (www.fda.gov
        # refuses scripted downloads). It exists for two facts: a drug's first US
        # approval, as the fallback where Wikipedia (#9/#10) states no first approval,
        # and the sponsor holding that NDA today (`holders`, the page title).
        # tools/fetch/fetch_drugsfda.py takes, per drug, the earliest original (ORIG)
        # approval among the NDAs whose single active ingredient is that drug (never an
        # ANDA, never a combination), and only when that NDA's own FDA class is "new
        # molecular entity" (a "new dosage form" NDA says an older approval exists, and
        # the export misses some old applications). `page` is the application number
        # (NDA019839), resolving at accessdata.fda.gov/scripts/cder/daf/ (ApplNo); the
        # quote is the product row copied by code (`extraction: "code"`, no judge).
        # Author-side pages like #14. Licence: openFDA data is public domain (CC0).
        "ref": "Drugs@FDA (U.S. FDA), approved application history",
        "citation": "U.S. Food and Drug Administration. Drugs@FDA: FDA-approved drugs, "
                    "cited application's original approval (openFDA drug/drugsfda "
                    "export, public domain; application number pinned per citation).",
        "url": "https://www.accessdata.fda.gov/scripts/cder/daf/",
        "pages_dir": "data_sources/drugsfda/pages",
        "editable": True,
        "page_kind": "application",
    },
    "clinpgx": {
        # Pharmacogenomic-association corpus #20: ClinPGx's (formerly PharmGKB) clinical
        # annotations for the genes of the modeled receptors and targets ("patients with
        # the AA genotype may have ..."), one node per annotation (kind receptor_variant).
        # tools/fetch/fetch_clinpgx.py filters the bulk download to our genes at levels
        # 1A-3 (level 4 dropped); `page` is the clinical annotation id, so a citation
        # resolves to clinpgx.org/clinicalAnnotation/<page>. One quote per genotype,
        # ClinPGx's own sentence, copied by code (`extraction: "code"`, no judge).
        # Committed and pinned by sha256 like #15, re-derived by check_data family 12.
        # Licence: CC BY-SA 4.0 (licence text beside the export; ShareAlike covers it).
        "ref": "ClinPGx (PharmGKB), clinical annotation",
        "citation": "ClinPGx (formerly PharmGKB). Clinical annotation, cited id. "
                    "clinpgx.org (CC BY-SA 4.0); annotations are revised, so the export "
                    "is dated.",
        "url": "https://www.clinpgx.org/",
        "tsv_dir": clinpgx.EXPORT_DIR,
        "export_sha256": clinpgx.load_pins(),
        "machine": True,
        "editable": True,
        "page_kind": "annotation",
        "page_url": "https://www.clinpgx.org/clinicalAnnotation/{page}",
    },
    "pubchem": {
        # Physicochemical corpus #21: PubChem's computed properties of a drug's compound
        # (kinds drug_lipophilicity / drug_polar_surface): XLogP3 and the topological
        # polar surface area, computed estimates, not measurements. The compound is the
        # CID on the drug's stored English Wikipedia drugbox; tools/fetch/fetch_physchem.py
        # stores one page per CID (one `Label: value` line per property, the quote, copied
        # by code, no judge). PubChem recomputes, so the page is dated (editable).
        # Licence: PubChem data is public domain.
        "ref": "PubChem (NCBI), computed compound properties",
        "citation": "Kim S, Chen J, Cheng T, et al. PubChem 2025 update. Nucleic Acids "
                    "Res. 2025;53(D1):D1516-D1525. doi:10.1093/nar/gkae1059. Computed "
                    "properties of the cited compound (CID), public domain.",
        "url": "https://pubchem.ncbi.nlm.nih.gov/",
        "pages_dir": "data_sources/pubchem/pages",
        "machine": True,
        "editable": True,
        "page_kind": "cid",
        "page_url": "https://pubchem.ncbi.nlm.nih.gov/compound/{page}",
    },
    "b3db": {
        # Brain-entry corpus #22: B3DB, a curated database of measured blood-brain
        # barrier permeability compiled from 50 published sources (kind drug_bbb): a
        # BBB+ / BBB- label per compound and, for about 1,000 of them, a measured logBB.
        # One bulk TSV from the B3DB GitHub repository, joined by CID (else exact name,
        # chirality-guarded, and always by InChI formula + connectivity) in
        # tools/fetch/fetch_physchem.py, which flattens the matched rows into one page per
        # CID (`page`); the quote is one row line, copied by code (no judge). The
        # repository is updated now and then, so the download is dated (editable).
        # Licence: CC0 1.0.
        "ref": "B3DB, blood-brain barrier permeability database",
        "citation": "Meng F, Xi Y, Huang J, Ayers PW. A curated diverse molecular "
                    "database of blood-brain barrier permeability with chemical "
                    "descriptors. Sci Data. 2021;8:289. doi:10.1038/s41597-021-01069-5. "
                    "github.com/theochem/B3DB (CC0 1.0).",
        "url": "https://github.com/theochem/B3DB",
        "pages_dir": "data_sources/b3db/pages",
        "machine": True,
        "editable": True,
        "page_kind": "cid",
    },
    "agnp_tdm": {
        # Consensus-guideline corpus #19: the AGNP TDM task force's 2026 update of its
        # therapeutic drug monitoring guidelines (Pharmacopsychiatry, open access, a
        # published article, so a book-like corpus: no `editable`, no freshness). Its
        # Table 5 gives each drug's therapeutic reference range, laboratory alert level
        # and level of recommendation to use TDM; Table 1 the CYP isoforms metabolising
        # it. tools/fetch/fetch_agnp_tdm.py reads both tables by cell rectangle off the
        # PDF and copies each row verbatim (`extraction: "code"`, no judge); `page` is
        # the PDF page, matching pages/<page>.md split by tools/fetch/pdf_to_pages.py.
        "ref": "AGNP Consensus Guidelines for TDM in Neuropsychopharmacology, 2026",
        "citation": "Hart XM, Gründer G, Hiemke C, et al. Consensus Guidelines for "
                    "Therapeutic Drug Monitoring in Neuropsychopharmacology: Update 2026. "
                    "Pharmacopsychiatry. 2026;59:166-295. doi:10.1055/a-2860-7861.",
        "url": "https://doi.org/10.1055/a-2860-7861",
        "pages_dir": "data_sources/books/agnp_tdm_2026/pages",
    },
}
