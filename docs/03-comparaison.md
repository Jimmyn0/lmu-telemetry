# Étape 3 — Comparaison de deux tours

**Statut : terminée.** Traces superposées, delta cumulé, carte du circuit, et
une interface web locale.

Prérequis : [01-decouverte.md](01-decouverte.md) pour le format des fichiers,
[02-lecture-tours.md](02-lecture-tours.md) pour le découpage en tours.

---

## Ce qui a été livré

| Module | Rôle |
|---|---|
| `lmu_telemetry/donnees_tour.py` | extrait un tour et le ramène sur un axe de distance |
| `lmu_telemetry/comparaison.py` | aligne deux tours et calcule le delta cumulé |
| `lmu_telemetry/web/serveur.py` | serveur local, quatre routes JSON |
| `lmu_telemetry/web/statique/graphes.js` | moteur de graphiques (canvas) |
| `lmu_telemetry/web/statique/app.js` | enchaînement des trois écrans |

Lancement : `python -m lmu_telemetry web`.

---

## L'axe de distance

### Quelle distance

`Lap Dist` mesure l'avancement **le long de la piste**. C'est celui qu'il faut :
deux tours qui prennent des trajectoires différentes doivent se comparer au même
endroit du circuit.

Ce n'est pas la distance réellement parcourue par la voiture. Mesuré : intégrer
`Ground Speed` sur un tour donne 10 à 40 m de plus que `Lap Dist` sur 5 776 m,
soit 0,2 à 0,7 %. L'écart est physique — la voiture s'écarte de l'axe — et les
deux mesures sont justes, elles ne mesurent simplement pas la même chose.

### De 10 Hz à 100 Hz

`Lap Dist` n'est qu'à 10 Hz, soit un point tous les 6 m à 227 km/h, alors que la
vitesse et l'angle volant sont à 100 Hz.

**L'interpolation linéaire suffit**, et ce n'est pas une approximation
grossière : comparée à une interpolation cubique sur les mêmes données, l'écart
médian est de **2 mm** et le 99e centile de **3 cm**. Sur 0,1 s, l'accélération
ne courbe pas assez la distance pour que ça se voie.

Le seul vrai piège est aux **bords du tour**. Le dernier échantillon de
`Lap Dist` tombe jusqu'à 0,1 s avant la ligne, et une interpolation classique
fige la valeur au-delà : la fin du tour se retrouve immobile, jusqu'à **5 m
perdus à 227 km/h**. On prolonge donc linéairement la pente locale, qui n'est
autre que la vitesse. Un test couvre ce cas.

---

## Le delta cumulé

```
delta(d) = temps_du_tour_comparé(d) − temps_du_tour_de_référence(d)
```

* delta positif : à cet endroit, le tour comparé a déjà perdu du temps
* delta qui **monte** : on perd du temps ici, maintenant
* delta qui **descend** : on en gagne ici

C'est la **pente** qui dit où se joue le chrono, pas la hauteur. Un palier, même
très haut, veut dire qu'on y roule aussi vite que la référence — le retard a été
pris avant.

### Le contrôle du calcul

En bout de tour, le delta doit valoir la différence des deux chronos officiels.
Vérifié sur des comparaisons réelles : l'écart reste **sous 0,035 s**. Le
résidu vient de ce que les deux tours ne couvrent pas exactement la même
longueur de `Lap Dist`, si bien que l'axe commun s'arrête un peu avant la ligne.

### Une formulation séduisante, et fausse

On lit souvent que le delta s'obtient en intégrant la différence des inverses de
vitesse le long de la distance :

```
delta(d) = ∫ (1/v_comparé − 1/v_référence) dx
```

C'est nettement plus lisse — la vitesse est à 100 Hz, la distance à 10 Hz. J'ai
implémenté les deux et comparé sur huit paires de tours réelles :

