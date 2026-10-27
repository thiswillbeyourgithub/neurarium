# Carte des substances

[English version](README.md)

**En ligne :** [drugsmap.olicorne.org](https://drugsmap.olicorne.org/) (aussi sur [neurarium.olicorne.org/drugs-map](https://neurarium.olicorne.org/drugs-map))

Une carte interactive des médicaments psychiatriques et actifs sur le système nerveux central, placés selon la ressemblance de leurs profils de liaison aux récepteurs. Les substances qui touchent les mêmes récepteurs dans les mêmes proportions se retrouvent proches ; celles aux mécanismes sans rapport se retrouvent éloignées. C'est une page compagnon de [neurarium](https://neurarium.olicorne.org/), un atlas 3D interactif du cerveau pour les neurosciences psychiatriques, entièrement construite à partir du jeu de données sourcé que neurarium sert librement.

Elle a été réalisée avec l'aide de [Claude Code](https://claude.com/claude-code).

## Ce que montre la carte

Chaque substance devient un vecteur, puis une analyse en composantes principales (ACP) projette tous ces vecteurs sur les deux axes qui écartent le plus les substances. L'ACP est recalculée pour ce que les filtres laissent à l'écran : filtrer sur les antipsychotiques donne les axes qui séparent le mieux *les antipsychotiques*, pas toute la liste.

Un exemple concret du vecteur d'une substance, en mode « Récepteurs » : un nombre par cible, l'affinité `pKi - 5` avec `pKi = 9 - log10(Ki en nM)`.

```python
# Ki 1 nM -> pKi 9 -> 4.0 ; Ki 100 nM -> pKi 7 -> 2.0 ; Ki >= 10 µM -> 0 (trop faible pour compter)
# olanzapine (Ki médian: D2 21 nM, 5-HT2A 3.3 nM, H1 2.4 nM, M1 4.7 nM, SERT 2.3 µM)
olanzapine = {"D2": 2.7, "5-HT2A": 3.5, "H1": 3.6, "M1": 3.3, "SERT": 0.6, ...}
```

Une liaison qu'une source affirme mais sans Ki mesuré compte quand même, avec une affinité moyenne. Par défaut chaque vecteur est ramené à une longueur unité, pour que la carte compare la *forme* d'un profil (quelles cibles, dans quelles proportions) plutôt que la puissance brute.

Réglages (des boîtes repliées au-dessus du graphique) :

- **Placer selon :** les affinités aux récepteurs, le tonus net par neurotransmetteur (l'effet signé de la substance sur chaque système), ou les deux.
- **Signé :** un agoniste et un antagoniste du même récepteur partent dans des directions opposées.
- **Cibles :** restreindre les vecteurs à certaines cibles ; en choisir une ou deux en fait directement les axes (sans ACP).
- **Filtres :** classe, année de première autorisation, commercialisées uniquement.
- **Couleur selon :** classe, nomenclature NbN, année d'autorisation, laboratoire d'origine, métabolisme, ou couverture des Ki.
- **Graphique :** molette / pincement pour zoomer, glisser pour déplacer, rotation à deux doigts pour tourner, bouton plein écran.

Cliquer sur une substance l'ouvre dans l'atlas 3D de neurarium (sa fiche complète : liaisons avec leurs sources citées, métabolisme, histoire...). Un clic droit ou un appui long la masque de la carte. Toute la vue est dans la barre d'adresse : une URL est un lien partageable vers exactement ce qui est à l'écran.

## D'où viennent les données

Tout vient des fichiers de données publics de neurarium (`/data/*.jsonl`, décrits dans [`llms.txt`](https://neurarium.olicorne.org/llms.txt), avec une page Markdown par nœud sous [`/api/`](https://neurarium.olicorne.org/api/)). Les liaisons viennent du Prescriber's Guide de Stahl, de la base de Ki PDSP, du Guide to Pharmacology IUPHAR/BPS et de Wikipédia ; chaque liaison porte sa source citée et un niveau de provenance, consultables en cliquant sur la substance. Cette page est un exemple de ce que l'on peut construire sur ce jeu de données ouvert.

**Limites :** c'est une visualisation exploratoire, pas un avis médical. Les Ki sont mesurés in vitro, souvent sur des récepteurs de rongeur, et ne disent rien de la dose réellement atteinte dans un cerveau ; une ACP ne garde que les deux directions les plus étalées, donc deux substances proches sur la carte peuvent différer sur une cible que les axes ne captent pas (la légende des axes indique quelles cibles pèsent le plus sur chacun).

## Hébergement

Cette page n'est pas un projet séparé : c'est `public/drugs-map.html` dans le dépôt de neurarium, démarrée par `public/js/drugs-map-main.js`, qui réutilise les modules du visualiseur (chargement des données, état de l'URL, thème et langue) sans charger le code 3D. Le conteneur neurarium la sert sur `/drugs-map`.

`drugsmap.olicorne.org` est le même conteneur derrière le reverse proxy extérieur, qui réécrit la racine vers la page : la barre d'adresse garde `drugsmap.olicorne.org` alors que tout est servi par neurarium. Avec Caddy comme proxy extérieur :

```caddy
drugsmap.olicorne.org {
	# Réécriture interne : l'adresse reste drugsmap.olicorne.org/ (le #hash de la vue est gardé)
	rewrite / /drugs-map.html
	# Garder l'application 3D hors de cet hôte : sa page d'entrée renvoie au vrai domaine
	redir /index.html https://neurarium.olicorne.org/ 301
	reverse_proxy <le même upstream que le bloc neurarium.olicorne.org>
}
```

Les liens de la carte vers l'atlas 3D détectent ce cas (page servie sur `/`) et pointent vers `https://neurarium.olicorne.org/` au lieu d'un chemin relatif. Les visites sont comptées par le même site umami que neurarium, sous le nom d'hôte `drugsmap.olicorne.org`.
