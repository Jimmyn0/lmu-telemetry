# Étape 19 — Le leaderboard entre amis

Demandé le 2026-11-09 : suivre automatiquement les performances de chacun dans un groupe d'amis.
Un onglet Leaderboard, des statistiques de performance et de course, une page par circuit, un
profil par pilote, et une mise à jour automatique entre plusieurs PC, par un groupe qu'on rejoint
avec un code. Puis comparer, dans l'onglet Télémétrie, son tour à celui d'un ami.

**Statut : les six étapes sont faites** (les performances de chaque séance, l'onglet
Leaderboard, les pages circuits et les fiches pilotes, la synchronisation de groupe, la
comparaison avec les records des amis, et le .exe pour les amis : GhostLine for LMU 2.0.0). Le
service du groupe est en ligne sur Cloudflare depuis le 2026-11-10 : voir
[20-groupe.md](20-groupe.md). Le même jour, les essais sont sortis du leaderboard, et la page
d'un circuit choisit deux tours (Réf. / Comp.) à comparer dans l'onglet Télémétrie.

---

## Le principe

Tout vient des fichiers de résultats que le jeu écrit à chaque séance (`UserData\Log\Results`,
voir [18-classement.md](18-classement.md)) : aucune saisie.

* Chaque PC en tire les seules **performances** de son propriétaire, une par séance. Jamais les
  autres pilotes de ses fichiers : les inconnus d'une séance en ligne n'ont rien à faire dans le
  classement du groupe. (Depuis le 2026-11-14, le classement complet de chaque course part aussi,
  mais seulement pour l'ouvrir dans l'onglet Résultats : voir « Après quelques jours d'usage ».)
* Ce sont ces performances que le groupe partagera. Chaque PC calcule ensuite le leaderboard et
  les statistiques à partir de celles de tous les membres.

## Le plan

| Étape | Quoi |
|---|---|
| 1 | Les performances de chaque séance, tirées des fichiers de résultats. **Fait.** |
| 2 | L'onglet Leaderboard, qualifs et courses en ligne seulement : les dernières courses, un menu des circuits, classement par meilleur tour, filtres (catégorie, voiture, pilote), statistiques de performance et de course. **Fait.** |
| 3 | Les pages circuits (pilotes, voitures, courses) et les fiches pilotes (statistiques, records personnels, courses). **Fait.** |
| 4 | La synchronisation de groupe : un service en ligne (Cloudflare Workers), un code de groupe, l'envoi et la réception automatiques à chaque ouverture et après chaque séance. **Fait**, et en ligne : voir [20-groupe.md](20-groupe.md) |
| 5 | La comparaison télémétrique avec les tours partagés : chaque PC envoie aussi la télémétrie de ses records (meilleur tour par tracé et par voiture), et l'onglet Télémétrie peut prendre le tour d'un ami comme tour comparé ; ou bien on les choisit sur la page d'un circuit (colonne Réf. / Comp.). **Fait** : voir [20-groupe.md](20-groupe.md), « Les records partagés », et plus bas « Comparer deux tours du classement » |
| 6 | Le .exe pour les amis, avec le leaderboard. **Fait** : GhostLine for LMU 2.0.0, distribué en dossier (voir « Étape 6 ») |

## Étape 1 : les performances

`domaine/performances.py`. Une performance résume la séance d'un pilote :

| Champ | Ce qu'il retient |
|---|---|
| Séance | Date, circuit, tracé (`TrackCourse`, seul gage de chronos comparables), type, en ligne ou non |
| Voiture | Modèle, marque, catégorie |
| Tours | Tours bouclés, tours chronométrés |
| Meilleur tour | Son chrono, son numéro, ses trois secteurs |
| Meilleurs secteurs | Le meilleur de chaque secteur, pris dans les tours chronométrés |
| Temps moyen | La moyenne des tours représentatifs, comme la régularité des statistiques : sans le départ, sans les tours d'entrée et de sortie des stands, sans les tours à plus de 7 % du meilleur |
| Vitesse de pointe | La plus haute de la séance |
| Gommes | Le nombre de tours sur chaque composé, et celui du meilleur tour |
| En course | Place sur la grille de sa catégorie, place à l'arrivée (générale et dans la catégorie), taille du plateau (générale et de la catégorie), statut (arrivée, abandon, disqualification) |

Un tour compte s'il a un chrono dans le fichier : le jeu n'en donne pas à un tour invalidé.

**Retrouver le propriétaire.** Seul contre l'IA (« Race Weekend »), le jeu ne marque que lui comme
joueur ; en ligne, il marque tous les humains. Les noms du propriétaire sont donc ceux de sa
télémétrie, plus le joueur de ses séances jouées seul. En ligne, seule sa ligne est gardée.

**Le bilan des courses** (`bilan_courses`) compte les courses, victoires, podiums, top 10 et
abandons, la place moyenne (sur les arrivées seulement) et les tours. Les places sont celles de la
catégorie. Une victoire contre l'IA ne vaut pas une victoire en ligne : le leaderboard ne compte
que les qualifs et les courses en ligne (étape 2).

L'index des résultats (`sources/resultats.py`) garde pour cela, dans le passage qu'il fait déjà sur
tous les fichiers, les joueurs de chaque séance avec leurs tours, et la taille du plateau par
catégorie.

### Sur les fichiers du disque (2026-11-09)

567 séances lues en 0,76 s, un nom de pilote retrouvé, 561 performances calculées en 0,01 s :

| | Essais | Qualifs | Courses |
|---|---:|---:|---:|
| En ligne | 187 | 74 | 75 |
| Seul | 145 | 16 | 64 |

238 séances n'ont aucun tour chronométré (une sortie sans boucler de tour) : elles comptent dans
les séances, pas dans les classements de chronos.

| Courses | Nombre | Victoires | Podiums | Top 10 | Abandons | Place moyenne |
|---|---:|---:|---:|---:|---:|---:|
| En ligne | 75 | 1 | 6 | 41 | 8 | 10,1 |
| Contre l'IA | 64 | 3 | 3 | 4 | 53 | 9,3 |

Les 53 abandons contre l'IA sont des courses quittées en route : 101 tours en tout sur 64 courses.

## Étape 2 : l'onglet Leaderboard

`domaine/leaderboard.py` calcule, `GET /api/leaderboard` sert (`web/reponses.py`), et
`ecran_leaderboard.js` montre. Le serveur applique les filtres et renvoie ceux qu'il a retenus :
la page n'a qu'à afficher.

**En ligne seulement.** Contre l'IA, on règle soi-même le niveau des adversaires : ni les chronos
ni les victoires ne s'y comparent. Les séances jouées seul ne comptent nulle part dans l'onglet
(une première version les montrait à part ; retiré à la demande, le 2026-11-10).

**Ni les essais** (demandé le 2026-11-10) : ne comptent que les qualifications et les courses
(`leaderboard.comptee`). Partout dans l'onglet (classements, menus, fiches, dernières courses), et
dans ce que le groupe partage : performances, contours et records (voir
[20-groupe.md](20-groupe.md)). Le leaderboard les écarte aussi à la réception : les essais
qu'aurait envoyés un ami resté sur une version précédente n'y entrent pas.

**La colonne de gauche** choisit le circuit, comme dans l'onglet Temps au tour : une carte par
circuit, avec son drapeau, ses courses et ses séances, le meilleur tour de ses catégories, et le
contour de son tracé en fond quand la télémétrie le connaît (`Index.contours` : les tracés de la
télémétrie et des fichiers de résultats portent le même nom). Elle se trie par nom ou par nombre
de séances. Sa première carte, **Dernières courses**, est la page d'accueil de l'onglet.

**Les dernières courses** : les courses en ligne, de la plus récente à la plus ancienne, tous
circuits et catégories mêlés. Chaque ligne dit donc son circuit et sa catégorie, avec la date et
l'heure, le pilote et sa voiture, la place au départ et à l'arrivée dans la catégorie (et les places
gagnées ou perdues), le meilleur tour et les tours. Vingt à la fois, et « Voir 20 de plus » en
dessous. Un clic sur une course ouvre le leaderboard de son circuit, dans sa catégorie. Sous la
liste, le bilan des courses de tous les circuits.

**Un circuit** s'ouvre sur son tracé le plus roulé ; une liste donne les autres (Monza et sa Curva
Grande, Bahreïn et son Paddock...). Puis les meilleurs tours et le bilan des courses du tracé.

