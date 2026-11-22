# 3.179.0 (2026-11-22)

## Added

- A drug's panel has a new "Sleep" section (beta): what review articles say the drug itself does to sleep, such as more total sleep, falling asleep faster, less REM sleep, deeper sleep, daytime sleepiness, restless legs. Statements that come only from rat studies carry an orange warning (b7d888dd, b7b655ae)
  fr: La fiche d'un médicament a une nouvelle rubrique « Sommeil » (bêta) : ce que des articles de synthèse disent de son effet sur le sommeil, par exemple plus de sommeil, un endormissement plus rapide, moins de sommeil paradoxal, un sommeil plus profond, une somnolence de jour, des jambes sans repos. Les données issues seulement d'études chez le rat portent un avertissement orange
- DrugsMap can place drugs by their effects on sleep (beta), and now opens on the antidepressants compared this way: the sedating ones (mirtazapine, trazodone, doxepin) sit apart from those that suppress REM sleep (paroxetine, vortioxetine). Links shared before keep showing what they showed (9b05eac5)
  fr: DrugsMap peut placer les médicaments selon leurs effets sur le sommeil (bêta), et s'ouvre désormais sur les antidépresseurs comparés ainsi : les sédatifs (mirtazapine, trazodone, doxépine) se séparent de ceux qui suppriment le sommeil paradoxal (paroxétine, vortioxétine). Les liens déjà partagés montrent toujours la même vue

## Fixed

- Brexpiprazole no longer shows a made-up action on the noradrenaline transporter: a table cell saying it has no effect there (0% at 10 µM) had been read as a very strong affinity (c268dc2e)
  fr: Le brexpiprazole n'affiche plus une action inventée sur le transporteur de la noradrénaline : une cellule de tableau disant qu'il n'y agit pas (0 % à 10 µM) avait été lue comme une affinité très forte
- Seven brand names no longer appear under the wrong drug, for example Spravato (esketamine) under ketamine or Fetzima (levomilnacipran) under milnacipran (84a7d5df)
  fr: Sept noms commerciaux n'apparaissent plus sous le mauvais médicament, par exemple Spravato (eskétamine) sous la kétamine ou Fetzima (lévomilnacipran) sous le milnacipran
- Quasym, a modified-release methylphenidate, is no longer listed as immediate release (b55a1265)
  fr: Quasym, un méthylphénidate à libération modifiée, n'est plus classé en libération immédiate

## Improved

- The sleep and seizure-threshold sections are drawn by one shared piece of code, so the next drug-level section needs no new code of its own (9a956943)
  fr: Les rubriques sommeil et seuil épileptogène sont dessinées par un même code partagé, si bien qu'une prochaine rubrique de ce type n'en demande pas de nouveau
