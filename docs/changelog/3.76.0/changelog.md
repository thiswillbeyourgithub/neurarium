# 3.76.0 (2026-09-10)

## Added

- Every source tooltip now ends with the chain of custody that produced its quote, so a green check tells you not only how well a claim is backed but by what process: "raw data → deterministic extraction → code checks the quote is on the page → neurarium" for a value copied out of a table, "source page → an LLM finds the quote → code checks the quote is on the page → an amnesic LLM judges the quote → neurarium" for a sentence read off a book page (26ba4cf).
    fr: Chaque infobulle de source se termine désormais par le parcours qui a produit sa citation : la coche verte ne dit plus seulement à quel point une affirmation est étayée, mais par quel procédé. « données brutes → extraction déterministe → le code vérifie que la citation est sur la page → neurarium » pour une valeur recopiée d'un tableau, « page source → un LLM trouve la citation → le code vérifie que la citation est sur la page → un LLM amnésique juge la citation → neurarium » pour une phrase lue sur une page de livre.
- The Sources & provenance panel says, under the grade key, that quotes reach the dataset by several different routes and that each tooltip names its own.
    fr: Le panneau Sources et provenance précise, sous la légende des niveaux, que les citations arrivent dans le jeu de données par plusieurs chemins différents et que chaque infobulle indique le sien.
