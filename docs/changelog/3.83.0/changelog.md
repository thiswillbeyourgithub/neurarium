# 3.83.0 (2026-09-16)

## Data

- A drug binding is now two claims, and each is graded on its own: that the drug binds the target (a measured affinity settles that) and in which direction it acts (agonist, antagonist, and so on), which only a written source can settle. Before, 767 bindings known only by their affinity counted as fully sourced; they now show a red "no source" mark on their direction, and the overall sourced figure drops from 95% to 83%, which is the honest number. (a8ddea2, 569d73e, 40c5586)
  fr: Une liaison médicamenteuse est désormais deux affirmations, chacune notée séparément : que le médicament se fixe sur la cible (une affinité mesurée le tranche) et dans quel sens il agit (agoniste, antagoniste, etc.), ce que seule une source écrite peut trancher. Auparavant, 767 liaisons connues par leur seule affinité comptaient comme entièrement sourcées ; elles portent maintenant une marque rouge « sans source » sur leur sens, et le taux global de sourçage passe de 95 % à 83 %, qui est le chiffre honnête.
- A new sourcing pass reads each drug's own Wikipedia article for a sentence that states the direction of a binding known only by its affinity, checks the sentence is really on the page, and has a second model confirm it supports the claim. It closed 55 of those bindings; the rest stay marked as missing because the article never says. (7b5681a, f482b7f, 711e13c)
  fr: Un nouveau passage de sourçage lit l'article Wikipédia de chaque médicament pour y trouver une phrase qui énonce le sens d'une liaison connue par sa seule affinité, vérifie que la phrase figure bien sur la page, et fait confirmer par un second modèle qu'elle soutient l'affirmation. Il a comblé 55 de ces liaisons ; les autres restent marquées comme manquantes parce que l'article ne le dit pas.

## Fixed

- In the simulation's "find drugs" answer, a pick that pulls against what you asked for (it only compensates a drug you already listed overshooting the target) now says so, and the fit percentage states how many receptors it was judged over. (276a667)
  fr: Dans la réponse « chercher des médicaments » de la simulation, une proposition qui va à l'encontre de ce que vous avez demandé (elle ne fait que compenser un médicament déjà listé qui dépasse la cible) le dit désormais, et le pourcentage d'ajustement précise sur combien de récepteurs il a été jugé.

## Docs

- The repository map lists the new binding-direction node kind and the Wikipedia pass that sources it. (40c5586, c55d661, e55a16c)
  fr: La carte du dépôt recense le nouveau type de nœud « sens de liaison » et le passage Wikipédia qui le source.
