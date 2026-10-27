# 3.143.0 (2026-10-27)

## Added

- The drug map can be rotated with a two-finger twist (or shift-scroll), and touching dots are spread apart by at most one dot width, with a faint line back to their true place (f30a40b, 0e01f1d)
  fr: La carte des substances peut pivoter en tournant deux doigts (ou Maj-molette), et les points qui se touchent sont écartés d’au plus une largeur de point, avec un trait discret vers leur vraie place (f30a40b, 0e01f1d)
- The drug map's class filter groups the classes into families (antidepressants, antipsychotics, stimulants...), each selectable as a whole (307ba4f, 0e01f1d)
  fr: Le filtre par classe de la carte des substances regroupe les classes en familles (antidépresseurs, antipsychotiques, stimulants...), chacune sélectionnable d’un coup (307ba4f, 0e01f1d)

## Improved

- The drug map's controls sit in rounded boxes folded by default (Inputs with its type and axes, Color by, Filter by, Advanced), and its legend and axis meaning in folded boxes under the plot (0e01f1d)
  fr: Les réglages de la carte des substances sont rangés dans des encadrés repliés par défaut (Entrées avec son type et ses axes, Colorer par, Filtrer par, Avancé), et sa légende et le sens des axes dans des encadrés repliés sous le graphique (0e01f1d)
- Drug map dots slide to their new place when the view changes, and fade in or out when they appear or leave; a spinner shows while a slow device recomputes, with a hint to reload past 5 seconds (0e01f1d)
  fr: Les points de la carte des substances glissent vers leur nouvelle place quand la vue change, et apparaissent ou disparaissent en fondu ; un indicateur tourne pendant le recalcul sur un appareil lent, avec une suggestion de recharger au-delà de 5 secondes (0e01f1d)
- The drug map carries an author byline under its title, and its watermark carries the app version (45117ad, 0e01f1d)
  fr: La carte des substances porte la mention de son auteur sous son titre, et son filigrane la version de l’application (45117ad, 0e01f1d)
