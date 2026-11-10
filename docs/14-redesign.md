# Étape 14 — Le redesign

**Statut : cadre, Résultats (tours et régularité), Télémétrie et Temps au tour terminés.**
Les écrans 01 à 06 ont suivi l'ingénieur de course : tous faits (voir
[18-classement.md](18-classement.md)). Fait le 2026-11-06, d'après les maquettes du
dossier `InterfaceDesign`.

---

## La technologie ne change pas

HTML, CSS et canvas reproduisent les maquettes sans limite. Le seul manque était une fenêtre à
soi : les maquettes montrent un programme, avec sa barre de titre et ses boutons. `pywebview`
affiche donc la même page dans une fenêtre Windows sans bordure.

L'outil garde son fonctionnement : `python -m lmu_telemetry web` ouvre toujours la page dans un
navigateur, et sans WebView2 le `.exe` s'y rabat de lui-même.

### Déplacer et redimensionner

Une fenêtre sans bordure perd sa barre et ses côtés. La page les dessine et prévient Python quand
le bouton s'enfonce ; Python suit ensuite la souris (voir `lmu_telemetry/fenetre.py`, qui dit
aussi pourquoi les autres méthodes ont été écartées).

Vérifié avec de vrais événements de souris, dans la vraie application :

| Geste | Résultat |
|---|---|
| Barre de titre, +60 / +40 px | fenêtre déplacée d'autant |
| Clic sur un onglet | onglet changé, fenêtre immobile |
| Bords droit, gauche, bas et coin | exacts au pixel |
| Coin tiré au-delà du minimum | s'arrête à 1 120 × 680 |
| Agrandir, restaurer | respecte la barre des tâches, retrouve la taille d'avant |
| Croix | ferme l'application |

### Le .exe

Plus de console : 38,7 Mo, fenêtre ouverte en 3,3 s. Un second lancement ramène la fenêtre
existante au lieu d'en ouvrir une autre (vérifié : une seule fenêtre). Une erreur s'affiche dans
une boîte de dialogue, et une copie va dans `journal.txt`.

## L'index des sessions

L'écran Temps au tour a besoin de toutes les sessions : tracé, voiture, meilleur chrono. Rouvrir
les 583 fichiers prend une à deux minutes. Ce qu'on en sait est donc gardé dans `index.sqlite`, et
seules les sessions nouvelles ou modifiées sont relues. Ce n'est qu'un cache : abîmé ou d'une
ancienne version, il se reconstruit seul.

La liste s'affiche tout de suite à partir des noms de fichiers, et se précise pendant la lecture.
Les routes `/api/resumes` et `/api/traces` disparaissent : l'index les remplace.

## L'accélérateur affiché est celui du pilote

La courbe lit `Throttle Pos Unfiltered`. Le canal filtré porte les coupures automatiques du
changement de rapport et de l'antipatinage, qui se lisent comme des levers de pied.

## L'écart sous les deux chronos

La carte des chronos affiche leur différence. Le delta en bout de courbe peut s'en écarter de
quelques centièmes : deux tours n'ont jamais exactement la même longueur. Cas réel : 1:53.208 et
1:53.229, delta final 0,000.

## La colonne suit la session ouverte

La carte surlignée à gauche est toujours la session affichée, d'où qu'elle ait été ouverte. Le
bouton « ouvrir cette session » de Temps au tour laissait surlignée la précédente, et au démarrage
aucune ne l'était. La session demandée est maintenant retenue dès le clic :

* trop ancienne pour les cartes déjà créées, la liste s'allonge jusqu'à elle ;
* écartée par un filtre, le filtre est retiré ;
* la liste défile jusqu'à elle, sauf si on vient de cliquer dessus.

Une réponse du serveur arrivée après le choix d'une autre session est ignorée : l'écran ne peut plus
contredire la colonne.

Vérifié dans la vraie fenêtre : session de rang 360, session écartée par un filtre, réponse retardée
de 1,5 s derrière la suivante, session illisible, clic ordinaire sans défilement.

## La carte sans numéros

Les pastilles T1, T2… réservaient une marge autour du tracé, alors que la liste des virages, juste
en dessous, donne déjà ces numéros. Elles sont retirées, avec leur placement (voir
[08-numerotation.md](08-numerotation.md)).

La hauteur de la carte suit aussi la forme du circuit, de 170 à 270 px. À hauteur fixe, un tracé
étiré comme Monza restait une bande au milieu de la carte. Ensemble, ces deux changements rendent
l'intérieur du tracé de Monza 1,8 fois plus grand, de 76 × 136 à 140 × 248 px.