**Les filtres** : la catégorie, la voiture et le pilote, sur les deux pages. Un filtre qui n'a plus
de sens disparaît : une catégorie absente du tracé choisi, une voiture absente de la catégorie ; un
tracé inconnu ramène aux dernières courses.

**Les meilleurs tours**, catégorie par catégorie, la plus rapide d'abord. Une ligne par pilote
**et par catégorie** : sur les fichiers du disque, une seule ligne par pilote laissait un tour en
LMP3 cacher tous les chronos en GT3 du même circuit.

| Colonne | Ce qu'elle montre |
|---|---|
| Pilote / voiture | Le pilote, et la voiture de son meilleur tour |
| Date | La date et le type de séance du meilleur tour |
| S1, S2, S3 | Les secteurs du meilleur tour |
| Meilleur tour | Le plus rapide de toutes les séances retenues, avec sa gomme |
| Écart | Avec la **référence de la catégorie** : son meilleur tour sur ce tracé, quels que soient les filtres de voiture et de pilote. Filtré sur une voiture, on voit donc ce qu'elle laisse au meilleur de la catégorie |
| Tour idéal | La somme des meilleurs secteurs, pris dans toutes les séances |
| Temps moyen | La moyenne des temps moyens des séances, chacun pesant ses tours représentatifs |
| V. max, Tours | La plus haute vitesse de pointe, et tous les tours bouclés dans la catégorie sur ce tracé |

