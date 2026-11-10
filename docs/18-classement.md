# Étape 18 — Le classement d'une séance

**Statut : fait.** Les six écrans des maquettes : classement et fiche d'une voiture (01, 02),
rythme de deux pilotes (03), évolution des positions (04), statistiques (05), incidents (06) ; le
chat des séances en ligne ; et les étiquettes de la colonne de gauche (victoire, départ de nuit,
en ligne), avec un filtre « en ligne ».

---

## D'où il vient

À chaque séance, le jeu écrit un fichier de résultats dans `UserData\Log\Results`. Il donne tout le
plateau, et chaque tour de chaque voiture, alors que le `.duckdb` ne connaît que la voiture du
joueur. `sources/resultats.py`, le seul module qui connaît ce format, le lit en entier
(`lire_session`).

Ce qu'il contient, vérifié le 2026-11-09 sur 571 fichiers :

| Où | Quoi |
|---|---|
| Par voiture | Pilote, équipe, modèle, catégorie, numéro, grille et place (au général et dans la catégorie), meilleur tour, temps à l'arrivée, tours, arrêts, statut d'arrivée |
| Par tour | Place au général, chrono, trois secteurs, vitesse de pointe, gommes, usure, carburant, passage aux stands |
| Journal de la séance | Contacts avec leur intensité (28 762), limites de piste (68 009), pénalités avec leur motif (544), meilleurs secteurs, messages du chat en ligne (1 300) |

Les cas à connaître :

* un tour sans temps s'écrit « --.---- », et ses secteurs manquent alors en partie ;
* les secteurs ne sont pas cumulés : leur somme fait le tour ;
* un tour passé aux stands porte `pit="1"` ;
* les gommes s'écrivent « 0,Medium » ou « 1,Wet », et « 15,N/A » quand le jeu n'en sait rien ;
* le statut vaut « Finished Normally », « DNF », « DQ », ou « None » hors course ;
* une course au temps annonce 2 147 483 647 tours, et sa durée en minutes ;
* l'horodatage d'un tour est celui de son départ, sur l'horloge de la séance : en course, tous les
  premiers tours partent au drapeau vert (68,1 s dans la course du 2026-11-09 au soir), et le temps
  à l'arrivée se compte depuis lui.

## Relier une session à sa séance

La colonne de gauche liste les sessions de télémétrie. Pour en montrer le classement, il faut
retrouver le fichier de la même séance : même circuit, même type (essais, qualifications, course).

L'heure ne suffit pas telle quelle. Le fichier date la séance de son début, la télémétrie de la
sortie du garage : en essais, l'écart va jusqu'à une heure. On prend donc la dernière séance
commencée avant la sortie, à cinq minutes près, car l'enregistrement d'une course démarre parfois
avant le départ. Elle doit contenir la voiture du joueur, ou au moins couvrir sa sortie (durée de la
séance plus dix minutes).

Vérifié sur les 586 sessions du disque : toutes retrouvent leur séance. 579 y retrouvent la voiture
du joueur. Les 7 autres sont des essais où il a changé de voiture en cours de séance, et le fichier
ne garde que la dernière. Lire les 571 fichiers pour cet index prend 0,6 s, une fois.

## Qui est « toi »

Le fichier marque la voiture du joueur (`isPlayer`), mais en multijoueur il marque tous les humains :
36 sur 36 dans une qualification en ligne, dont 5 sous le même engagement que le joueur. C'est son nom
de pilote qui le désigne : la télémétrie et le fichier l'écrivent de la même façon, et il ne désigne
qu'une voiture dans chacune des 586 séances. Le marquage du jeu ne sert que s'il ne désigne qu'une
voiture. Sinon, personne n'est marqué : mieux vaut personne que le mauvais.

## Ce que montre l'écran

Le sous-onglet **Classement** s'ouvre le premier, avant Tours et Régularité.

* **En course** : place, numéro, pilote, voiture, gomme, meilleur tour, écart, arrêts, tours, temps
  ou abandon.
* **En essais et en qualifications** : les trois secteurs du meilleur tour à la place des arrêts et
  du temps.
* Le meilleur tour et les meilleurs secteurs de ce qui est affiché sont en violet.
* **Les catégories**, de la plus rapide à la plus lente d'après leur meilleur tour, filtrent le
  tableau. Places et écarts deviennent alors ceux de la catégorie.
* **L'écart** : en course, les tours de retard, sinon le temps à l'arrivée ; ailleurs, l'écart de
  meilleur tour.
* **La gomme** : celle de l'arrivée en course, celle du meilleur tour ailleurs, en lettre (S, M, H,
  W) et en couleur.

