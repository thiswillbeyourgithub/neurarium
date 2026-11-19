# 3.172.0 (2026-11-19)

## Added

- 13 CNS drugs common in France: periciazine, penfluridol, carpipramine, iproniazid, etifoxine, nefopam, nordazepam (also the shared active metabolite of prazepam and clorazepate), piribedil, eslicarbazepine acetate, valpromide, oxetorone, stiripentol and opium, each with its sourced bindings, class, kinetics, history and French label checks where a source states them (9eaec070, 7779ef2d)
  fr: 13 médicaments du système nerveux courants en France : propériciazine, penfluridol, carpipramine, iproniazide, étifoxine, néfopam, nordazépam (aussi le métabolite actif commun du prazépam et du clorazépate), piribédil, acétate d'eslicarbazépine, valpromide, oxétorone, stiripentol et opium, chacun avec ses liaisons, sa classe, sa cinétique, son historique et les examens de son RCP français lorsqu'une source les indique
- Muscarinic, alpha-1 and dopamine receptor groups as targets, for a source naming a receptor class without a subtype (9c1b0bd5)
  fr: Groupes de récepteurs muscariniques, alpha-1 et dopaminergiques comme cibles, pour une source qui nomme une classe de récepteurs sans sous-type
- Search finds flupenthixol, dothiepin and loflazepate by their international spelling (1676a561)
  fr: La recherche trouve le flupentixol, la dosulépine et le loflazépate par leur orthographe internationale

## Data

- Drug bindings read from section 5.1 of the French SmPC, such as the alpha-1, dopamine and muscarinic blockade of alimemazine or the muscarinic blockade of tropatepine (2e9060fb, a7cd44b8)
  fr: Liaisons de médicaments lues dans la rubrique 5.1 du RCP français, comme le blocage alpha-1, dopaminergique et muscarinique de l'alimémazine ou le blocage muscarinique de la tropatépine
- Benzodiazepine-site affinities for alpidem, nitrazepam, chlordiazepoxide and lormetazepam (bd98d7d4, 70c1ea21, 871a57f8)
  fr: Affinités pour le site des benzodiazépines de l'alpidem, du nitrazépam, du chlordiazépoxide et du lormétazépam

- Lipophilicity, polar surface area and blood-brain barrier entry for 12 of the new drugs (PubChem, B3DB)
  fr: Lipophilie, surface polaire et passage de la barrière hémato-encéphalique pour 12 des nouveaux médicaments (PubChem, B3DB)

## Fixed

- A Wikipedia sentence holding an abbreviation tooltip is no longer cut short, which had truncated quotes on 79 articles (885d1519)
  fr: Une phrase de Wikipédia contenant une info-bulle d'abréviation n'est plus coupée, ce qui tronquait des citations sur 79 articles
- A receptor group is no longer offered as a missing binding on a drug already binding one of its subtypes (a302efb6)
  fr: Un groupe de récepteurs n'est plus proposé comme liaison manquante pour un médicament qui lie déjà l'un de ses sous-types
- Expression regions of receptors sharing a gene with a receptor group are kept when only the group is refreshed (f01df0ea)
  fr: Les régions d'expression des récepteurs partageant un gène avec un groupe de récepteurs sont conservées quand seul le groupe est rafraîchi
- The node filter's parenthesis uses the same purple as every other purple text (a0f7b601)
  fr: La parenthèse du filtre de nœuds utilise le même violet que tous les autres textes violets
