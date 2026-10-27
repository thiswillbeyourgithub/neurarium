# Drugs, metabolism and simulation

The drug dataset, drug metabolism and the Simulation (beta) tab, in full. Split out of `CLAUDE.md` (which keeps a terse summary of each section) to keep that file small; this project is built with the help of Claude Code. Section names referenced below (Nodes, Source provenance, Receptors & targets, ...) are sections of `CLAUDE.md` unless they are one of the three below; the provenance detail lives in [`PROVENANCE.md`](PROVENANCE.md).

## Drugs

A focusable Drugs section showing, per drug, what it does to the brain. The psychiatric
drugs come from **Stahl's Prescriber's Guide (8th ed.)**, extracted **strictly from the dump**
(only interactions literally stated; Stahl's bindings are never overwritten, and a target Stahl does not
list is added only from a judged Wikipedia sentence, see Binding gaps); the `recreational`
category (LSD, MDMA, ketamine, cocaine, nicotine, ...) and any future substance are **not**
Stahl-bound, their bindings sourced from measured **PDSP Ki** instead. Adding a drug is just a
new row in `drugs_data.jsonl` (see Changing the data), so the corpus is open-ended, not a
fixed Stahl list.

> [!NOTE]
> **The roster's scope is CNS-active, not psychiatric.** Both growth routes so far were
> psychiatry-shaped (Stahl's monographs, then the Wikipedia *psychotropic / psychiatric
> medications* lists the roster pass diffed against), so whole CNS families were never
> candidates and their absence looked deliberate when it was only an artefact of the
> sources. A drug belongs here when it acts on a modeled target, whatever specialty
> prescribes it. Deliberately left out: never-marketed research compounds (the abandoned
> non-benzodiazepine GABA-A modulators), and loperamide, a mu agonist that does not cross
> the blood-brain barrier at therapeutic doses, so it would light regions it never reaches.

- **Data.** The drugs live in `tools/data/drugs_data.jsonl`, read by `_load_drugs`. Vocabularies are
  defined once in `generate_data.py`: `DRUG_CATEGORY_LABELS`, `DRUG_ACTIONS` (action -> {label, net
  `effect`}), `DRUG_EFFECT_COLORS`/`DRUG_EFFECT_LABELS` (boost/block/modulate), `DRUG_TARGETS`
  (non-receptor targets, `type` a `TARGET_TYPE_LABELS` key). `_build_drug_targets` merges
  `DRUG_TARGETS` with every receptor id (so a binding can target `sert` or `5ht2a`) ->
  `meta.drug_targets`. `_drug_record` validates category/target/action/effect + rejects duplicate
  ids. A binding's net `effect`: agonist / reuptake-inhibitor / releaser / enzyme-inhibitor / PAM ->
  **boost**; antagonist / inverse-agonist / NAM / blocker -> **block**; partial-agonist / modulator
  -> **modulate**.
- **Animation** (`js/drug-anim.js`). Clicking a drug row (`buildDrugLegend`, grouped by the `#drugs-sort` switch: class, A-Z, approval decade or half-life bucket via `js/legend/drug-groups.js`,
  with the live `#drugs-filter`, which also matches the approval year) focuses it: dims to the union of its targets' regions
  (`selection.setCircuit(regionMeshes, flowArrows)`) + `createDrugAnimation.show(...)`, which
  scatters a `buildGemCloud` coloured by net effect (pulsed per effect) under a `buildWashShell`
  in the same colour, **one pair per (region, effect)**, not per binding: a region carrying many
  of the drug's targets otherwise stacked a cloud + a full-surface wash per binding (26 on one
  region for clozapine), which saturated it to flat white and paid that many shader passes for
  one colour. The group keeps its strongest binding's `affinityWeight`, which scales dot density
  (`buildGemCloud`'s `densityScale`), size and brightness (potent target reads denser/brighter),
  and the wash gain is split between the effects on a region (`washScale`), so a region glows
  like one wash however many effects it carries. Stopped via an `onIsolate` watcher (`.matches`).
- **By-mechanism flow overlay** (reuses `js/circuit-anim.js`). The focus also rides beads along the
  projections of the drug's target system(s). It is a **tone-setter + autoreceptor** model, split from
  the dots: only *tone-setting* bindings drive flow (a reuptake/enzyme/vesicle target or a presynaptic
  inhibitory autoreceptor), never a postsynaptic receptor (those stay dots). `js/data/drugs.js` gives each
  binding a signed `toneSign` (`toneSignOf`: reuptake-inhibitor/releaser/MAO-inhibitor +, vesicular
  (VMAT2)/vesicle-protein blocker − but a VMAT2 **substrate** (`vesicular_releaser`: the amphetamines,
  MDMA, which dump the stores) +, autoreceptor agonist − / antagonist +; a `vesicular` flag + the α2
  group's `sign`/`synaptic` come from `meta.drug_targets`) and an `affinityWeight` (0.35..1 pKi ramp
  from the measured Ki, engagement not effect size). Per engaged kind it sums `toneSign*affinityWeight`
  into `flowSystems` (`{direction, weight, rel}`): the sign is the flow direction (an SSRI drives serotonergic
  **up**, buspirone's 5-HT1A agonism **down**, a VMAT2 blocker **down**), the clamped magnitude its absolute
  `weight`, and `rel` the same normalized **per-drug** so the strongest engaged system = 1 (dosage varies, so
  the overlay shows *relative* intensity across systems). `circuit-anim.js` `play(arrows, flowSystems)` streams
  beads **continuously** end-to-end along each arc (a curated circuit keeps its sequential BFS volley; a drug
  focus, signalled by a passed `flowSystems`, streams so the relative density + speed read), recolouring/scaling
  per arrow off `rel` (boost = warm/bright/fast/dense, damp = cool/dim/slow/sparse). The system map is data: `system_flow_kinds`
  (target `system` -> projection `kind`, the diffuse systems with a modeled source; glutamate/GABA
  left out, and `melatonergic` is mapped for the group panel though its MT1/MT2 are postsynaptic so no
  drug ever rides it). `focusDrug` filters arrows (`flowArrowsOf`), pins + `circuitAnim.play()`s
  them; a purely postsynaptic drug sets no tone -> dots + wash only. **Caveat:** a D2-antagonist
  antipsychotic reads dopaminergic-**up** (blocking the D2 *autoreceptor* disinhibits release); its
  postsynaptic blockade shows in the block-coloured dots. (This is why the dataset carries the ascending
  monoamine pathways.)
- **Panel** (`showDrug`): every `h3`-headed section (Identification: class, NbN, history, brands; Pharmacokinetics with its CNS penetration subsection; Pharmacodynamics: binding profile; Pharmacodynamics: net neurotransmission; Metabolism, whose `h4` subsections (`panel/dom.js` `subSection`) are Active metabolites (`panel/active-metabolites.js`), Metabolic pathways and Pharmacokinetic interactions (`panel/pk-interactions.js`); Pharmacogenomics, whose `h4` subsections are Pharmacogenomic dosing (CPIC) and the BETA Pharmacogenomic associations (ClinPGx), omitted when the drug has neither; then the BETA sections, last: Predicted effects (target-based), Presynaptic modulation, Monitoring (French SmPC)); every heading carries a plain-language subtitle (`panel/dom.js` `withSubtitle`, i18n `<key>Sub`) that stays visible while folded) starts folded, like every detail panel (see
  `docs/VIEWER.md` "Folded panel sections"). A name shown beside the INN (`DRUG_NAME_QUALIFIERS`, display-only + searchable:
  "Paliperidone (9-OH-risperidone)") becomes `drug.label`; a metabolite that is a modeled drug shows under that
  label as a plain `drugNameLink` (the Drugs-list row look), and that drug's own panel opens with "Active
  metabolite of <parent>" (`drug.metaboliteOf`, the parent's sourced entry). Then the molecule image (when fetched), the class, the NbN, the description
  (live-refreshed from Wikipedia, re-graded `sourced`), a Wikipedia link + the EMA / FDA / ClinPGx /
  Drugs.com (+ Vidal in French) `appendLookupLink` searches, then the **Pharmacodynamics: binding profile** binding
  list (each row: an effect glyph + target + action·note, "· speculative" when tentative, plus a
  `bindingProvenancePill` = the binding's quote source, else its Ki (verified), else `NOSOURCE`, or the
  orange ⚠ when it carries `uncertainty[]`, see Source provenance),
  sorted strongest-affinity first. Below it a **Pharmacodynamics: net neurotransmission (estimate)** section (only when `flowKinds` or
  `contextKinds` is non-empty), opening with a derived "indicative only" caution box and the formula caption: one row per
  ascending system whose tone the drug sets (jumps to that kind-mode group), an up/down arrow and the
  signed raw sum `flowSystems[kind].sum`, then one line per contributing binding (`toneBySystem` terms in
  `js/data/tone.js`: target, `tone.rule.<driver>` label from `meta.tone_rules`, `±1 × factor × toneWeightOf(ki)`,
  its own pill), then one neutral-swatch "no tone change" row per `contextKinds` system (engaged only
  through a postsynaptic receptor, pathways lit statically, no beads). `toneWeightOf` is the floor-free Ki ramp (0 at 1 µM, 1 at 0.1 nM, 0.5 without a Ki) so weak hits
  add up without each counting as a strong one; `factor` comes from `meta.tone_factors` (`TONE_FACTORS` in
  `tools/data_generators/drugs.py`: an autoreceptor counts 0.5x, its brake on release being partial). The
  gem dots and the overlay's `weight` keep the floored `affinityWeightOf`. Class +
  Nomenclature (rows of the "Identification" section, above the regulatory history) are clickable (open search with a `class:`/`nbn:` filter) and each carries its grade
  pill: the NbN quote source, and the class classification's `category_provenance` (its own node, kind
  `drug_categories`, default `llm`, upgradeable via `DRUG_CATEGORY_PROVENANCE` / `category_sources`).
