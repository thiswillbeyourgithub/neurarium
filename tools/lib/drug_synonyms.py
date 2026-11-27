"""Same-molecule name synonyms, keyed by drug (or metabolite-store) id.

One list read by two consumers: the PDSP Ki join (``fetch/fetch_ki.py`` merges these
labels into a drug's direct match) and the viewer search (``data_generators/drugs.py``
adds the ones naming a modeled drug to its search aliases), so a former INN such as
"trimeprazine" both joins its assays and finds alimemazine in the search box.
"""

# Pure name synonyms: the SAME molecule filed under a second label, usually an
# abbreviation the submitting lab used ("PCP"). Unlike ALIAS these are merged INTO the
# direct match rather than being a fallback, and carry no "measured as" warning,
# because there is no other compound involved: dropping them would just silently throw
# away assays (PCP's 18 rows against phencyclidine's 7). Only add a label that names
# the identical substance; anything with a different structure belongs in ALIAS.
SYNONYMS = {
    "phencyclidine": ["PCP"],
    "norquetiapine": ["N-Desalkylquetiapine"],
    # Former INN / US name of the same molecule.
    "alimemazine": ["Trimeprazine"],
    "clorgiline": ["Clorgyline"],
    "pizotifen": ["Pizotyline"],
    "desipramine": ["Desmethylimipramine"],
    "desvenlafaxine": ["O-Desmethylvenlafaxine"],
    "levodopa": ["L-DOPA"],
    "cannabidiol": ["CBD"],
    # The INN "tomoxetine" named the (R)-enantiomer, renamed atomoxetine in 2003. Its
    # racemate LY135252 is deliberately absent.
    "atomoxetine": ["Tomoxetine"],
    # US Adopted Name of the same (racemic) molecule.
    "chlorphenamine": ["Chlorpheniramine"],
    # Developer code names (company serial numbers) of the same molecule.
    "agomelatine": ["S 20098"],
    "aripiprazole": ["OPC-14597"],
    "asenapine": ["ORG-5222"],
    "flibanserin": ["BIMT 17"],
    "flumazenil": ["Ro15-1788"],
    "ketanserin": ["R-41-468"],
    "lurasidone": ["SM 13496"],
    "mirtazapine": ["Org3770", "ORG-3770"],
    "pimavanserin": ["ACP-103"],
    "tropisetron": ["ICS 205-930", "ICS 205930"],
}
