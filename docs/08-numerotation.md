# Numérotation des virages, un par apex

**Statut : terminé.** Chaque virage porte un numéro — T1, T2… — et les deux
moitiés d'une chicane comptent pour deux virages distincts, comme sur les
cartes officielles de circuit.

Prérequis : [07-sorties-de-piste.md](07-sorties-de-piste.md), qui a rendu le
signe de la courbure disponible.

---

## Pourquoi séparer les moitiés d'une chicane

L'étape précédente signalait les chicanes mais les gardait en un seul virage,
au motif qu'on les enchaîne d'un seul geste. C'est vrai pour le pilotage, faux
pour la lecture des données : dans un tableau, une chicane fondue en un virage
mélange le freinage de son entrée et la réaccélération de sa sortie. On ne peut
plus lire ni l'un ni l'autre.

C'est aussi ainsi que comptent les organisateurs : à Monza, la Variante del
Rettifilo est **T1 et T2**, la Variante della Roggia **T4 et T5**, la Variante
Ascari **T8, T9 et T10**.

---

## La numérotation officielle n'est pas dans le jeu

Vérifié avant de coder :

* les circuits sont livrés dans des archives `.mas` illisibles — pas de fichier
  AIW ni GDB accessible, contrairement à rFactor 2 ;
* une recherche binaire sur tout le dossier du jeu pour « Parabolica »,
  « Ascari », « Lesmo » et « Variante » ne donne **aucune occurrence**.

Le découpage reste donc **mesuré sur la piste**. La numérotation officielle
n'a servi qu'à une chose : de **référence pour régler les seuils**. Les
nombres de virages ont été relevés sur Wikipédia — Monza 11, Spa 19, Portimão
15, Fuji 16, la Sarthe 38.

---

## Comment un virage est délimité

On découpe d'abord la piste en plages de courbure de sens constant — un
changement de sens sépare deux virages, c'est ce que le découpage par zone ne
voyait pas. Puis on alterne deux opérations jusqu'à ce que plus rien ne bouge :

* **recoller** deux plages voisines qui tournent dans le même sens ;
* **jeter** celles qui ne tournent pas assez pour être un virage.

Le recollage ne joue **jamais** entre deux sens opposés : deux moitiés de
chicane restent donc toujours distinctes, même collées l'une à l'autre. C'est
tout l'objet du découpage.

### L'angle, pas la longueur

Le critère est l'**angle balayé** — l'intégrale de la courbure — et non la
longueur de la portion. Un seuil en longueur se trompe des deux côtés :

* à Portimão, un virage de 14 m de rayon qui tourne de 90° ne mesure que 22 m,
  et se faisait jeter par un seuil à 20 m. Pire, une fois jeté, les deux
  virages qui l'encadraient — de même sens — se recollaient par-dessus lui : un
  virage de 395 m qui n'existe pas, et le circuit tombait de 15 virages à 8 ;
* à l'inverse, un coude de 400 m de rayon long de 30 m ne tourne que 4°, et
  passait pour un virage.

### Pourquoi alterner recollage et tri

Les deux ordres simples ratent chacun un cas réel, et c'est la revue du code
qui a mis le second au jour.

**Trier d'abord** — la première version. Elle empêchait bien un frémissement
de l'axe, à l'intérieur d'un virage serré, de le couper en morceaux : la
chicane de Monza donnait sinon quatre virages au lieu de deux sur une session
sur trois. Mais elle jetait aussi les morceaux d'un virage doux dont la
courbure oscille autour du seuil : à Long Beach, un virage de 21 à 23° à 62 m
de la ligne n'était détecté que dans une session sur trois, chacun de ses
fragments tombant sous les 15°.

**Recoller d'abord** — la bribe de sens opposé sépare le virage serré en deux
morceaux non voisins, impossibles à recoller. On retombe sur les quatre
virages de Monza.

**En alternant**, le recollage réunit les fragments du virage doux, et le tri
fait disparaître la bribe parasite — ce qui rend voisins les deux morceaux qui
l'encadraient, recollés au tour suivant. Mesuré sur trois sessions par tracé :

