# 3.55.0 (2026-09-02)

## Added

- The address bar now describes the whole view, so a link brings someone to exactly what you were looking at: every open tab and the order you dragged them into, which one is in front, the popup you had up, the sliders and toggles, the open section, what you had typed in search, and roughly where the brain is turned. Copy the URL, that is the link (c063bfc)
  fr: La barre d'adresse décrit maintenant toute la vue : un lien amène la personne exactement sur ce que vous regardiez, avec tous les onglets ouverts dans l'ordre où vous les avez glissés, celui qui est au premier plan, la fenêtre que vous aviez ouverte, les curseurs et les cases cochées, la section dépliée, ce que vous aviez tapé dans la recherche, et l'orientation approximative du cerveau. Copiez l'URL, c'est le lien (c063bfc)

## Fixed

- A link to a pathway (`#focusConnection=...`) opened nothing; it now opens the pathway it names (c063bfc)
  fr: Un lien vers une voie (`#focusConnection=...`) n'ouvrait rien ; il ouvre désormais la voie qu'il nomme (c063bfc)
- A link asking for the 3D brain to be shown (`#panel=0`) was ignored for a visitor who had previously turned the brain off; the link now wins (c063bfc)
  fr: Un lien demandant l'affichage du cerveau 3D (`#panel=0`) était ignoré pour une personne ayant précédemment masqué le cerveau ; le lien l'emporte désormais (c063bfc)
