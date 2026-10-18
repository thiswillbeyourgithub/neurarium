# 3.131.4 (2026-10-18)

## Fixed

- A shared simulation link with an absurd dose ratio no longer breaks every curve: the ratio is kept between 0.1 and 100 (7cac055)
  fr: Un lien de simulation partagé avec un rapport de dose aberrant ne casse plus toutes les courbes : le rapport reste entre 0,1 et 100 (7cac055)
- A bad ghost-opacity value in a view link is ignored instead of making the brain invisible (80827ed)
  fr: Une valeur d'opacité fantôme invalide dans un lien de vue est ignorée au lieu de rendre le cerveau invisible (80827ed)
- Clicking quickly between structures no longer fetches the same Wikipedia summary or changelog twice (90998e4)
  fr: Cliquer rapidement entre structures ne télécharge plus deux fois le même résumé Wikipédia ou le même journal des nouveautés (90998e4)
- The offline cache no longer grows with every language or tour link opened (b2974db)
  fr: Le cache hors ligne ne grossit plus à chaque lien de langue ou de visite guidée ouvert (b2974db)
- Guided-tour text is escaped before display, closing a latent injection path (4a98efb)
  fr: Le texte de la visite guidée est échappé avant affichage, ce qui ferme une faille d'injection latente (4a98efb)

## Improved

- Viewer cleanup: one helper for external links and buttons, no more state hidden on page elements, dead translation fallbacks and an unused export removed (0d35d36, ce3f84d, e8996db, e6c2c36, 1204203, 06e9972, 744f095)
  fr: Nettoyage de la visionneuse : une seule fonction pour les liens externes et les boutons, plus d'état caché sur les éléments de la page, suppression de replis de traduction morts et d'un export inutilisé (0d35d36, ce3f84d, e8996db, e6c2c36, 1204203, 06e9972, 744f095)