**Un clic sur une voiture ouvre sa fiche** : grille et arrivée dans sa catégorie, avec le général en
dessous ; son meilleur tour et le tour où il l'a fait ; sa vitesse de pointe, ses tours, ses arrêts,
son arrivée et son écart. Puis chacun de ses tours : place, chrono, secteurs, vitesse de pointe,
gomme, passage aux stands. La place de chaque tour est celle de la catégorie : les voitures de la
catégorie qui ont bouclé ce tour, classées par leur place au général à la fin du tour.

## Le rythme de deux pilotes

Le sous-onglet **Rythme** compare deux pilotes tour par tour (maquette 03). Par défaut, toi et le
rival de ta catégorie juste devant toi au classement, juste derrière si tu es en tête. Le bouton
**Comparer avec moi** de la fiche d'une voiture l'ouvre sur cette voiture et toi. Deux listes, par
catégorie, changent l'un ou l'autre.

* **Le graphique** : les chronos de chacun, en violet et en orange comme dans l'onglet Télémétrie, et
  l'étiquette de leur meilleur tour. Sous la souris, les deux temps du tour et l'écart.
* Un tour sans temps coupe la ligne. Un tour passé aux stands est un rond creux.
* Un tour plus lent de 7 % que le meilleur des deux (le départ, un arrêt) est posé en haut du cadre,
  en triangle : à l'échelle, il écraserait les autres. Dans la course du 2026-11-09 au soir, le premier
  tour d'une GT3 prend 2:19 pour un meilleur tour en 1:53.
* **Les tableaux** : les tours de chacun, avec ses secteurs et son écart sur le même tour de l'autre,
  en vert quand il est plus rapide.

Le classement suffit : chaque voiture y a tous ses tours. Le graphique est dans `rythme.js`, à part
de `graphes.js` comme `chronos.js` : un axe de numéros de tour, pas de distance.

## L'évolution des positions

Le sous-onglet **Positions** (maquette 04) n'existe qu'en course : en essais et en qualifications,
une place au fil des tours ne raconte rien. Une ligne par voiture, de la grille à l'arrivée, la
première place en haut ; une croix au dernier tour d'un abandon.

* En multiclasse, il s'ouvre sur la catégorie du pilote, et ses places sont celles de la catégorie.
  Le général reste à un clic, avec ses 38 lignes.
* La liste des pilotes, dans l'ordre de l'arrivée, donne la couleur de chacun. Le violet est le
  tien, comme partout.
* La voiture sous la souris, dans le graphique ou dans la liste, passe devant les autres, qui
  s'estompent, avec son nom et sa place au bout de sa ligne. **Me mettre en avant** fait de même
  avec la tienne.

Les places de chaque tour viennent du classement : `courbesPositions` (`format.js`, testée avec
Node) les met en points, et `positions.js` les dessine.

## Les statistiques

Le sous-onglet **Statistiques** (maquette 05) n'existe qu'en course, comme les Positions. Pour
chaque catégorie, de la plus rapide à la plus lente, les meilleures performances
(`domaine/classement.py`, `statistiques`) :

| Carte | Ce qu'elle retient |
|---|---|
| Meilleur tour | Le chrono le plus rapide, et son tour |
| Meilleur secteur 1, 2, 3 | Le secteur le plus rapide, pris seulement dans les tours chronométrés : le premier secteur d'un tour invalidé plus loin ne compte pas |
| Régularité | Le plus petit écart-type des tours représentatifs : ni le départ, ni les tours d'entrée et de sortie des stands, ni ceux à plus de 7 % du meilleur tour du pilote. Il en faut au moins trois |
| Le plus de places gagnées, perdues | Entre la grille et l'arrivée, dans la catégorie |
| Gomme la plus utilisée | La gomme du plus grand nombre de tours de la catégorie |

À égalité, le mieux classé l'emporte. Le titre de chaque carte a la couleur de son genre, comme sur
la maquette : violet pour un record, bleu pour la régularité, vert et rouge pour les places, jaune
pour la gomme.

Dans la course du 2026-11-09 au soir : chez les GT3, le meilleur tour est un 1:53.450 au tour 3.
La plus belle remontée gagne 11 places, de 14e sur la grille à 3e. Le pilote le plus régulier des
LMP2 tourne à 0,046 s d'écart-type sur 6 tours.

## Les incidents

Le sous-onglet **Incidents** (maquette 06) existe pour toutes les séances. Il lit le journal du
fichier de résultats :

