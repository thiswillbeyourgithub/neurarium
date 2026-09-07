# 3.60.1 (2026-09-07)

## Fixed

- Both affinity databases were read by a name match that ignored stereochemistry, so a single mirror-image form of a molecule was silently counted as the everyday form. Seventeen drugs pooled measurements taken on one mirror image into the other's figures. The two readers now check which form a measurement was made on, and a drug only claims the form it actually is (a646294)
  fr: Les deux bases d'affinités étaient lues par une correspondance de noms qui ignorait la stéréochimie, si bien qu'une seule forme en miroir d'une molécule était comptée en silence comme la forme courante. Dix-sept médicaments mélangeaient ainsi des mesures faites sur une forme en miroir aux chiffres de l'autre. Les deux lecteurs vérifient désormais sur quelle forme une mesure a été faite, et un médicament ne revendique que la forme qu'il est réellement

- Ketanserin was published as a sub-nanomolar 5-HT1F ligand on the strength of one measurement, while some forty others put the same drug a thousand to ten thousand times weaker across that whole receptor family, one of them on the very same receptor. That measurement is now excluded and the binding with it (a646294)
  fr: La kétansérine était présentée comme un ligand 5-HT1F de l'ordre du nanomolaire sur la foi d'une seule mesure, alors qu'une quarantaine d'autres situent le même médicament mille à dix mille fois plus faible sur toute cette famille de récepteurs, dont une sur ce récepteur précis. Cette mesure est désormais écartée, et la liaison avec elle

## Data

- Pentazocine is measured almost only as its separated mirror images, so its figures now say so: its opioid kappa affinity carries a "measured as" warning naming the form assayed, and its sigma-1 affinity uses the measurements made on the mixture actually prescribed (a646294)
  fr: La pentazocine n'est presque mesurée que sous ses formes en miroir séparées, ce que ses chiffres indiquent désormais : son affinité opioïde kappa porte un avertissement « mesuré en tant que » nommant la forme testée, et son affinité sigma-1 s'appuie sur les mesures faites sur le mélange réellement prescrit

- Propranolol's serotonin 5-HT1A entry no longer states a direction. The only source for it described a separated mirror image of the molecule, so the affinity stands and the direction does not (a646294)
  fr: L'entrée sérotonine 5-HT1A du propranolol n'indique plus de direction. La seule source dont elle disposait décrivait une forme en miroir séparée de la molécule : l'affinité demeure, la direction non
