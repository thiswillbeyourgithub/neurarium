# 3.166.0 (2026-11-18)

## Added

- Three new receptor effects: hypersalivation, mydriasis (pupil dilation) and miosis (pupil constriction); mu opioid agonism is now sourced as causing miosis (3621bc23)
  fr: Trois nouveaux effets de récepteur : hypersalivation, mydriase (pupille dilatée) et myosis (pupille contractée) ; l'agonisme opioïde mu est désormais sourcé comme cause de myosis

## Data

- A drug's half-life or time to peak can now be flagged as contradicted by another source: methylphenidate's conflicting half-lives and diphenhydramine's Stahl half-life (8 h) against dimenhydrinate's (5 to 6 h) are flagged (41fd4244, 539b71c2, 5ed57c10)
  fr: La demi-vie ou le temps au pic d'un médicament peut désormais être signalé comme contredit par une autre source : les demi-vies contradictoires du méthylphénidate et la demi-vie de la diphenhydramine selon Stahl (8 h) face à celle du dimenhydrinate (5 à 6 h) sont signalées
- AGNP drug-monitoring rows split across a line break are read correctly, and a misattributed varenicline row is dropped (9cb46280)
  fr: Les lignes du guide AGNP coupées par un saut de ligne sont lues correctement, et une ligne de varénicline mal attribuée est écartée
- A blood-brain barrier row named after another drug of the roster is refused (c337cd80)
  fr: Une ligne sur la barrière hémato-encéphalique portant le nom d'un autre médicament de la liste est refusée

## Improved

- Internal cleanup: the AGNP fetcher reads its page files through the shared helper (2d71666a)
  fr: Nettoyage interne : le récupérateur AGNP lit ses pages via l'utilitaire partagé
