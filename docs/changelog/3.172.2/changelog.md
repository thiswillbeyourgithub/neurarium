# 3.172.2 (2026-11-20)

## Fixed

- Data browser: an AND NOT filter with text now lists its own kind's rows that miss the text ("benzodiazepine AND NOT excretion: urine" lists the excretion rows of benzodiazepines never excreted in urine, instead of a class row), and a drug with no data of that kind is no longer counted as a match; an AND NOT with no text still finds what is missing (95f14140)
  fr: Explorateur de données : un filtre ET NON avec du texte liste désormais les lignes de son propre type qui ne contiennent pas ce texte ("benzodiazépine ET NON excrétion : urine" liste les lignes d'excrétion des benzodiazépines jamais excrétées dans l'urine, au lieu d'une ligne de classe), et un médicament sans donnée de ce type n'est plus compté comme une réponse ; un ET NON sans texte trouve toujours ce qui manque

## Data

- Excretion sourced for seven of the newly added French CNS drugs (periciazine, etifoxine, nefopam, nordazepam, piribedil, eslicarbazepine acetate, oxetorone), from their Wikipedia articles and French SmPCs (2681cac6)
  fr: Excrétion sourcée pour sept des médicaments du SNC français récemment ajoutés (périciazine, étifoxine, néfopam, nordazépam, piribédil, acétate d'eslicarbazépine, oxétorone), à partir de leurs articles Wikipédia et de leurs RCP français
