# 3.30.0 (2026-07-26)

## Added
- Metabolism: each drug now lists the liver enzymes that clear it, or whose activity it changes, with the source for each (9c1b26d, 439f759)
  fr: Le métabolisme : chaque médicament liste désormais les enzymes hépatiques qui l'éliminent, ou dont il modifie l'activité, avec la source de chaque information
- Possible drug interactions, worked out from those enzymes: which other drugs in the dataset could see their levels rise or fall (279ae71)
  fr: Les interactions possibles entre médicaments, déduites de ces enzymes : quels autres médicaments du jeu de données pourraient voir leur concentration monter ou descendre
- An Enzymes section in the side panel: pick an enzyme to see the drugs it handles, grouped by role (279ae71, 1dad5cb)
  fr: Une section Enzymes dans le panneau latéral : choisissez une enzyme pour voir les médicaments qu'elle traite, groupés par rôle
- Molecule diagrams for the 53 drugs added in the previous release (4cda9c7)
  fr: Les schémas moléculaires des 53 médicaments ajoutés à la version précédente

## Docs
- Surveyed how drug metabolism could be sourced before building it (7c51882)
  fr: État des lieux des sources possibles pour le métabolisme des médicaments, avant de le construire
