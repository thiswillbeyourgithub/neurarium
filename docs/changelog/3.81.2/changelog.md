# 3.81.2 (2026-09-12)

## Fixed

- The button that hides the 3D model kept reading "Hide the 3D model" once the model was already hidden, in its tooltip and in the search results alike, while a click did the opposite. It now names what a click will actually do, the way the day/night button beside it does. (c1d4a7e)
  fr: Le bouton qui masque le modèle 3D continuait d'afficher « Masquer le modèle 3D » une fois le modèle déjà masqué, dans son infobulle comme dans les résultats de recherche, alors qu'un clic faisait l'inverse. Il indique désormais ce qu'un clic va réellement faire, comme le bouton jour/nuit à côté de lui.
- Choosing "Show active metabolites" in the search results changed the setting with nothing at all to show for it: the option sits inside the Drugs section, which was left closed. Search now opens the section holding an option it changes, so you can see what you just did. (60d7626)
  fr: Choisir « Afficher les métabolites actifs » dans les résultats de recherche modifiait le réglage sans rien laisser voir : l'option se trouve dans la section Médicaments, qui restait fermée. La recherche ouvre désormais la section contenant l'option qu'elle modifie, pour que le changement soit visible.