- **Half-life + active metabolites (Stahl PK).** A drug carries an elimination `half_life`
  (`{hours, hours_max?}`, its own graded node kind `drug_half_life`, source `half_life_sources`) and a
  `metabolites[]` list of **active metabolite** references `{id, sources}` (graded node kind
  `drug_metabolites`, the sources saying "X is a metabolite of this drug"); the molecule itself (its `name`,
  own `half_life`/`half_life_sources`, a `drug_id` when it is itself a modeled drug so the panel links to it,
  own `bindings`) is ONE record in `tools/data/metabolites_data.jsonl`, whatever drugs make it. `showDrug` renders T½ as an `hl-chip` (auto-scaled to min/h/days via
  `formatHalfLife`, in a **Pharmacokinetics** section between the brands and the **Pharmacodynamics: binding profile** list, beside the Tmax
  chip below) and an **Active metabolites** subsection at the top of Metabolism
  (each row its name + its own T½ chip, "a bit like the Ki"; a link another corpus denies is active wears the orange `contradicted` pill, `CONTRADICTIONS` in docs/PROVENANCE.md). In `buildDrugLegend` a default-on
  **Show active metabolites** toggle (`#drugs-show-metabolites`, persisted `neurarium.metabolites`) adds
  discreet indented `.metab-item` bullets under each parent (a bullet + its parent both stay visible
  when the drugs filter or the global search matches the metabolite name). Pipeline mirrors the brand one:
  `tools/fetch/fetch_pharmacokinetics.py` scans the Stahl page spans into `pk_worklist.json`, one LLM pass
  writes `pk_judged.json`, and `tools/sourcing/apply_pharmacokinetics.py` quote-gates + merges T½/metabolites
  into `drugs_data.jsonl` + `metabolites_data.jsonl` (sole writer). It **merges** each judged metabolite into the store record matched by name
  (`drugs_io.find_metabolite`; the record keeps its name and `bindings`, the quote lands on the drug's reference), accepts a `wikipedia_pharm` quote (`page` = slug) as well
  as a Stahl one, takes an explicit `drug_id` link, and `half_life: null` clears a wrong drug T½. Always scope a
  rerun with `--only <drug ids>`: a full rerun re-applies every old pick, including ones a later pass removed.
- **Time-to-peak (Tmax, Wikipedia + Stahl + DailyMed).** A drug carries a `tmax` in the same `{hours, hours_max?}`
  shape (kind `drug_tmax`, source `tmax_sources`), chipped beside the T½ in the panel's **Pharmacokinetics**
  section. It is what turns the simulation's single assumed peak into a per-drug one
  (`js/sim-model.js` `tmaxHours`): the T½ says how the curve falls, this says how it rises, and a drug
  with no sourced peak keeps `TMAX_HOURS`. Four-step pipeline, over three corpora since none covers
  the roster alone (see `docs/SOURCING_GAPS.md`): `tools/fetch/fetch_tmax.py` offers every peak-naming,
  duration-carrying line of the drug's own Wikipedia article (#9), Stahl monograph (#1) and US
  prescribing label (#14, the one that reaches the drugs the prose corpora never mention) into
  `tmax_worklist.json` with **no verdict of its own**, one LLM pass answers by candidate **index** into
  `tmax_judged.json`, `tools/sourcing/apply_tmax.py` gates it (drug offered; index resolves; the judged
  hours are one the quote actually states, re-parsed by code, so the model never supplies a number;
  `MAX_TMAX_HOURS` = 24 h, which is what rejects a depot or implant peaking in days; quote verbatim on
  its page) and is the sole writer, then `recheck_quotes.py` stamps the judge. The drugbox is
  deliberately not read: it has no Tmax row, and its `Onset of action` row is clinical onset on 60 of
  its 76 rows.
- **Formulations (one molecule, several products).** A drug is ONE molecule (bindings, enzymes, metabolites, TDM stay on it), but a brand, a Tmax or a T½ can belong to one product: Seroquel XR peaks hours after the quetiapine tablet, Invega Sustenna is a monthly depot. So a drug carries an optional `formulations[]`, one per release type a source names (`{release, release_sources, brands?, tmax?, tmax_sources?, half_life?, half_life_sources?}`, kind `drug_formulations`, ONE node per formulation, graded by `release_sources`). `release` is from the closed `RELEASES` vocabulary in `tools/data_generators/formulations.py` (ir, xr, dr, odt, sublingual, nasal, transdermal, injection, depot; emitted as `meta.drug_releases`), each id carrying the patterns a quote must contain to attest it (abbreviations like `LA` / `ER` matched case-sensitively, so French "La" never reads as Ritalin LA; "modified release" deliberately matches nothing, since it covers both DR and XR). A claim whose source names no formulation stays at molecule level: nothing is guessed (valproate's 4 h Tmax is for "oral dosing with divalproex", no release named, so it stays on the molecule). Placement is the usual pipeline with a code half: `tools/fetch/fetch_formulation_worklist.py` reads by code a brand's own release suffix ("Seroquel XR"), a BDPM brand whose every marketed product is one release (Sifrol is not: tablet AND prolonged-release), and a DailyMed / BDPM label sentence naming no formulation (it belongs to the product its page is the label of: paliperidone's 24 h Tmax is the ER tablet's), and offers the rest (EN + FR article sentences naming a brand and a release; a Tmax / T½ quote that itself names a release, e.g. oxycodone "IR : 2–3 hours CR : 4.5 hours" -> two formulations) with no verdict; one LLM pass answers by index into `formulation_judged.json`; `tools/sourcing/apply_formulations.py` gates (offered, index resolves, the sentence attests the release and names the brand, a value is one the sentence states, verbatim on its page) and is the sole writer, moving each placed claim off the molecule; `recheck_quotes.py --kinds drug_formulations` stamps the judge. Every brand / Tmax / T½ applier skips a claim already placed on a formulation (`formulations.placed`, guarded by `tools/tests/test_applier_fixpoint.py`), and `generate_data.py` raises on a claim cited at both levels. A combination product (Contrave, Qsymia, Sativex) is never placed under one constituent. Viewer: the Brands row lists the molecule's brands on one wrapping row of chips (each brand + its own pill), sorted alphabetically (locale-aware, case-insensitive), formulation brands the same way; the Pharmacokinetics section lists each formulation (release + pill, its Tmax / T½ chips, its brands) under the molecule-level chips; search and the primary brand see every brand; the simulation uses the molecule's Tmax / T½, else the IR formulation's only.
- **Therapeutic drug monitoring (AGNP guideline, corpus #19).** A drug carries an optional `therapeutic_range`
  (`{low, high, unit, analyte?, tdm_level?}`, kind `drug_therapeutic_range`) and `alert_level` (`{value, unit,
  analyte?}`, kind `drug_alert_level`), each with its own `*_sources`, emitted by `tools/data_generators/tdm.py` from
  the committed `tools/generated_cache/agnp_tdm.json` (`tools/fetch/fetch_agnp_tdm.py`, code-read Table 5 rows, no
  judge). Shown as chips closing the Pharmacokinetics block (`js/tdm.js`, numbers in the reading language's
  format); the TDM recommendation level rides in the range chip's tooltip. `analyte` names what is measured when it
  is not the drug alone (amitriptyline + nortriptyline). The same cache's Table 1 rows are the last-ranked
  metabolism source (`tdm.merge_enzymes`, in `_load_drug_enzymes` before the generic-UGT pass): a confirming quote on a
  substrate row another corpus states, a substrate row of their own where none does (no `strength`: the table's bold
  marks an in vivo interaction size, not a major route); isoforms outside `ENZYMES` are listed in `tdm.NOT_ADDED`.
- **Regulatory history (first approval + withdrawals, Wikipedia EN then FR).** A drug carries an optional
  `first_approval` (`{year, country?, agency?, national?}`, kind `drug_first_approval`, source `first_approval_sources`)
  and an optional `withdrawals[]` (`{year, country, reason, sources}`, kind `drug_withdrawals`, one node
  each), shown by `js/drug-history.js` as rows of the panel's "Identification" section, above the brands (a withdrawal in caution ink; the approval year is followed by the years elapsed, computed at view time so it never goes stale in the data).
  Every value is an id from a closed vocabulary in `tools/data_generators/history.py` (`COUNTRIES`, with
  the `worldwide` / `most_markets` scopes; `AGENCIES`; `WITHDRAWAL_REASONS`, with `unstated` for a
  sentence that gives no why), emitted into meta as `drug_history_countries` / `drug_history_agencies` /
  `drug_withdrawal_reasons`. Each entry carries the pattern its quote must contain, so the LLM picks the
  sentence and code checks the sentence says it. Four-step pipeline: `tools/fetch/fetch_drug_history.py`
  offers every year-bearing approval/withdrawal sentence of the lead and the history-like sections of the
  stored EN (#9) and FR (#10) articles, with no verdict; one LLM pass answers by index into
  `drug_history_judged.json`; `tools/sourcing/apply_drug_history.py` gates (drug offered; index resolves;
  the year is in the quote; an approval quote names an approval, so a patent-only sentence never passes;
  a withdrawal quote names a withdrawal of a marketed medicine, so neither it nor the sentence before it,
  carried as the candidate's `context`, may be about a food / salt substitute / drink, `NOT_A_MEDICINE_RE`;
  every country / agency / reason is attested by the quote; quote
  verbatim on its page) and is the sole writer; then `recheck_quotes.py` stamps the judge. A brand or
  formulation discontinued, a scheduling ban of a substance not marketed there as a medicine, a ban of it
  as a food (lithium salts sold as a table-salt substitute, US 1949), or "withdrawal" symptoms are not
  market withdrawals; the worklist's `instructions` say so to the judge.
  **Drugs@FDA fallback** (corpus #18): where Wikipedia dates no first approval, `tools/sourcing/apply_drugsfda.py`
  writes the first **US** one, `{year, country: "us", agency: "fda", national: true}`, from the earliest original
  approval of a new-molecular-entity NDA whose only active ingredient is the drug (`tools/fetch/fetch_drugsfda.py`,
  code-read, no judge). `national` relabels the row "First national approval" (`approvalLabel` in
  `js/drug-history.js`), since a US-only register says nothing about earlier approvals abroad. Nothing is
  published when a matching NDA is undated (pre-1982 records) or the earliest one is classed a new dosage form,
  formulation, salt or a drug already marketed unapproved (the export misses some old applications: OxyContin's
  1995 NDA is absent). It replaces a Wikipedia approval only when the FDA date is strictly earlier, since an earlier dated approval proves the later one was not the first (`history.earliest_wins`, applied by both appliers); the wording then follows the FDA source.
- **Origin: originator, its country, current holders.** Three more node kinds in the same "Identification" section (`tools/data_generators/origin.py`, rows by `js/drug-history.js`). `holders[]` (`{market, names[], sources}`, kind `drug_holders`, ONE node per (drug, market), markets `HOLDER_MARKETS` = us, fr) is who holds the marketing authorisation **today**, read by code (`extraction: "code"`, no judge) by `tools/sourcing/apply_drug_holders.py`: the US sponsor from the Drugs@FDA page title of the first-approval NDA (corpus #18), the French holders from the `holder:` header line of the drug's BDPM brand product pages (corpus #16, several when several companies hold brands). A current holder is not the inventor (Seroquel's US NDA is held by CHEPLAPHARM today), hence the separate originator: `originator` (`{name, now?}`, kind `drug_originator`, ONE node per drug) is the company or lab the drug's EN article (#9) says discovered / synthesized / developed it, `name` verbatim in the quote; `now` is that company's current name when the company's own article says it was acquired / merged / renamed (`originator_now_sources`, part of the same node). `originator_country` (a `history.COUNTRIES` id, kind `drug_originator_country`) is read off the originator company's own EN article (Headquarters row or a lead sentence), attested by the country pattern like a withdrawal country. Four-step pass: `tools/fetch/fetch_originator.py` offers the drug sentences matching `origin.ORIGINATOR_RE` and, per company article listed in its `COMPANY_ARTICLES` (slug -> the names the company goes by, hand-confirmed), its location rows and country / successor sentences; one LLM pass answers by index into `generated_cache/originator_judged.json`; `tools/sourcing/apply_originator.py` gates and is the sole writer; `recheck_quotes.py` stamps the judge. A person alone, a later licensee or marketer, or a co-development where the sentence names two companies publishes no originator; a university or institute counts when the sentence names it (it then carries no country, having no company article).
- **Prodrugs (inactive until metabolised).** A drug whose source says it is itself inactive and acts through a named active metabolite carries `prodrug: true` + `prodrug_sources` (kind `drug_prodrug`, ONE node per prodrug) and **no binding of its own**: its pharmacology is its metabolite's, either a linked modeled drug (`drug_id`, e.g. lisdexamfetamine -> Dextroamphetamine) or the metabolite's own sourced `bindings[]` (psilocybin -> Psilocin, clorazepate / prazepam -> nordazepam). The viewer (`js/data/bindings.js`, the prodrug pass before the drug loop) borrows those bindings tagged `viaMetabolite`, so focusing the prodrug lights the 3D scene, flow and "Pharmacodynamics: binding profile" (each row reads "via <metabolite>"), while the node browser and the simulation skip the tag, since the metabolite already owns that node. A receptor / target panel lists a prodrug acting through a modeled metabolite drug (lisdexamfetamine via dextroamphetamine) in its interacting drugs, its row reading "via <metabolite>", but leaves it out of the count (`prodrugsByTarget`, built with `drugsByTarget` by `indexDrugsByTarget`). A drug active itself AND through a metabolite (bupropion) is not a prodrug here, and keeps its metabolites' bindings apart (`metabolite_bindings`, resolved to `metaboliteBindings` with `fromMetabolite`, joined into `allBindings` by `js/data/drugs.js`): they feed the panel readouts (Pharmacodynamics: binding profile, after the parent's own rows; Pharmacodynamics: net neurotransmission and the flow overlay; Predicted effects (target-based) via `effect_index.drug_bindings`; release changes), each row tagged by its compound and the section capped by the shared several-compounds warning (`panel/addons.js` `derivedActiveMetabolites` with `metaboliteContributors`), never its lit regions; codeine, heroin, levodopa, oxcarbazepine and ethyl loflazepate are, since their articles call them prodrugs. A prodrug keeps only the bindings whose action is in `PRODRUG_OWN_ACTIONS` (`precursor`: levodopa is the AADC substrate dopamine is made from), and the viewer appends the borrowed ones to them. Four-step pipeline: `tools/fetch/fetch_prodrug_worklist.py` offers every prodrug / inactive sentence of the drug's EN article (#9) with no verdict; one LLM pass answers by index into `prodrug_judged.json`; `tools/sourcing/apply_prodrug.py` gates (drug offered; index resolves; the quote says prodrug / inactive; it names the metabolite; quote verbatim on its page), is the sole writer of `prodrug` / `prodrug_sources`, adds the metabolite when missing and drops the drug's own bindings; then `recheck_quotes.py` stamps the judge. `generate_data.py` raises on a prodrug with a binding or without a metabolite, and `fetch_ki.py --apply` / `fetch_wikipedia_pharmacology.py` never add a binding to one.
- **Non-modeled-metabolite receptor bindings (Wikipedia).** A metabolite that is not itself a modeled
  drug carries its own `bindings[]` (kind `drug_metabolite_bindings`), sourced from the metabolite's own
  English Wikipedia pharmacology (corpus #9 `wikipedia_pharm`) + the PDSP Ki database (corpus #5): **target
  + action** from a quote-gated prose sentence; **affinity** prefers a PDSP measured Ki, else the Wikipedia
  table value. PDSP is BOTH a target-discovery source (every modeled target with an active assay on the
  metabolite's own name becomes a binding, so norfluoxetine gets its 11 measured sites even though its
  Wikipedia article has no Ki table) AND the preferred Ki for a Wikipedia-found target; a discovered target
  with no sourced action stays an `affinity_only` binding. A receptor's
  Interacting-drugs list then shows the binder as "NAME (metab. of PRODRUG)" (`drug.metaboliteOf`, via
  `drugsByTarget`). Pipeline: `tools/fetch/fetch_metabolite_bindings.py` (reuses
  `fetch_wikipedia_pharmacology` as a library) mines each metabolite's own article (an allow-list of
  confirmed own-articles) **and its parent drug's article** for prose (parent lines mention-filtered to the
  metabolite so a parent-only claim can't leak; an own-article metabolite still draws on its parent because
  a thin own article, e.g. Seproxetine for norfluoxetine, often omits the binding profile the parent states),
  a quote gating against whichever read page holds it, into `metabolite_bindings_worklist.json`; one LLM pass writes
  `metabolite_bindings_judged.json`; `tools/sourcing/apply_metabolite_bindings.py` quote-gates + merges
  into `metabolites_data.jsonl` (sole writer of a metabolite's bindings; a metabolite linked to a roster drug by `drug_id` keeps none, the drug owns them). Scope a rerun with `--only <parent drug ids>`: a full rerun rewrites every metabolite and clobbers later direction / Ki writes. **Shared metabolite:** one
  molecule can be produced by several modeled drugs (desipramine by imipramine + lofepramine, mCPP by
  nefazodone + trazodone, nordazepam by four benzodiazepines); it is one store record referenced by each
  parent, so its bindings and T½ exist once, are tallied once and the viewer lists it once ("metab. of A, B").
- **Binding directions (Wikipedia).** An `affinity_only` binding has a measured Ki and no `action`,
  so what the drug *does* at that target is a NOSOURCE `drug_binding_action` node; a drug's own
  English Wikipedia article (corpus #9) often states that direction in prose where no assay can.
  Pipeline, the same four steps as the CYP one: `tools/fetch/fetch_binding_directions.py` offers, per
  drug, the prose lines naming one of its affinity-only targets (`fetch_metabolite_bindings.action_lines`
  over the stored page, then the shared alias matcher `tools/lib/target_aliases.py`) into
  `binding_directions_worklist.json` with **no verdict of its own**; one LLM pass answers by candidate
  **index** into `binding_directions_judged.json`; `tools/sourcing/apply_binding_directions.py`
  gates it (drug offered, index resolves, target is a **currently** affinity-only binding of that
  drug, action in `DRUG_ACTIONS`, the quote names the target under the very matcher that offered it,
  the quote verbatim on the page) and is the sole writer of the direction; `recheck_quotes.py`
  then stamps the judge. **Confirm-only**: it never adds a binding and never revises a direction
  another corpus states. A **second input** reaches the targets prose never discusses:
  `tools/fetch/fetch_binding_direction_tables.py` reads the `Action` column of the article's own Ki
  table (an exact-vocabulary cell, one verbatim table row as the quote, `extraction: "code"`, so no
  judge and no recheck, exactly like the Ki in the same row) into `binding_directions_tables.json`,
  applied by the same applier's `--tables` through the gates above. A binding neither the prose nor
  the table states stays a NOSOURCE `drug_binding_action` node on purpose, which is most of them (an
  article states a handful of directions, not a whole assay panel).
- **Binding gaps (Wikipedia).** The passes above only complete a binding that already exists; a
  target no assay panel covers and no monograph names (an anaesthetic's GABA-A potentiation,
  amantadine's sigma1 agonism) needs a **new** binding, which the drug's own article (corpus #9)
  often states in prose (only ~15 stored articles carry a drugbox "Biomolecular targets" row, which
  is read too). Same four steps: `tools/fetch/fetch_binding_gaps.py` offers each direction-stating
  sentence naming a target the drug does not yet cover (coarse relatives count, `fetch_ki.COARSE_MEMBERS`)
  into `binding_gaps_worklist.json`, no verdict; one LLM pass decides **every** candidate by index
  into `binding_gaps_judged.json` (a pick needs an action: a direction-less "binds" has no Ki to show);
  `tools/sourcing/apply_binding_gaps.py` is the sole writer, gating index, target, action, not already
  bound, the shared matcher, a per-clause negation/hedge cue, stereo relatives (a racemate's article
  naming its enantiomer is another molecule), and the verbatim quote; `recheck_quotes.py` stamps the
  judge. The predicates fetcher and applier share live in `tools/lib/binding_gaps.py`. A Stahl drug takes a gap too:
  its dump-sourced bindings are never overwritten (a gap only adds a target it does not list), and an unjudged index is reported, so a
  partial pass cannot read as complete.
- **Binding affinity (PDSP Ki).** A binding's `ki` (from `fetch_ki.py`) renders as a `kiChip`: the
  median + `[min-max]` + human/non-human counts + a **verified** badge (tooltip = the representative
  assay). Non-human-only is amber; an alias-borrowed value (`ki.mapped`) carries a "⚠ measured as
  `<compound>`" warning, except an `identity` alias (the same molecule under another PDSP label, e.g.
  paliperidone = 9-OH-risperidone), which keeps only `relation` + `pdsp_names`. `affinity_only` bindings (a Ki, no known direction) list as "affinity only"
  with a neutral glyph, no source pill, and never animate (excluded from `structureIds`/`flowKinds`);
  the missing direction is its own NOSOURCE node (`drug_binding_action`, red ✕ on the action line).
  A **combo** drug (name "A + B") leads with a warning box linking each constituent (`drug.combo`);
  combos carry no Ki. A salt with an INN of its own (dimenhydrinate = diphenhydramine +
  8-chlorotheophylline) declares `constituents` + `constituents_sources` (kind `drug_constituents`,
  ONE node per salt, pilled on the warning box) and borrows each **modeled** constituent's bindings
  tagged "via <constituent>", like a prodrug (`js/data/bindings.js`, mirrored by `effect_index.drug_bindings`;
  kept on the salt's own ligand in the simulation, listed apart in receptor panels); an unmodeled
  constituent lends nothing. A measured Ki backs `_binding_grade`, lifting the binding to `verified`.
  `fetch_ki.py --apply` drops every PDSP assay >=10 uM as "inactive", so a genuine but weak binder
  (caffeine at A2a) can only be recorded by hand; such a `ki.source` carries `"curated": true` so the
  idempotent `--apply` refresh never strips it (`_is_curated_ki`). Where PDSP has no assay at all,
  GtoPdb's curated interactions (corpus #11) fill in: a Ki for a Ki-less binding, and a
  direction for an `affinity_only` one (see `apply_gtopdb_ki.py`). Such a binding is a binding
  like any other: it animates, and its source pill names the corpus. The authored
  `provisional_action` flag exists only for that applier's idempotency and is deliberately **not**
  emitted (`sources` already carry the corpus, so it would be a derivable duplicate).

5 drugs stay unbound as genuinely non-receptor agents (lithium, disulfiram, l-methylfolate,
triiodothyronine, caprylidene). A book corpus carries no `url` key at all (there is no free landing
page to link, and the grade, not the link, conveys provenance); a *present* corpus url must be a
real link, which `check_data.py` enforces.
### Receptor effects (BETA)

`receptor_effect` nodes (H1 antagonism -> sedation, 5-HT3 antagonism -> antiemetic: side effects and therapeutic effects share one vocabulary, the direction-aware join needs no inversion) come from Stahl Essential (#3) prose, with the receptor's own Wikipedia article (#9) as fallback, plus GtoPdb's curated target-function rows (#23: physiological functions, pathophysiology, altered gene expression; a row with a stated non-human species is never offered, see docs/PROVENANCE.md), human / clinical statements only (no knockout phenotype, no gene-association-only or "potential target" line, no ligand list). The GtoPdb candidates are appended after the prose ones, so adding the corpus never shifts an index the judged file answers by. The GtoPdb pages need one network step first (`python tools/fetch/fetch_gtopdb_function.py`, GtoPdb API key as for #7; `--no-fetch` re-flattens offline). Four-step pipeline, offline:

(runbook: [tools/README.md#receptor-effects-release-modulation-and-demographics-beta](../tools/README.md#receptor-effects-release-modulation-and-demographics-beta))

The applier rebuilds the cache from the judged file every run, so dropping a pick there (after a judge reject) drops its node. Gates: closed vocabularies, `inhibition` on non-receptor targets only, the picked sentence was offered for that effect, verbatim on its page.

### Release modulation (BETA)

`receptor_release_modulation` nodes (a 2nd-order effect: H3 autoreceptors on presynaptic terminals decrease histamine release; 5-HT2C heteroreceptors on GABA interneurons decrease dopamine release) come from the same two corpora, human / clinical statements only. Same four steps, sharing the receptor-effect fetcher + `prose_gate.run_applier`:

(runbook: [tools/README.md#receptor-effects-release-modulation-and-demographics-beta](../tools/README.md#receptor-effects-release-modulation-and-demographics-beta))

Gates: closed vocabularies (`RELEASE_KINDS` / `RELEASE_CELLS` / `RELEASE_TRANSMITTERS` / `RELEASE_EFFECTS`), `structure` a modeled structure or null, the sentence names the modulated transmitter (a receptor name like "5HT2C" does not name serotonin), an autoreceptor modulates its own system's transmitter and sits on the releasing neuron (never an interneuron). Use `--unstamped` rather than `--kinds receptor_release_modulation`: a quote shared with another kind is skipped by the `--kinds` filter and leaves the site unjudged.


`receptor_demographic` nodes (receptor / transporter availability across age or sex, e.g. D2 declines ~7% per decade, MAO-B rises with age, 5-HT1A is higher in women) come from human PET / SPECT abstracts hand-listed in Europe PMC (#17) `PAPERS` and routed per owner by `fetch_demographics.PAPERS_BY_OWNER`. Same four steps on `prose_gate`:

(runbook: [tools/README.md#receptor-effects-release-modulation-and-demographics-beta](../tools/README.md#receptor-effects-release-modulation-and-demographics-beta))

Gates: closed factor / direction vocabulary, `structure` a modeled structure or null, the factor's cue offered, every picked paper `human` in the MeSH species ledger (animal studies out), `magnitude` verbatim in a picked sentence (`check_data.py` re-checks it against the emitted quotes). A judge reject is dropped from the judged file (a subgroup-only finding, e.g. CB1 rising with age only in women, is not an unqualified age node).


### Physicochemistry and brain entry

A drug panel's "CNS penetration" subsection (`js/physchem.js`, closing the Pharmacokinetics section, which also renders for a drug carrying only these) shows three chips, each its own node kind with ONE node per drug: lipophilicity as PubChem's XLogP3 (`drug_lipophilicity`, log10 of the octanol/water partition; higher crosses membranes more easily), topological polar surface area (`drug_polar_surface`, in Å²; brain-penetrant drugs usually sit below about 90 Å²), and B3DB's BBB+/BBB- label with measured logBB where a study reported one (`drug_bbb`, a range when its rows differ, e.g. olanzapine `BBB+ (logBB 0.78 to 0.8)`). The label tooltips say the first two are computed estimates and the third curated measurement data, so a reader never takes an XLogP3 for an assay.

Everything is code-read (corpora #21 / #22, see docs/PROVENANCE.md), no LLM and no judge: `python tools/fetch/fetch_physchem.py` writes `tools/generated_cache/physchem.json`, which `tools/data_generators/physchem.py` emits. Coverage: XLogP3 and TPSA on 286 drugs, BBB on 239 (227 BBB+, 12 BBB-; 9 joined by name because B3DB lists a different CID). No value for combination products, salts or mixtures (acamprosate, sodium oxybate, thiopental, ...), inorganics (lithium, xenon) or drugs without a CID (erenumab, nitrous oxide); the cache's `skipped` map says why per drug. A B3DB row whose structure is not the drug's own (InChI guard) is refused rather than published, and rows disagreeing on the label publish no BBB node at all (none today).

### Pre-prescription workup (beta)

A drug panel's "Monitoring (French SmPC)" section (BETA, `js/workup.js`, folded like every section) lists the tests the French product label (RCP) asks for, grouped "before starting" and "during treatment", each row its own `drug_workup` node with its pill (the RCP sentence on hover, linked to the official BDPM `/extrait` page) and a not-medical-advice caveat closing the section. ONE node per (drug, test, timing), from two closed vocabularies in `tools/data_generators/workup.py`: `TESTS` (ECG, echocardiography, blood pressure, heart rate, blood count, electrolytes, kidney / liver / thyroid function, blood glucose, lipids, weight, prolactin, drug level, ammonia, clotting, pregnancy test, HLA genotype, EEG, eye exam) and `TIMINGS` (`before`, `during`). Each entry carries an `attests` pattern the quote must match, so a pick cannot claim a test or timing its sentence does not word; `during` only when the label clearly says so (a monitoring frequency, "en cours de traitement", "surveillance").

Scope rule, applied at pick time and re-read by the judge: a check the label asks of **every** patient is a plain row; a check it asks only of some patients (diabetic or elderly patients, patients at risk, one ancestry for an HLA test) is a **conditional** row, its `conditions` a verbatim French span of the same RCP sentence (gated as a substring of the quote at apply time and again at build time), shown "only if: <condition>" ("seulement si : ..."). Still one node per (drug, test, timing): an unconditional ask outranks a conditional one for the same node. An optional "peut" and a correction ("doivent être corrigées") rather than a test are left out.

Pipeline: corpus #24 (see docs/PROVENANCE.md), fetch -> index pick -> `apply_workup.py` (seven gates, sole writer of `workup.json`) -> recheck (runbook: [tools/README.md#physicochemistry-workup-and-tdm-19-21-22-24](../tools/README.md#physicochemistry-workup-and-tdm-19-21-22-24)). Coverage: 246 nodes over 85 drugs, 85 of them conditional (170 drugs have an RCP page, 8 of them through an EPAR found by name: asenapine, brexpiprazole, cariprazine, deutetrabenazine, guanfacine, lurasidone, tasimelteon, zuranolone; 145 offer at least one candidate line; most others are neither marketed in France nor authorised in the EU), blood pressure 36, weight 32, ECG 29, blood glucose 25, liver tests 24, blood count 18.

## Drug metabolism

Which enzymes clear a drug, or have their activity changed by it. **Pharmacokinetics, so it
has no anatomy**: a liver enzyme is not a brain region, and nothing here ever lights the 3D
scene (the Enzymes section's caption says so, so a still scene reads as intended).

Each row is a sourced claim; the **list is not**, and the section says so out loud via the
`section.metabolism` addon (`docs/VIEWER.md`): it holds the routes some corpus here happens to
name, so a missing isoform means no source stated that route, never that the drug avoids it.
The derived drug -> drug rows read the same list, so an unnamed shared route is an interaction
nothing draws.

- **Data.** `ENZYMES` / `ENZYME_ROLES` (`substrate`/`inhibitor`/`inducer`, each with the
  `direction` it moves a co-prescribed substrate's level) / `ENZYME_STRENGTHS` (`major`/`minor`
  for a substrate, `strong`/`moderate`/`weak` for the rest) live in `tools/data_generators/drugs.py`,
  emitted into `meta.enzymes*`. Field is `enzyme`, not `cyp`: the non-CYP routes (UGT, esterases,
  MAO) will want the same one. Strength is **ordinal on purpose**: the AUC fold-changes behind
  the regulatory tiers are not in the corpora (see `docs/SOURCING_GAPS.md`).
- **Sourcing: the four-step pipeline**, over two corpora, writing two committed caches
  `generate_data.py` merges (rows are NOT authored in `drugs_data.jsonl`); **Stahl wins** a
  (enzyme, role) pair both state.
  - `tools/fetch/fetch_cyp_worklist.py` -> `generated_cache/cyp_worklist.json`: the worklist
    builder, and the only pass that reads a corpus. It offers candidate sentences with **no
    verdict of its own**: Stahl's `Pharmacokinetics` bullets (via `fetch_cyp.py`) and the stored
    English Wikipedia article's drugbox `Metabolism` row plus its isoform-naming sentences (via
    `lib/corpora/wikipedia.py`), each already confirmed verbatim on a real page. It vetoes nothing:
    a negation or somebody else's drug is the judge's problem, not a regex's.
  - The extract pass answers per drug with a candidate **index** plus `(enzyme, role, strength?)`
    into `generated_cache/cyp_judged.json`. An index, never a string, so a paraphrase is not
    expressible; the worst failure is picking the wrong true sentence, which gate 3 below catches.
  - `tools/sourcing/apply_cyp_sources.py` -> `generated_cache/drug_enzymes.json` (Stahl) +
    `drug_enzymes_wikipedia.json` (corpus #9), the **sole writer** of both. Five gates: drug and
    index resolve; the triple is in the vocabulary; **the quote names the isoform the row claims**;
    the quote is verbatim on the cited page under `lib.quote_match.normalize_for_match`; one
    (enzyme, role) pair per drug per corpus, keeping the reading that carries a strength tier.
    A second judged file, `generated_cache/cyp_strength_judged.json`, is the **tier pass**: picks over
    the same worklist naming a sentence that states a kept row's tier in words. Confirm-only (a pick
    restating no kept pair, or a different tier, is rejected and reported), the quote must carry the
    `ENZYME_STRENGTH_WORDS` tier word, and it rides the row the generator keeps (Stahl's when both
    corpora hold the pair) unstamped, so `recheck_quotes.py --unjudged` must judge it.
  - Both fetchers are **libraries, not scripts**: they know where a corpus keeps its pages and how
    its sentences are shaped, and state no claim.
- **Which enzyme FORMS an active metabolite** is the mirror relation (there the drug is the
  substrate, here the metabolite is the product) and its own node kind, so it is **hand-curated**
  in `tools/data_generators/quotes/metabolism.py` (`METABOLITE_ENZYME_QUOTES`, keyed
  `(drug_id, metabolite name)`) rather than grepped: the corpora state it as prose whose near
  misses are all wrong the same way (an enzyme that *clears* the metabolite, or makes a different
  one). 14 of the 36 metabolites are covered; the rest stay NOSOURCE. `reaction` is an optional
  `ENZYME_REACTIONS` key (a closed, translated vocabulary), omitted when the source names the
  enzyme but not the step. `generate_data.py` raises if a key matches no metabolite, so an
  applier re-run cannot silently drop a node.
- **Population variability** (corpus #13 PharmFreq). The rows above say which isoform clears a
  drug; this says how fast *people* do, which is the only thing in the dataset that varies by who
  is taking the drug. Per isoform, the frequency of each metabolizer phenotype (`METABOLIZER_PHENOTYPES`,
  ordered slowest to fastest: PM/IM/NM/RM/UM) in each population group (`METABOLIZER_GROUPS`, both in
  `data_generators/drugs.py`, emitted as `meta.metabolizer_*`). `tools/fetch/fetch_pharmfreq.py`
  reshapes the export into `tools/generated_cache/enzyme_variability.json`, which
  `build_enzymes()` merges onto the emitted `meta.enzymes`; deterministic, so `pipeline = machine`.
  The export is the one corpus **committed** with the repo (`tools/data/pharmfreq/`, one TSV per
  gene, small and freely redistributable), so its record declares `tsv_dir`, not `pages_dir`: the
  quote is a sentence composed out of the table, so a page written from the same numbers could not
  gate it. The cache pins each file's sha256 instead, `provenance.py` re-checks the pins at
  generation time and `check_data.py` family 12 rebuilds every profile and quote from the files, so
  this is the only quote gate that runs on a plain clone. Shared reader:
  `data_generators/pharmfreq.py`.
  5 of the 18 isoforms are covered, and an uncovered one simply has no `variability` key: CYP3A4 and
  CYP1A2, the two this dataset leans on hardest, are absent from the source, which is a gap in the
  corpus and not a claim that they do not vary.
- **Prescribing guidance** (corpus #15 CPIC, node kind `drug_pgx`). The third layer: #13 says how
  common a clearance speed is, the enzyme rows say which isoform clears *this* drug, and neither says
  what either implies for the person taking it. One node per (drug, gene, phenotype), carrying CPIC's
  implication sentence and its recommendation verbatim plus the strength CPIC attaches to the advice
  (`classification`). 104 rows over 18 drugs, 4 genes and 6 guidelines. Three rules keep it honest:
  only genes with a #13 frequency profile are imported (a row with no base rate beside it would be
  guidance with no readout); CPIC's two-gene rows are kept only where the *other* gene is a normal
  metabolizer, recorded as `assumes` on the row rather than left implicit; and a guideline that states
  a population narrower than CPIC's default (`adults`, `PHT naive`) says so on the block instead of
  passing as general. `tools/fetch/fetch_cpic.py` pulls the API into the committed
  `tools/data/cpic/cpic_recommendations.json` + `tools/generated_cache/cpic_guidance.json`; shared
  reader `data_generators/cpic.py`, gated by re-derivation exactly like #13 (`check_data.py` family
  12). Every exclusion is printed on each fetch run, never silently skipped.
  CPIC also fills a **metabolic route** when its own wording states one
  (`cpic.enzyme_claims_for`): the stock faster-metabolizer line "Consider alternative drug not
  metabolized by CYP2C19; If clomipramine is warranted, ..." names the gene and the drug, so it
  can be quoted for the enzyme row. Only that phrasing is read, since a levelled pair on its own
  is a verdict and not a sentence, and only as a filler, `_load_drug_enzymes` keeping whatever a
  book or an article already said about the pair. It fires on 5 pairs and adds exactly one row:
  clomipramine's CYP2C19, which Stahl files under CYP1A2 and Wikipedia does not mention.
- **Viewer.** `showEnzyme` leads with **How fast people clear it** (one stacked bar per population
  group, segments in phenotype order, its own grade pill on the heading) above the drug lists,
  because it qualifies all of them: a "major substrate" row means something different to a poor
  metabolizer. Nothing rounds or drops a band: each bar is drawn at the measured widths and a tip
  on the **bar** (not on a segment, since a 1%-wide one is no hover target) names every speed with
  its exact frequency. A PharmFreq lookup link sits beside the caption (`PHARMFREQ_URL`, a browse
  link like PDSP's: the site is a Shiny app with no per-gene URL). The caption states the caveat
  that carries the ethics of the section: these are frequencies across study cohorts, most groups
  contain every speed, and only a genetic test says which one a person has. `showDrug` gains a **Metabolism** list (caption, ClinPGx pathway-search link, the section caveats, then one `h4.enz-role` heading per role, "Substrate of" / "Inhibits" / ..., from `ENZYME_ROLES` `heading`, over single-line enzyme rows: enzyme, its role pill, then strength + its strength pill, clickable to the enzyme) ending in a **Pharmacokinetic interactions**
  subsection, **after** the anatomy sections
  (pharmacokinetics lights nothing in the scene, so it does not interrupt Pharmacodynamics: binding profile -> Pharmacodynamics: net neurotransmission);
  each **Active metabolites** row gains a `.metab-formed` "formed by
  <enzyme>" line with its own pill. An **Enzymes** accordion section
  (`buildEnzymeLegend`) opens `showEnzyme`: a ClinPGx search (the variant / poor-vs-ultra-rapid
  metabolizer story this dataset does not model), the metabolites that isoform forms, then its drugs
  grouped by role. Both ends share one `enzymeRow` builder (same node, either side).
  `pgxSection` then adds **Pharmacogenomic dosing (CPIC)**, the first subsection of the **Pharmacogenomics** section right under Metabolism: one
  `<select>` picking a population group, then per gene a block (CPIC level + guideline link) whose
  rows run slowest to fastest, each a swatch from the *same* `--var-*` ramp as the enzyme bars, that
  group's frequency, a grade pill, CPIC's implication, its recommendation, the strength, and the
  assumption if the row carries one. The pick is **not persisted** (`pgxGroup` is a module-level
  variable, deliberately not in `js/prefs.js`): nothing should record which ancestry a clinician
  looked at. The caveat paragraph is part of the section rather than a tip, because the number is a
  group base rate and an ancestry is not a genotype.
- **The drug -> drug edges are derived, never stored** (`pkInteractionsOf` in `js/data/pk.js`, like
  `flowSystems`): an inhibitor/inducer of an enzyme meets its substrates, one row per (other drug,
  direction) naming every shared isoform. Rendered two ways from the same edges via a persisted
  segmented control (`PK_GROUP_KEY`): **by drug** (the four `PK_DIRECTIONS` buckets as headings,
  raises/lowers first, then raised-by/lowered-by) or **by enzyme** (one heading per isoform, so a
  pair meeting at two isoforms appears under each, sub-grouped by those same four directions). A
  row is the drug name alone: the direction is always a heading above it, never repeated per row.
  Capped **per heading** (8) with the rest expandable in place, since a global cap would swallow
  whole headings. Collapsed by default (a `disclosure` `<details>`,
  summary = title + edge count, opening it scrolls itself to the top of the pane) so dozens of
  derived rows don't bury the sourced sections above. Because the edges are an **inference**, every
  string stays conditional ("could raise", never "raises"). The caption states it is a flag to check
  with a prescriber, **never a contraindication**, and that a missing row is not a safety claim.

## Simulation (beta)

**Receptor occupancy, asked from both ends**: forward, what a combination of drugs engages, and
backward, which combination would approach a profile the visitor describes. The only place in the
app that **computes** a claim instead of reporting a sourced one, which is why the tab leads with
what it answers and in what unit, then a box listing what the model does not know (stated as
non-exhaustive, and every string in it conditional).

**What it computes is an engagement index, never a percentage occupied**, and the distinction is
load-bearing: occupancy is `(C/Ki)/(1 + Σ C/Ki)`, so a Ki supplies the denominators and the
concentration at the receptor supplies everything else. Reaching a real C needs per-drug PK the
dataset does not have (dose + molar mass, bioavailability, Vd, free fraction, unbound
brain-to-plasma ratio, an absorption rate), plus two terms that are not PK at all (the endogenous
transmitter the drug competes with, and efficacy). `js/sim-model.js`'s header point 5 spells this
out; it is also why potencies add instead of competing, since competition is meaningless before
every C is on one real scale and would break the linearity the inverse solve needs.

- The maths live in `js/sim-model.js`, whose header states each shortcut once (one assumed
  time-to-peak for a drug with no sourced one, a range T½ collapsed to its midpoint, potencies added with no competition, a
  fully-formed metabolite); the warnings box is that list rendered for the visitor, plus the
  enzyme-sharing flags `pkFlags` derives from the picked drugs.
- The tab is `js/simulation.js` (sections + state) over `js/sim-plots.js` (the two SVGs): a plasma
  plot whose scrub position re-reads the receptor plot at that hour, and a receptor plot of boost /
  block stacks split per ligand, grouped by neurotransmitter system. A bar is filled in its
  receptor's **transmitter** colour (`meta.receptor_family_colors`, so a column reads as its
  pathways do in the scene); the ligands sharing one bar are told apart by stepped opacity,
  strongest first, since the hue is spoken for.
- **A direction-less (`affinity_only`) binding is not signed**: it draws as a hatched grey "binds,
  effect unknown" band above the boost stack and stays out of the net, so an occupied receptor
  nobody sourced a direction for reads as a gap rather than disappearing.
- The reverse question ("which drugs give me this profile?") is a non-negative least squares over
  the same matrix, held to the drugs already listed, so it answers what to *add*.
- URL: tab key `simulation:1` (a view, not a node, so `#simulation=1` is its legacy alias) plus
  `sim=<id>[:<ratio>],...` for the picked list.