Vérifié sur les 13 circuits du disque, et sur Long Beach, celui de la maquette : 251 × 97 px contre
environ 250 × 98.

## Comparaison aux maquettes

Captures de la vraie fenêtre à 1 460 × 880, avec `tools/captures_ecrans.py`, mises côte à côte
avec les maquettes recadrées sur leur fenêtre. Couleurs moyennes mesurées dans les deux images :

| Zone | Maquette (RVB) | Outil (RVB) |
|---|---|---|
| Barre de titre | 26, 35, 48 | 25, 37, 50 |
| Fond sous les cartes | 45, 60, 70 | 43, 60, 70 |
| Fond en bas à droite | 25, 55, 64 | 25, 52, 61 |
| Graphique | 25, 35, 47 | 28, 39, 51 |

### Ce qui diffère, volontairement

| Où | Écart | Pourquoi |
|---|---|---|
| Partout | Emblème de l'outil au lieu du logo des images | L'outil garde son nom et son emblème |
| Partout | Pas de titres « RACE RESULTS 01 » | Ils sont autour de la fenêtre, pas dedans |
| Partout | Français, km/h | Choix de l'outil ; l'anglais est dans les réglages |
| Partout | Langue et dossier dans une roue dentée | La maquette la montre sans dire ce qu'elle contient |
| Télémétrie | Rangée Delta en plus | Fonction de la v1, absente de la maquette |
| Télémétrie | Carte à 4 modes au lieu de 3 | Le mode Delta vient de la v1 |
| Télémétrie | Carte plus haute sur la plupart des circuits | Sa hauteur suit le tracé ; celle de Long Beach, le circuit de la maquette, est proche |
| Télémétrie | Vue de la route et tableau par virage en plus | Fonctions de la v1 |
| Télémétrie | ★ au lieu de l'étiquette « BEST » | Une liste Windows ne peut pas contenir d'étiquette |
| Temps au tour | Tracé du circuit au lieu d'une photo | Aucune photo libre de droits dans l'outil |

### Ce qui manque encore

| Où | Écart | Quand |
|---|---|---|
| Entête de session | Boutons favori et carburant | Sans fonction pour l'instant |
| Télémétrie | Boutons favori et enregistrer, poignées pour réordonner les courbes | Enregistrer viendra avec l'export de tours |
| Colonne de gauche | Les cartes s'estompent vers le bas, moins que sur la maquette au survol | Choix de lisibilité |

## Choisir une voiture du classement

Demandé le 2026-11-06 : cliquer sur une voiture du classement pour voir ses détails et, si possible,
la comparer. Fait le 2026-11-09 avec les écrans 01 à 06 : la fiche d'une voiture, et son rythme
comparé au tien (voir [18-classement.md](18-classement.md)). Ce que les fichiers permettent,
vérifié sur une course de 20 voitures et 192 tours :

| Source | Sur les autres voitures | Ce que ça permet |
|---|---|---|
| XML de résultats | Pilote, équipe, voiture, catégorie, numéro, grille, classement, arrêts, arrivée. Par tour : chrono, S1 à S3, position, vitesse de pointe, pneus, stands | Fiche de la voiture, ses tours, comparaison tour par tour : chronos, secteurs, écart, position |
| `.duckdb` | Rien : seule la voiture du joueur y figure | Aucune courbe de vitesse, de freinage ou de trajectoire |
| Mémoire partagée | Tout le plateau, chaque voiture avec sa télémétrie (course de sonde du 2026-11-09, voir [12-memoire-partagee.md](12-memoire-partagee.md)) | Des courbes des autres, seulement pour les séances captées en direct |

## Les écrans sans maquette

Créés dans le même style : Overlay, réglages, tours d'une session, régularité, virage par virage,
choix du dossier, et les états : chargement, aucune session, aucun tour, jeu non détecté, format
de mémoire inconnu, session verrouillée par le jeu, comparaison impossible, outil injoignable.

Vérifiés un par un. Un défaut est apparu à cette occasion : sans dossier de télémétrie, cliquer
sur un onglet quittait l'écran de choix et annonçait « aucune session ». Ces onglets y ramènent
désormais.

## Le découpage de la page

`app.js` faisait 1 610 lignes. Chaque onglet a son fichier `ecran_*.js`, et ce qui ne dépend pas du
navigateur est dans `format.js`, testé avec Node (`tests/js/`). Sans Node, ces tests sont ignorés.

Un bogue du côté-à-côte mérite d'être retenu : les groupes de tableau restaient gris, parce que la
couleur par défaut, écrite plus bas dans la feuille de style, écrasait celle de la catégorie. Elle
est désormais dans un `:where()`, qui ne pèse rien.
