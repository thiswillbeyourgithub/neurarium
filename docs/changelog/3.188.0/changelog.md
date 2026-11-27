# 3.188.0 (2026-11-27)

## Added
- 46 new drugs, each with its receptor bindings and as many sourced facts as the references give (half-life, time to peak, metabolism, brands, approval, holders, excretion, checks the French label asks for, brain entry, molecule drawing) (34e44aba, 20305777)
  fr: 46 nouveaux médicaments, chacun avec ses liaisons aux récepteurs et autant de faits sourcés que les références en donnent (demi-vie, délai du pic, métabolisme, marques, approbation, titulaires, excrétion, examens demandés par la notice française, passage dans le cerveau, dessin de la molécule)
- Antiemetics: palonosetron, tropisetron, metopimazine, alizapride, cyclizine, chlorphenamine, plus aprepitant and its injectable prodrug fosaprepitant (a16221b3, 697b43cb)
  fr: Antiémétiques : palonosétron, tropisétron, métopimazine, alizapride, cyclizine, chlorphénamine, ainsi que l'aprépitant et son promédicament injectable, le fosaprépitant
- Anaesthesia: remimazolam, methohexital, desflurane, remifentanil, sufentanil, alfentanil (4fca2aec)
  fr: Anesthésie : rémimazolam, méthohexital, desflurane, rémifentanil, sufentanil, alfentanil
- Opioids and muscle relaxants: oxymorphone, levomethadone, dihydrocodeine (with its active metabolite dihydromorphine), nalbuphine, butorphanol, cyclobenzaprine, orphenadrine, carisoprodol (with meprobamate as its metabolite), tolperisone, thiocolchicoside, dantrolene (8057888b, 347379fb, 697b43cb)
  fr: Opioïdes et myorelaxants : oxymorphone, lévométhadone, dihydrocodéine (avec son métabolite actif, la dihydromorphine), nalbuphine, butorphanol, cyclobenzaprine, orphénadrine, carisoprodol (avec le méprobamate comme métabolite), tolpérisone, thiocolchicoside, dantrolène
- Antiseizure and neurology: opicapone, cenobamate, rufinamide, felbamate, fosphenytoin, ganaxolone, riluzole, physostigmine, mirogabalin, ziconotide (347379fb, 2472304b)
  fr: Antiépileptiques et neurologie : opicapone, cénobamate, rufinamide, felbamate, fosphénytoïne, ganaxolone, riluzole, physostigmine, mirogabaline, ziconotide
- Migraine: zolmitriptan (with its active metabolite), eletriptan, naratriptan, almotriptan, frovatriptan, lasmiditan, ubrogepant, atogepant, ergotamine, dihydroergotamine, methysergide (with methylergonovine as its active metabolite) (fcb19ac9, 7a927186, 30ba7efc, 62d19170)
  fr: Migraine : zolmitriptan (avec son métabolite actif), élétriptan, naratriptan, almotriptan, frovatriptan, lasmiditan, ubrogépant, atogépant, ergotamine, dihydroergotamine, méthysergide (avec la méthylergométrine comme métabolite actif)
- New receptor NK1, the substance P receptor aprepitant blocks, with its brain regions, expression density and antiemetic effect, and the muscle ryanodine receptor RyR1 as a peripheral drug target, the site of dantrolene (cb5cfe1f, 3174d31e)
  fr: Nouveau récepteur NK1, le récepteur de la substance P que bloque l'aprépitant, avec ses régions cérébrales, sa densité d'expression et son effet antiémétique, et le récepteur musculaire à la ryanodine RyR1 comme cible périphérique, site d'action du dantrolène

## Fixed
- Racemic methadone's affinity table can no longer be overwritten by its single enantiomer levomethadone (4fd0fea0, 0ac3b1dd)
  fr: La table d'affinités de la méthadone racémique ne peut plus être écrasée par celle de son énantiomère seul, la lévométhadone
- French labels spelling "fèces" now count as a fecal excretion route, and heptahydrate salts are recognised in the French drug database (cf037592, 7e1ee7a1)
  fr: Les notices françaises écrivant « fèces » comptent désormais comme voie d'excrétion fécale, et les sels heptahydratés sont reconnus dans la base française des médicaments
- Tolperisone shows no single half-life, since its source gives two phases (2 h and 12 h) (8252309b)
  fr: La tolpérisone n'affiche pas de demi-vie unique, sa source donnant deux phases (2 h et 12 h)