| Formulation | Saut maximal au mètre | Erreur sur la valeur finale |
|---|---:|---|
| par la distance | 0,049 s | **de 0,000 à 0,032 s** |
| par les vitesses | 0,017 s | de 0,004 à **6,9 s** |

La formulation par les vitesses **dérive** : elle intègre la vitesse de la
voiture, donc la distance parcourue, alors que l'axe est l'avancement le long de
la piste ; l'écart entre les deux ne se compense pas d'un tour à l'autre. Un
delta plus joli mais faux ne vaut rien. **On garde la formulation par la
distance.**

### Le plancher de bruit, et pourquoi il n'est pas lissé

Comme `dt/dd = 1/v`, une imprécision de distance pèse d'autant plus que la
voiture est lente : à 46 km/h, un demi-mètre d'erreur fait 0,04 s de delta. Dans
les virages les plus lents, la courbe porte donc un bruit de l'ordre de
**±0,03 s au mètre**.

Ce bruit n'est pas lissé, après mesure. Sur un tour entier, **1 084 pas de
`Lap Dist` sur 1 122** sont déjà cohérents avec la vitesse au dixième près
(rapport moyen 1,0061, aucun pas nul) : l'irrégularité est locale à un virage
lent, pas générale. Lisser réduirait le bruit de 30 % mais décalerait la
position de plusieurs mètres. On perdrait plus qu'on ne gagnerait.

**À retenir en lisant la courbe :** une oscillation de quelques centièmes dans
un virage lent est du bruit, pas du pilotage. Un décrochage de plusieurs
dixièmes, lui, est réel.

### La limite de la comparaison par distance

Quand une voiture s'arrête, la distance n'avance plus alors que le temps
continue : le delta fait un **saut vertical**. Mesuré sur un cas réel à Spa,
un tour arrêté 5 s produit un saut de 6,4 s d'un mètre au suivant.

Ce n'est pas une erreur de calcul, c'est ce que la comparaison par distance ne
sait pas représenter. L'outil le dit explicitement, en tête de la comparaison,
dès qu'un des deux tours contient un quasi-arrêt.

---

## L'interface

### Pourquoi une interface web sans bibliothèque de graphiques

Le brief impose de fonctionner **hors ligne, sans dépendance à un service
extérieur**. Embarquer une bibliothèque de graphiques supposerait de la
télécharger et de la figer dans le dépôt.

Ça s'est révélé inutile : l'axe de distance ramène déjà chaque tour à
**5 780 points** (un par mètre), la performance n'est donc pas un enjeu. Les
graphiques sont écrits directement en canvas, en 350 lignes commentées, ce qui
supprime toute dépendance et donne la main sur la lisibilité — qui est la
priorité affichée du brief.

Le serveur utilise `http.server` de la bibliothèque standard, pas un cadriciel :
il sert une page et quatre routes JSON. Il n'écoute que sur `127.0.0.1`, rien
n'est exposé sur le réseau.

### La liste des sessions : ne charger que ce qu'on affiche

Les noms de fichiers suffisent à dresser la liste, et c'est instantané : circuit,
date et type se lisent dans le nom. Le nombre de tours et le meilleur chrono,
eux, obligent à **ouvrir** chaque fichier — une douzaine de secondes pour les 378
du disque, ce qui est insupportable à chaque ouverture.

Le navigateur ne demande donc l'analyse que des **10 sessions réellement
affichées**, et un bouton en charge 10 de plus. Le filtre « masquer les sessions
sans tour chronométré » tire quelques sessions supplémentaires en remplacement
des sessions vides, pour qu'il y ait toujours 10 lignes exploitables : sur les
données de test, il a fallu ouvrir 22 fichiers pour en afficher 10.

### L'exception : le tri par meilleur chrono

Ce compromis tient tant qu'on classe par date, qui se lit dans le nom du
fichier. Classer par **meilleur chrono** oblige au contraire à ouvrir tout le
lot filtré, puisque c'est justement l'information qui manque.

