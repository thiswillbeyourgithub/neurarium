# 3.57.0 (2026-09-02)

## Added

- On a device that turns out to be too slow to build the brain's 3D shapes in reasonable time, the remaining structures are now built at reduced detail so the page still opens promptly, and the loading screen says so rather than quietly serving you a coarser brain. Only the shapes soften; no data changes (1df2505)
  fr: Sur un appareil qui s'avère trop lent pour construire les formes 3D du cerveau en un temps raisonnable, les structures restantes sont désormais générées avec moins de détail pour que la page s'ouvre rapidement, et l'écran de chargement le signale au lieu de vous servir discrètement un cerveau plus grossier. Seules les formes sont adoucies, aucune donnée ne change (1df2505)

## Improved

- The startup progress bar now reflects the real remaining work: it advances while a single structure is being built rather than only once it lands, and it weighs each structure by how much work it actually costs, so a long pause reads as progress instead of a freeze (1df2505)
  fr: La barre de progression au démarrage reflète maintenant le travail réellement restant : elle avance pendant la construction d'une structure au lieu d'attendre qu'elle soit terminée, et pondère chaque structure selon son coût réel, pour qu'une longue pause traduise une progression plutôt qu'un blocage (1df2505)