| Tracé | officiel | trier d'abord | en alternant |
|---|---|---|---|
| Monza | 11 | 11/11/11 | 11/11/11 |
| Monza Curva Grande | — | 9/9/9 | 9/9/9 |
| Spa | 19 | 18/17/17 | **17/17/17** |
| Fuji | 16 | 11/12/11 | **12/12/12** |
| Long Beach | — | 12/11/11 | **12/12/12** |
| Portimão | 15 | 15/14/14 | 15/14/14 |

Quatre tracés instables sur six avant, un seul après, et aucun n'a changé de
nombre de virages là où il était déjà stable.

---

## Le réglage du seuil, et ce qu'il coûte

Le seuil a été choisi sur deux critères, dans cet ordre.

**1. La stabilité.** Trois sessions du même circuit doivent donner le même
nombre de virages, sinon les tableaux ne se comparent plus d'une session à
l'autre.

**2. La justesse.** Ce nombre doit approcher le compte officiel.

Balayage de l'angle minimal, sur trois sessions par circuit :

| angle | circuits instables | écart moyen au compte officiel |
|---|---|---|
| 10° | 3 | 9 % |
| 12° | 3 | 9 % |
| **15°** | **2** | **9 %** |
| 20° | 2 | 10 % |
| 25° | 1 | 15 % |

À 15°, **Monza donne 11 virages sur les trois sessions** — exactement sa
numérotation officielle, chicanes séparées comprises. C'est le réglage retenu.

### Ce que ça donne circuit par circuit

| Circuit | officiel | détecté |
|---|---|---|
| Autodromo Nazionale Monza | 11 | **11** |
| Algarve International Circuit | 15 | 14–15 |
| Circuit de Spa-Francorchamps | 19 | 17 |
| Fuji Speedway | 16 | 12 |
| Circuit de la Sarthe | 38 | ~29 |

**Monza tombe juste. Les autres non, et il faut dire pourquoi.** Le compte
officiel d'un circuit est une convention, pas une mesure : il inclut des coudes
que 400 m de rayon et 15° d'angle ne retiennent pas. Fuji plafonne à 13 virages
quel que soit le réglage essayé — son 16 compte des inflexions de ligne droite.
La Sarthe compte 38 virages sur 13,6 km, dont plusieurs courbes des Hunaudières
qui ne tournent presque pas.

Aucun jeu de seuils ne rattrape ça sans fabriquer des virages ailleurs. Le
fichier `virages/<circuit>.json` reste modifiable à la main : c'est là qu'on
ajuste un circuit dont le découpage ne convient pas.

### L'instabilité résiduelle

Seul Portimão varie encore d'**un** virage selon la session utilisée pour la
première détection. Les sessions qui divergent sont celles qui n'ont que trois
tours valides : l'axe de la piste y est moins bien contraint, et détecter sur
plus de tours n'y change rien.

Sans conséquence à l'usage : le découpage est enregistré une fois par tracé,
puis réutilisé tel quel.

---

## L'affichage

* Les tableaux affichent **T1, T2…** au lieu de « Virage 1 ». Un nom écrit à la
  main dans le fichier du circuit vient en complément : « T3 — Curva Grande ».
  Aucun nom n'est posé automatiquement.
* Chaque virage porte une flèche indiquant son sens, ↰ ou ↱.
* **La carte du circuit porte les numéros**, dans une pastille posée à
  l'extérieur du tracé, reliée à son virage par un trait.

### Placer les numéros a demandé cinq corrections

**1. Calculer la courbure en mètres, pas en pixels.** Première version : la
dérivée seconde du tracé, en coordonnées écran. Elle marchait sur une carte de
mille pixels et pas sur celle de la page, qui en fait 207 : la flèche d'un
virage de 200 m de rayon vue sur 20 m ne mesure que 25 cm, soit un centième de
pixel une fois le circuit mis à l'échelle. Le calcul tombait sous le seuil de
bruit et le code se rabattait sur « un côté au hasard ».

