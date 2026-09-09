# 3.69.0 (2026-09-09)

## Added

- The guided tour now shows the three controls it used to walk past: the **Legend** popup, the **Data browser** (introduced right after the sourcing breakdown, since it holds the very facts that tally counts), and the two view toggles, hiding the 3D model to read in peace and folding the panel away to see the brain alone. It opens with how to read the app before walking the data, and runs 32 steps in about four minutes. (1d82c83)
  fr: La visite guidée montre enfin les trois commandes qu'elle passait sous silence : la fenêtre **Légende**, l'**explorateur de données** (présenté juste après le récapitulatif des sources, puisqu'il contient précisément les faits que ce décompte totalise) et les deux bascules d'affichage, masquer le modèle 3D pour lire tranquillement et replier le panneau pour voir le cerveau seul. Elle commence par expliquer comment lire l'application avant de parcourir les données, et compte 32 étapes pour environ quatre minutes.

## Fixed

- The tour named two sections by labels they no longer carry ("Receptors", "Projections") and listed them in the wrong order; it now names all five as they appear on screen. The drug-interactions step no longer repeats the caption it is pointing at, and says how to move on. (1d82c83)
  fr: La visite nommait deux sections par des libellés qu'elles ne portent plus (« Récepteurs », « Projections ») et les listait dans le désordre ; elle nomme désormais les cinq telles qu'elles apparaissent à l'écran. L'étape sur les interactions médicamenteuses ne répète plus la légende qu'elle désigne, et indique comment poursuivre.
- Switching from a drug's tab back to **Settings** left the drug's animation, its glow and its pinned pathways playing behind the controls. The scene is now put back; the tab stays open, and clicking it again brings the focus back. (b03ff95)
  fr: Passer de l'onglet d'un médicament aux **Réglages** laissait tourner son animation, sa lueur et ses voies épinglées derrière les commandes. La scène est maintenant rendue à son état neutre ; l'onglet reste ouvert, et le rouvrir ramène la mise au point.
- Folding the panel down while the 3D model was hidden left a single line of header over an empty black screen. Folding the panel now brings the brain back. (b2c2a54)
  fr: Replier le panneau alors que le modèle 3D était masqué ne laissait qu'une ligne d'en-tête sur un écran noir. Replier le panneau ramène désormais le cerveau.
