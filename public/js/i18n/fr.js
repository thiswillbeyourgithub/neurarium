// The French UI message table, one of the per-language halves of the
// catalogue js/i18n.js owns (the runtime: language pick, lookup, interpolation).
// A classic script loaded BEFORE js/i18n.js, which reads it off this global; any
// key added here needs its twin in the other language (tools/tests/test_i18n.py).
window.__I18N_MESSAGES__ = window.__I18N_MESSAGES__ || {};
window.__I18N_MESSAGES__.fr = {
  "lang.en": "EN",
  "lang.fr": "FR",
  "lang.switchTo": "Changer de langue",

  "panel.controls": "Contrôles 3D",
  "panel.separate": "Séparer",
  "panel.transparency": "Transparence",
  "panel.autorotate": "Rotation auto",
  "panel.seeInside": "Voir l'intérieur",
  "panel.animations": "Animations",
  "panel.no3d": "Masquer le modèle 3D (le panneau occupe tout l'écran)",
  "panel.show3d": "Réafficher le modèle 3D",
  "panel.speed": "Vitesse d'animation",
  "panel.arrowColors": "Couleur des flèches",
  "panel.colorNt": "Neurotransmetteur",
  "panel.colorPotential": "Potentiel",
  "panel.structures": "Structures cérébrales",
  "panel.projections": "Projections et circuits",
  "panel.legend": "Légende",
  "panel.receptors": "Récepteurs et cibles",
  "panel.enzymes": "Enzymes",
  "panel.effects": "Effets",
  "panel.nodes": "Explorateur de données",
  "panel.simulation": "Simulation",
  "panel.about": "À propos",
  "nodes.filter": "Filtrer les faits…",
  "nodes.kindLabel": "Type de fait",
  "nodes.gradeLabel": "Sources",
  "nodes.sortLabel": "Trier par",
  "nodes.allKinds": "Tous les types",
  "nodes.allGrades": "Toutes les sources",
  "nodes.sortWeakest": "Les moins sourcés d’abord",
  "nodes.sortStrongest": "Les mieux sourcés d’abord",
  "nodes.sortName": "Nom",
  "nodes.sortKind": "Type",
  "nodes.count": "{shown} sur {total}",
  "nodes.twins": "Afficher les deux hémisphères",
  "nodes.twinsHint": "Une région gauche/droite forme deux faits qui disent la "
    + "même chose : chaque région est donc lue une seule fois, sans son côté. "
    + "Cochez pour les lister séparément, ce que comptent les statistiques de "
    + "sources.",
  "nodes.intro": "Chaque fait ci-dessous est un nœud : une chose nommée (name) "
    + "qui énonce une notion, d’un certain type (kind), avec un niveau de source "
    + "(grade). Une ligne = un nœud ; cliquez la pastille pour voir sa source, ou "
    + "la ligne pour ouvrir ce à quoi elle appartient.",
  "nodes.dataFiles": "Les mêmes données en fichiers →",
  "nodes.dataFilesHint": "Ouvrir la liste des fichiers de données téléchargeables "
    + "(et le dépôt du code source) depuis la fenêtre À propos",
  "nodes.colGrade": "grade : à quel point ce fait est sourcé (cliquez la pastille "
    + "pour la source elle-même)",
  "nodes.colName": "name : la chose dont parle le fait",
  "nodes.colNotion": "notion : ce que le fait en dit",
  "nodes.colKind": "kind : la sorte de fait dont il s’agit, telle que comptée "
    + "dans la couverture des sources",

  "sim.beta": "bêta",
  "sim.lead": "Dans quelle mesure une association de substances engage chaque récepteur, et la même question à l'envers : quelle association approcherait un profil que vous décrivez. Les deux bouts parlent d'occupation des récepteurs.",
  "sim.leadUnit": "Ce qui est tracé est un indice relatif, non un pourcentage de récepteurs occupés : une affinité dit avec quelle force une substance tient un récepteur, jamais quelle quantité lui parvient.",
  "sim.warnTitle": "Ce que cette simulation ignore",
  "sim.warnNotExhaustive": "Cette liste n'est pas exhaustive. Elle nomme les raccourcis pris en connaissance de cause ; d'autres y manquent certainement.",
  "sim.warn.interactions": "Aucune interaction médicamenteuse n'est modélisée : rien ici ne modifie le niveau d'une autre substance.",
  "sim.warn.halfLife": "Une seule demi-vie moyenne par ligand (le milieu de l'intervalle publié), alors que les valeurs réelles varient beaucoup d'une personne à l'autre.",
  "sim.warn.plasma": "Cinétique plasmatique seulement : l'exposition cérébrale ne lui est pas simplement proportionnelle.",
  "sim.warn.dose": "Ni dose, ni biodisponibilité, ni volume de distribution, ni fraction libre, ni pénétration cérébrale : aucune concentration au récepteur ne peut donc être calculée, et les barres restent un indice plutôt qu'un pourcentage d'occupation. Une prise orale unique est supposée, montant jusqu'au délai de pic sourcé de la substance quand il en existe un, et jusqu'à {h} h pour celles dont aucune source ne le donne.",
  "sim.warn.endogenous": "Le neurotransmetteur du cerveau lui-même est ignoré : une substance entre en compétition au récepteur avec la dopamine ou la sérotonine déjà présentes, ce qui explique qu'une occupation mesurée ne corresponde jamais à une affinité en éprouvette.",
  "sim.warn.additive": "Les puissances s'additionnent simplement, sans compétition au récepteur, sans efficacité ni tolérance.",
  "sim.warn.unknown": "Un récepteur dont la direction n'a jamais été sourcée apparaît en bande grise « se lie, effet inconnu », et n'entre pas dans le net.",
  "sim.warn.assumedKi": "Une liaison de direction connue mais sans Ki mesuré est supposée à {ki}.",
  "sim.warn.metabolite": "Un métabolite actif est supposé formé en totalité.",
  "sim.warnBetween": "Entre ces substances",
  "sim.flag.sharedSubstrate": "{a} et {b} sont tous deux éliminés par {enzyme}.",
  "sim.flag.inhibits": "{a} inhibe {enzyme}, qui élimine {b}.",
  "sim.flag.induces": "{a} induit {enzyme}, qui élimine {b}.",
  "sim.flag.profile": "{assumed} liaison(s) à une affinité supposée, {unknown} sans direction sourcée.",
  "sim.flag.unknownList": "Lesquelles ?",
  "sim.drugs": "Substances",
  "sim.empty": "Ajoutez une substance pour commencer.",
  "sim.addDrug": "Ajouter une substance",
  "sim.searchDrug": "Tapez un nom de substance",
  "sim.noMatch": "Aucun résultat",
  "sim.ratio": "Dose relative",
  "sim.ratioHint": "Quelle quantité de cette substance par rapport aux autres (la première sert de référence).",
  "sim.less": "Moins",
  "sim.more": "Plus",
  "sim.remove": "Retirer",
  "sim.toggleVisible": "Afficher ou masquer cette substance dans les deux graphiques",
  "sim.openPanel": "Ouvrir la fiche de cette substance",
  "sim.metabolites": "Inclure les métabolites actifs",
  "sim.pkTitle": "Taux plasmatique au cours du temps",
  "sim.pkCaption": "Taux relatif de chaque ligand après une prise unique à t = 0, toutes les substances partageant un délai de pic supposé de {h} h. Survolez le graphique ou faites-y glisser le doigt pour lire le graphique des récepteurs à cet instant.",
  "sim.pkNone": "Aucune substance choisie n'a de demi-vie à tracer.",
  "sim.pkAtPeak": "Lecture au pic propre de chaque ligand.",
  "sim.pkHours": "{n} h",
  "sim.pkDays": "{n} j",
  "sim.pkAxisHours": "heures",
  "sim.pkAxisDays": "jours",
  "sim.rxTitle": "Engagement des récepteurs",
  "sim.rxCaption": "La hauteur vaut log10(1 + puissance / seuil), le seuil étant une affinité de {floor} (en deçà, un dosage compte comme inactif) : une unité vaut donc environ un facteur dix : {scale}. Au-dessus de la ligne la combinaison active un récepteur, en dessous elle le bloque.",
  "sim.rxNone": "Rien n'est engagé au-dessus du seuil.",
  "sim.rxThreshold": "Masquer en dessous de",
  "sim.rxUnknownToggle": "Afficher les bandes de direction inconnue",
  "sim.rxBoost": "Activation",
  "sim.rxBlock": "Blocage",
  "sim.rxUnknown": "Se lie, effet inconnu",
  "sim.rxNet": "Net",
  "sim.rxWhich": "Quelles substances :",
  "sim.systemOther": "Autre",
  "sim.solveTitle": "Trouver des substances pour un profil",
  "sim.solveCaption": "Indiquez récepteur par récepteur le profil souhaité, puis laissez le solveur chercher une combinaison qui le reproduit. Les substances listées ci-dessus sont conservées telles quelles : la réponse dit donc quoi ajouter.",
  "sim.addReceptor": "Ajouter un récepteur",
  "sim.searchReceptor": "Tapez un nom de récepteur ou de cible",
  "sim.useCurrent": "Reprendre le profil actuel",
  "sim.useCurrentHint": "Remplir la liste à partir des valeurs nettes affichées en ce moment par le graphique des récepteurs.",
  "sim.onlyListed": "Seulement ces récepteurs",
  "sim.onlyListedHint": "N'ajuster que les récepteurs listés ici. Décoché, chaque autre récepteur touché par les candidats devient une ligne souhaitée à zéro : un effet hors cible coûte alors de la qualité d'ajustement.",
  "sim.maxDrugs": "Nombre max.",
  "sim.solve": "Chercher",
  "sim.solving": "Recherche...",
  "sim.fit": "Ajustement : {pct} % sur {n} récepteur(s)",
  "sim.pickOpposes": "va à l'encontre du souhait sur {targets} : elle ne fait que compenser ce que les substances listées dépassent",
  "sim.noPicks": "Rien n'améliore ce qui est déjà listé.",
  "sim.addPick": "Ajouter",
  "sim.addAll": "Tout ajouter",
  "sim.solveNote": "Beaucoup de combinaisons conviennent aussi bien ; celle-ci en est une.",
  "sim.solveEmpty": "Ajoutez d'abord au moins un récepteur.",
  "sim.boostLabel": "activation",
  "sim.blockLabel": "blocage",
  "panel.tabSettings": "Réglages",
  "panel.tabDetails": "Détails",
  "panel.closeTab": "Fermer l’onglet",

  "toolbar.reset": "Recentrer la vue",
  "toolbar.search": "Rechercher",
  "search.close": "Fermer la recherche",
  "toolbar.searchAria": "Rechercher structures, connexions, récepteurs et substances",
  "search.placeholder": "Rechercher une structure, une connexion, un récepteur/cible, une substance ou un réglage…",
  "search.noMatch": "Aucun résultat",
  "search.tagCircuit": "circuit",
  "search.tagPathways": "voies",
  "search.tagEnzyme": "enzyme",
  "search.tagEffect": "effet",
  "search.filterAll": "Tous",
  "search.filterCommands": "Réglages",
  "search.on": "activé",
  "search.off": "désactivé",
  "search.clear": "Effacer la recherche",
  "search.syntaxLabel": "Syntaxe de recherche",
  "search.syntax": "Tapez pour rechercher par nom. Filtres : <code>classe:&quot;IRSN&quot;</code> les substances d'une classe, <code>nbn:&quot;…&quot;</code> par nomenclature. Astuce : cliquez la <b>Classe</b> ou la <b>Nomenclature</b> d'une substance pour en remplir un.",

  "shortcuts.title": "Raccourcis clavier",
  "shortcuts.names": "Afficher / masquer les noms",
  "shortcuts.spread": "Séparer / rassembler",
  "shortcuts.structures": "Afficher / masquer les structures cérébrales",
  "shortcuts.projections": "Afficher / masquer les projections",
  "shortcuts.legend": "Afficher / masquer la légende",
  "shortcuts.seeInside": "Voir l'intérieur",
  "shortcuts.receptors": "Ouvrir Récepteurs et cibles",
  "shortcuts.drugs": "Ouvrir la section Substances",
  "shortcuts.search": "Ouvrir la recherche",
  "shortcuts.tabs": "Naviguer entre les onglets",
  "shortcuts.close": "Fermer la recherche / replier les sections",

  "tour.start": "Démarrer le tutoriel",
  "tour.next": "Suivant",
  "tour.back": "Précédent",
  "tour.done": "Terminer",
  "tour.skip": "Passer",
  "tour.step": "{n} sur {total}",
  "tour.aria": "Visite guidée",
  "tour.scrollHint": "Faites défiler dans ce sens jusqu'à la partie en surbrillance",
  "tour.welcome.title": "Bienvenue sur neurarium",
  "tour.welcome.body":
    "Une carte 3D du cerveau : ses régions, leurs voies, et les récepteurs et substances qui agissent dessus. La visite dure environ 4 minutes, et vous pouvez la quitter quand vous voulez.",
  "tour.rotate.title": "Se déplacer",
  "tour.rotate.body":
    "<b>Faites glisser</b> pour tourner le cerveau, défilez pour zoomer. Faites-le tourner pour continuer.",
  "tour.separate.title": "Écarter les régions",
  "tour.separate.body":
    "Le curseur <b>Séparer</b> ouvre le cerveau et révèle les noyaux profonds. Saisissez-le pour continuer.",
  "tour.legendOpen.title": "La clé de la scène",
  "tour.legendOpen.body":
    "Ici, les couleurs et les symboles ont un sens. Cliquez sur <b>Légende</b> pour voir lequel.",
  "tour.legendLook.title": "La légende",
  "tour.legendLook.body":
    "Toutes les couleurs et tous les symboles de la vue 3D, au même endroit. Elle reste à un clic dans la barre d'outils. Fermez-la (le <b>&times;</b>) pour continuer.",
  "tour.sourcesOpen.title": "Chaque fait est sourcé",
  "tour.sourcesOpen.body":
    "Les données sont assistées par IA : chaque fait est noté. Cliquez sur <b>Sources et provenance</b> pour voir le détail.",
  "tour.sourcesDetail.title": "Le récapitulatif de provenance",
  "tour.sourcesDetail.body":
    "La part des données vérifiée, sourcée, ou encore non contrôlée. Fermez-la (le <b>&times;</b>) pour continuer.",
  "tour.nodesOpen.title": "Lire les faits eux-mêmes",
  "tour.nodesOpen.body":
    "Chacun de ces faits notés est une ligne que vous pouvez lire. Cliquez sur <b>Explorateur de données</b> pour ouvrir la liste.",
  "tour.nodesLook.title": "L'explorateur de données",
  "tour.nodesLook.body":
    "Tous les faits du jeu de données en une liste : filtrez, triez, ne gardez qu'un type ou qu'une note. Chaque ligne ouvre la chose qu'elle décrit. C'est un tableau large : il emprunte toute la fenêtre et la vue 3D s'efface.",
  "tour.show3d.title": "Afficher ou masquer le cerveau",
  "tour.show3d.body":
    "Ce bouton masque la vue 3D pour que le panneau occupe tout l'écran, pour lire. Le cerveau est masqué en ce moment : cliquez pour le faire revenir.",
  "tour.collapsePanel.title": "Replier le panneau",
  "tour.collapsePanel.body":
    "Et l'inverse : cliquez sur l'en-tête <b>neurarium</b> pour replier le panneau en une seule ligne et laisser le cerveau seul à l'écran. Essayez, puis <b>Suivant</b>.",
  "tour.browse.title": "Parcourir les données",
  "tour.browse.body":
    "Tout tient en six listes, dans l'ordre du panneau : <b>Substances</b> ({drugs}+), <b>Récepteurs et cibles</b> ({receptors}+), <b>Enzymes</b>, <b>Effets</b> (bêta), <b>Structures cérébrales</b> ({structures}+) et <b>Projections et circuits</b> ({projections}+). On en ouvre quelques-unes ensuite.",
  "tour.openDrugs.title": "Ouvrir une liste",
  "tour.openDrugs.body":
    "Commençons par une substance. Cliquez sur <b>Substances</b> pour ouvrir la liste.",
  "tour.drugTap.title": "Mettre une substance en avant",
  "tour.drugTap.body":
    "Cliquez sur <b>olanzapine</b>. Le cerveau s'assombrit et ses effets s'animent sur les régions qu'elle atteint.",
  "tour.drugActs.title": "Ce sur quoi elle agit",
  "tour.drugActs.body":
    "Les sections de chaque fiche sont repliées : un titre ouvre sa section. Ici, ses <b>liaisons</b>, classées de la plus forte affinité à la plus faible : chaque cible touchée, l'effet, et l'affinité (Ki) qui pilote l'animation. <b>À noter :</b> les animations de substances sont l'aspect le moins scientifique de neurarium, encore en chantier ; voyez-les comme une illustration, pas un fait.",
  "tour.drugMetabolism.title": "Comment le corps l'élimine",
  "tour.drugMetabolism.body":
    "Plus bas, son <b>métabolisme</b> : les enzymes hépatiques qui dégradent cette substance, ou dont elle modifie l'activité. Chacune est sourcée, et cliquable. C'est de la pharmacocinétique : rien ne s'allume dans la vue 3D.",
  "tour.drugPk.title": "Et ce que cela implique",
  "tour.drugPk.body":
    "Ouvrez <b>Interactions entre psychotropes</b>. Ces lignes sont <b>déduites</b> des enzymes ci-dessus, jamais mesurées : deux substances qui se croisent sur une même enzyme <i>pourraient</i> déplacer leur concentration sanguine. Puis <b>Suivant</b> pour continuer.",
  "tour.drugToReceptor.title": "Suivre vers un récepteur",
  "tour.drugToReceptor.body":
    "Remontez aux liaisons : chacune est un lien. Cliquez sur la ligne <b>H1</b> pour ouvrir ce récepteur.",
  "tour.receptorFacts.title": "Sa classification",
  "tour.receptorFacts.body":
    "Sa <b>classification</b> : famille, mécanisme, excite ou inhibe, place sur la synapse. Chaque fait a sa propre note.",
  "tour.receptorRegions.title": "Où on le trouve",
  "tour.receptorRegions.body":
    "Les <b>régions</b> où il est exprimé, chacune avec sa source, et toutes cliquables.",
  "tour.closePanel.title": "Fermer le panneau",
  "tour.closePanel.body":
    "Lecture terminée ? Cliquez sur le <b>&times;</b> pour fermer le panneau.",
  "tour.openStructures.title": "Ouvrir une structure",
  "tour.openStructures.body":
    "Un autre type de nœud. Cliquez sur <b>Structures cérébrales</b> pour ouvrir la liste.",
  "tour.structureTap.title": "Isoler une région",
  "tour.structureTap.body":
    "Cliquez sur <b>hippocampe</b>. Il est isolé pour que vous le voyiez seul.",
  "tour.structureLook.title": "En savoir plus",
  "tour.structureLook.body":
    "Chaque panneau s'ouvre sur une image et une description Wikipédia en direct. <b>Faites défiler</b> vers le bas pour continuer.",
  "tour.openProjections.title": "Ouvrir les projections",
  "tour.openProjections.body":
    "Dernier type de nœud : les voies entre régions. Cliquez sur <b>Projections et circuits</b>.",
  "tour.projectionTap.title": "Un système entier",
  "tour.projectionTap.body":
    "Cliquez sur le système <b>dopamine</b>. Il épingle d'un coup toutes les voies dopaminergiques.",
  "tour.projectionLook.title": "En savoir plus",
  "tour.projectionLook.body":
    "Ses <b>voies membres</b> et une description. <b>Faites défiler</b> vers le bas pour continuer.",
  "tour.backToSettings.title": "Retour au panneau",
  "tour.backToSettings.body":
    "Retour aux commandes. Cliquez sur <b>Réglages</b> pour revenir au panneau principal.",
  "tour.openSearch.title": "Ouvrir la recherche",
  "tour.openSearch.body":
    "Cliquez sur la <b>loupe</b> pour ouvrir la recherche.",
  "tour.search.title": "Tout retrouver",
  "tour.search.body":
    "La <b>recherche</b> mène à toute structure, voie, récepteur ou substance par son nom (essayez). Vous pouvez aussi filtrer les substances par classe.",
  "tour.wrap.title": "Vous êtes prêt",
  "tour.wrap.body":
    "Voilà la visite. Les réglages, le sélecteur EN/FR et une relance de la visite sont dans le panneau (relance depuis <b>À propos</b>). Bonne exploration.",

  "legend.showNames": "Afficher tous les noms",
  "legend.showProjections": "Afficher les projections",
  "legend.projections": "Projections",
  "legend.circuits": "Circuits",
  "legend.hypothetical": "Voies hypothétiques",
  "legend.hypotheticalHint":
    "Connexions moins certaines, tracées en pointillés. Masquées par défaut.",
  "legend.showSpeculative": "Afficher les spéculatives",
  "legend.hideSpeculative": "Masquer les spéculatives",

  "legendKey.dots": "Points d'expression",
  "legendKey.dotsDesc": "Sélectionner un récepteur ou une cible disperse des points lumineux sur chaque région où il se trouve, colorés selon son action :",
  "legendKey.effects": "Effets des substances",
  "legendKey.effectsDesc": "Sélectionner une substance fait pulser des points et une onde de lumière sur chaque région où elle agit, colorés selon l'effet :",
  "legendKey.flow": "Billes en mouvement (substance)",
  "legendKey.flowDesc": "Sélectionner une substance envoie aussi des billes le long des voies ascendantes du ou des systèmes de neurotransmetteurs dont elle règle le *tonus*, pour montrer quelles « autoroutes » de diffusion elle pilote. Seules les liaisons qui règlent le tonus circulent : inhibiteurs de recapture, inhibiteurs d'enzyme, bloqueurs vésiculaires et autorécepteurs présynaptiques ; un récepteur purement postsynaptique reste sous forme de points. Les billes sont vives/rapides/denses quand la substance augmente le tonus du système et ternes/lentes/rares quand elle le baisse (un ISRS augmente l'éventail sérotoninergique, l'agonisme 5-HT1A de la buspirone l'atténue, un bloqueur VMAT2 l'épuise), et leur intensité suit l'affinité mesurée de la substance. Le système est lu depuis les cibles de la substance, pas depuis les régions qui s'allument. Seuls ces systèmes ascendants diffus dotés d'un noyau source modélisé circulent :",
  "legendKey.pathways": "Voies",
  "legendKey.speculative": "Voie hypothétique (pointillés)",

  "info.connection": "Connexion",
  "info.projectionType": "Projection",
  "info.dirOut": "Projection sortante",
  "info.dirIn": "Projection entrante",
  "info.dirBoth": "Projection réciproque (deux sens)",
  "info.toneUp": "Le tonus monte",
  "info.toneDown": "Le tonus baisse",
  "info.arrowColour": "La couleur indique le type de voie : {label}.",
  "info.wikipedia": "Wikipédia ↗",
  "info.vidal": "Vidal ↗",
  "info.vidalTitle": "Rechercher cette substance sur Vidal (base de données du médicament)",
  "info.drugscom": "Drugs.com ↗",
  "info.drugscomTitle": "Rechercher cette substance sur Drugs.com",
  "info.ema": "EMA ↗",
  "info.emaTitle": "Rechercher sur l’Agence européenne des médicaments",
  "info.fda": "FDA ↗",
  "info.fdaTitle": "Rechercher dans la base de données de la FDA (États-Unis)",
  "info.clinpgx": "ClinPGx ↗",
  "info.clinpgxTitle": "Rechercher sur ClinPGx (pharmacogénomique : variants génétiques et réponse au médicament)",
  "info.clinpgxPathwaysTitle": "Rechercher sur ClinPGx les voies pharmacocinétiques de cette substance",
  "info.clinpgxEnzymeTitle": "Rechercher cette enzyme sur ClinPGx (variants, phénotypes, adaptation posologique)",
  "info.clinpgxGeneTitle": "Rechercher sur ClinPGx le gène de cette protéine (variants et effet sur la réponse aux médicaments)",
  "info.pathways": "Voies",
  "info.pharmfreq": "PharmFreq ↗",
  "info.pharmfreqTitle": "Parcourir PharmFreq, l’atlas d’où viennent ces fréquences (son outil « Metabolizer status » couvre plus de gènes que nous n’en modélisons)",
  "info.frequencies": "Fréquences",
  "info.pdsp": "PDSP Ki ↗",
  "info.pdspTitle": "Parcourir la base d’affinités de liaison PDSP Ki (NIMH)",
  "info.uniprot": "UniProt ↗",
  "info.uniprotTitle": "Rechercher ce récepteur dans UniProt (humain uniquement)",
  "info.gtopdb": "GtoPdb ↗",
  "info.gtopdbTitle": "Rechercher ce récepteur dans le Guide to Pharmacology",
  "info.reference": "Référence",
  "info.provDetails": "Cliquez pour savoir comment chaque information de neurarium est sourcée",
  "info.provNone": "Aucune source pour ce nœud pour l’instant.",
  "info.provLlm": "Niveau de source : LLM seul. Produite de mémoire par un LLM, sans vérification dans aucun document : il peut donc s’agir d’une hallucination.",
  "info.provSourced": "Niveau de source : documentée. Rédigée par un LLM ayant eu accès au document source (par ex. le guide de Stahl), mais ce nœud précis n’a pas été vérifié par citation.",
  "info.provVerified": "Niveau de source : vérifiée. Un LLM a extrait une citation, sa présence dans la source a été confirmée par programme, et un second LLM a confirmé qu’elle étaye ce nœud. C’est le niveau le plus élevé disponible ici et il reste piloté par un LLM : il peut donc encore se tromper. Aller plus loin demanderait un effort humain considérable, lui-même sujet à erreur, et sort donc du cadre de ce projet.",
  "info.provUncertain": "Niveau de source : incertaine. La citation ci-dessous figure bien dans la source et porte bien sur ce sujet, mais elle n’énonce jamais cette affirmation précise : elle dit quelque chose de plus large, la rattacher ici est donc une inférence. Les raisons d’en douter sont listées ci-dessus, chacune avec sa propre source.",
  "info.uncertainLead": "Voici des raisons, rédigées par un LLM, de douter de cette affirmation :",
  "uncertain.side_effect_rule": "La phrase source explique un effet indésirable, et son sujet est le mécanisme plutôt que la substance : elle n’affirme donc jamais que cette substance a cette action.",
  "uncertain.family_claim": "Une seule phrase de la source couvre {n} sous-types de récepteurs à la fois : elle nomme la famille et jamais ce sous-type précis, dont le découpage relève de notre propre lecture.",
  "uncertain.class_wide": "La même phrase est imprimée sur {n} autres monographies, elle peut donc énoncer une règle sur le mécanisme plutôt qu’une mesure sur cette substance.",
  "uncertain.measured_ki": "Une affinité mesurée indépendante l’étaye : Ki médian de {ki} nM sur {n} essais.",
  "uncertain.no_measured_ki": "Aucune affinité de liaison mesurée n’a été trouvée pour cette cible : rien d’indépendant n’étaye la phrase.",
  "uncertain.not_a_mechanism": "La source ne cite jamais cette action parmi les mécanismes d’action de la substance.",
  "uncertain.blanket_claim": "Une seule phrase de la source couvre {n} voies issues de cette structure à la fois et ne nomme aucune de leurs cibles : elle décrit l’étendue du système, et la tracer jusqu’à cette région en particulier relève de notre propre lecture.",
  "uncertain.set_claim": "Une seule phrase de la source affirme ceci pour {n} voies à la fois et ne nomme aucune des deux extrémités de celle-ci : elle parle de systèmes entiers (comme « le cortex cérébral » vers « le striatum »), et l’appliquer à cette voie en particulier relève de notre propre lecture.",
  "uncertain.contradicted": "Une autre source de ce jeu de données affirme le contraire, et elle est citée ci-dessous. Les corpus divergent le plus souvent sur ce qu’une mesure de laboratoire signifie chez l’être vivant (un effet réel in vitro qui ne se retrouve pas in vivo) : les deux sont donc conservées ici plutôt que l’une écartée en silence.",
  "uncertain.animal_evidence": "Toutes les sources qui précisent l’espèce étudiée ici nomment un animal ({species}), aucune l’humain ni un singe : l’affirmation peut ne pas valoir de la même façon dans le cerveau humain que cette carte représente.",
  "uncertain.isolated_tissue": "Toutes les sources citées ici décrivent une préparation de tissu humain isolé (un anneau de vaisseau, une bande de muqueuse), pas une personne vivante : l’effet peut ne pas se manifester de la même façon dans l’organisme entier.",
  "info.quoteChain": "Parcours de cette citation :",
  "quotechain.raw_data": "données brutes",
  "quotechain.page": "page source",
  "quotechain.extract_code": "extraction déterministe",
  "quotechain.extract_llm": "un LLM trouve la citation",
  "quotechain.gate": "le code vérifie que la citation est sur la page",
  "quotechain.judge_llm": "un LLM amnésique juge la citation",
  "quotechain.neurarium": "neurarium",
  "info.provWikipedia": "Chargé directement depuis Wikipédia. Ce texte est récupéré en direct et tel quel depuis l’article Wikipédia actuel (CC BY-SA), sans aucun LLM : il ne peut donc pas s’écarter de l’article. Voir le lien Référence ci-dessus pour inspecter la source.",
  "enzyme.gradesRole": "Niveau de source du rôle : {role}",
  "enzyme.gradesStrength": "Niveau de source de l’intensité : {strength}",
  "info.provDataset": "À propos de ces données : une remarque sur la construction de ce jeu de données, pas une affirmation sur le cerveau ou une substance, donc aucune source ne pourrait l’étayer. Elle n’est pas comptée dans le bilan de couverture.",
  "prov.name.verified": "Vérifiée : citation trouvée sur la page et confirmée par un juge",
  "prov.name.sourced": "Sourcée : écrite d’après la source, citation non vérifiée",
  "prov.name.llm": "LLM seul : de mémoire, non vérifiée",
  "prov.name.uncertain": "Incertaine : la citation existe mais n’énonce pas cette affirmation précise",
  "prov.name.wikipedia": "Texte Wikipédia en direct, repris tel quel",
  "prov.name.none": "Aucune source",
  "prov.name.dataset": "À propos de ces données : une remarque sur la construction de ce jeu de données, pas une affirmation sur le cerveau ou une substance, donc aucune source ne pourrait l’étayer.",
  "prov.name.unknown": "Inconnu : recherché, aucune source ne l’indique",
  "info.provUnknown": "Inconnu : toutes les sources que ce jeu de données utilise pour ce type d’affirmation ont été consultées, et aucune ne l’indique. Un constat sur la littérature à cette date, pas un manque de notre part : il est mis à part du bilan de couverture.",
  "info.unknownSearched": "Recherché le {date}, aucune source ne l’indique :",
  "info.descFromWikipedia": "Cette description est l’introduction de l’article Wikipédia de la substance, reprise telle quelle sous licence CC BY-SA. Voir le lien Référence ci-dessus.",
  "info.sourceRef": "{corpus}, p. {page}",
  "info.sourcePage.target": "{corpus}, cible {page}",
  "info.sourcePage.ligand": "{corpus}, ligand {page}",
  "info.sourcePage.gene": "{corpus}, gène {page}",
  "info.sourcePage.row": "{corpus}, ligne {page}",
  "info.sourcePage.article": "{corpus}, article {page}",
  "info.sourcePage.setid": "{corpus}, setid {page}",
  "info.sourcePage.cis": "{corpus}, CIS {page}",
  "info.sourcePage.product": "{corpus}, produit {page}",
  "info.sourcePage.guideline": "{corpus}, recommandation {page}",
  "info.sourcePage.pmid": "{corpus}, PMID {page}",
  "info.sourcePage.application": "{corpus}, {page}",
  "info.sourcePage.annotation": "{corpus}, annotation {page}",
  "info.sourcePage.cid": "{corpus}, CID {page}",
  "info.sourceFetched": "téléchargé le {date}",
  "info.sourceSpecies": "Espèce testée : {species}",
  "info.kiRow": "Ligne PDSP n° {id} : Ki {value} nM ({species}, {radioligand} ; {reference})",
  "info.sourceLicence": "Licence du texte : {licence}",
  "info.citeAs": "Cette source demande à être citée ainsi :",
  "info.noConnections": "Aucune connexion répertoriée pour l’instant.",
  "info.connections": "Connexions",

  "circuit.heading": "Circuit fonctionnel",
  "circuit.structures": "Structures de cette boucle",
  "circuit.pathways": "Voies de cette boucle",
  "group.actingDrugs": "Substances agissant sur ce système",
  "group.actingDrugsHint": "Classées par le tonus indicatif que chaque substance impose à ce système (+ l'augmente, − le baisse) : une somme approximative, pas une mesure clinique. La section Tonus des neurotransmetteurs d'une substance détaille le calcul de sa valeur.",
  "group.kindHeading": "Voies par neurotransmetteur",
  "group.signHeading": "Voies par effet",
  "group.pathways": "Voies",

  "receptor.system": "Système",
  "receptor.neurotransmitter": "Neurotransmetteur",
  "receptor.type": "Type",
  "receptor.effect": "Effet",
  "receptor.synaptic": "Site synaptique",
  "receptor.foundIn": "Présent dans",
  "effects.heading": "Effets",
  "effects.hint": "Effets cliniques qu'une source attribue à une action de ce type sur la cible, chez l'humain. Un énoncé sur le récepteur, pas sur un médicament en particulier.",
  "effects.drugHeading": "Effets indésirables inférés",
  "effects.drugHint": "Déduit, non sourcé pour ce médicament : ce que ses liaisons orientées pourraient causer, parce qu'une source attribue cet effet à la même action sur le récepteur. Une simple affinité (sens inconnu) n'apporte rien. Ni la liste de ce que ce médicament cause de façon avérée, ni un avis médical.",
  "effects.couldCause": "pourrait causer : {effect}",
  "effects.unknown": "Aucun effet trouvé dans les sources consultées",
  "effect.heading": "Effet clinique",
  "effect.hint": "Déduit, pas un avis médical : quels récepteurs une source relie à cet effet, et quelles substances pourraient le produire par leurs liaisons. Une substance listée ici ne le cause pas forcément.",
  "effect.owners": "Récepteurs et cibles ({n})",
  "effect.drugs": "Substances qui pourraient le causer ({n})",
  "effect.drugsHint": "Déduit, non sourcé pour chaque substance : une de ses liaisons orientées agit sur un récepteur dans le sens auquel une source attribue cet effet. Une simple affinité (sens inconnu) n'apporte rien.",
  "effect.noDrugs": "Aucune substance modélisée n'y mène par ses liaisons orientées.",
  "effects.legendHint": "Les effets cliniques qu'une source attribue à l'action sur un récepteur, chacun avec ses récepteurs et les substances qui pourraient le produire. Déduit, pas un avis médical ; en sélectionner un ne change rien à la vue 3D.",
  "effects.legendTag": "Substances qui pourraient le causer",
  "effects.loadError": "Impossible de charger l'index des effets ({msg}) : la section Effets et les effets possibles de chaque médicament sont vides.",
  "relmod.heading": "En aval",
  "relmod.hint": "Comment son activation modifie la libération d'un neurotransmetteur, selon le circuit décrit par une source (un effet de second ordre, chez l'humain). Un énoncé sur le récepteur, pas sur un médicament en particulier.",
  "relmod.activation.increase": "son activation augmente la libération {transmitter}",
  "relmod.activation.decrease": "son activation diminue la libération {transmitter}",
  "relmod.site": "{kind} sur {cell}{where}",
  "relmod.inStructure": " (région : {structure})",
  "relmod.drugHeading": "Modifications de libération possibles via ses liaisons",
  "relmod.drugHint": "Déduit, non sourcé pour ce médicament : ses liaisons orientées croisées avec la façon dont une source décrit la modulation de la libération par chaque récepteur. Un antagoniste inverse l'effet de l'activation ; une simple affinité (sens inconnu) n'apporte rien. Indicatif seulement, et pas un avis médical.",
  "relmod.could.increase": "pourrait augmenter la libération {transmitter}{where}",
  "relmod.could.decrease": "pourrait diminuer la libération {transmitter}{where}",
  "demog.heading": "Selon l'âge et le sexe",
  "demog.hint": "Ce que des études TEP / TEMP chez l'humain rapportent de la quantité disponible dans le cerveau selon l'âge et entre les sexes. Des moyennes de groupe sur de petits échantillons, pas une prédiction pour une personne donnée, et pas un avis médical.",
  "demog.age.decrease": "diminuerait avec l'âge{where}",
  "demog.age.increase": "augmenterait avec l'âge{where}",
  "demog.age.no_difference": "aucune variation avec l'âge rapportée{where}",
  "demog.sex.higher_in_female": "plus élevé chez les femmes que chez les hommes, selon les études{where}",
  "demog.sex.higher_in_male": "plus élevé chez les hommes que chez les femmes, selon les études{where}",
  "demog.sex.no_difference": "aucune différence entre les sexes rapportée{where}",
  "demog.magnitude": "« {magnitude} »",
  "variant.heading": "Variants génétiques",
  "variant.hint": "Variants de ce gène que ClinPGx (anciennement PharmGKB) annote comme associés à la réponse à un médicament, niveaux de preuve 1A à 3 (le niveau 4, cas isolés et signaux non répliqués, est écarté). Presque tous sont de niveau 3 : une seule étude, ou plusieurs qui ne concordent pas nettement. Survolez une pastille pour lire les phrases de ClinPGx par génotype.",
  "variant.drugHeading": "Variabilité génétique",
  "variant.drugHint": "Variants des gènes de ses récepteurs et cibles que ClinPGx annote pour ce médicament nommément (une classe comme « opioids » n'est pas comptée), niveaux de preuve 1A à 3.",
  "variant.level": "Niveau {level} · {strength}",
  "variant.assoc": "pourrait être associé à : {category}, sous {drugs}",
  "variant.assocNoDrug": "pourrait être associé à : {category}",
  "variant.withVariant": "{variant} : {text}",
  "variant.population": "chez les {population}",
  "variant.link": "ClinPGx",
  "variant.linkTitle": "Cette annotation clinique sur ClinPGx (nouvel onglet)",
  "variant.caveat": "Ceci n'est pas un avis médical, et ne prédit rien sur une personne donnée. Une annotation dit qu'une étude a associé un génotype à une réponse, ce qui ne veut pas dire que le génotype la cause ; la plupart de ces résultats sont modestes et non répliqués. Les phrases de ClinPGx sont citées verbatim (en anglais), datées par l'export ; le lien donne la version à jour.",
  "receptor.foundOther": "Autres régions",
  "receptor.ubiquitous": "Dans tout le cerveau",
  "receptor.noRole": "Pas de rôle significatif dans le système nerveux central.",
  "receptor.locUnsourced": "La liste des régions où cela se trouve est rédigée par IA (connaissances générales), pas encore vérifiée contre un atlas d'expression.",
  "receptor.speciesTag": "· {species}",
  "receptor.speciesTip": "Expression vérifiée chez : {species}, pas chez l'humain.",
  "receptor.density": "Quantité relative",
  "receptor.densityAgreement": "accord entre donneurs r = {r}",
  "receptor.densityTip": "La quantité présente dans chaque région, rapportée à la moyenne de ce gène sur l'ensemble du cerveau. Mesure d'ARNm (puces à ADN de l'Allen Human Brain Atlas) : c'est donc du transcrit et non de la protéine, et il se situe dans les corps cellulaires plutôt qu'au bout des projections. Un transporteur ressort donc surtout dans son noyau d'origine, pas dans les régions où il agit.",
  "receptor.densityAgreementTip": "À quel point les {donors} cerveaux donneurs reproduisent ce profil (corrélation entre leurs mesures). Proche de 1, tous classent les régions de la même façon ; une valeur basse signalerait un gène proche du bruit de mesure, et seuls les profils au-dessus de {min} sont affichés.",
  "receptor.densityValueTip": "{z} écarts-types par rapport à la moyenne de ce gène sur tout le cerveau.",
  "species.human": "humain",
  "species.rat": "rat",
  "species.mouse": "souris",
  "species.monkey": "singe",
  "species.guinea_pig": "cobaye",
  "species.hamster": "hamster",
  "species.rabbit": "lapin",
  "species.cat": "chat",
  "species.dog": "chien",
  "species.pig": "porc",
  "species.cow": "bœuf",
  "species.sheep": "mouton",
  "species.ferret": "furet",
  "species.chicken": "poulet",
  "species.opossum": "opossum",
  "species.fish": "poisson",
  "species.leech": "sangsue",
  "receptor.stubHint": "Pas de rôle significatif dans le système nerveux central",
  "targets.otherSystem": "Autre / non-aminergique",
  "targets.interactingDrugs": "Substances en interaction",
  "targets.bySubtype": "Par sous-type de récepteur",
  "target.polarity": "Polarité tonique",
  "target.polarityVesicular": "Transporteur vésiculaire (le bloquer épuise les stocks, abaisse le tonus)",
  "target.polarityAutoreceptor": "Autorécepteur inhibiteur présynaptique (le bloquer élève le tonus)",

  "panel.drugs": "Substances",
  "drugs.filter": "Filtrer les substances…",
  "drugs.none": "Aucune substance correspondante.",
  "drug.class": "Classe",
  "drug.nomenclature": "Nomenclature",
  "drug.nbnNonstandard": "· classe de la substance, pas de NbN formelle",
  "drug.brands": "Noms commerciaux",
  "drug.formulations": "Formes galéniques",
  "drug.halfLife": "Demi-vie d'élimination plasmatique",
  "drug.pkTiming": "Pharmacocinétique",
  "wiki.readMore": "Lire la suite",
  "wiki.readLess": "Réduire",
  "drug.tmax": "Délai du pic",
  "drug.firstApproval": "Première autorisation",
  "drug.yearsAgo": "il y a {n} ans",
  "drug.yearAgo": "il y a 1 an",
  "drug.thisYear": "cette année",
  "drug.admin": "Administratif",
  "drug.firstApprovalTip": "La plus ancienne autorisation ou mise sur le marché à usage médical que sa source mentionne (une année, plus le pays ou l'agence quand la source les nomme).",
  "drug.firstNationalApproval": "Première autorisation nationale",
  "drug.firstNationalApprovalTip": "La plus ancienne autorisation que le régulateur de ce pays recense (ici le registre de la FDA, Drugs@FDA). Pas forcément la première au monde : le médicament a pu être autorisé plus tôt ailleurs.",
  "drug.withdrawn": "Retiré",
  "drug.withdrawnGroup": "{year} : {reason},",
  "drug.originator": "Laboratoire d'origine",
  "drug.originatorNow": "{name} (aujourd'hui {now})",
  "drug.originatorTip": "L'entreprise ou le laboratoire qui a découvert, synthétisé le premier ou développé le médicament, d'après son article Wikipédia anglais, puis le pays de cette entreprise d'après son propre article.",
  "drug.holders": "Titulaire actuel",
  "drug.holdersTip": "L'entreprise titulaire de l'autorisation de mise sur le marché dans chaque marché aujourd'hui, lue dans le registre du régulateur (États-Unis : Drugs@FDA, la demande de première autorisation ; France : la base de données publique des médicaments de l'ANSM, ses spécialités de marque). Pas forcément l'entreprise qui l'a découvert.",
  "drug.prodrug": "Promédicament : inactif lui-même, agit par son métabolite actif",
  "drug.constituentsOf": "Composé de {parts}",
  "drug.prodrugTip": "Sa source indique que le médicament est inactif tant qu'il n'est pas métabolisé : il ne porte aucune liaison propre, les cibles listées sont celles de son métabolite actif.",
  "drug.viaMetabolite": "via {name}",
  "drug.tmaxTip": "Combien de temps après une prise orale unique la concentration sanguine atteint son maximum (Tmax). Il dit quand la substance arrive, là où la demi-vie dit combien de temps elle met à partir.",
  "drug.therapeuticRange": "Zone thérapeutique",
  "drug.therapeuticRangeTip": "La plage de concentration sanguine (en général résiduelle, à l'équilibre) dans laquelle la recommandation de consensus AGNP attend les meilleures chances de réponse avec une tolérance acceptable. Un repère de population, pas une cible pour chaque patient.",
  "drug.alertLevel": "Alerte",
  "drug.alertLevelTip": "Le seuil d'alerte du laboratoire : au-dessus de cette concentration sanguine, la recommandation de consensus AGNP demande au laboratoire de prévenir aussitôt le prescripteur, la tolérance ou la sécurité pouvant être en jeu.",
  "drug.physchem": "Passage cérébral",
  "drug.xlogp": "XLogP3",
  "drug.xlogpTip": "Lipophilie : le log10 du partage de la molécule entre l'octanol (qui figure les graisses et les membranes cellulaires) et l'eau. Plus il est élevé, plus elle est liposoluble : 0 est un partage égal, 3 mille fois plus dans l'octanol. La plupart des médicaments agissant sur le cerveau se situent entre 1 et 4 environ ; bien plus bas, ils franchissent mal les membranes, bien plus haut, ils tendent à se fixer aux graisses et aux protéines. Une valeur que PubChem calcule à partir de la structure (XLogP3) : une estimation, pas une mesure.",
  "drug.tpsa": "Surface polaire",
  "drug.tpsaTip": "Surface polaire topologique : la part de la surface de la molécule faite d'atomes polaires (oxygène, azote et les hydrogènes qu'ils portent), en ångströms carrés. La barrière hémato-encéphalique laisse passer plus facilement les molécules peu polaires : moins de 90 Å² environ est la règle empirique habituelle pour un médicament qui atteint le cerveau, une règle empirique et non une mesure (des transporteurs peuvent faire entrer ou sortir un médicament quelle que soit sa surface). Calculée par PubChem à partir de la structure.",
  "drug.bbb": "Passage cérébral",
  "drug.bbbTip": "Si le médicament franchit la barrière hémato-encéphalique, d'après B3DB, une base de données de mesures publiées. BBB+ signifie qu'il atteint le cerveau à des niveaux notables (selon le seuil de la base, un rapport cerveau/sang d'au moins un dixième environ, logBB ≥ −1), BBB− qu'il y passe peu. Le logBB, quand une étude l'a mesuré, est le log10 de la concentration cérébrale divisée par la concentration sanguine : 0 pour des niveaux égaux, 1 pour dix fois plus dans le cerveau, −1 pour dix fois moins. Les numéros R de sa ligne source sont les clés propres à B3DB des études qu'elle a compilées.",
  "drug.bbbRange": "{lo} à {hi}",
  "drug.workup": "Bilan demandé par le RCP",
  "drug.workupHint": "Examens et mesures que le résumé des caractéristiques du produit (RCP, rubriques 4.2 à 4.4) demande, cités depuis la base officielle de l'ANSM (ou, pour un médicament sans spécialité française, le RCP européen que l'EMA publie en français). Un contrôle que le RCP réserve à certains patients (diabétiques, âgés, à risque) est marqué « seulement si », avec les mots du RCP.",
  "drug.workupOnlyIf": "seulement si :",
  "drug.workup.before": "Le RCP demande ceci avant l'instauration :",
  "drug.workup.during": "Le RCP demande ceci en cours de traitement :",
  "drug.workupShort": "Bilan :",
  "drug.workupCaveat": "Ceci n'est pas un avis médical. C'est ce que dit la notice officielle d'un pays, lue automatiquement et vérifiée contre son texte, pas un plan de soins : les RCP diffèrent d'un pays à l'autre et évoluent, et le prescripteur adapte le bilan au patient. Consultez le RCP à jour, lié sur chaque ligne, avant de vous y fier.",
  "drug.tdmLevel": "Niveau de recommandation du suivi thérapeutique pharmacologique : {level}, {label}.",
  "drug.tdmLevel1": "fortement recommandé",
  "drug.tdmLevel2": "recommandé",
  "drug.tdmLevel3": "utile",
  "drug.tdmLevel4": "potentiellement utile",
  "drug.nonLinearPk": "Pharmacocinétique non linéaire détectée. En savoir plus dans la section Métabolisme ci-dessous ; cliquez pour y aller.",
  "drug.hlMinutes": "min",
  "drug.hlHours": "h",
  "drug.hlDays": "jours",
  "drug.metabolites": "Métabolites actifs",
  "drug.metaboliteOf": "métab. de {prodrug}",
  "drug.metabSeeBindings": "Ouvrir sa fiche : {n} liaisons",
  "drug.activeMetaboliteOf": "Métabolite actif de",
  "drug.formedBy": "formé par",
  "drugs.showMetabolites": "Afficher les métabolites actifs",
  "drug.metabolism": "Métabolisme",
  "drug.metabEnzymes": "Enzymes",
  "drug.metabolismHint": "Les enzymes hépatiques qui éliminent cette substance, ou dont elle modifie l'activité. Pharmacocinétique : rien n'est allumé dans la vue 3D.",
  "drug.pgx": "Adaptation posologique d'origine génétique",
  "drug.pgxHint": "Ce qu'une vitesse d'élimination implique pour cette prescription, dans les termes mêmes du CPIC, à côté de sa fréquence. Choisissez un groupe de population pour chiffrer chaque ligne.",
  "drug.pgxGroup": "Groupe de population",
  "drug.pgxNoGroup": "Choisir un groupe",
  "drug.pgxFreq": "{pct} de ce groupe",
  "drug.pgxNoFreq": "non mesuré dans ce groupe",
  "drug.pgxAssumes": "en supposant {genes} normal",
  "drug.pgxLevel": "CPIC niveau {level}",
  "drug.pgxLevelTitle": "Niveau A : une adaptation de la prescription est recommandée. Niveau B : une adaptation peut être envisagée.",
  "drug.pgxPopulation": "énoncé pour : {population}",
  "drug.pgxGuideline": "Recommandation ↗",
  "drug.pgxCaveat": "Ceci n'est pas un avis médical, et ne prédit rien sur une personne donnée. Une fréquence est un taux de base sur de larges groupes de cohortes d'étude : elle dit à quelle fréquence un phénotype apparaît, jamais qui le porte, et seul un test génétique répond à cela. La plupart des médicaments sont éliminés par plusieurs voies : une voie lente ne fait pas un patient lent. Le texte du CPIC est cité verbatim ; le lien vers la recommandation donne la version à jour.",
  "panel.themeLight": "Passer au thème clair",
  "panel.themeDark": "Passer au thème sombre",
  "drug.autoPkTitle": "Pharmacocinétique non linéaire",
  "drug.autoPkInhibits": "Cette substance figure ci-dessous à la fois comme substrat et comme inhibiteur du {enzymes} : elle pourrait donc ralentir sa propre élimination, et les concentrations sanguines augmenter plus vite que la dose.",
  "drug.autoPkInduces": "Cette substance figure ci-dessous à la fois comme substrat et comme inducteur du {enzymes} : elle pourrait donc accélérer sa propre élimination au fil des premières semaines, et les concentrations sanguines baisser à dose constante.",
  "drug.autoPkDerived": "Déduit des lignes d'enzymes ci-dessous, dont chacune porte sa propre source. Aucune source n'énonce cette conséquence pour cette substance : rapprocher les deux rôles relève de notre lecture.",
  "drug.pkInteractions": "Interactions entre psychotropes",
  "drug.pkInteractionsHint": "Seules les interactions entre médicaments présents dans Neurarium sont prises en compte : un médicament absent de sa liste (la plupart des médicaments non psychotropes) n'apparaît jamais, même s'il interagit fortement. Déduit des enzymes ci-dessus, non mesuré : cette substance et celle listée se rencontrent sur la même enzyme, donc l'une pourrait déplacer la concentration sanguine de l'autre. « Pourrait augmenter » signifie que la concentration de l'autre pourrait monter (celle-ci inhibe l'enzyme qui l'élimine), « pourrait diminuer » qu'elle pourrait baisser (elle l'induit). Que cela compte vraiment dépend de la dose, de la voie et de la personne : c'est un signal à vérifier avec un prescripteur, jamais une contre-indication, et l'absence de ligne ne vaut pas garantie d'innocuité.",
  "info.more": "+{n} de plus",
  "structure.expressed": "Récepteurs présents ici",
  "structure.expressedCaption": "Récepteurs et autres cibles médicamenteuses dont la liste d’expression nomme cette région, regroupés par système de neurotransmission. Chaque ligne porte la note de source propre à cette région, la même affirmation que la fiche du récepteur montre depuis l’autre bout.",
  "structure.expressedEverywhere": "dans tout le cerveau",
  "drug.pkByDrug": "Par substance",
  "drug.pkByEnzyme": "Par enzyme",
  "drug.pkHeadRaises": "Pourrait augmenter la concentration de",
  "drug.pkHeadLowers": "Pourrait diminuer la concentration de",
  "drug.pkHeadRaisedBy": "Sa concentration pourrait être augmentée par",
  "drug.pkHeadLoweredBy": "Sa concentration pourrait être diminuée par",
  "enzyme.heading": "Enzyme du métabolisme",
  "enzyme.drugs": "Substances sur cette enzyme",
  "enzyme.forms": "Métabolites actifs qu'elle forme",
  "enzyme.formsOf": "à partir de {drug}",
  "enzyme.noDrugs": "Aucune substance enregistrée sur cette enzyme.",
  "enzyme.variability": "Vitesse d'élimination selon les personnes",
  "enzyme.variabilityCaveat":
    "Fréquence de chaque vitesse d'élimination, par grand groupe de population. "
    + "Ce sont des fréquences observées dans des cohortes d'étude, pas une "
    + "prédiction pour une personne donnée : la plupart des groupes contiennent "
    + "toutes les vitesses, et seul un test génétique dit laquelle on a.",
  "enzyme.variabilityNone":
    "Pas de profil de vitesse d'élimination ici, et ce vide ne signifie pas que "
    + "cette isoforme serait uniforme : répartir les personnes en métaboliseurs "
    + "lents, normaux et ultrarapides exige une table génotype-phénotype "
    + "reconnue, qui n'existe que pour les gènes dotés d'une recommandation de "
    + "posologie. Celle-ci n'en a pas, donc aucun atlas n'en publie les "
    + "fréquences.",
  "enzymes.title": "Enzymes",
  "enzymes.hint": "Les enzymes qui métabolisent les substances (surtout les cytochromes P450 du foie). Elles ne font pas partie du cerveau : c'est de la pharmacocinétique, donc en sélectionner une ne change rien à la vue 3D.",
  "drug.actsOn": "Cibles moléculaires directes",
  "drug.activeMetabWarnOne": "Cette substance est transformée en {names}, qui agit aussi dans l'organisme : ses propres actions ne figurent pas dans cette liste.",
  "drug.activeMetabWarnMany": "Cette substance est transformée en {names}, qui agissent aussi dans l'organisme : leurs propres actions ne figurent pas dans cette liste.",
  "drug.activeMetabMixed": "Prudence : plusieurs composés contribuent à ce qui est affiché ici, cette substance et ses métabolites actifs ({names}). Chaque ligne indique le composé dont elle provient.",
  "drug.activeMetabSee": "Les voir",
  "drug.noTargets": "Aucune cible moléculaire répertoriée pour l'instant.",
  "drug.tone": "Tonus des neurotransmetteurs (indicatif)",
  "drug.toneWarnTitle": "Valeur indicative",
  "drug.toneWarn": "Une somme approximative calculée par cette application, ni une mesure ni une prédiction clinique : elle ignore la dose, la part de chaque cible réellement occupée, le passage dans le cerveau, les métabolites et l'adaptation du cerveau au fil des semaines. Elle indique sur quels systèmes une substance pousse, dans quel sens et comment ses systèmes se comparent entre eux, jamais ce qui se passe chez un patient.",
  "drug.toneHow": "Chaque liaison qui règle le tonus d'un système (pompe de recapture, enzyme de dégradation ou de synthèse, protéine vésiculaire, autorécepteur présynaptique) compte +1 si elle augmente le tonus et −1 si elle le baisse, multiplié par son poids d'affinité : 0 pour un Ki de 1 µM ou plus faible, jusqu'à 1 pour 0,1 nM ou plus fort, {none} sans Ki. Un autorécepteur présynaptique ne fait qu'ajuster le rétrocontrôle de la libération, il compte donc × {auto}. Les récepteurs postsynaptiques comptent 0. La valeur est la simple somme : une substance qui touche plusieurs régulateurs d'un même système peut dépasser 1. Une flèche vers le haut signifie que le tonus monte, une flèche vers le bas qu'il baisse.",
  "drug.toneNone": "pas de changement de tonus",
  "drug.toneNoneWhy": "Engagé uniquement par un récepteur postsynaptique : le bloquer ou le stimuler change le message reçu par le neurone cible, pas la quantité de neurotransmetteur libérée. Ses voies sont éclairées à titre indicatif (sans billes).",
  "group.toneTip": "Tonus indicatif que cette substance impose au système (+ augmente, − baisse), d'après ses liaisons régulatrices : voir la section Tonus des neurotransmetteurs de la substance",
  "tone.rule.reuptake_block": "recapture bloquée",
  "tone.rule.transporter_release": "neurotransmetteur expulsé par la pompe",
  "tone.rule.vesicular_depletion": "vésicules vidées",
  "tone.rule.vesicular_store_release": "réserves vésiculaires libérées",
  "tone.rule.enzyme_inhibition": "enzyme de dégradation bloquée",
  "tone.rule.precursor_supply": "précurseur fourni",
  "tone.rule.synthesis_inhibition": "synthèse bloquée",
  "tone.rule.vesicle_protein_block": "machinerie de libération bloquée",
  "tone.rule.autoreceptor_agonism": "frein de l'autorécepteur activé",
  "tone.rule.autoreceptor_block": "frein de l'autorécepteur levé",
  "drug.speculative": "spéculative",
  "drug.affinityOnly": "affinité seule, sens non établi",
  "drug.actionNoSource": "Aucune source ne dit si la cible est activée ou bloquée",
  "drug.actionUnknown": "Recherché, et aucune source ne dit si la cible est activée ou bloquée",
  "drug.actionLlm": "Le sens est énoncé de mémoire ; seule la liaison elle-même est sourcée",
  "drug.peripheral": "hors du cerveau, donc rien ne s’allume",
  "drug.kiCounts": "{h} humaines, {n} non humaines",
  "drug.kiTip": "Affinité de liaison mesurée (Ki), plus bas = plus forte. Médiane sur {h} études humaines + {n} non humaines ; le badge cite une étude représentative : {assay}",
  "drug.kiTipNonHuman": "Aucune étude humaine : ce Ki provient de tissu non humain ({species}).",
  "drug.kiInactive": "{n} inactive(s)",
  "drug.kiInactiveTip": "Plus {n} étude(s) au plafond de ≥10 µM (testé, liaison quasi nulle) ; exclues de la médiane ci-dessus.",
  "drug.kiMapped": "mesuré sur {compound}",
  "drug.kiCitedTip": "Valeur d'affinité citée depuis le tableau de liaison de la source (une valeur bibliographique, pas une mesure brute). Le lien pointe vers la révision exacte de la source.",
  "drug.kiCited": "valeur bibliographique",
  "drug.kiMappedTip": "Le Ki de cette liaison a été mesuré sur {compound} ({relation}), sous lequel PDSP répertorie cette substance.",
  "drug.rel.identity": "même molécule",
  "drug.rel.enantiomer": "énantiomère",
  "drug.rel.racemate": "racémique",
  "drug.rel.prodrug": "forme active",
  "drug.rel.metabolite": "métabolite",
  "drug.combo": "Médicament combiné",
  "drug.comboNote": "Les données de liaison sont indiquées par constituant ci-dessous ; des interactions entre eux peuvent exister. Ouvrez un constituant pour son profil complet :",
  "drug.structureAlt": "Structure chimique de {name}",
  "structure.imageAlt": "Illustration de {name}",
  "structure.galleryShow": "Voir {n} image(s) de plus",
  "structure.galleryHide": "Voir moins d'images",
  "image.close": "Fermer",
  "image.zoomHint": "Cliquer pour agrandir",

  "status.loadError":
    "Impossible de charger les données : {msg}. Le site est-il servi via HTTP ? (voir CLAUDE.md)",

  "loading.start": "Chargement…",
  "loading.data": "Chargement des données…",
  "loading.shapes": "Chargement des formes… ({done}/{total})",
  "loading.meshing": "Construction : {name}… ({done}/{total})",
  "loading.geometry": "Chargement des formes 3D… ({done}/{total})",
  "loading.building": "Assemblage du cerveau…",
  "loading.reducedQuality":
    "Cet appareil construit les maillages lentement : les structures restantes ont donc été générées avec moins de détail pour garder un temps de chargement raisonnable. Les données ne sont pas affectées, seules les formes 3D sont un peu plus lisses.",
  "loading.tagline": "un atlas (en grande partie) sourcé des neurosciences psychiatriques",
  "loading.cta":
    'Une idée de fonctionnalité ? Je la réaliserais volontiers, ' +
    '<a href="https://olicorne.org/fr/contact" target="_blank" ' +
    'rel="noopener noreferrer">prenez contact</a>.',
  "loading.ai":
    'Utilisable par les IA : collez une fois <a href="llms.txt" target="_blank" rel="noopener">ce lien</a> ' +
    'dans Claude, ChatGPT, Le Chat ou Gemini et demandez-lui de retenir le site, ' +
    'pour qu\'il vérifie chaque fait d\'ici avec sa citation source.',
  "loading.enter": "Commencer l'exploration",
  "common.byline":
    'par <a href="https://olicorne.org/fr" target="_blank" ' +
    'rel="noopener noreferrer">Olivier Cornelis</a>',

  "about.p1":
    "neurarium est une carte 3D interactive du cerveau, en cours de " +
    "développement. Elle montre les régions cérébrales et les projections " +
    "neuronales qui les relient, des circuits fonctionnels nommés autour " +
    "desquels on peut voir une impulsion circuler, les récepteurs de " +
    "neurotransmetteurs exprimés par chaque région, et des substances " +
    "psychoactives animées pour montrer ce que chacune fait au cerveau. " +
    "Tout est consultable et cliquable, et chaque fait porte une note de " +
    "source (voir Sources et provenance ci-dessous). Les formes sont " +
    "schématiques : elles aident à situer et relier les structures, sans " +
    "prétendre à l’exactitude anatomique ; les données sur les récepteurs " +
    "et les substances sont générées automatiquement et non vérifiées : " +
    "considérez tout ceci comme illustratif, et non comme un avis médical.",
  "about.p2":
    'Réalisé par <a href="https://olicorne.org/" target="_blank" ' +
    'rel="noopener noreferrer">Olivier Cornelis</a> (développeur et ' +
    'psychiatre) et <a href="https://claude.com/claude-code" ' +
    'target="_blank" rel="noopener noreferrer">Claude</a>.',
  "about.p3":
    "Sous le capot, c’est un simple site statique : des modules " +
    'JavaScript natifs et <a href="https://threejs.org/" target="_blank" ' +
    'rel="noopener noreferrer">three.js</a> (embarqué, sans étape de ' +
    "build), l’anatomie stockée dans des fichiers de données " +
    "générés, servis par Caddy.",
  "about.animCaveat":
    "<strong>Les animations de substances sont de loin l’aspect le moins " +
    "scientifique de neurarium et sont encore très largement en cours " +
    "d’élaboration</strong> : voyez-les comme une illustration évolutive, pas " +
    "comme un fait établi.",
  "about.animSummary": "Ce que signifient les animations",
  "about.animIntro":
    "L’animation des substances est un modèle de <em>réglage du tonus</em>, pas une " +
    "image littérale de molécules circulant dans le cerveau. Tout ce qui suit est " +
    "dérivé des données de liaison de la substance, et évolue donc avec elles.",
  "about.animList":
    "<li><b>Billes-gemmes colorées à la surface d’une structure cérébrale : un " +
    "récepteur lié par cette substance y est exprimé.</b> Les billes sont dispersées " +
    "sur chaque région qui exprime cette cible, et leur couleur dit ce que la " +
    "substance lui fait :" +
    "<ul>" +
    "<li>vert = elle la renforce (agoniste, inhibiteur de recapture, libérateur)</li>" +
    "<li>rouge = elle la bloque (antagoniste, agoniste inverse, bloqueur)</li>" +
    "<li>violet = elle la module (agoniste partiel, modulateur)</li>" +
    "</ul>" +
    "Des billes plus denses et plus vives signalent une affinité mesurée plus forte : " +
    "la cible principale d’une substance ressort donc davantage qu’une cible " +
    "secondaire. Sélectionner un récepteur seul utilise les mêmes billes sans le code " +
    "couleur : elles disent alors seulement <em>exprimé ici</em>.</li>" +
    "<li><b>Des billes qui filent le long d’une flèche : la substance déplace le " +
    "tonus de tout un système.</b> Seules les liaisons qui <em>règlent le tonus</em> " +
    "le font (inhibiteurs de recapture, inhibiteurs d’enzyme, bloqueurs vésiculaires, " +
    "autorécepteurs présynaptiques) ; une substance purement postsynaptique n’a que " +
    "des billes et une lueur, et aucun flux. Le sens du déplacement se lit dans les " +
    "billes :" +
    "<ul>" +
    "<li>chaudes, vives, rapides et denses = elle augmente le tonus du système</li>" +
    "<li>froides, ternes, lentes et clairsemées = elle le diminue</li>" +
    "</ul>" +
    "Vitesse et densité sont normalisées <em>par substance</em> : ce que vous lisez " +
    "est lequel de ses systèmes elle engage le plus, jamais une dose absolue. Guettez " +
    "le cas contre-intuitif : un antipsychotique qui bloque l’<em>autorécepteur</em> " +
    "D2 se lit comme une hausse du tonus dopaminergique, tandis que son blocage des " +
    "récepteurs D2 postsynaptiques apparaît dans les billes rouges.</li>" +
    "<li><b>Des billes qui s’allument en séquence plutôt qu’en flux : c’est un " +
    "circuit, pas une substance.</b> Sélectionner un circuit nommé joue son signal " +
    "dans l’ordre, chaque tronçon s’allumant une fois atteint par celui qui " +
    "l’alimente, avec une onde de lumière là où chaque bille arrive. Une sélection de " +
    "substance produit un flux continu : une substance ne déclenche pas un circuit, " +
    "elle change un niveau de fond.</li>" +
    "<li><b>Une lueur qui baigne toute une région : les mêmes billes, d’un coup " +
    "d’œil.</b> Une lueur par région et par effet, dans les mêmes vert / rouge / " +
    "violet, pour qu’une région portant vingt cibles de la substance brille une fois " +
    "et non vingt.</li>" +
    "<li><b>Un liseré pâle autour d’une structure : c’est celle que vous avez " +
    "sélectionnée.</b> Le survol affiche son nom ; le clic l’épingle et ouvre sa " +
    "fiche.</li>" +
    "<li><b>Une flèche en pointillés plutôt que pleine : cette voie est " +
    "hypothétique.</b> La connexion est proposée plutôt que bien établie, et sa note " +
    "de source dans la fiche dit à quel point elle est étayée.</li>",
  "about.dataSummary": "Cliquez pour accéder aux données structurées",
  "about.dataIntro":
    "L’ensemble des données est du simple JSONL / JSON, séparé du rendu et libre de " +
    "réutilisation. Chaque fichier ci-dessous est servi directement depuis ce site " +
    "(un objet JSON par ligne, auto-descriptif, chaque ligne graduée et sourcée) :",
  "about.dataRepo": "Ou parcourez-les dans le dépôt du code source →",
  "about.outreach":
    "Je pense que ce genre de visualiseur interactif pourrait être vraiment utile au " +
    "domaine médical, et je réaliserais volontiers des animations similaires pour " +
    "d’autres sujets. Si vous avez une idée, ou un retour sur celui-ci, n’hésitez pas à " +
    "me contacter (le plus simple est le suivi des tickets ci-dessous) et à me dire ce " +
    "qui vous serait utile.",
  "about.issues":
    "Vous avez repéré un bug, une inexactitude ou une idée de fonctionnalité ? " +
    'Merci d’<a id="about-issues" target="_blank" rel="noopener noreferrer">ouvrir ' +
    "un ticket sur GitHub</a>.",
  "about.sourceCode": "Code source",
  "about.license":
    'Sous licence <a href="https://www.gnu.org/licenses/agpl-3.0.html" ' +
    'target="_blank" rel="noopener noreferrer">GNU AGPL-3.0</a>.',
  "about.attribution":
    "Les descriptions des substances et les schémas de structure moléculaire " +
    'proviennent de Wikipédia, sous licence <a ' +
    'href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" ' +
    'rel="noopener noreferrer">CC BY-SA</a> ; chaque fiche de substance ' +
    "renvoie à son article source.",
  "about.sourcingTitle": "Sources et provenance",
  "sourcing.openLink": "Sources et provenance →",
  "changelog.title": "Nouveautés",
  "changelog.openLink": "Nouveautés →",
  "changelog.commit": "Voir ce changement dans le dépôt du code source",
  "changelog.empty": "Pas encore de notes de version.",
  "changelog.showAll": "Voir toutes les notes de version",
  "changelog.cat.added": "Nouveau",
  "changelog.cat.improved": "Améliorations",
  "changelog.cat.fixed": "Corrections",
  "changelog.cat.data": "Données et sources",
  "changelog.cat.docs": "Documentation",
  "about.sourcingIntro":
    "Chaque nœud de ce jeu de données (toute donnée sourçable : une région, " +
    "une voie, un récepteur, une liaison médicamenteuse, ...) porte un niveau " +
    "de source. Rien n’a encore été vérifié par un humain : même un nœud " +
    "« vérifié » peut être faux. Les niveaux :",
  "about.sourcingCaveat":
    "Une donnée sourcée n’est pas pour autant vraie. La source peut elle-même se " +
    "tromper, l’IA peut avoir rattaché une citation correcte à la mauvaise affirmation, " +
    "et le code d’affichage comporte parfois ses propres bugs. Restez critique : si " +
    "quelque chose semble faux, c’est peut-être une erreur. Les corrections sont les " +
    "bienvenues via le lien de signalement ci-dessous.",
  "about.gradeVerified":
    "Vérifié : la citation à l’appui a été confirmée présente dans la source citée.",
  "about.gradeLlm":
    "IA seule : peut être une hallucination.",
  "about.gradeNone": "Sans source : aucune réunie pour l’instant.",
  "about.gradeUnknown": "Inconnu : toutes les sources requises ont été consultées à une date enregistrée, et aucune ne l’indique. Mis à part du % (ni étayé ni manquant) ; refait chaque année.",
  "about.requiredCitations": "Certaines sources demandent que toute réutilisation de leurs données les cite. Neurarium le fait ici, et sous chacune de leurs pastilles de source :",
  "about.quoteChains": "Toutes les coches vertes ne s’obtiennent pas de la même manière : certaines citations ont été recopiées d’un tableau lisible par machine par du code seul, d’autres ont été trouvées sur une page de livre par un LLM, vérifiées mot pour mot sur cette page, puis jugées par un second LLM qui n’avait pas vu le raisonnement du premier. Chaque infobulle de source se termine par le parcours exact qui l’a produite, pour que vous puissiez en juger vous-même.",
  "about.gradeUncertain":
    "Incertain : la citation est bien présente, mais elle n’attribue pas " +
    "l’affirmation. Survolez le badge pour les raisons, chacune avec sa source.",
  "about.segVerified": "Vérifié",
  "about.segUncertain": "Incertain",
  "about.segSourced": "Sourcé",
  "about.segLlm": "IA seule",
  "about.segNone": "Sans source",
  "about.segUnknown": "Inconnu",
  "about.sourcingUnknown": "S’y ajoutent {n} affirmation(s) recherchées dans toutes les sources requises sans résultat (∅ Inconnu), exclues de ce %.",
  "about.coverageTitle": "Couverture",
  "about.sourcingHeadline":
    "{pct} % des {total} nœuds de connaissance ici sont sourcés ou vérifiés.",
  "about.sourcingByKind": "Détailler par type de nœud",
  "about.exampleLead": "p. ex.",
  "about.kiCoverage":
    "Affinité de liaison mesurée (Ki PDSP) : {pct} % des {total} liaisons en portent une ; {drugsNone} des {drugs} substances n'en ont aucune (sourcées par citation ou sans source).",
  "about.sourcingBrowser":
    "Chacun des nœuds comptés ci-dessus est listé un par un dans l'explorateur "
    + "de données, avec sa propre source, filtrable par type et par qualité de sourçage.",
  "about.sourcingBrowserLink": "Ouvrir l'explorateur de données \u2192",
  "about.kindBindings": "Liaisons cibles des substances",
  "about.kindBindingAction": "Sens des liaisons médicamenteuses",
  "about.kindNbn": "Nomenclature des substances (NbN)",
  "about.kindDrugBrands": "Noms commerciaux des substances",
  "about.kindDrugCategories": "Classe de la substance",
  "about.kindDrugHalfLife": "Demi-vie de la substance (T½)",
  "about.kindDrugTmax": "Délai du pic de la substance (Tmax)",
  "about.kindDrugFormulations": "Forme galénique de la substance (type de libération)",
  "about.kindDrugFirstApproval": "Première autorisation de la substance",
  "about.kindDrugWithdrawals": "Retraits du marché de la substance",
  "about.kindDrugHolders": "Titulaires actuels de l'AMM de la substance",
  "about.kindDrugOriginator": "Laboratoire d'origine de la substance",
  "about.kindDrugOriginatorCountry": "Pays du laboratoire d'origine",
  "about.kindDrugProdrug": "Promédicaments",
  "about.kindDrugConstituents": "Constituants des sels / associations",
  "about.kindDrugTherapeuticRange": "Zones thérapeutiques des substances",
  "about.kindDrugAlertLevel": "Seuils d'alerte du laboratoire",
  "about.kindDrugLipophilicity": "Lipophilie de la substance (XLogP3)",
  "about.kindDrugPolarSurface": "Surface polaire de la substance",
  "about.kindDrugBbb": "Passage de la barrière hémato-encéphalique",
  "about.kindDrugWorkup": "Bilan demandé par le RCP (bêta)",
  "about.kindDrugEnzymes": "Enzymes du métabolisme de la substance",
  "about.kindDrugEnzymeStrength": "Importance de la voie métabolique",
  "about.kindEnzymeVariability": "Vitesse d'élimination par population",
  "about.kindDrugPgx": "Conseils de prescription selon la vitesse d'élimination",
  "about.kindDrugMetabolites": "Métabolites actifs de la substance",
  "about.kindDrugMetaboliteEnzyme": "Enzymes formant les métabolites",
  "about.kindDrugMetaboliteBindings": "Liaisons des métabolites",
  "about.kindProjections": "Voies neuronales",
  "about.kindProjectionTransmitter": "Neurotransmetteur de la voie",
  "about.kindProjectionSign": "Signe de la voie (excitateur/inhibiteur)",
  "about.kindCircuits": "Circuits fonctionnels",
  "about.kindProjectionGroups": "Groupes de projections",
  "about.kindReceptors": "Système/famille du récepteur",
  "about.kindReceptorClass": "Classe mécanistique du récepteur",
  "about.kindReceptorSign": "Signe du récepteur (excitateur/inhibiteur)",
  "about.kindReceptorSynaptic": "Site pré/postsynaptique du récepteur",
  "about.kindReceptorLocations": "Régions d'expression des récepteurs",
  "about.kindReceptorDensity": "Quantité relative des récepteurs par région",
  "about.kindTargets": "Classifications des cibles",
  "about.kindTargetPolarity": "Polarité tonique de la cible",
  "about.kindTargetLocations": "Régions d'expression des cibles",
  "about.kindTargetDensity": "Quantité relative des cibles par région",
  "about.kindReceptorEffect": "Effets cliniques des récepteurs (bêta)",
  "about.kindReleaseModulation": "Modulation de la libération par les récepteurs (bêta)",
  "about.kindDemographic": "Disponibilité des récepteurs selon l'âge et le sexe (bêta)",
  "about.kindReceptorVariant": "Variants génétiques des récepteurs et cibles",
  "about.kindStructures": "Anatomie des régions",
  "about.kindAddons": "Annotations de panneau",

  "dev.wip": "En cours de développement",
  "dev.restarted":
    "Ce conteneur a été redémarré {ago} ; il est donc activement développé. ",
  "dev.activelyDeveloped": "Ce site est activement développé. ",
  "dev.stayTuned": "En cas de problème, revenez plus tard.",
  "dev.source": "Source",
  "dev.clickHide": "Cliquer pour masquer (réapparaît au rechargement)",
  "time.lessThanMinute": "il y a moins d’une minute",
  "time.minutes": "il y a {n} minute{s}",
  "time.hours": "il y a {n} heure{s}",
  "time.days": "il y a {n} jour{s}",

  "error.dismiss": "Fermer",
  "error.prefix": "Erreur : {msg}",
  "error.unhandled": "Erreur non gérée : {msg}",
  "error.failedLoad": "Échec du chargement de {what}",
};
