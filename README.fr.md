# neurarium

*Read this in [English / en anglais](README.md).*

**Un atlas 3D libre et sourcé du cerveau humain : chaque région, voie, récepteur et
médicament est un nœud gradué et inspectable sur une même carte que vous pouvez faire
tourner, écarter, rechercher et explorer au clic.**

> [!IMPORTANT]
> <!-- SOURCED_HEADLINE:START --><b>90% of the 1913 knowledge nodes are sourced or verified</b><!-- SOURCED_HEADLINE:END -->
> dans le jeu de données livré, et chaque fait de l'application porte une note de
> provenance que vous pouvez inspecter. C'est un vrai comptage programmatique des
> données (voir [Chaque nœud est gradué](#chaque-nœud-est-gradué)).

En ligne sur [neurarium.olicorne.org](https://neurarium.olicorne.org).

[![démo neurarium](docs/images/preview.gif)](https://neurarium.olicorne.org)

> [!WARNING]
> **Travail en cours : il contient très probablement des erreurs.** L'anatomie
> (régions, formes, projections, descriptions) n'est pas encore relue ni sourcée et
> peut contenir des hallucinations du modèle ; les données sur les médicaments sont
> extraites automatiquement d'une source unique (le *Prescriber's Guide* de Stahl) et
> ne sont pas relues non plus. Ne vous fiez à rien de tout ceci, et ne l'utilisez
> jamais pour des décisions médicales.

neurarium prend des faits qui vivent d'ordinaire éparpillés entre atlas, schémas de
voies, tables de récepteurs et monographies de médicaments, et les pose sur un seul
modèle 3D. L'objectif est de rendre visibles d'un coup d'œil les *relations* entre eux
(quelle région projette où, quel récepteur siège dans quelle structure, ce que fait un
médicament et sur quoi) plutôt que de les reconstruire de tête. Sous le capot, c'est un
**graphe de nœuds**, et comme le jeu de données est assemblé par la machine, chaque
nœud porte une note de source pour que vous sachiez toujours à quel point lui faire
confiance.

## Ce que vous pouvez explorer

| Couche | Ce que vous voyez | Ce que vous pouvez en faire |
| --- | --- | --- |
| **Anatomie** | Lobes corticaux, noyaux gris centraux, diencéphale, système limbique et tronc cérébral comme un seul maillage 3D procédural | Faire tourner, écarter au curseur pour révéler les noyaux profonds, rendre transparent, retirer la face proche, ou isoler une seule structure |
| **Câblage** | Les projections neuronales comme des flèches orientées, colorées par type (excitatrice, dopaminergique, ...) ou par signe excitateur/inhibiteur | Cliquer une voie pour son trajet, son transmetteur et ses sources ; jouer un **circuit fonctionnel** nommé sous forme d'impulsion qui circule |
| **Récepteurs & cibles** | Les récepteurs plus d'autres cibles moléculaires (transporteurs, enzymes, canaux ioniques) | En focaliser un : le cerveau se ternit vers les structures qui l'expriment (parsemées de points lumineux), à côté de sa classe, son signe et chaque médicament qui agit dessus |
| **Médicaments** | Des médicaments psychiatriques tirés du *Prescriber's Guide* de Stahl | En focaliser un : des points colorés par effet (renforce / bloque / module) s'animent sur les régions qu'il touche, des billes circulent le long des systèmes de transmetteurs par lesquels il agit, et le panneau montre sa structure, sa classe, ses liaisons et la source de chacune |
| **Tout** | Une seule barre de recherche ; un état entièrement adressable par URL | Chercher régions, voies, récepteurs et médicaments à la fois ; pivoter d'un médicament vers sa classe ou d'une cible vers tous les médicaments qui l'atteignent ; partager n'importe quelle vue par un lien direct |

## Chaque nœud est gradué

Un *nœud* est toute donnée sourçable : une région cérébrale, une projection entre deux
régions, un circuit fonctionnel, un récepteur, l'expression d'un récepteur dans une
région donnée, un médicament, une seule liaison médicament-cible. Les nœuds
s'interconnectent (un récepteur renvoie aux régions qui l'expriment et aux médicaments
qui agissent dessus), et un panneau de détail est une vue d'**un nœud plus tous les
nœuds qui lui sont liés**, si bien que vous explorez de proche en proche à partir de ce
que vous avez cliqué.

Comme le jeu de données est vaste et assemblé par la machine, la question honnête pour
tout nœud est *comment le sait-on ?* Chaque source affichée dans un panneau y répond
sur place avec une **pastille de provenance** colorée. L'objectif de conception est que
**chaque nœud porte une source**, et la pastille rend les manques visibles. Du plus
faible au plus fort :

- **gris `?` (LLM seul) :** produit par un modèle de mémoire, non vérifié ; peut être une hallucination.
- **jaune `~` (sourcé) :** issu du document cité, mais le nœud lui-même n'a pas été vérifié par citation.
- **vert `✓` (vérifié) :** un modèle a extrait une citation, sa présence dans la source citée a été confirmée *programmatiquement*, et un second modèle a convenu qu'elle étaye le nœud. Note la plus élevée disponible, et toujours pilotée par un modèle.
- **orange `NOSOURCE` :** pas encore de source ni de référence pour ce nœud.

La note fait partie des données, relevée à mesure que chaque nœud est vérifié, si bien
que la couverture ci-dessous est un vrai comptage :

<!-- SOURCING_STATS:START (generated by tools/update_readme_stats.py; do not edit by hand) -->

**90% of the 1913 knowledge nodes in the dataset are sourced or verified.** A node is any sourceable datum (a region, a pathway, a receptor, a drug binding, ...). This is a programmatic count (`tools/update_readme_stats.py`, from the emitted data), not hand-typed:

```
Wikipedia reference links       ██████████████████████████  100%  305/305
Drug nomenclature (NbN)         ██████████████████████████  100%  116/116
Brain-region anatomy            ██████████████████████████  100%    52/52
Projection groups               ██████████████████████████  100%    10/10
Functional circuits             ██████████████████████████  100%      6/6
Drug target bindings            ██████████████████████████   98%  691/703
Receptor system/family          █████████████████████████░   96%    54/56
Neuron pathways                 █████████████████████████░   96%   99/103
Drug class                      █████████████████████████░   95%  156/165
Receptor expression regions     ████████████████████████░░   94%  360/383
Target expression regions       ███████████████████████░░░   87%  108/124
Target classifications          ██████████████████████░░░░   84%    21/25
Receptor mechanism class        ██████████████░░░░░░░░░░░░   54%    30/56
Target tone polarity            █████████████░░░░░░░░░░░░░   50%      1/2
Receptor sign (excit./inhib.)   ██████░░░░░░░░░░░░░░░░░░░░   23%    13/56
Receptor pre/postsynaptic site  ████░░░░░░░░░░░░░░░░░░░░░░   14%     8/56
```

<!-- SOURCING_STATS:END -->

Les liaisons de médicaments sont en tête parce qu'elles passent la porte complète de
vérification par citation ; l'anatomie, les voies et les régions d'expression sont la
frontière actuelle. La même légende et la même barre de couverture vivent dans le
panneau « À propos » de l'application.

**Au sujet des sources.**

<!-- SOURCES_TABLE:START (generated by tools/update_readme_stats.py; do not edit by hand) -->

Every `~` and `✓` grade is checked against one of the sources below. Each is a standard, widely cited reference in its field, not a casual web page:

| Source | Field | Grades here |
| --- | --- | --- |
| Prescriber's Guide: Stahl's Essential Psychopharmacology, 8th ed. | Clinical psychopharmacology | Drug bindings, nomenclature, class |
| Kandel, Principles of Neural Science, 6th ed. | Neuroscience (standard textbook) | Neuron pathways, region anatomy |
| Stahl's Essential Psychopharmacology: Neuroscientific Basis, 5th ed. | Psychopharmacology (mechanisms) | Receptor & target mechanism |
| Carlat Medication Fact Book for Psychiatric Practice, 7th ed. | Clinical psychopharmacology | Drug bindings (cross-check) |
| Nieuwenhuys, Voogd & van Huijzen, The Human Central Nervous System, 4th ed. | Neuroanatomy (CNS atlas) | Region anatomy, connectivity |
| [IUPHAR/BPS Guide to Pharmacology (GtoPdb), tissue distribution](https://www.guidetopharmacology.org/) | Molecular pharmacology (IUPHAR/BPS database) | Receptor & target expression regions |
| [PDSP Ki Database (NIMH PDSP)](https://pdspdb.unc.edu/databases/kidb.php) | Receptor binding pharmacology | Drug binding affinities (Ki) |
| [Allen Human Brain Atlas, microarray (Hawrylycz et al. 2012)](https://human.brain-map.org/) | Brain transcriptome atlas (microarray) | Receptor & target expression regions |

<!-- SOURCES_TABLE:END -->

Les références de livres sont sous droit d'auteur, donc seul l'outillage qui les
utilise est versionné, pas le texte. Quiconque possède un exemplaire peut reproduire
l'extraction et confirmer chaque citation gradée `✓` : déposez le PDF de Stahl dans
`data_sources/books/stahl/` et trois scripts versionnés reconstruisent exactement ce
que la porte vérifie :

```sh
uv run tools/fetch/pdf_to_pages.py    # le PDF -> un fichier Markdown par page
uv run tools/fetch/build_index.py     # l'index de pages par médicament
python tools/check_data.py      # revérifie que chaque citation est bien sur la page citée
```

## Conçu pour être réutilisé

L'anatomie est de simples **données structurées**, gardées délibérément séparées du
rendu. Sous `public/data/`, elle est répartie par type de nœud (`structures`,
`projections`, `circuits`, `receptors`, `drugs` ; un objet JSON par ligne) à côté d'un
`meta.json` auto-descriptif (cartes de couleurs et de légende plus le décompte de
sourçage) et d'un fichier de géométrie par forme. Elle est générée depuis une source de
vérité unique (`tools/generate_data.py`, la liste des médicaments dans
`tools/data/drugs_data.jsonl`), si bien que le JSONL/JSON brut est facile à consommer
depuis un autre moteur.

Pour le flux de données complet et le graphe des modules, voir
[`ARCHITECTURE.md`](docs/ARCHITECTURE.md) ; pour étendre le jeu de données, la référence
par outil et le contrat de champs des données émises, voir
[`tools/README.md`](tools/README.md) ; pour la carte fichier par fichier du visualiseur
et les règles non évidentes, voir [`CLAUDE.md`](CLAUDE.md).

## Feuille de route

Un échantillon des directions prévues, aucune fixée dans l'ordre : **plus d'animation**
de l'activité et du flux de signal à travers le cerveau ; **plus de substances** (LSD,
MDMA, kétamine, nicotine, cannabis) avec leurs noms commerciaux ; des **pathologies**
projetées sur les régions, circuits et systèmes de transmetteurs ; une **pharmacologie
plus profonde** (interactions enzymatiques CYP, effets récepteurs de second ordre) ;
des **vérifications de cohérence** qui signalent les données auto-contradictoires ; et
**vers un sourçage complet**, en relevant la note de chaque nœud du gris vers le vert à
mesure qu'il est vérifié.

## Retours

Vous avez repéré un bug, une **inexactitude** anatomique ou pharmacologique, ou vous
avez une **idée de fonctionnalité** ? Merci d'**ouvrir un ticket** sur ce dépôt. Les
corrections des données de régions, projections, récepteurs et médicaments sont
particulièrement bienvenues, tout comme les **idées de ce qui aurait sa place sur une
carte comme celle-ci**. Ceci a commencé comme une démo de quelques jours pendant mon
internat de médecine et a continué d'absorber de nouveaux types de données plus
facilement que prévu, donc les suggestions sur la suite à lui donner aident vraiment.

Je crois aussi que ce genre de visualiseur interactif et sourcé pourrait être vraiment
utile au domaine médical, au-delà de la psychopharmacologie, et je réaliserais
volontiers des animations similaires pour **d'autres sujets médicaux**. Si vous avez une
idée, ou si vous pensez qu'une carte comme celle-ci aiderait votre enseignement ou votre
recherche, n'hésitez pas à **me contacter** pour me dire ce qui vous serait utile. Vous
pouvez me joindre sur [mon site](https://olicorne.org/).

## Lancer

La page charge ses données avec `fetch()`, elle doit donc être servie en HTTP (pas
ouverte depuis le disque). Le site servi est `public/`. Depuis la racine du dépôt :

```sh
python tools/serve.py            # sert public/ avec le cache désactivé
# ou : cd public && python -m http.server 8000
```

Puis ouvrez <http://localhost:8000/>.

## Pile technique

Délibérément légère, avec une faible surface d'attaque et sans étape de build :

- **Frontend :** modules ES natifs + [three.js](https://threejs.org/) chargé via une
  import map et intégré sous `public/vendor/three`, si bien que la page n'exécute aucun
  script tiers à l'exécution et fonctionne hors ligne. Pas de framework, de bundler ni
  de `node_modules`.
- **Données :** `tools/generate_data.py` (bibliothèque standard de Python uniquement)
  émet l'anatomie sous `public/data/` (`meta.json` + `*.jsonl` + `shapes/*.json`),
  récupérée à l'exécution.
- **Service :** un conteneur [Caddy](https://caddyserver.com/) durci (non-root, système
  de fichiers en lecture seule, capabilities retirées, limites de ressources, Content-
  Security-Policy stricte) derrière un reverse proxy qui termine le TLS.
- **Débogage :** une console à l'écran [eruda](https://github.com/liriliri/eruda),
  chargée seulement en dev ou avec `?debug`, si bien qu'elle n'est jamais livrée aux
  visiteurs normaux.

## Crédits

Réalisé par [Olivier Cornelis](https://olicorne.org/) (développeur et psychiatre) avec
l'aide de [Claude Code](https://claude.com/claude-code). Les descriptions de
médicaments et les images de structures moléculaires proviennent de Wikipédia, sous
licence [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/).

## Licence

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