Trois choses rendent ça supportable :

* le tri s'applique au **circuit choisi**, pas aux 388 sessions du disque — une
  dizaine de secondes pour les 80 sessions de Monza, contre une minute pour
  tout ;
* le chargement se fait **par paquets de 25**, en réaffichant entre chaque : le
  classement se précise sous les yeux au lieu de figer l'écran. Une session
  dont le chrono est encore inconnu est mise en fin de liste, sinon elle
  sauterait en tête à chaque paquet et la liste danserait ;
* le cache du serveur fait tomber le deuxième passage à moins d'une seconde
  (mesuré : 9,9 s puis 1,0 s sur Monza).

Un changement de circuit ou de tri **annule** le chargement en cours : sans ça,
choisir un autre circuit laissait tourner des requêtes devenues inutiles, et
leurs réponses venaient réafficher une liste qui n'était plus la bonne.

Le serveur garde en cache les résumés déjà calculés, indexés par chemin, taille
et date de modification — une session réécrite par le jeu est donc recalculée.

### Ce que l'écran affiche

* **Delta cumulé**, en haut et en grand, coloré en rouge au-dessus de zéro et en
  vert en dessous.
* **Vitesse, frein, accélérateur, angle volant, rapport**, superposés, tour de
  référence en bleu et tour comparé en orange.
* **Curseur synchronisé** sur tous les graphiques, avec les valeurs chiffrées
  des deux tours et leur écart.
* **Carte du circuit**, tracée depuis les coordonnées GPS, avec la position du
  curseur et le tracé coloré selon la pente du delta — la même information que
  le graphique, posée sur le circuit.
* Le **tableau par virage** (étape 4), directement sous les graphiques.

L'axe du **rapport engagé** est gradué de 1 en 1. Une échelle « nice » classique
choisit un pas de 2, ce qui oblige à compter les interlignes pour distinguer la
3e de la 4e — sur une grandeur qui ne prend que des valeurs entières, ça n'a pas
de sens.

### La vue rapprochée de la route

Le delta dit **combien** on perd ; la vue de la route dit **où l'on passe**. Elle
montre la portion de circuit autour du curseur, orientée dans le sens de marche,
avec les deux trajectoires et la position des deux voitures.

Elle repose sur trois canaux à 10 Hz, dont un dont la sémantique n'est
documentée nulle part et a dû être établie par la mesure :

* `GPS Latitude` / `Longitude` : la position de la voiture.
* `Path Lateral` : son écart à l'axe de la piste, en mètres, signé.
* `Track Edge` : **la position latérale du bord de piste du côté où se trouve la
  voiture**. Vérifié : au même endroit, deux tours passant du même côté donnent
  la même valeur à 9 mm près ; de côtés opposés, les valeurs diffèrent de
  10,5 m. Et le signe de `Track Edge` suit celui de `Path Lateral` dans 100 %
  des cas.

L'axe de la piste s'obtient en retirant l'écart latéral perpendiculairement au
sens de marche. La normale dépend de la direction de l'axe, qu'on ne connaît pas
encore : on part de la direction de la trajectoire, on en déduit un premier axe,
puis on recommence. Deux passes suffisent.

**Le contrôle est intégré à la méthode** : deux tours de trajectoires
différentes doivent retrouver le MÊME axe. Sur de vraies sessions, la dispersion
entre les axes déduits de chaque tour vaut 0,20 à 0,34 m. Sur le circuit de test
— un anneau de rayon connu — la reconstruction retrouve le rayon exact et une
dispersion de 0,3 mm.

**Ce qui est mesuré et ce qui est estimé.** Un tour ne renseigne qu'un bord,
celui de son côté ; sur une trajectoire de course on reste du même côté, si bien
que les deux bords ne sont connus que sur 10 à 30 % du tour. Ailleurs, le bord
manquant est **interpolé entre ses propres mesures**, prises avant et après.
L'interface trace chaque bord en trait plein là où il a été longé, en pointillé
ailleurs, et le dit sous la vue.