Le meilleur de chaque colonne est en violet, comme ailleurs dans l'outil ; seul dans sa catégorie,
un pilote n'a rien en violet (toute sa ligne le serait). Les colonnes ont des largeurs fixes : elles
s'alignent d'une catégorie à l'autre, et tout tient à côté de la colonne des circuits, d'où le
pilote et sa voiture dans une même cellule.

**Les familles de catégories.** Le jeu écrit « Hyper », « LMP2 » ou « LMP2_ELMS » ; comme les
étiquettes de l'écran (`familleClasse` de `format.js`), le leaderboard n'en garde que la famille :
HYPER, LMP2, LMP3, GTE, GT3. Les LMP2 aux deux réglementations se comparent donc ensemble.

**Le bilan des courses**, sur le tracé choisi ou sur tous : courses, victoires, podiums, top 10,
abandons, place moyenne, tours en course, tours au total. Les plus victorieux d'abord, puis les plus
souvent sur le podium, puis la meilleure place moyenne.

Tant que le groupe n'existe pas, l'en-tête le dit : seules les séances de ce PC comptent.

**Le contour derrière les sessions.** Demandé avec le menu des circuits : les cartes de la colonne
de gauche de l'onglet Résultats ont aussi le contour de leur tracé en fond. `/api/sessions` donne
les contours une fois pour toutes (`contours`, par tracé), et `contourSvg` (`commun.js`) les dessine
pour les trois écrans.

### Sur les fichiers du disque (2026-11-10)

11 circuits roulés en ligne, dont 9 ont un contour : la télémétrie n'en connaît pas pour le tracé
principal de Bahreïn ni pour Sebring. 75 courses en ligne dans les dernières courses. Le premier
affichage relit l'index des résultats (0,75 s) ; ensuite, le calcul prend moins d'une milliseconde.
À Monza : LMP3 en 1:49.775, GT3 en 1:51.744, GTE en 1:58.536. En ligne, sur tous les circuits :
75 courses, 1 victoire, 6 podiums, 41 top 10, place moyenne 10,1.

Sans les essais (même jour) : 149 séances comptent sur 336 en ligne (74 qualifs, 75 courses).
7 circuits, dont 6 ont un contour. À Monza ne reste que le GT3, en 1:51.744 : les tours en LMP3
et en GTE étaient des essais.

## Étape 3 : les pages circuits et les fiches pilotes

