# 3.133.0 (2026-10-19)

## Improved

- The drug panel's "Acts within" section is folded into Neurotransmitter tone: a system the drug reaches only through a postsynaptic receptor is now a "no tone change" row there, with one line saying why (ce5b137)
  fr: La section « Agit au sein de » du panneau médicament est intégrée au tonus des neurotransmetteurs : un système que la substance n'atteint que par un récepteur postsynaptique y devient une ligne « pas de changement de tonus », avec une phrase qui explique pourquoi (ce5b137)
- Every data-sourcing step can be re-run without undoing another step's work, every saved cache has one fixed format, and tests check both (858ff57, 38cab71, bb552e4, 1d060b0, 8d0328d, 8895765, 990a06a, b683a65, ab3067e, 38d1fca)
  fr: Chaque étape de sourçage des données peut être relancée sans défaire le travail d'une autre, chaque cache enregistré a un seul format fixe, et des tests vérifient les deux (858ff57, 38cab71, bb552e4, 1d060b0, 8d0328d, 8895765, 990a06a, b683a65, ab3067e, 38d1fca)

## Data

- Seven more verified drug classes: bumetanide, cannabidiol, cannabinol, furosemide, nabilone, rimonabant and tiapride (1522e1b)
  fr: Sept classes médicamenteuses vérifiées de plus : bumétanide, cannabidiol, cannabinol, furosémide, nabilone, rimonabant et tiapride (1522e1b)
- Three more sourced pathways: raphe to caudate, raphe to putamen, and frontal cortex to putamen (d5eb4ea)
  fr: Trois voies sourcées de plus : raphé vers noyau caudé, raphé vers putamen, et cortex frontal vers putamen (d5eb4ea)
- Six more active-metabolite bindings: noribogaine at the serotonin transporter and the kappa and mu opioid receptors, norzimelidine at the serotonin and noradrenaline transporters, 2-oxoquazepam at the alpha7 nicotinic receptor (6fbbfdf)
  fr: Six liaisons de métabolites actifs de plus : noribogaïne au transporteur de la sérotonine et aux récepteurs opioïdes kappa et mu, norzimélidine aux transporteurs de la sérotonine et de la noradrénaline, 2-oxoquazépam au récepteur nicotinique alpha7 (6fbbfdf)
- Measured affinities for benztropine at the dopamine transporter, naltrexone at the delta and kappa opioid receptors and fentanyl at kappa, plus benztropine at 5-HT2A (abc3f10)
  fr: Affinités mesurées pour la benztropine au transporteur de la dopamine, la naltrexone aux récepteurs opioïdes delta et kappa et le fentanyl à kappa, plus la benztropine à 5-HT2A (abc3f10)
- Five receptor-effect caveats are now judged like every other quote (1bceb28)
  fr: Cinq réserves sur des effets de récepteurs sont désormais jugées comme toute autre citation (1bceb28)
