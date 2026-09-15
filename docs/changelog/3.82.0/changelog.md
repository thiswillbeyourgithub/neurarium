# 3.82.0 (2026-09-15)

## Added

- A new **Simulation (beta)** section: pick a few drugs, set how much of each, and see what the combination does. One plot follows each molecule in the blood over the hours or days after a single dose; the other shows which receptors the mixture activates, blocks, or merely occupies without anyone having sourced the effect. Moving across the first plot re-reads the second at that moment. (83bd006, ba748a8, be4745f, 7c3d26a)
  fr: Une nouvelle section **Simulation (bêta)** : choisissez quelques médicaments, réglez la part de chacun et voyez ce que fait la combinaison. Un graphique suit chaque molécule dans le sang au fil des heures ou des jours après une prise unique ; l'autre montre quels récepteurs le mélange active, bloque, ou occupe simplement sans que personne ait sourcé l'effet. Se déplacer sur le premier graphique relit le second à cet instant.
- The same section can work backwards: describe the receptor profile you would want, receptor by receptor, and it looks for a combination of drugs that comes close, keeping the ones you already picked. It is one answer among many that fit alike, and it says so. (83bd006, be4745f)
  fr: La même section fonctionne aussi à l'envers : décrivez récepteur par récepteur le profil souhaité et elle cherche une combinaison de médicaments qui s'en approche, en conservant ceux que vous avez déjà choisis. C'est une réponse parmi beaucoup d'autres qui conviennent aussi bien, et elle le dit.
- The simulation opens with what it does not know, spelled out: no interaction between drugs, one average half-life per molecule, no dose and no absorption data, and effects that simply add up. Where two of your drugs are cleared by the same liver enzyme, or one of them slows the enzyme that clears another, it says so under "Between these drugs". (be4745f, 7c3d26a)
  fr: La simulation s'ouvre sur ce qu'elle ignore, écrit noir sur blanc : aucune interaction entre médicaments, une seule demi-vie moyenne par molécule, aucune donnée de dose ni d'absorption, et des effets qui s'additionnent simplement. Lorsque deux de vos médicaments sont éliminés par la même enzyme hépatique, ou que l'un d'eux ralentit l'enzyme qui élimine un autre, elle le signale sous « Entre ces médicaments ».

## Docs

- The repository map gained a section on the simulation: what it assumes, where its maths live, and why a binding whose direction was never sourced is drawn as its own grey band rather than quietly counted. (1fa5c7c)
  fr: La carte du dépôt comporte désormais une section sur la simulation : ce qu'elle suppose, où vit son calcul, et pourquoi une liaison dont la direction n'a jamais été sourcée apparaît en bande grise distincte plutôt que d'être comptée en silence.