Demandé le 2026-11-09 : « une page dédiée à chaque circuit permettant de comparer les pilotes, les
voitures et leurs performances », et « une fiche individuelle avec l'historique des performances,
les records personnels et les statistiques générales ». Fait le 2026-11-10, dans le même onglet :
`GET /api/leaderboard` donne la page demandée (`vue`), d'après `trace` (un circuit) ou `profil`
(un pilote) ; sans l'un ni l'autre, les dernières courses. Un tracé l'emporte sur un pilote, et un
pilote inconnu ramène aux dernières courses.

**La colonne de gauche** montre au choix les **circuits** ou les **pilotes** (deux boutons en
haut, chacun avec son nombre), sous la carte des dernières courses. Elle suit la page : une fiche
la met sur les pilotes, un circuit sur les circuits. La carte d'un pilote : ses initiales (un
pilote n'a pas de drapeau), ses courses, victoires et podiums, ses trois catégories les plus
roulées, la date de sa dernière séance.

**La page d'un circuit**, en en-tête : le drapeau, ce que le tracé a vu (courses, séances,
pilotes, voitures, tours), une liste pour ses autres tracés, et le contour du tracé en fond
(`contour` de la réponse). Puis trois sous-onglets, comme ceux de Résultats :

| Sous-onglet | Ce qu'il compare |
|---|---|
| Pilotes | Les meilleurs tours, catégorie par catégorie (voir l'étape 2), avec une colonne Réf. / Comp. pour les tours enregistrés, qui se comparent dans l'onglet Télémétrie (voir « Comparer deux tours du classement ») |
| Voitures | Catégorie par catégorie, une ligne par voiture (`classement_voitures`) : le meilleur tour bouclé à son volant et qui l'a signé, l'écart avec la référence de la catégorie, combien de pilotes l'ont prise, ses séances, son temps moyen tous pilotes confondus, sa vitesse de pointe, ses tours |
| Courses | Le bilan des courses sur ce tracé, puis ses dernières courses |

Même seul, l'onglet Voitures a son intérêt : à Monza en GT3, la Ferrari 296 Evo est la plus
rapide du propriétaire, 3 millièmes devant la Porsche et 5 centièmes devant la McLaren.

**La fiche d'un pilote** (`fiche_pilote`) : ses initiales en grand, son nom, depuis quand il roule
en ligne, son circuit et sa voiture favoris (les plus roulés). Sept tuiles : séances, courses,
victoires, podiums, top 10, place moyenne, tours. Puis :

* **Records personnels** (`records_personnels`) : son meilleur tour sur chaque tracé, dans chaque
  catégorie, avec la voiture, la date, la gomme, l'écart avec la référence de la catégorie et son
  **rang** parmi les meilleurs tours des pilotes du groupe (« P2 / 3 »). Filtrée sur une voiture,
  la fiche montre ses records dans cette voiture, mais le groupe compte toutes les voitures : la
  référence peut alors être son propre tour dans une autre.
* **Par catégorie** : ses séances et le bilan de ses courses dans chacune.
* **Dernières courses** : les siennes.

Les filtres de catégorie et de voiture restent ; celui du pilote n'a plus de sens et disparaît.
Une fiche s'ouvre toujours entière, sans les filtres de la page d'où l'on vient : ouverte depuis
une page filtrée en LMP3, elle ne montrait que 10 séances sur 336, sans qu'on comprenne pourquoi.

**Les liens.** Le nom d'un pilote ouvre sa fiche, partout : meilleurs tours, voitures, bilans,
dernières courses. Une course ou un record ouvre le circuit, dans sa catégorie.

Au passage : Road Atlanta n'avait pas de drapeau ; il est dans la table des pays (`domaine/pays.py`).

### Sur les fichiers du disque (2026-11-10)

La fiche du propriétaire : 336 séances en ligne depuis le 16/05/2026, Monza pour circuit favori
(114 séances), la Porsche 911 GT3 R pour voiture favorite (105), 18 records personnels. Calculée
en 5 ms ; la page de Monza, en 2 ms.

Sans les essais : 149 séances depuis le 17/05/2026, toujours Monza (60) et la Porsche (53),
9 records personnels. La page de Monza prend maintenant 40 ms : elle cherche le tour enregistré
de chaque ligne.

## Comparer deux tours du classement

Demandé le 2026-11-10 : choisir depuis le leaderboard les deux tours à comparer dans l'onglet
Télémétrie.

**Les pastilles.** Sur la page d'un circuit, onglet Pilotes, la dernière colonne, **Réf. /
Comp.**, est celle de l'onglet Résultats : sur chaque ligne dont un tour est **enregistré**, une
pastille violette le prend en référence, une orange en tour comparé. Le tour enregistré est le
record de ce PC dont la télémétrie est ici, ou celui qu'un ami a partagé (étape 5). Ce n'est pas
toujours le tour du classement : un meilleur tour roulé sans enregistrer la télémétrie n'en a pas.
La ligne prend alors le tour enregistré de la même voiture, sinon le plus rapide de sa catégorie,
et la bulle de la pastille dit lequel (« Tour de référence : le tour enregistré en 1:51.744,
Ferrari 296 LMGT3 Evo »). Le serveur l'ajoute à chaque ligne de la page d'un circuit, et
seulement là (`enregistre`, par `reponses._tours_enregistres`). La colonne fait 100 px : les
marges des cellules du leaderboard (7 et 14 px) ne laissaient pas la place des deux pastilles
dans les 74 px de Résultats ; S1 à S3, la date, le meilleur tour, le tour idéal, le temps moyen,
la vitesse et les tours ont rendu ce qu'ils avaient de trop.

**Le choix**, comme dans Résultats : une pastille donne son rôle au tour, et un tour qui avait
l'autre rôle l'échange. Recliquer une pastille choisie la retire, la référence comprise : rien
n'est choisi d'avance ici, quand Résultats prend le meilleur tour en référence. Une barre
au-dessus du classement dit la référence et le tour comparé, avec leur couleur, et son bouton
**Comparer dans Télémétrie** les ouvre. Une référence suffit : sans tour comparé, l'onglet
Télémétrie la montre seule. Le choix survit aux filtres et au passage par l'onglet Télémétrie ;
un autre tracé le vide. (Une première version cochait deux cases et prenait le plus rapide en
référence ; remplacée à la demande, le même jour.)

**Deux records d'amis** se comparent aussi entre eux. Le record d'un ami en référence n'a pas de
session de ce PC d'où tirer le découpage en virages : le découpage connu du tracé sert, ou à
défaut il se détecte sur les deux tours eux-mêmes et s'enregistre comme celui d'une session
(`circuits.definition_depuis_tours`). L'onglet Télémétrie propose d'ailleurs les records des amis
pour les deux tours, la référence comme le comparé.

## Étape 6 : le .exe pour les amis

Fait le 2026-11-10, sous le nouveau nom de l'outil : **GhostLine for LMU 2.0.0** (voir
[NOTES-DE-VERSION.md](../NOTES-DE-VERSION.md)). Les modes d'emploi des amis (`distribution/`)
expliquent comment rejoindre un groupe et ce qui est partagé. Ils disaient aussi que l'outil ne
se connectait à aucun serveur : ce n'est plus vrai dans un groupe, et ils le disent.

