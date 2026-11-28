# 3.189.0 (2026-11-28)

## Added
- The interface now uses Atkinson Hyperlegible Next, a typeface designed by the Braille Institute to keep similar letters (I, l, 1) apart for readers with low vision (50e0e1df)
  fr: L'interface utilise désormais Atkinson Hyperlegible Next, une police conçue par le Braille Institute pour bien distinguer les lettres semblables (I, l, 1) pour les personnes malvoyantes
- Missing bindings: orphenadrine blocks muscarinic receptors, riluzole blocks sodium channels, thiocolchicoside acts on glycine receptors, levomethadone activates the mu opioid receptor and cenobamate enhances GABA-A receptors (5962f225, 9b593083, 23e8a096)
  fr: Liaisons manquantes : l'orphénadrine bloque les récepteurs muscariniques, le riluzole bloque les canaux sodiques, le thiocolchicoside agit sur les récepteurs de la glycine, la lévométhadone active le récepteur opioïde mu et le cénobamate renforce les récepteurs GABA-A
- Caffeine activates the muscle ryanodine receptor RyR1 (786b9235)
  fr: La caféine active le récepteur musculaire à la ryanodine RyR1
- Fosaprepitant now reads its European label: the clotting checks it asks for under long-term warfarin, plus its US holder and first US approval (8448247a, 28548e8a)
  fr: Le fosaprépitant lit désormais sa notice européenne : les contrôles de coagulation demandés sous warfarine au long cours, ainsi que son titulaire et sa première approbation aux États-Unis

## Fixed
- Dihydroergotamine's 45 minute time to peak belongs to its nasal spray, so it now sits on that formulation instead of the molecule (f9fa4754, 9989638a)
  fr: Le délai du pic de 45 minutes de la dihydroergotamine est celui de son spray nasal : il est désormais rattaché à cette forme et non à la molécule
- Felbamate's NMDA antagonism and methysergide's 5-HT2B antagonism are flagged as contradicted, by the French label and by a human assay respectively (22fce030, 8a810ed0)
  fr: L'antagonisme NMDA du felbamate et l'antagonisme 5-HT2B du méthysergide sont signalés comme contredits, respectivement par la notice française et par un essai humain
- Ergotamine's 5-HT1A and D2 bindings now carry their direction (agonist), read off a table the reader used to skip (aca83a60, 4d077d64)
  fr: Les liaisons 5-HT1A et D2 de l'ergotamine portent désormais leur sens (agoniste), lu dans un tableau que le lecteur ignorait