| Genre | Ce que le jeu écrit | Ce que montre l'écran |
|---|---|---|
| Contact | « A(4) reported contact (115.48) with another vehicle B(17) », ou « … with Immovable », « Post », « Sign », « Wheel », « Wing », « Cone » | « Contact avec B · moyen », « Contact avec le décor · violent » |
| Limites | `TrackLimits`, et sa suite : « No Further Action » (87 % des cas), « Warning », « Invalid Lap Cut Track », une pénalité | « Sans suite », « Avertissement », « Tour invalidé »... |
| Pénalité | `Penalty` reçue (type, motif, durée) ou purgée (« A served 1st Drive Thru penalty… ») | « Stop and go 10 s · Excès de vitesse dans les stands », « Stop and go purgé » |

* **La gravité d'un contact** vient de sa force : léger sous 100, moyen jusqu'à 1 000, violent
  au-delà. Sur les 28 762 contacts du disque, quatre sur dix sont légers et un sur six violent.
* **Le temps restant** se compte depuis le départ (le drapeau vert en course, le début de la séance
  ailleurs), plus la durée de la séance. Sans durée, l'écran montre le temps écoulé.
* **Le tour** est celui que le pilote courait : le dernier parti avant l'incident. Pendant le tour
  de formation, il n'y en a pas encore.
* Les filtres : la catégorie, le genre (une pénalité purgée va avec les pénalités), le pilote. Tes
  lignes sont teintées de violet.
* Le reste du journal (scores, meilleurs secteurs, chat) n'est pas un incident. Les contacts sans
  nom de pilote (41 sur le disque) sont écartés.

Dans la course du 2026-11-09 au soir : 42 incidents, dont 35 contacts (12 légers, 17 moyens, 6
violents) et les 7 sorties du pilote hors des limites de piste, toutes sans suite.

Une fois le temps de la séance écoulé (le dernier tour d'une course au temps), le temps restant
devient le temps passé depuis : « +1:23 ».

## Le chat des séances en ligne

Le sous-onglet **Chat** n'existe que pour une séance en ligne. Il donne chaque message du journal
(« Auteur: texte »), avec son heure comme les incidents : les « gg » d'après l'arrivée y sont en
« +0:59 ». 189 séances du disque en ont, 1 300 messages en tout.

## Les étiquettes de la colonne des sessions

| Étiquette | D'où elle vient |
|---|---|
| **Victoire** | La séance est une course, et le pilote y finit premier de sa catégorie, arrivée vue (un abandon en tête n'en est pas une). Il est retrouvé par son nom, ou comme seul joueur du fichier |
| **Départ de nuit** (lune) | L'heure du jeu au départ, que la télémétrie donne (`SessionTime`) : entre 20 h et 6 h. Le départ seul compte : une course qui part à 16 h et roule jusqu'à la nuit reste une course de jour. 61 sessions du disque partent de nuit |
| **En ligne** (antenne) | Le fichier de résultats : `Setting` vaut « Multiplayer » (19 à 38 humains, aucune IA), et « Race Weekend » pour une séance seul, avec ou sans IA |

Le filtre **Seulement les séances en ligne** (bouton Filtres) ne garde qu'elles.

* L'heure du jeu est une colonne de plus dans l'index des sessions : à la première ouverture de
  cette version, l'index se reconstruit seul (68 s pour 587 sessions), et les lunes apparaissent au
  fil de la lecture.
* Victoire et en ligne sont retrouvés à chaque liste, dans l'index des fichiers de résultats déjà
  en mémoire. Vérifier que le dossier n'a pas changé demande un passage sur ses fichiers : un objet
  `Seances` ne le fait qu'une fois par liste. Le faire pour chaque session coûtait 0,6 s ; la liste
  revient en 0,035 s.

## Vérifié

* 32 tests côté Python : lecture d'une séance, appariement, écarts, places par tour, « toi » en
  multijoueur, statistiques, journal et incidents, étiquettes (victoire en ligne et hors ligne,
  départ de nuit), chat, la route. Côté page, le duel par défaut, les points des positions, l'heure
  de séance, le temps restant et le filtre « en ligne » sont testés avec Node.
* Dans la vraie fenêtre, sur les vraies sessions : la course multiclasse du 2026-11-09 au soir (38
  voitures), son filtre GT3, la fiche du pilote, une qualification en ligne de 20 GT3, le rythme
  ouvert depuis la fiche du vainqueur des GT3 avec la bulle du survol, et les positions des GT3 puis
  du général, avec le survol d'un pilote et la mise en avant, les statistiques des trois catégories,
  et les incidents, au complet puis filtrés sur les limites de piste des GT3. En qualification, les
  onglets Positions et Statistiques disparaissent. Puis la colonne après la reconstruction de
  l'index : les séances en ligne filtrées, le chat d'une course en ligne, et une victoire à Monza
  Curva Grande.
* Les étiquettes de la colonne de gauche (victoire, en ligne), et le chat des séances en ligne.