**Un dossier, pas un seul fichier.** En un seul fichier, le .exe se décompresse dans un dossier
temporaire à chaque lancement, puis y charge la fenêtre (.NET, WebView2) depuis des fichiers
tout neufs. Mesuré sur ce PC, avec des données isolées :

| Lancement | Prêt en |
|---|---|
| Depuis le code, fenêtre comprise | 3,3 s |
| .exe en un seul fichier, sans sa fenêtre | 3,6 s |
| .exe en un seul fichier, avec sa fenêtre | 21 s, à chaque lancement |
| Dossier, tout premier lancement après la construction | 21,8 s |
| Dossier, lancements suivants, et copie du dossier ailleurs | 3,0 à 3,2 s |

Le délai suit les fichiers nouveaux sur le disque, pas leur chemin : le plus probable est
l'analyse de Windows à leur première lecture. Le dossier ne le paie qu'une fois, le fichier
unique à chaque lancement. Les modes d'emploi préviennent qu'un tout premier lancement peut
prendre une vingtaine de secondes, pour qu'on ne double-clique pas une seconde fois. Le zip
contient le dossier `GhostLine` : `GhostLine.exe` (8 Mo), `_internal` et les deux modes
d'emploi, 96 Mo décompressé, 40 Mo zippé.

**Vérifié sur le .exe lui-même**, avec des données isolées et le service du groupe lancé sur ce
PC à la place du vrai : version 2.0.0, fenêtre « GhostLine for LMU », vrais logos sans aucun
logo perso, création d'un groupe et synchronisation par ses routes, leaderboard qui voit le
groupe, fermeture avec la fenêtre. L'icône du .exe est le nouveau logo. L'essai s'annule si une
fenêtre de l'outil tourne déjà : le .exe lancé ne ferait que la ramener, et l'essai parlerait au
vrai outil.

