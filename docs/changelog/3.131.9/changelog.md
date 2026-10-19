# 3.131.9 (2026-10-19)

## Fixed

- Leftover expression sources for receptor groups that were split long ago are pruned, and the data check now re-verifies every stored quote of every corpus against its page, so an orphaned quote can no longer hide (cf342a9, 229172b, e64eaf6)
  fr: Les sources d'expression restées pour des groupes de récepteurs scindés depuis longtemps sont supprimées, et la vérification des données revérifie désormais chaque citation stockée de chaque corpus sur sa page, pour qu'une citation orpheline ne puisse plus passer inaperçue (cf342a9, 229172b, e64eaf6)
- The README sourcing figures are up to date again, and one test now fails whenever any committed generated file falls behind its generator (33e48b3, d72191b)
  fr: Les chiffres de sourçage du README sont à nouveau à jour, et un test échoue désormais dès qu'un fichier généré commité prend du retard sur son générateur (33e48b3, d72191b)
- Every data tool refuses a page name shaped like a file path, enforced by a lint test (82b5648, 269e4b1, 32e9fad)
  fr: Chaque outil de données refuse un nom de page ressemblant à un chemin de fichier, ce qu'impose un test de style (82b5648, 269e4b1, 32e9fad)
