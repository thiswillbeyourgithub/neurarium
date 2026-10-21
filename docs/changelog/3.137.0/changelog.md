# 3.137.0 (2026-10-21)

## Added

- Every panel section now always appears, even when empty: an empty one says "No information about ... for this receptor yet", so a panel shows what the dataset tracks elsewhere (e.g. age and sex differences on 5-HT3) (464c96c, 8f98cb9, cf4a7df)
  fr: Chaque section d'un panneau apparaît désormais toujours, même vide : une section vide l'indique (« Pas encore d'information sur ... pour ce récepteur »), pour montrer ce que le jeu de données suit ailleurs (par ex. les différences d'âge et de sexe sur 5-HT3) (464c96c, 8f98cb9, cf4a7df)
- The About popup now says a text-only version exists for LLMs and links llms.txt and /api/ (8866eb9)
  fr: La fenêtre À propos indique qu'une version texte existe pour les LLM, avec un lien vers llms.txt et /api/ (8866eb9)
- Each section of an /api text page is also served alone, e.g. /api/drug/sertraline/bindings, so an LLM reads only what it needs (a47fb09, f60c93f)
  fr: Chaque section d'une page texte /api est aussi servie seule, par ex. /api/drug/sertraline/bindings, pour qu'un LLM ne lise que ce dont il a besoin (a47fb09, f60c93f)

## Improved

- The /api text pages now use exactly the panel's headings, subtitles, labels and notes, read from the same strings, and a test fails whenever the panels and the text version drift apart (54cc989, 98de2a3, 569d0ce, d038e6a)
  fr: Les pages texte /api reprennent exactement les titres, sous-titres, libellés et encadrés des panneaux, lus depuis les mêmes chaînes, et un test échoue dès que les panneaux et la version texte divergent (54cc989, 98de2a3, 569d0ce, d038e6a)
- In the /api text pages each claim carries its sources on its own line, a grades legend heads every page, and a claim written by an LLM from memory is spelled out as UNSOURCED (a47fb09, f00ee6e)
  fr: Dans les pages texte /api, chaque affirmation porte ses sources sur sa propre ligne, une légende des niveaux ouvre chaque page, et une affirmation écrite de mémoire par un LLM est marquée NON SOURCÉE (a47fb09, f00ee6e)
- Clinical section names and plain-language subtitles across the receptor, structure, connection, circuit, group, effect and enzyme panels; "Found in" becomes "Regional distribution" (be1d605, 1dbe131, 8629d61, 9a4313d, b07349c)
  fr: Noms de sections cliniques et sous-titres en langage courant dans les panneaux récepteur, structure, connexion, circuit, groupe, effet et enzyme ; la section des régions d'expression s'appelle désormais « Distribution régionale » (be1d605, 1dbe131, 8629d61, 9a4313d, b07349c)
- Plainer explanations for psychiatrists across hints, notes, the Sources popup and the tour (3fc0ffc, f23c8bb, 09c2b4f, 8ae82f3, 840ef56)
  fr: Explications plus simples pour les psychiatres dans les aides, les encadrés, la fenêtre Sources et la visite guidée (3fc0ffc, f23c8bb, 09c2b4f, 8ae82f3, 840ef56)

## Fixed

- Source links in some tooltips (enzyme roles, doubted claims, median Ki) showed as plain text instead of a clickable link (25f6915)
  fr: Dans certaines infobulles (rôles d'enzymes, affirmations douteuses, Ki médian), le lien vers la source s'affichait en texte brut au lieu d'être cliquable (25f6915)
- The pathway symmetry note now says plainly that left/right symmetry is assumed (9072ca7)
  fr: L'encadré sur la symétrie des voies dit désormais clairement que la symétrie gauche/droite est supposée (9072ca7)
- The guided tour frames the structure illustration again (2fa1ce1)
  fr: La visite guidée cadre de nouveau l'illustration de la structure (2fa1ce1)

## Docs

- The pre-push hook also runs the JavaScript tests (0f58053)
  fr: Le hook pre-push lance aussi les tests JavaScript (0f58053)