La direction se déduit désormais de la **corde du virage** : un arc s'écarte
toujours de sa corde du côté opposé à son centre, et ce rapport ne dépend
d'aucune échelle.

**2. L'extérieur d'un virage n'est pas l'extérieur du circuit.** Dans une
chicane, les deux apex tournent en sens opposés : l'extérieur de l'un pointe
donc forcément vers l'intérieur de la boucle. Le circuit étant fermé, on le
traite comme un polygone et on teste l'appartenance par lancer de rayon. Une
pastille qui tomberait dedans passe de l'autre côté.

**3. Noter les emplacements plutôt que prendre le premier valable.** Aux
enchaînements serrés — les trois virages de la Variante Ascari tiennent en
250 m — aucun emplacement ne satisfait les trois conditions à la fois : hors du
circuit, à distance du tracé, sans recouvrir une pastille voisine. Douze
emplacements sont donc évalués et **noté**, l'appartenance au circuit pesant
plus que tout le reste réuni. Vérifié sur quatre circuits : **aucune pastille à
l'intérieur**, sur 11, 17, 15 et 29 virages.

Ces conditions se testent sur la position FINALE, jamais sur la première
proposée : un écartement destiné à éviter un chevauchement peut très bien
ramener la pastille dans la boucle.

**4. Empêcher les traits de rappel de se croiser.** Deux traits qui se coupent,
ce sont deux numéros échangés : on rattache chacun au mauvais virage. Un test
d'intersection de segments, et une pénalité. Vérifié : **zéro croisement** à
Monza comme à Spa.

**5. Ranger les numéros dans le sens de la marche.** Les deux moitiés d'une
chicane sont à trois pixels l'une de l'autre sur la carte : rien n'impose alors
l'ordre de leurs numéros, et on lisait « 2 » avant « 1 ». Les replacer ne
marche pas — remonter le second le ferait chevaucher un troisième — mais comme
les deux ancres sont quasiment confondues, les deux emplacements conviennent
aussi bien à l'un qu'à l'autre : **on échange les deux pastilles**.

**Le résultat est mis en cache.** Le placement coûte cher — appartenance au
polygone et distance au tracé, sur des milliers de points, pour douze
emplacements par virage — et la carte est redessinée à chaque mouvement de
souris sur un graphique. Sans cache, la Sarthe et ses 29 virages faisaient
ramer la page.

### Ce que ça donne

| Circuit | virages | dans le circuit | traits croisés | trait moyen |
|---|---|---|---|---|
| Monza | 11 | 0 | 0 | 19 px |
| Spa | 17 | 0 | 0 | 21 px |

Mesuré sur la carte à sa taille réelle dans la page, 207 pixels de côté — le
cas le plus défavorable. Les pastilles ne se recouvrent pas : 16 px entre les
deux plus proches, pour un diamètre de 16.

---

## Conséquence sur les fichiers de circuit

Les définitions enregistrées ont été **régénérées** : Monza passe de 8 à 11
virages, Spa de 20 à 17. Les anciennes numérotations ne valent plus.

---

## Ce qui a été retiré

Une table de noms usuels — Parabolica, Bus Stop, Chicane des Hunaudières —
avait été ajoutée à l'étape précédente. Elle a été **retirée** : la
numérotation la remplace, et ses positions, calées sur l'ancien découpage en
zones, ne correspondaient plus aux virages par apex.

Le champ `nom` reste lu dans le fichier du circuit, pour qui veut nommer ses
virages lui-même.

---

## Tests

20 tests, tous exécutables sans le jeu, sur des profils de courbure construits
à la main : c'est le seul moyen de vérifier une convention de signe ou un
seuil au chiffre près.

Sont couverts : gauche est positif et droite négatif, le rayon reste retrouvé
malgré le signe, une chicane donne bien deux virages, deux moitiés collées ne
se recollent jamais, une courbe qui se relâche en son milieu reste un seul
virage, deux virages de même sens bien séparés en font deux, un virage serré et
court est gardé, un coude long mais mou est écarté, et le seuil d'angle est
respecté à deux degrés près de part et d'autre.
