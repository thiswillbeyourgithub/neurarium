# 3.65.0 (2026-09-07)

## Added

- The six missing Parkinson's drugs: levodopa, carbidopa, benserazide, entacapone, tolcapone and istradefylline. This was the emptiest family the drug roster had left (3 of 9 present), and every new binding comes with its source quote. (829fa64)
    fr: Les six médicaments antiparkinsoniens manquants : lévodopa, carbidopa, bensérazide, entacapone, tolcapone et istradéfylline. C'était la famille la plus incomplète du catalogue (3 sur 9), et chaque nouvelle liaison arrive avec sa citation source. (829fa64)
- Two new enzymes to act on: AADC, which builds dopamine from levodopa, and COMT, which breaks it down. Both list where they are expressed, confirmed against the Allen human brain atlas. (1019b68)
    fr: Deux nouvelles enzymes sur lesquelles agir : l'AADC, qui fabrique la dopamine à partir de la lévodopa, et la COMT, qui la dégrade. Les deux indiquent où elles sont exprimées, confirmé sur l'atlas humain Allen. (1019b68)
- A drug can now be a precursor of a transmitter, not only a blocker of something: levodopa is dopamine's raw material, so it raises dopaminergic tone the way an enzyme inhibitor does, while blocking that same synthesis (carbidopa) lowers it. (1019b68)
    fr: Un médicament peut désormais être le précurseur d'un neurotransmetteur, et pas seulement le bloqueur de quelque chose : la lévodopa est la matière première de la dopamine, elle augmente donc le tonus dopaminergique comme le ferait un inhibiteur enzymatique, tandis que bloquer cette même synthèse (carbidopa) le diminue. (1019b68)

## Improved

- A binding its own source says happens outside the brain now says so, and lights nothing in the 3D scene. Carbidopa, benserazide and entacapone are built not to cross into the brain, so showing them acting all over it would have been the opposite of the truth. (ce7e5f5)
    fr: Une liaison dont la source dit elle-même qu'elle se produit hors du cerveau l'indique désormais, et n'allume rien dans la scène 3D. La carbidopa, le bensérazide et l'entacapone sont conçus pour ne pas entrer dans le cerveau : les montrer agir partout aurait dit l'inverse de la vérité. (ce7e5f5)
