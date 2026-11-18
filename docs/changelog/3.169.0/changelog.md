# 3.169.0 (2026-11-18)

## Improved

- The data browser waits for a Search button (or Enter) instead of re-listing on every keystroke, which keeps it responsive on a phone; the button lights up when the filters changed since the last search (c6ab4ad5)
  fr: Le navigateur de données attend un bouton Rechercher (ou Entrée) au lieu de tout relister à chaque frappe, ce qui le garde réactif sur téléphone ; le bouton s'allume quand les filtres ont changé depuis la dernière recherche
- An added AND filter only offers the kinds that can still match: after "Drug class: benzo", region kinds are no longer suggested (c6ab4ad5)
  fr: Un filtre ET ajouté ne propose que les types encore possibles : après « Classe de médicament : benzo », les types anatomiques ne sont plus suggérés

## Fixed

- On a touchscreen, swiping the data browser's kind list now scrolls it instead of picking the item under the finger (c6ab4ad5)
  fr: Sur écran tactile, glisser dans la liste des types du navigateur de données la fait défiler au lieu de choisir l'élément sous le doigt
