# 3.40.1 (2026-07-29)

## Added
- A source's tooltip now shows where in the book the passage sits, as a trail like "Clozapine › Side effects › How Drug Causes Side Effects", for all five books (bd27676, 9eab4ce, 7e1b5dc)
  fr: L'infobulle d'une source indique désormais où se situe le passage dans le livre, sous la forme d'un fil d'Ariane comme « Clozapine › Effets indésirables › Comment le médicament provoque ces effets », et ce pour les cinq ouvrages

## Fixed
- The uncertain claims were missing from the per-topic bars in the Sources popup, which left a gap in each bar and understated its percentage (3d688ca)
  fr: Les affirmations incertaines manquaient dans les barres par thème de la fenêtre Sources, ce qui laissait un trou dans chaque barre et sous-estimait son pourcentage
- "What's new" no longer skips a visit where you grabbed the separate slider while the brain was assembling (1a1c181)
  fr: « Nouveautés » ne saute plus une visite où vous avez attrapé le curseur d'écartement pendant l'assemblage du cerveau
- A release whose notes had not been published yet is no longer marked as read, which used to lose it for good (2b1b78f)
  fr: Une version dont les notes n'étaient pas encore publiées n'est plus marquée comme lue, ce qui la faisait disparaître définitivement

## Data
- 22 more drug bindings carry the uncertain badge: where the book names a whole receptor family and we publish its subtypes, a subtype with no measured affinity is our own reading, not the book's (c745ba5)
  fr: 22 fixations supplémentaires portent le badge « incertain » : là où le livre nomme toute une famille de récepteurs et où nous en publions les sous-types, un sous-type sans affinité mesurée relève de notre lecture, pas de celle du livre
- The uncertain badge is now derived from where each quote sits in the book rather than from a hand-written list, so a new drug is covered the day it lands (e8098eb)
  fr: Le badge « incertain » découle désormais de l'emplacement de chaque citation dans le livre plutôt que d'une liste écrite à la main : un nouveau médicament est donc couvert dès son ajout
