# 3.74.0 (2026-09-09)

## Data

- Every drug-metabolism row (which enzyme clears a drug, which enzyme the drug blocks or speeds up) is now read by a model and checked against the source page, like every other fact in the dataset. They used to be found by pattern matching, which could not tell "is metabolized by CYP2D6" from "is not", so a handful of rows said the opposite of their own source. 88 more rows, all quote-verified. (747efd5)
  fr: Chaque ligne de métabolisme des médicaments (quelle enzyme élimine un médicament, quelle enzyme il bloque ou accélère) est désormais lue par un modèle puis confrontée à la page source, comme tous les autres faits du jeu de données. Ces lignes provenaient d'une simple reconnaissance de motifs, incapable de distinguer « est métabolisé par le CYP2D6 » de « ne l'est pas », si bien que quelques lignes affirmaient le contraire de leur propre source. 88 lignes de plus, toutes vérifiées par citation.
