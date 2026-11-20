# 3.173.0 (2026-11-20)

## Added

- Data browser: the kind picker opens on "Name", which filters by a drug's, receptor's or region's name (as the last filter it lists every row of what it matched), then groups every kind under its owner and its panel section, in the panel's own order, with short labels ("Originator" under Drug > Identification, not "Drug originator") (1b672f05, d047b3a0)
  fr: Explorateur de données : le sélecteur de type commence par "Nom", qui filtre sur le nom d'un médicament, d'un récepteur ou d'une région (en dernier filtre il liste toutes les lignes de ce qu'il a trouvé), puis regroupe chaque type sous son propriétaire et sa section du panneau, dans l'ordre du panneau, avec des libellés courts ("Laboratoire d'origine" sous Médicament > Identification, et non "Laboratoire d'origine du médicament")
- Data browser: a section or owner header can be picked as the kind and covers every kind under it, so "Excretion" AND NOT "fec" on the benzodiazepines lists those never excreted in faeces (1b672f05, d047b3a0)
  fr: Explorateur de données : un en-tête de section ou de propriétaire peut être choisi comme type et couvre tous les types qu'il contient, ainsi "Excrétion" ET NON "féc" sur les benzodiazépines liste celles jamais excrétées dans les fèces

## Improved

- Data browser: each filter has a ⋮ menu (Delete, Duplicate, Include metabolites) in place of the ✕ button, metabolites are now included by default, and the AND / OR selector is narrower so a filter fits on one line (8e0e7a54)
  fr: Explorateur de données : chaque filtre a un menu ⋮ (Supprimer, Dupliquer, Inclure les métabolites) à la place du bouton ✕, les métabolites sont désormais inclus par défaut, et le sélecteur ET / OU est plus étroit pour qu'un filtre tienne sur une ligne