## Après quelques jours d'usage (2026-11-14)

Neuf demandes, faites ensemble (GhostLine for LMU 2.1.0) :

* **Temps au tour sans les essais** : `reponses.circuits` ne compte que les qualifs et les courses
  (`TYPES_COMPTES`), comme le leaderboard. Les essais restent dans la colonne de Résultats.
* **Temps au tour avant Télémétrie** dans la barre des onglets.
* **Une même voiture sous deux noms** : à Spa, la Ferrari 296 faisait deux lignes de l'onglet
  Voitures, « Ferrari 296 LMGT3 » (engagements de 2025) et « Ferrari 296 LMGT3 Evo » (2026), sans
  différence en jeu. `resultats.MEMES_VOITURES` ramène les noms d'un même modèle à un seul, dès la
  lecture des fichiers du jeu et à la réception de ce qu'envoie un ami (performances, tours). Relevé
  le même jour dans les 576 fichiers du disque : « Genesis GMR001 » / « GMR-001 », réunis aussi ;
  « Toyota GR010 » / « TR010 », laissés à part en attendant de savoir si c'est la même voiture.
* **Le meilleur temps ne décale plus sa colonne** : le cadre violet (`.temps-record`) prenait 8,5 px
  de chaque côté, et le chiffre se décalait d'autant (17 px avec la gomme à côté). Des marges
  négatives lui rendent cette place : mesuré dans la page, les chiffres s'alignent à 0,5 px près
  (le gras), et la hauteur des lignes ne change pas.
* **Comparer les tours des courses** : sur la page d'un circuit, l'onglet Courses a sa colonne
  Réf. / Comp., comme les meilleurs tours. Chaque PC partage pour cela la télémétrie du meilleur
  tour de chacune de ses courses en ligne (`reponses.mes_courses`), sous un numéro tiré de celui de
  la performance (`tours.identifiant_course`) : la ligne retrouve son tour sans que la liste des
  tours ait à le dire. Voir [20-groupe.md](20-groupe.md), « Les courses partagées ».
* **Une course s'ouvre dans Résultats** depuis les dernières courses (et toute liste de courses),
  même celle d'un ami, avec tous les onglets du classement : classement, rythme, positions,
  statistiques, incidents, chat. Pas les tours ni la régularité, qui demandent la télémétrie. Une
  course de ce PC s'ouvre par sa session, ou par son seul fichier de résultats si elle n'a pas été
  enregistrée ; celle d'un ami, par le classement qu'il a partagé (`groupe/seances.py`). « Toi » y
  est le propriétaire de ce PC s'il a couru, et personne sinon. La course d'un ami dont la version
  de l'outil ne partage pas encore les courses ne mène nulle part (sa bulle le dit).
* **La liste des sessions se met à jour toute seule** : la page la redemande toutes les 20 s et
  quand la fenêtre revient au premier plan, et ne se redessine que si elle a changé. Une session
  que le jeu tient ouverte se retente au bout de 20 s (60 avant) : la course apparaît peu après
  qu'on a quitté la séance, quand le jeu referme son fichier.
* **Le nom de la voiture, jamais celui de l'écurie**, dans les cartes de l'onglet Télémétrie : elles
  montraient l'engagement (« Kessel Racing 2026 #57:ELMS ») au lieu du modèle, que l'index des
  voitures connaissait pourtant (aucun engagement sans modèle sur les 595 sessions du disque).
