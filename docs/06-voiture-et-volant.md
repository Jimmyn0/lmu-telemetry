# Voiture, marque, drapeau, et volant en degrés

**Statut : terminé.** Trois ajouts demandés après l'étape 5, qui ont en commun
d'avoir obligé à aller chercher de la donnée là où on ne l'avait pas encore
cherchée.

---

## Le problème : le fichier de télémétrie ne dit pas quelle voiture

Le champ affiché jusqu'ici venait de `metadata.CarName`. Il vaut :

```
Manthey DK Engineering 2026 #91:WEC
```

C'est l'**engagement** — l'écurie, l'année, le numéro, le championnat. Pas la
voiture. Rien dans le `.duckdb` ne dit qu'il s'agit d'une Porsche : ni
`CarClass` (« GT3 »), ni le setup, ni aucun des 101 canaux.

### Où le modèle se trouve réellement

Le jeu écrit un second jeu de fichiers, sous `UserData\Log\Results\*.xml`, un
par session. Chaque pilote y a un bloc :

```xml
<VehName>Manthey DK Engineering 2026 #91:WEC</VehName>   <!-- = CarName -->
<CarType>Porsche 911 GT3 R LMGT3</CarType>
<CarClass>GT3</CarClass>
```

`VehName` est identique au `CarName` de la télémétrie. C'est la clé qui relie
les deux sources, et elle n'a demandé aucune supposition : sur les 414 fichiers
présents, **347 engagements distincts, et aucun ne correspond à deux modèles
différents**. Les 26 voitures pilotées sont toutes couvertes.

### Conséquence sur l'architecture

C'est une **deuxième source de données**. Le principe posé au départ — un seul
module connaît le format du jeu — devient donc : un module par source.

| Module | Source | Casse si… |
|---|---|---|
| `reader.py` | `.duckdb` de télémétrie | le format des canaux change |
| `resultats.py` | `.xml` de résultats | la structure XML change |

Aucun des deux ne dépend de l'autre. Le reste de l'outil ne parle qu'à eux.

### Ce que la lecture des XML doit tolérer

Vérifié sur les 414 fichiers :

* le bloc de session s'appelle `Practice1` (243 fichiers), `Race` (106) ou
  `Qualify` (64) — et rien ne garantit qu'il n'y en aura pas d'autres. On ne
  cherche donc pas ces noms : on prend tout enfant qui n'est pas une des
  26 balises d'en-tête connues ;
* **un fichier sur 414 est syntaxiquement invalide**, écriture interrompue en
  cours de route. Il est ignoré, les 413 autres sont lus.

Relire tout le dossier coûte 0,39 s. C'est assez peu pour ne rien stocker sur
disque, et assez pour ne pas le refaire à chaque page : l'index est gardé en
mémoire, avec une signature (nombre de fichiers, date du plus récent) qui le
fait reconstruire dès qu'une session s'ajoute.

### La marque

Elle se déduit du modèle. Le premier mot suffit pour 30 des 32 modèles présents
dans les fichiers du jeu ; deux ne se devinent pas :

* `Corvette C8.R GTE` — le premier mot est le modèle, pas le constructeur ;
* `Mercedes-AMG LMGT3` — c'est le nom de l'écurie de course.

Un modèle inconnu retombe sur son premier mot plutôt que sur rien : une voiture
ajoutée par une mise à jour s'affichera correctement sans toucher au code.

### Les logos : non

Les logos des constructeurs sont des marques déposées. Un dessin fait à la main
serait à la fois approximatif et douteux. L'outil affiche donc une **pastille
aux couleurs de la marque**, portant ses initiales.

Qui veut les vrais logos dépose ses propres fichiers dans un dossier `logos/`,
nommés d'après la marque telle qu'elle est affichée — `Porsche.png`,
`Aston Martin.svg`. Ils remplacent alors la pastille.

Le nom demandé par le navigateur n'est jamais transformé en chemin : on le
compare aux fichiers réellement présents dans le dossier. Un paramètre du genre
`../../secret` ne correspond alors à rien.

---

## Le drapeau du circuit

Contrairement au modèle de voiture, **le pays n'existe nulle part** dans les
fichiers du jeu. Trois pistes essayées :

* `TrackVenue` et `TrackEvent` ne donnent que des noms ;
* `TrackData` donne un chemin de fichier, sans pays ;
* les canaux `GPS Latitude` / `GPS Longitude` sont **factices**. Mesuré sur les
  neuf circuits enregistrés : tous ont pour centre 60,00° N et 0,00° E, à
  quelques millièmes de degré près. Ce n'est pas une position terrestre mais un
  repère local, centré sur un point arbitraire au nord de l'Écosse.

  Ça ne remet rien en cause : `piste.py` ne s'en sert que comme d'un repère
  plan pour reconstruire la géométrie de la route, ce qui reste parfaitement
  valable. Mais ils ne disent pas où se trouve le circuit.

