# 3.164.0 (2026-11-18)

## Added

- Data browser: stack filters with "Add filter". Each filter has a free-text kind box and a text box, and each one after the first is joined by AND, OR or XOR. For example "Drug classes: benzo" AND "Drug half-life" lists the half-lives of every benzodiazepine. Drag the handle to reorder filters (long press on a phone). A filter that lists drugs can also include their metabolites (768f61b3, e132be79)
  fr: Explorateur de données : empilez des filtres avec « Ajouter un filtre ». Chaque filtre a un champ de type libre et un champ de texte, et chaque filtre après le premier est relié par ET, OU ou OU exclusif. Par exemple « Classes de médicaments : benzo » ET « Demi-vie » liste les demi-vies de toutes les benzodiazépines. Glissez la poignée pour réordonner les filtres (appui long sur téléphone). Un filtre qui liste des médicaments peut aussi inclure leurs métabolites (768f61b3, e132be79)

## Improved

- Data browser: the "Sorting" menu sits on its own line next to the sourcing filter and can now sort by value (half-life, Ki, year...), smallest or largest first (768f61b3, e132be79)
  fr: Explorateur de données : le menu « Tri » a sa propre ligne à côté du filtre de sourçage et trie désormais aussi par valeur (demi-vie, Ki, année...), croissante ou décroissante (768f61b3, e132be79)

## Fixed

- Data browser: the "show both hemispheres" checkbox only appears when a region is listed. More generally, a hidden control can no longer stay on screen (8dfb75cd, e132be79)
  fr: Explorateur de données : la case « afficher les deux hémisphères » n'apparaît que si une région est listée. Plus généralement, un contrôle masqué ne peut plus rester affiché (8dfb75cd, e132be79)
