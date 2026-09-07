# 3.64.0 (2026-09-07)

## Added

- Four antiepileptics: vigabatrin, ethosuximide, lacosamide and brivaracetam, in a new Anticonvulsant class. Vigabatrin brought a new target with it, GABA transaminase, the enzyme that breaks GABA down, so blocking it raises GABA everywhere at once (3e62c3c).
  fr: Quatre antiépileptiques : vigabatrine, éthosuximide, lacosamide et brivaracétam, dans une nouvelle classe Anticonvulsivant. La vigabatrine a amené une nouvelle cible : la GABA transaminase, l'enzyme qui dégrade le GABA, dont le blocage élève donc le GABA partout à la fois (3e62c3c).

## Fixed

- An affinity measured at or past 10 micromolar now reads as "tested, essentially inactive" whatever database it came from, instead of only in the one where that rule was already applied. Vigabatrin showed why: it inhibits its enzyme irreversibly, so the very weak number its assay reports is not a binding strength (ef9b52a).
  fr: Une affinité mesurée à 10 micromolaires ou au-delà signifie désormais « testé, essentiellement inactif » quelle que soit la base d'origine, et non plus seulement dans celle où cette règle s'appliquait déjà. La vigabatrine l'a montré : elle inhibe son enzyme de façon irréversible, si bien que le chiffre très faible mesuré n'est pas une force de liaison (ef9b52a).