* **Les courses en ligne seulement** : c'était déjà le cas (qualifs et courses en ligne). Mais
  l'utilisateur, sûr de n'avoir jamais couru en Hypercar en ligne, voyait cette catégorie sur sa
  fiche : le 29/08, il avait rejoint un serveur Hypercar à Fuji (Peugeot 9x8), dont le jeu a écrit
  les essais et les qualifs avec lui dedans, à 0 tour, avant de repartir en GT3 dix minutes plus
  tard. Désormais (`leaderboard.a_roule`), une séance sans aucun tour bouclé ne compte plus, ni à
  l'affichage, ni à l'envoi au groupe, ni pour les courses partagées ; une course quittée avant
  la fin du premier tour compte encore, comme un abandon (choix de l'utilisateur : le fichier ne
  la distingue pas d'un départ du serveur avant le feu vert). Sur le disque et la copie du groupe,
  4 séances sur 388 sortent (cette qualif, une course sans statut à Bahreïn, deux qualifs d'un
  ami), 5 abandons sans tour restent, et la fiche de l'utilisateur n'a plus que GT3.

Vérifié dans la page servie par l'outil (données copiées, service du groupe local, un ami simulé
qui partage une course à Spa) : l'ordre des onglets, l'alignement mesuré (Résultats, et les sept
colonnes de la page de Spa), la course de l'ami ouverte dans Résultats et ses six onglets sans
erreur, la Ferrari 296 en une seule ligne, les pastilles de l'onglet Courses jusqu'à la
comparaison dans Télémétrie (cartes au nom du modèle), Temps au tour sans essais (141 séances), et
une session ajoutée au dossier pendant que la page était ouverte, apparue seule en 10 s.

## Vérifié

* 5 tests : la performance d'une séance (meilleur tour, meilleurs secteurs sans le tour invalidé,
  temps moyen sans le départ, vitesse, gommes, grille et arrivée), hors course, les noms du
  propriétaire, une séance en ligne qui ne garde que lui, le bilan des courses.
* 26 tests pour les étapes 2 et 3 : une ligne par pilote et par catégorie, le meilleur tour et ce
  qui l'entoure (secteurs, tour idéal, temps moyen pondéré, gommes), l'écart avec la référence de
  la catégorie malgré les filtres, les familles de catégories, le bilan des courses trié, les
  dernières courses (ordre, page, filtres), les menus des circuits et des pilotes, les voitures d'un
  circuit, la fiche d'un pilote et le rang de ses records (même filtrée sur une voiture), la page
  demandée, les listes des filtres, les filtres d'une demande, les seules séances en ligne, la
  route, et l'absence du dossier de résultats.
* L'écran dans la vraie fenêtre : les dernières courses et « voir plus », Spa, Monza et sa Curva
  Grande, le clic sur une course ; les trois sous-onglets d'un circuit, le menu des pilotes, la
  fiche, un record qui mène à son circuit, un nom qui mène à sa fiche. Puis avec deux amis simulés
  le temps d'une capture : l'historique mêlé, le tri, les écarts, le violet, les rangs. Les
  contours derrière les sessions de Résultats, et l'onglet Temps au tour inchangé.
* Sans les essais : un test (une séance d'essais en ligne ne compte nulle part), et ceux du groupe
  (rien d'autre ne part que les qualifs et les courses ; un record d'essai reçu est écarté).
* Les deux tours choisis : 3 tests (`tests/test_tours_partages.py`) : le tour enregistré de
  chaque ligne, le record d'un ami en référence (découpage détecté, puis connu), un record demandé
  par plusieurs routes à la fois. Puis dans la vraie fenêtre, contre le service local et deux amis
  simulés : à Monza, les pastilles des trois lignes du GT3 ; mon tour en référence contre celui
  d'un ami ; au retour, le choix gardé, l'échange des rôles, une pastille retirée puis remise ;
  les deux amis entre eux, jusqu'au virage par virage (11 virages) ; une référence seule ; Spa, où
  le choix repart de zéro.
