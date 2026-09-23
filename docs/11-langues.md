# Version 1.1.0 — Le français et l'anglais

**Statut : terminé.** L'outil existe en anglais, pour pouvoir le partager avec
des pilotes qui ne lisent pas le français. Un seul `.exe` pour les deux langues,
avec un bouton **FR | EN** en haut à droite, plutôt que deux versions à
construire et à tenir à jour séparément.

---

## Où sont les textes

**Toutes** les phrases de l'outil sont dans deux fichiers :

```
lmu_telemetry/web/statique/langues/fr.json
lmu_telemetry/web/statique/langues/en.json
```

Chaque phrase a une clé — `session.meilleur_tour`, `graphe.frein`… — et le code
n'utilise que la clé. Les clés sont regroupées par préfixe :

| Préfixe | Ce qu'elles couvrent |
|---|---|
| `sessions.`, `session.`, `comparaison.`, `virages.`, `regularite.`… | les écrans de la page |
| `serveur.tour.` | les remarques sur les tours (« passage par les stands ») |
| `serveur.virage.` | les remarques par virage (« pris sans freiner ») |
| `serveur.avert.` | les avertissements au-dessus d'une comparaison |
| `serveur.erreur.` | les messages d'erreur |
| `console.` | la fenêtre noire du `.exe` |

Un emplacement `{n}`, `{chemin}`… est remplacé par une valeur au moment de
l'affichage. Une clé en `.un` / `.plusieurs` existe au singulier et au pluriel.

## Corriger ou ajouter une traduction

**Corriger une phrase** : la modifier dans le fichier de sa langue, en gardant
ses emplacements `{…}` tels quels. Relancer l'outil et recharger la page.

**Ajouter une phrase** (dans un correctif) :

1. l'ajouter, avec la même clé, dans `fr.json` ET `en.json` ;
2. l'utiliser dans le code : `t("ma.cle")` dans la page, `Message("serveur.ma.cle",
   {...})` côté Python, ou `data-t="ma.cle"` sur un élément de `index.html`.

Un oubli ne passe pas : les tests échouent, et `construire-exe.bat` refuse alors
de construire le `.exe`.

## Comment le serveur parle les deux langues

Le serveur ne rédige plus de phrases. Il envoie un **message** : une clé et ses
valeurs, par exemple `{"cle": "serveur.tour.hors_piste", "valeurs": {"duree":
"1.8"}}`. C'est la page qui en fait une phrase, dans la langue choisie. Les
valeurs sont déjà mises en forme par le serveur (« 1.8 » et non 1.8123), pour que
les deux langues affichent les mêmes chiffres.

Le français reste nécessaire côté Python : la ligne de commande l'affiche, et
les journaux s'en servent. Il est lu dans le **même** `fr.json` que la page
(`lmu_telemetry/textes.py`) : chaque phrase n'existe qu'à un seul endroit. La
ligne de commande est restée en français.

Les messages du serveur sont affichés en **texte brut**, jamais en HTML : leurs
valeurs — un chemin, un nom de voiture — viennent de fichiers, et un fichier
piégé ne doit rien pouvoir injecter dans la page. Un test vérifie qu'aucun
message `serveur.*` ne contient de balise.

## La langue choisie

* **Au premier lancement**, la page prend la langue du navigateur, et la
  fenêtre du `.exe` celle de Windows.
* **Le bouton FR | EN** change la langue immédiatement. L'écran en cours est
  redessiné à partir des données déjà chargées, sans rien redemander au serveur,
  et le zoom des graphiques est conservé.
* **Le choix est enregistré par le serveur**, dans `reglages.json`, et non par
  le navigateur. Le `.exe` peut changer de port d'un lancement à l'autre (8770
  pris, il passe à 8771), et le navigateur range ce qu'il mémorise par port : le
  choix aurait été perdu. La fenêtre du `.exe` lit ce même réglage.

Les **noms de pays**, sous les drapeaux, viennent du navigateur lui-même, qui
connaît le nom de chaque pays dans chaque langue : il n'y a pas de liste à
tenir à jour. La **météo** (« Light Clouds ») reste telle que le jeu l'écrit :
c'est une donnée du fichier de session, pas un texte de l'outil.

## Ce que vérifient les tests

`tests/test_langues.py` :

* les deux fichiers ont exactement les mêmes clés, sans texte vide ;
* chaque traduction a les mêmes emplacements `{…}` et les mêmes balises que
  l'original — un `{n}` oublié s'afficherait tel quel ;
* chaque clé utilisée dans le code existe, et chaque clé définie sert
  quelque part ;
* aucun texte n'est resté écrit en dur dans `index.html` — ce test a trouvé un
  « Tous » oublié dans le menu Circuit ;
* aucun message du serveur ne contient de balise ;
* la langue est retenue, une langue inconnue est refusée, et la fenêtre du
  `.exe` parle bien anglais quand c'est la langue choisie.

## Choix de vocabulaire

Le vocabulaire anglais est celui du simracing : *Practice / Qualifying / Race*,
*Lap*, *Cumulative delta*, *Coasting* pour « sur l'erre », *Ideal lap*, *Back on
throttle* pour « remise des gaz », *Spread* pour « dispersion », *Consistency*
pour « régularité ». Une relecture par un anglophone est la bienvenue : il suffit
de corriger `en.json`.
