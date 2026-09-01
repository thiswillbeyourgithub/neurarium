# 3.53.0 (2026-09-01)

## Added

- The Data browser now opens as its own tab instead of a dropdown inside the panel, so the whole list of facts gets the full pane (f0a95cf)
  fr: L'explorateur de données s'ouvre désormais dans son propre onglet plutôt que dans un menu déroulant du panneau, ce qui donne toute la place à la liste des faits (f0a95cf)
- Two more things are now shareable as a link: the Data browser itself (add `#browser=1` to the address) and the reading mode that hides the 3D brain (`#panel=1`, or `#panel=0` to force the brain back on) (f0a95cf)
  fr: Deux choses de plus se partagent maintenant par lien : l'explorateur de données lui-même (ajoutez `#browser=1` à l'adresse) et le mode lecture qui masque le cerveau 3D (`#panel=1`, ou `#panel=0` pour le réafficher) (f0a95cf)
- The Data browser explains what a node is and labels its columns with the fields each line carries, so it reads as the graph of facts it is (564f411)
  fr: L'explorateur de données explique ce qu'est un nœud et nomme ses colonnes d'après les champs que porte chaque ligne, pour qu'il se lise comme le graphe de faits qu'il est (564f411)
- A "The same data as files" link at the top of the Data browser opens the list of downloadable data files (564f411)
  fr: Un lien « Les mêmes données en fichiers » en haut de l'explorateur de données ouvre la liste des fichiers téléchargeables (564f411)

## Fixed

- A sourcing badge in the Data browser only offered "Click for details"; it now shows the actual source behind the fact (the quote, the measured affinity, or the reasons to doubt it), like the same badge inside a panel (564f411)
  fr: Une pastille de source dans l'explorateur de données ne proposait que « Cliquez pour en savoir plus » ; elle montre désormais la source réelle du fait (la citation, l'affinité mesurée ou les raisons d'en douter), comme la même pastille dans un panneau (564f411)

## Improved

- "Show both hemispheres" is now off by default in the Data browser, so each region is read once instead of twice, and the checkbox only appears when brain structures are actually in view (564f411)
  fr: « Afficher les deux hémisphères » est maintenant décoché par défaut dans l'explorateur de données, chaque région se lit donc une seule fois, et la case n'apparaît que lorsque des structures cérébrales sont effectivement affichées (564f411)
