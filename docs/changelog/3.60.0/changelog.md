# 3.60.0 (2026-09-06)

## Added

- Ten opioid analgesics join the dataset: morphine, tramadol, codeine, oxycodone, fentanyl, hydromorphone, tapentadol, pethidine, pentazocine and heroin. Until now the only opioids modeled were the addiction-medicine ones (buprenorphine, methadone, naltrexone, naloxone, nalmefene), because the drug corpus grew from a psychiatric prescriber's guide and from lists of psychiatric medications, neither of which covers pain medicine. The mu, delta and kappa receptors were already in the atlas, so each of these lights the brain the day it lands
  fr: Dix analgésiques opioïdes rejoignent les données : morphine, tramadol, codéine, oxycodone, fentanyl, hydromorphone, tapentadol, péthidine, pentazocine et héroïne. Jusqu'ici les seuls opioïdes modélisés étaient ceux de l'addictologie (buprénorphine, méthadone, naltrexone, naloxone, nalméfène), parce que le corpus des médicaments est né d'un guide de prescription psychiatrique et de listes de médicaments psychiatriques, dont aucun ne couvre la médecine de la douleur. Les récepteurs mu, delta et kappa étaient déjà dans l'atlas, donc chacun de ces médicaments éclaire le cerveau dès son arrivée

- Tramadol and pethidine also inhibit serotonin and noradrenaline reuptake, so both drive the by-mechanism flow overlay along the ascending monoamine pathways, not only the opioid dots
  fr: Le tramadol et la péthidine inhibent aussi la recapture de la sérotonine et de la noradrénaline : tous deux animent donc le flux par mécanisme le long des voies monoaminergiques ascendantes, et pas seulement les points opioïdes

## Data

- Each new drug carries its measured affinities (PDSP, completed by the Guide to Pharmacology where PDSP has no assay), its elimination half-life, its metabolising enzymes and its drug class, every one of them quote-checked against its source. Codeine and tramadol bring the CYP2D6 story with them, so their interaction lists build themselves
  fr: Chaque nouveau médicament porte ses affinités mesurées (PDSP, complétées par le Guide to Pharmacology là où PDSP n'a pas de dosage), sa demi-vie d'élimination, ses enzymes de métabolisation et sa classe, toutes vérifiées mot pour mot dans leur source. La codéine et le tramadol amènent avec eux l'histoire du CYP2D6, si bien que leurs listes d'interactions se construisent d'elles-mêmes

- Heroin is modeled as what it is: a prodrug with low affinity of its own, whose effect is carried by its active metabolites 6-monoacetylmorphine and morphine, the latter now linked to its own entry
  fr: L'héroïne est modélisée pour ce qu'elle est : un promédicament de faible affinité propre, dont l'effet est porté par ses métabolites actifs, la 6-monoacétylmorphine et la morphine, cette dernière renvoyant désormais à sa propre fiche

## Fixed

- A single affinity measurement placed tramadol among the potent delta and kappa opioids, three orders of magnitude away from every other measurement of the same drug in the same database. It is now excluded by name, with the contradiction written down beside it
  fr: Une mesure d'affinité isolée plaçait le tramadol parmi les opioïdes delta et kappa puissants, à trois ordres de grandeur de toutes les autres mesures du même médicament dans la même base. Elle est désormais exclue nommément, la contradiction consignée à côté d'elle

- The affinity reader missed every row filed under the short receptor names MOR, DOR and KOR, which carry no gene identifier. Those measurements now count, which sharpens the figures shown for several opioids
  fr: Le lecteur d'affinités ignorait toutes les lignes classées sous les noms courts de récepteurs MOR, DOR et KOR, dépourvues d'identifiant de gène. Ces mesures comptent désormais, ce qui affine les chiffres affichés pour plusieurs opioïdes
