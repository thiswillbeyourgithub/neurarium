# 3.176.0 (2026-11-21)

## Added

- A drug with active metabolites now has an "Include / Exclude metabolites" picker on its binding profile, so a receptor both compounds bind no longer has to show twice; the choice is remembered (3302d9dd)
  fr: Une substance à métabolites actifs a désormais un choix « Inclure / Exclure les métabolites » sur son profil de liaison, pour qu'un récepteur lié par les deux composés n'apparaisse plus forcément deux fois ; le choix est mémorisé
- Shift+F now also finds what a panel lists: typing "M1" on a drug panel jumps to its M1 binding, even inside a folded section (8f0640a9)
  fr: Maj+F trouve aussi ce qu'une fiche liste : taper « M1 » sur une fiche de substance mène à sa liaison M1, même dans une section repliée
- Searching an effect also finds it by related words and lists its opposite: "saliva" finds dry mouth and hypersalivation, "mydriasis" also shows miosis (daba09c6)
  fr: La recherche d'un effet le trouve aussi par des mots voisins et montre son contraire : « salive » trouve la sécheresse buccale et l'hypersalivation, « mydriase » montre aussi le myosis

## Improved

- Net neurotransmission is now the last part of the binding profile it is computed from, instead of a section of its own (3302d9dd)
  fr: La neurotransmission nette est désormais la dernière partie du profil de liaison dont elle est calculée, au lieu d'une section à part
- On a drug's metabolism, "strong" and "major route" are now in bold (0066ae3c)
  fr: Dans le métabolisme d'une substance, « puissant » et « voie principale » sont désormais en gras
- Ctrl+F (Cmd+F) is left to the browser's own find again; f and Shift+F still open neurarium's search and the in-panel find (aeb542c1)
  fr: Ctrl+F (Cmd+F) revient à la recherche du navigateur ; f et Maj+F ouvrent toujours la recherche de neurarium et la recherche dans la fiche

## Fixed

- Thirteen bindings were marked speculative though their source states them plainly (viloxazine at 5-HT7, alpha-1B and beta-2, among others): a "weak" effect is about potency, not doubt (846879e8)
  fr: Treize liaisons étaient marquées spéculatives alors que leur source les affirme (la viloxazine sur 5-HT7, alpha-1B et bêta-2, entre autres) : un effet « faible » parle de puissance, pas de doute
- Pimavanserin (5-HT2A, 5-HT2C) and pitolisant (H3) listed each receptor twice, once as antagonist and once as inverse agonist, from a single sentence (bf8a1cee)
  fr: La pimavansérine (5-HT2A, 5-HT2C) et le pitolisant (H3) listaient chaque récepteur deux fois, comme antagoniste puis agoniste inverse, à partir d'une seule phrase
- Tropatepine showed its synthesis scheme instead of its molecule; it now shows no image, since no vector drawing of it exists (6f2f136d)
  fr: La tropatépine affichait son schéma de synthèse au lieu de sa molécule ; elle n'affiche plus d'image, faute de dessin vectoriel existant
