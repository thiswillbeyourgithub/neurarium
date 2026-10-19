# 3.132.1 (2026-10-19)

## Fixed

- The Data browser now lists the gene-based dosing rows and the genetic-variant rows, and a test checks every kind's rows against the coverage tally (944a8f9)
  fr: Le navigateur de données liste désormais les lignes de posologie selon le génotype et les variants génétiques, et un test compare les lignes de chaque type au décompte de couverture (944a8f9)
- Opening a link with only a language or tour setting no longer stops the brain from spinning; only a link that frames a specific view does (242499a)
  fr: Ouvrir un lien qui ne précise que la langue ou la visite guidée n'arrête plus la rotation du cerveau ; seul un lien qui cadre une vue précise le fait (242499a)

## Improved

- Less duplicated code in the data tools: one gene map, one grade ranking, one Ki-quote check, one page reader and quote gate for every sourcing pass, one hemisphere-suffix rule, and unused imports removed, with no change to the published data (c8d3f83, 8e2b105, fe37e5b, 60c8532, 60856f3, 96d1331, a7e36ff, c7bf7e0, 7c4b78e, 1104ca4, adc8556, 5f062db, 806e979, a564772, fa4ec35, 54e2634)
  fr: Moins de code dupliqué dans les outils de données : une seule table de gènes, un seul classement des niveaux de preuve, une seule vérification des citations de Ki, un seul lecteur de pages et une seule porte de citation pour chaque passe de sourçage, une seule règle de suffixe d'hémisphère, et les imports inutilisés retirés, sans changement des données publiées (c8d3f83, 8e2b105, fe37e5b, 60c8532, 60856f3, 96d1331, a7e36ff, c7bf7e0, 7c4b78e, 1104ca4, adc8556, 5f062db, 806e979, a564772, fa4ec35, 54e2634)
