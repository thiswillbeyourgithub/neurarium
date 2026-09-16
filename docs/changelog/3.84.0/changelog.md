# 3.84.0 (2026-09-16)

## Data

- The Wikipedia binding tables now fill in 64 more binding directions, across 15 drugs: where the article lists a drug's affinities, it often names the direction in the column beside them. Bindings still missing a direction drop from 712 to 648, and the overall sourced figure rises from 83% to 84%. (1123486)
  fr: Les tableaux de liaisons de Wikipédia renseignent désormais 64 sens de liaison supplémentaires, sur 15 médicaments : là où l'article liste les affinités d'un médicament, il nomme souvent le sens dans la colonne voisine. Les liaisons encore sans sens passent de 712 à 648, et le taux global de sourçage monte de 83 % à 84 %.

## Added

- A second sourcing pass for binding directions, reading the "Action" column of a drug's own Wikipedia affinity table rather than its prose. A copied cell cannot be the wrong sentence, so this one is read by code with no model in the loop, and only a wording the dataset already knows is accepted: anything ambiguous is reported and left alone. (4f5541c, 34ee884)
  fr: Un second passage de sourçage pour les sens de liaison, qui lit la colonne « Action » du tableau d'affinités de l'article Wikipédia du médicament plutôt que sa prose. Une cellule recopiée ne peut pas être la mauvaise phrase : celui-ci est donc lu par du code, sans modèle dans la boucle, et seule une formulation déjà connue du jeu de données est acceptée ; tout ce qui est ambigu est signalé et laissé tel quel.

## Docs

- The repository map and the tool reference describe the new table pass beside the prose one it complements. (5b4ad82)
  fr: La carte du dépôt et la référence des outils décrivent le nouveau passage par tableau à côté du passage en prose qu'il complète.
