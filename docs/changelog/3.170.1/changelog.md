# 3.170.1 (2026-11-19)

## Data

- Measured binding affinities (PDSP) are now found for drugs the database files under a former name or code name: alimemazine (trimeprazine), atomoxetine (tomoxetine), desipramine, desvenlafaxine, levodopa, cannabidiol, clorgiline, pizotifen and the code names of aripiprazole, asenapine, agomelatine, lurasidone, mirtazapine, pimavanserin, flibanserin, flumazenil and ketanserin (9480bb19)
  fr: Les affinités de liaison mesurées (PDSP) sont désormais trouvées pour les médicaments que la base range sous un ancien nom ou un nom de code : alimémazine (triméprazine), atomoxétine (tomoxétine), désipramine, desvenlafaxine, lévodopa, cannabidiol, clorgyline, pizotifène et les noms de code de l'aripiprazole, l'asénapine, l'agomélatine, la lurasidone, la mirtazapine, la pimavansérine, la flibansérine, le flumazénil et la kétansérine
- Benzodiazepines and Z-drugs get a measured GABA-A affinity, and D1, D5, D4, MAO, melatonin, opioid, orexin and PDE5 assays filed under a free-text name now count (4a5e2833)
  fr: Les benzodiazépines et les apparentés (Z) reçoivent une affinité GABA-A mesurée, et les essais D1, D5, D4, MAO, mélatonine, opioïdes, orexine et PDE5 rangés sous un nom libre comptent désormais

## Fixed

- GABA-A subunit assays were read as nicotinic receptor ones (alprazolam showed a 1 nM nicotinic affinity), and 71 "bindings" resting only on null results or a 1000 nM screening ceiling are removed, such as venlafaxine at opioid receptors (4a5e2833)
  fr: Les essais sur sous-unités GABA-A étaient lus comme nicotiniques (l'alprazolam affichait une affinité nicotinique de 1 nM), et 71 « liaisons » qui ne reposaient que sur des résultats nuls ou un plafond de criblage à 1000 nM sont retirées, comme la venlafaxine aux récepteurs opioïdes