### Chaque bord suit ses propres mesures

Première version : le bord manquant était déduit de l'AUTRE, en reportant la
largeur de piste. Il copiait donc tous les accidents du bord longé. Signalé
sur l'épingle de Long Beach, où la vue montrait une encoche en dents de scie
en travers de la route. Données brutes au sommet :

```
distance   bord extérieur (mesuré)   bord intérieur (estimé)
2 807 m          −7,4 m                    +5,7 m
2 817 m         −12,2 m                    +0,9 m   <-- tiré vers la trajectoire
2 822 m         −12,9 m                    +0,3 m
2 827 m          −6,5 m                    +6,7 m
```

Le bord extérieur s'évase de 6 m au sommet — les deux tours donnent exactement
la même valeur, l'épingle a une large zone goudronnée. Personne ne longe
l'intérieur, qui se trouvait donc tiré de 6 m vers la trajectoire. Les deux
bords d'une route étant indépendants, chacun est désormais interpolé entre ses
propres mesures : l'intérieur reste à +7,3 m, et l'évasement réel de
l'extérieur reste affiché. Le tour étant une boucle, un trou qui chevauche la
ligne se comble entre la dernière mesure et la première.

Même défaut à l'affichage : un seul indicateur « mesuré » servait aux deux
bords, si bien que le bord extérieur de l'épingle, bel et bien longé,
s'affichait en pointillé. Chaque bord a maintenant le sien.

### Les mesures de bord aberrantes

`Track Edge` donne la limite de la surface roulable, qui s'ouvre parfois sur
autre chose que la piste. À la sortie de la même épingle, le bord droit passe
de 6,5 m à **21,9 m** sur une dizaine de mètres, puis revient : l'entrée de la
voie des stands. La route s'y dessinait sur 28 m de large.

Une mesure à plus de **2,5 fois la demi-largeur typique** du circuit est donc
écartée, et le bord interpolé à cet endroit. Le seuil est calé sur les neuf
tracés enregistrés : au-delà de 2,5 fois, on ne trouve que ce pic de Long Beach
(3,3 fois), soit 0,08 % de ses mesures, et rien ailleurs. Les vrais
élargissements restent en dessous — l'épingle s'évase à 1,9 fois.

Effet sur les sauts de bord de plus de 1,5 m d'un mètre au suivant :

| Tracé | avant | après |
|---|---:|---:|
| Long Beach | 34 | 14 |
| Fuji | 2 | 0 |
| Monza Curva Grande | 2 | 0 |

Les 14 qui restent à Long Beach tombent tous entre deux points réellement
mesurés : ce sont les murs du circuit urbain et leurs décrochements, tels que
le jeu les décrit.

### Un canal qu'il ne faut surtout pas interpoler

La première version dessinait un créneau rectangulaire dans le corridor à
chaque virage. La cause n'était pas la géométrie mais le rééchantillonnage :
**`Track Edge` est un signal discontinu, et je l'interpolais linéairement.**

Quand la voiture franchit l'axe de la piste, la valeur bascule d'un bord à
l'autre d'un seul échantillon au suivant. Vérifié sur un tour de Monza : elle
passe de −5,22 m à +4,78 m entre deux points consécutifs, et **aucun des 1 143
échantillons bruts ne vaut moins de 2 m en valeur absolue**. Les positions de
bord au milieu de la route que produisait l'interpolation — 26 fois par tour —
n'existaient tout simplement pas dans les données.

Ce canal est désormais rééchantillonné **au plus proche voisin**, aux deux
étapes : du brut vers la grille temporelle, puis de celle-ci vers l'axe de
distance. Effet mesuré sur la même comparaison :

| | Avant | Après |
|---|---:|---:|
| Positions de bord inventées | 26 par tour | **0** |
| Largeur minimale du corridor | 1,84 m | **8,67 m** |
| Saut du bord d'un mètre au suivant (p99) | 2,45 m | **0,25 m** |
| Saut maximal | 6,71 m | **1,89 m** |

