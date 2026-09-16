# 3.87.0 (2026-09-16)

## Added
- Drugs now carry a sourced time to peak: how long after a dose the blood concentration is at its highest. It sits beside the half-life in a new Timing section of the drug panel, with its own source pill, on the 90 drugs a corpus states it for.
    fr: Les médicaments portent désormais un délai de pic sourcé : le temps qu'il faut, après une prise, pour que la concentration sanguine soit à son maximum. Il figure à côté de la demi-vie dans une nouvelle section Chronologie du panneau du médicament, avec sa propre pastille de source, pour les 90 médicaments dont un corpus le donne.

## Improved
- The simulation's plasma curve rises at each drug's own pace instead of a single assumed two hours for everyone. A drug that peaks in half an hour and one that peaks in eight now look different, and the warnings box says which of the two a given curve is drawn from.
    fr: La courbe plasmatique de la simulation monte au rythme propre de chaque médicament, au lieu des deux heures supposées pour tout le monde. Un médicament qui culmine en une demi-heure et un autre en huit heures ne se ressemblent plus, et l'encadré d'avertissements précise laquelle des deux situations a servi à tracer une courbe donnée.

## Data
- The time-to-peak pass read both stored corpora, claimed 92 values and shipped 90: a second model rejected two of them, one sentence being about a combination product and the other about a breakdown product rather than the drug itself.
    fr: Le passage sur le délai de pic a lu les deux corpus stockés, revendiqué 92 valeurs et en a publié 90 : un second modèle en a rejeté deux, l'une des phrases portant sur une association et l'autre sur un produit de dégradation plutôt que sur le médicament lui-même.
