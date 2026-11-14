# Notes de version

Une entrée par version distribuée, la plus récente en haut. Le numéro est
celui de `lmu_telemetry/__init__.py` : le dernier chiffre augmente pour une
correction, celui du milieu pour un ajout, le premier pour un grand changement.

---

## 2.1.0 — 14/11/2026

**Les courses des amis s'ouvrent dans Résultats, et leurs tours se comparent.**

* Dans le leaderboard, une course s'ouvre dans l'onglet Résultats, même celle
  d'un ami : classement, rythme, positions, statistiques, incidents et chat.
* Sur la page d'un circuit, l'onglet Courses a sa colonne Réf. / Comp. : le
  meilleur tour de chaque course se compare dans l'onglet Télémétrie.
* Pour cela, chaque PC partage désormais avec son groupe le classement complet
  de ses courses en ligne (les autres pilotes de la course et son chat compris)
  et la télémétrie du meilleur tour de chacune. Les amis doivent avoir la 2.1.0
  pour que leurs courses s'ouvrent.
* La liste des sessions se met à jour toute seule : une course apparaît peu
  après qu'on a quitté la séance, sans relancer l'outil.
* Une séance où l'on n'a bouclé aucun tour (un serveur rejoint sans rouler) ne
  compte plus au leaderboard. Une course quittée avant la fin du premier tour
  compte toujours, comme un abandon.
* Temps au tour ne compte plus les essais, et passe avant Télémétrie dans la
  barre des onglets.
* La Ferrari 296 « Evo » et la Ferrari 296 ne font plus qu'une voiture.
* Le meilleur temps encadré ne décale plus sa colonne dans les tableaux.
* Les cartes de l'onglet Télémétrie montrent le modèle de la voiture, jamais le
  nom de l'écurie.
* Le découpage automatique en virages ne se laisse plus tromper par un
  demi-tour, ni par un passage dans un dégagement bitumé : à Spa, une course en
  comptait trois de trop.

---

## 2.0.1 — 13/11/2026

**La fenêtre s'ouvre aussi quand l'outil vient d'un zip téléchargé.**

* Windows marque « venu d'Internet » chaque fichier d'un zip téléchargé, et .NET
  refusait alors de charger les bibliothèques de la fenêtre : l'outil s'ouvrait
  dans le navigateur, en accusant à tort WebView2. Il retire désormais cette
  marque de ses propres fichiers au lancement.
* Quand la fenêtre ne peut vraiment pas s'ouvrir, le message dit de le garder
  ouvert tant qu'on se sert de l'outil dans le navigateur (le fermer arrête
  l'outil), et où trouver `journal.txt`, qui en note désormais la cause.

---

## 2.0.0 — 10/11/2026

**L'outil s'appelle GhostLine for LMU, et il se partage entre amis.**

* **Nouveau nom, nouveau logo** : `GhostLine.exe`. Tes réglages, tes découpages
  et tes logos suivent tout seuls : au premier lancement, le dossier
  `%LOCALAPPDATA%\Telemetrie LMU` devient `%LOCALAPPDATA%\GhostLine`. Supprime
  l'ancien `Telemetrie-LMU.exe`.
* **Un dossier plutôt qu'un seul fichier** : décompresse le zip, puis lance
  `GhostLine.exe` dans le dossier `GhostLine`, à garder entier. L'outil s'ouvre
  en 3 à 4 secondes ; en un seul fichier, il lui en aurait fallu 21.
* **Nouvelle interface**, dans sa propre fenêtre sans bordure : onglets
  Résultats, Télémétrie, Temps au tour et Leaderboard. La liste des sessions
  s'affiche tout de suite, même avec des centaines de fichiers. Plus de fenêtre
  noire : un problème s'affiche dans une boîte de dialogue, et un second
  lancement ramène la fenêtre déjà ouverte.
* **Le classement de chaque séance**, tiré des résultats que le jeu écrit :
  classement et fiche de chaque voiture, rythme de deux pilotes, évolution des
  positions, statistiques, incidents (contacts, limites de piste, pénalités) et
  chat des séances en ligne. Dans la liste, les séances gagnées, de nuit et en
  ligne sont marquées.
* **Temps au tour** : tes records, circuit par circuit.
* **Leaderboard entre amis** : les qualifs et les courses en ligne de chacun,
  une page par circuit (meilleurs tours, voitures, courses) et une fiche par
  pilote. On rejoint un groupe avec un code, et la synchronisation se fait
  toute seule.
* **Se comparer aux amis** : la télémétrie des records se partage dans le
  groupe. Deux tours se choisissent depuis le leaderboard (colonne
  Réf. / Comp.) ou dans l'onglet Télémétrie, et se comparent jusqu'au virage
  par virage.
* **Les logos des 20 marques du jeu** sont livrés ; seul ADESS garde une
  pastille à ses initiales.
* Les seuils de mesure d'un virage se règlent dans `parametres.json`.

---

## 1.1.0 — 23/09/2026

**L'outil existe en anglais.**

* Bouton **FR | EN** en haut à droite : toute l'interface change de langue,
  sans perdre l'écran en cours ni le zoom. Le choix est retenu d'un lancement à
  l'autre. Au premier lancement, l'outil prend la langue du navigateur.
* Tout est traduit : écrans, graphiques, remarques sur les tours, remarques par
  virage, avertissements, messages d'erreur, noms de pays, et la fenêtre noire
  du `.exe`, qui suit la langue choisie (ou celle de Windows).
* Mode d'emploi en anglais, `README.txt`, à côté de `LISEZ-MOI.txt`.
* Un test vérifie que les deux langues ont exactement les mêmes phrases : un
  oubli empêche de construire le `.exe`.

---

## 1.0.0 — 23/09/2026

Première version distribuée, en `.exe` autonome.

* **Liste des sessions** : tri par date ou par meilleur chrono, filtre par
  circuit, variantes de tracé séparées (Monza et Monza Curva Grande).
* **Tours d'une session** : chronos, secteurs, validité ; meilleur tour et
  meilleurs secteurs en violet.
* **Comparaison de deux tours**, y compris de deux sessions différentes :
  delta cumulé, vitesse, pédales, angle volant en degrés, rapport, carte du
  circuit et vue rapprochée de la route.
* **Virage par virage** : virages numérotés T1, T2… comme sur les cartes
  officielles, temps perdu ou gagné sur chacun, freinage, vitesses, remise des
  gaz, temps sur l'erre.
* **Régularité** : dispersion des chronos, tour idéal, virages où tu es le moins
  constant.
* **Modèle de la voiture**, logo de la marque et drapeau du circuit.
* Le jeu est trouvé tout seul dans les bibliothèques Steam ; sinon, l'outil
  demande le dossier et retient la réponse.