La table circuit → pays est donc **écrite à la main**, ce qui est acceptable
ici et seulement ici : se tromper de drapeau n'a aucun effet sur une analyse.
Elle couvre les seize circuits installés avec le jeu, reconnaît par fragment de
nom plutôt que par égalité (« monza » restera dans le nom même s'il change), et
un circuit inconnu n'affiche simplement pas de drapeau. Le fichier
`circuits/pays.json` permet d'en ajouter sans toucher au code.

Les drapeaux sont dessinés en SVG dans la page. Pas d'emoji : Chrome sous
Windows affiche « IT » au lieu du drapeau italien. Pas d'image téléchargée non
plus — l'outil doit marcher sans connexion.

---

## L'angle volant en degrés

`Steering Pos` est en **pourcentage**, ce qui n'est comparable qu'à l'intérieur
d'une même voiture réglée pareil. 40 % valent 117° sur la Porsche 911 GT3 R et
67° sur l'Oreca 07.

Le débattement se trouve dans le setup que le jeu recopie dans le fichier de
télémétrie :

```json
"VM_STEER_LOCK": {"caption": "Wheel Range (Lock)", "stringValue": "584 (20.3) deg"}
```

Premier nombre : débattement total du volant, d'une butée à l'autre. Second :
angle des roues avant à fond de braquage.

> À noter : le brief excluait toute lecture des fichiers de setup du jeu. Ce
> n'en est pas un — c'est une copie que le jeu a lui-même écrite dans le
> fichier de télémétrie — et une seule valeur en est extraite, pour une
> conversion d'unité. Aucune recommandation de réglage n'en découle.

### La chaîne n'a pas de format stable

Trois écritures coexistent sur les 26 voitures :

```
584 (20.3) deg      la plus courante
524deg (18.5deg)    McLaren 720S
516 deg(19.7 )      BMW M4
```

On extrait donc les nombres sans rien supposer de la ponctuation, et on rejette
le résultat s'il sort des bornes plausibles. Mieux vaut afficher des
pourcentages que des degrés faux. Résultat : **388 sessions sur 388** lues sans
échec.

### Pourquoi 100 % = la moitié du débattement

C'est le point qui demandait une vérification, et le premier essai n'a pas
suffi.

**Ce qui n'a pas marché.** L'idée était de confronter l'angle déduit du
pourcentage à la physique : en virage stabilisé, `angle ≈ (empattement +
K·v²) × courbure`. Une régression devait rendre un empattement plausible. Elle
a rendu 3,0 à 5,9 m selon les voitures, contre 2,5 à 3,0 m en réalité —
correct en ordre de grandeur, mais avec un biais systématique. En remplaçant la
courbure dérivée du GPS par celle déduite de l'accélération latérale, la
dispersion a empiré (corrélations de 0,32 à 0,68).

La raison est simple : **un tour réel n'est presque jamais en virage
stabilisé**. Entrée, freinage dégressif, réaccélération — le modèle ne
s'applique qu'à une minorité des points. Cette méthode confirme que la relation
est *linéaire* (corrélation de 0,84 à 0,94 par tranche de vitesse), mais elle
ne peut pas en fixer l'échelle.

**Ce qui a marché.** Un test direct, sans modèle : `Steering Pos` **sature à
exactement 100,000 %** et ne dépasse jamais cette valeur. Mesuré sur les
388 sessions, dont **149 atteignent la butée**. Donc 100 % correspond au
braquage maximal d'un côté, soit la moitié du débattement annoncé :

```
angle au volant = pourcentage / 100 × débattement / 2
```

**Recoupement.** La démultiplication qui en découle vaut 14,4:1 sur la
911 GT3 R et 12,9:1 sur l'Oreca 07, et reste entre 12,3 et 15,9:1 sur les
26 voitures — exactement l'ordre de grandeur attendu. Si le premier nombre
avait été le braquage d'un seul côté, on obtiendrait le double, ce qui n'aurait
aucun sens.

### Ce qui est affiché

Le canal en pourcentage **reste disponible** : on ajoute un canal calculé, on
n'en remplace aucun. Le graphique et le tableau de lecture affichent des degrés
quand le débattement est connu, et retombent sur le pourcentage sinon.

---

## Ce qui n'a pas été fait

**La télémétrie des autres pilotes n'existe pas.** Le fichier de session ne
contient que la voiture du joueur : les autres ne sont, pour le moteur du jeu,
que des positions réseau. Ni leur vitesse, ni leur freinage, ni leur
trajectoire ne sont enregistrés nulle part. Aucun développement ne peut créer
cette donnée.

Ce qui existe, en revanche, ce sont leurs **temps** : les fichiers de résultats
donnent, pour chaque pilote, chaque tour avec ses trois secteurs et sa vitesse
de pointe — et 309 des sessions enregistrées comptent d'autres pilotes, jusqu'à
62 à la Sarthe. Une comparaison par secteurs était possible ; elle a été
écartée d'un commun accord, trois secteurs étant grossiers à côté du découpage
par virage déjà en place.

---

## Tests

51 tests ajoutés, tous exécutables **sans le jeu** : les XML de résultats sont
fabriqués par les tests eux-mêmes.

Sont couverts : la liaison engagement → modèle, l'indexation de pilotes qu'on
n'a jamais été, la tolérance à un fichier tronqué, l'invalidation de l'index
quand une session s'ajoute, les deux marques qui ne se devinent pas, la
déduction du dossier de résultats depuis celui de la télémétrie, les neuf
circuits roulés plus trois installés, le fichier de pays complémentaire, les
trois écritures du débattement, les réglages invraisemblables, et la conversion
elle-même — dont le fait que deux voitures au même pourcentage ne braquent pas
du même angle.

Un test touche aux vrais fichiers et se saute ailleurs : il vérifie que le
débattement reste lisible sur les sessions du disque. C'est lui qui préviendra
si une mise à jour du jeu change ce champ.