La leçon vaut au-delà de ce canal : `donnees_tour.py` distingue maintenant
explicitement les canaux continus, interpolés, des canaux discontinus, pris au
plus proche voisin. Un test de non-régression fait traverser l'axe à un tour de
la session de test et vérifie qu'aucune valeur intermédiaire n'apparaît.

### Le zoom

Trois façons de zoomer : glisser pour encadrer une zone, molette, ou double-clic
pour tout remontrer. Un bouton « Voir le tour entier » fait la même chose et se
grise quand on y est déjà, et un bandeau indique en permanence la portion de
circuit affichée.

Trois défauts de la première version ont été corrigés après essai :

* **La molette recentrait la vue sur le curseur** au lieu d'y ancrer le point
  visé. Zoomer ailleurs qu'au milieu du graphique faisait donc sauter la vue à
  chaque cran. Le point sous le curseur reste maintenant sous le curseur —
  vérifié : il tient à 1 m près sur cinq crans consécutifs.
* **La position n'était pas bornée à la zone de tracé.** Les 62 px de marge de
  l'axe vertical donnaient une proportion négative, donc un zoom hors du tour.
* Accessoirement, dézoomer en butée de début ou de fin **rognait la fenêtre au
  lieu de la faire glisser** : la vue continuait de rétrécir alors qu'on
  demandait à l'élargir. La largeur est maintenant fixée d'abord, puis la
  fenêtre est glissée dans les bornes.

Seul le **signe** de `deltaY` est lu, jamais son amplitude : elle varie du tout
au tout entre une molette crantée et un pavé tactile.

### Décimation

Au-delà d'un point par pixel, chaque colonne affiche le **minimum et le maximum**
de la tranche plutôt qu'un point sur N. Prendre un point sur N ferait disparaître
les pics de freinage, qui sont précisément ce qu'on vient regarder.

---

## Une chose vérifiée en passant

Le graphique de l'accélérateur paraît saturé de traits verticaux. Vérification
faite, c'est fidèle : sur un tour de Monza, la pédale franchit **84 fois** le
seuil de 50 % contre 14 fois pour le frein, avec des chutes à 13 % en pleine
ligne droite. Ce sont les levés de pied aux changements de rapport. La pédale
est à fond 67 % du tour et au repos 15 %.

---

## Tests

55 tests, dont 52 sans le jeu.

La session de test a dû être corrigée à cette étape : sa distance avançait à
vitesse constante indépendamment du canal de vitesse, si bien qu'un arrêt de
deux secondes n'apparaissait pas dans le delta. `Lap Dist` y est désormais
l'intégrale de la vitesse, et les tours 1, 2 et 3 couvrent exactement la même
distance — le tour 3 met simplement 2 s de plus parce qu'il s'arrête.

Sont notamment couverts : un tour comparé à lui-même donne un delta nul partout ;
le delta part de zéro et finit sur la différence des chronos ; les bords du tour
ne sont pas figés ; le rapport engagé reste en escalier sans valeur
intermédiaire ; la somme des tronçons redonne le delta final ; deux circuits
différents sont refusés ; un tour avec arrêt déclenche l'avertissement.

Un test de bout en bout rejoue le contrôle chrono/delta sur les vraies sessions
du disque quand LMU est installé.

---

## Prochaine étape

**Étape 4 — tableau par virage** : découpage automatique du circuit en virages à
partir du freinage et de l'angle volant, puis les métriques du brief (point de
freinage, vitesse d'entrée, vitesse minimale et sa position, durée de freinage,
pression maximale, point de remise des gaz, vitesse de sortie, temps de
coasting), comparées ligne à ligne avec le tour de référence.

Le découpage produira un fichier de définition par circuit, éditable à la main,
comme validé au début du projet.
