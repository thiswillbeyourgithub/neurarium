# 3.132.2 (2026-10-19)

## Fixed

- Six drugs (diazepam, diphenhydramine, lorazepam, mirtazapine, olanzapine, sildenafil) no longer list a brand literally named "Other", and a placeholder name can no longer enter as a brand, holder or originator (4d9fcf4)
  fr: Six médicaments (diazépam, diphénhydramine, lorazépam, mirtazapine, olanzapine, sildénafil) n'affichent plus une marque nommée littéralement « Other », et un nom de remplissage ne peut plus être enregistré comme marque, titulaire ou laboratoire d'origine (4d9fcf4)
- Re-running the binding-direction table and metabolite fetchers offline reproduces their saved results again, and a test now checks the fetchers against their committed caches (5eb0171, dbed4a7, eb2a2f8)
  fr: Relancer hors ligne les collecteurs de directions de liaison et de métabolites reproduit de nouveau leurs résultats enregistrés, et un test compare désormais les collecteurs à leurs caches versionnés (5eb0171, dbed4a7, eb2a2f8)

## Docs

- The sourcing gaps document now lists only the gaps that are open today, with its figures generated from the data and a test keeping dates and stale counts out (789ed97, 22b3048, a3c2f17, 6ab7d4e)
  fr: Le document des lacunes de sourçage ne liste plus que les lacunes ouvertes aujourd'hui, ses chiffres étant générés à partir des données et un test en écartant dates et décomptes périmés (789ed97, 22b3048, a3c2f17, 6ab7d4e)

## Improved

- Every source page is read through one shared reader, and the non-receptor target filter exists once (5efc669, e631955, 61c8289, bd1f9ba)
  fr: Chaque page source est lue par un seul lecteur partagé, et le filtre des cibles non réceptrices n'existe plus qu'une fois (5efc669, e631955, 61c8289, bd1f9ba)
