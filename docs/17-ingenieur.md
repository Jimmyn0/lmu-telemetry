# Étape 17 — L'ingénieur de course

**Statut : abandonné le 2026-11-10**, avec la lecture du jeu en direct dont il dépendait : l'idée
n'était pas assez aboutie, et il en existe d'autres en ligne. Retiré sans archive : son premier
commit (b6f2003) a été enlevé de l'historique de la branche v2, et la suite n'avait jamais été
commitée. La voix et Piper ne sont plus installés. Ce qui suit est le journal de ce qui avait été
fait.

---

Une voix radio qui annonce, pendant la course, ce qui compte pour le pilote. Il remplace les
conseils de pilotage affichés par-dessus le jeu (étapes 15 et 16), abandonnés après l'essai en
piste.

Tout ce qu'il sait vient de la mémoire partagée du jeu, lue cinq fois par seconde pour le
classement de tout le plateau. Ce que cette mémoire publie vraiment en course a été vérifié sur une
course contre l'IA : Monza, 38 voitures, 10 minutes, le 2026-11-09 (voir plus bas).

## Ce qu'il dit

| Annonce | Quand | Exemple |
|---|---|---|
| Départ | Tour de formation, puis drapeau vert (course seulement) | « Drapeau vert, drapeau vert ! » |
| Jaune | Un secteur passe au jaune et la voiture en cause est à moins de 1 500 m devant le pilote. S'il est plus loin, l'annonce attend qu'il s'en approche. | « Jaune secteur deux, voiture arrêtée à la sortie de Lesmo 2. » |
| Vert | Le jaune annoncé est levé, après au moins 3 s | « Secteur deux, c'est vert. » |
| Voiture plus rapide | Une voiture d'une catégorie plus rapide arrive à moins de 3 s derrière le pilote ; au plus une fois par tour pour chaque catégorie, dont les voitures arrivent en file | « Hypercar derrière, à trois secondes. » |
| Bilan du tour | À chaque passage sur la ligne : la place dans la catégorie si elle a changé, l'écart avec le rival devant et derrière (sous 30 s), leur tendance au-delà de 0,2 s | « Tu passes deuxième. Devant, un dixième. Derrière, deux secondes sept. » |
| Secteurs | Le pilote ou son rival finit un secteur ; rival à moins de 5 s devant ou 3 s derrière ; écart d'au moins 0,3 s ; aucun des deux tours passé aux stands | « Secteur deux, la voiture derrière est plus rapide de quatre dixièmes. » |
| Limites de piste | Le compteur du pilote avance | « Limites de piste à Lesmo 2. Un quart de point sur cinq. » |
| Tour invalidé | Le tour ne compte plus depuis 3 s (le jeu pardonne parfois une seconde après) | « Tour invalidé. » |
| Pénalité | Reçue, puis purgée | « Pénalité. Tu as une pénalité à purger. » |
| Temps restant | Course au temps : 30, 15, 10, 5, puis 2 minutes | « Plus que cinq minutes. » |
| Tours restants | Course au nombre de tours : 10, 5, 3, puis 2 tours | « Plus que cinq tours. » |
| Dernier tour | Le leader prendra le damier avant le prochain passage du pilote ; à défaut, quand le leader le prend | « Dernier tour ! » |
| Arrivée | Le pilote passe sous le damier | « Drapeau à damier ! Tu termines quatorzième. » |
| Énergie | L'énergie virtuelle (ou le carburant) ne suffira pas jusqu'à l'arrivée ; rappel tous les 3 tours | « Attention, énergie pour quatre tours seulement. Il reste onze tours. » |

Les rivaux sont ceux de la catégorie du pilote : en multiclasse, la voiture juste devant au général
est souvent d'une autre catégorie, et elle ne l'intéresse pas. Les places annoncées sont celles de
sa catégorie, sans le préciser : « Tu es quatorzième. »

Il ne parle que français : la voix retenue est française. Les nombres sont écrits en toutes lettres
(`phrases.py`) : « une seconde deux », jamais « 1,2 ».

## Comment il choisit quoi dire

Il dit une phrase à la fois, et une phrase prend deux à six secondes. Les annonces attendent leur
tour dans une file (`annonces.py`) :

* **Urgentes** (jaunes, départ, neutralisation) : dites dès que possible, même en plein freinage.
* **Importantes** (voiture plus rapide derrière, pénalité, dernier tour, arrivée, énergie), puis
  **normales** (écarts, secteurs, limites) : elles attendent que la pédale de frein soit relâchée
  (sous 5 %).
* Chaque annonce a une durée de vie (4 à 20 s) : passé ce délai, elle ne veut plus rien dire et
  disparaît sans être dite.
* Une annonce remplace celle du même genre qui attendait encore : seul le dernier écart compte.
* Un jaune levé avant d'avoir été annoncé ne l'est jamais, et son retour au vert non plus.
* Si le classement ne bouge plus pendant 2 s (pause, menu), la file est vidée.
* Le pilote n'entend pas parler de son propre jaune : la cause d'un jaune est la voiture la plus
  lente du secteur. Si c'est lui, l'ingénieur se tait.
* Le pilote coupe les familles d'annonces qu'il ne veut pas entendre (voir ci-dessous).

## Ses réglages

Dans l'onglet Ingénieur, sous ses boutons. Ils valent tout de suite, même en piste : l'interface
les enregistre, puis prévient l'ingénieur en marche, qui les relit (`reglages.py`).

* **Volume**, de 0 à 100 %. Le curseur suit l'oreille : le son est multiplié par le carré de sa
  position, pour que chaque cran s'entende autant. À 50 %, il est quatre fois plus faible
  (-12 dB). À 100 %, c'est le niveau d'origine, déjà saturé comme un émetteur poussé.
* **Bavardage**, trois niveaux tout prêts :

  | Niveau | Ce qu'il dit |
  |---|---|
  | Discret | Départ et neutralisation, jaunes, voitures plus rapides derrière, pénalités, dernier tour et arrivée, énergie |
  | Normal | Le Discret, plus les écarts à chaque tour, le temps ou les tours restants, les limites de piste et les tours invalidés |
  | Bavard (par défaut) | Tout, y compris les secteurs face aux rivaux : jusqu'à trois annonces par tour dans une bagarre |

* **Annonces** : les neuf familles, à cocher une par une. Un choix qui ne correspond à aucun
  niveau est « personnalisé ». Une famille coupée se tait aussitôt, même ce qui attendait d'être
  dit. Les tours restants d'une course au nombre de tours sont une annonce à part du bilan du
  tour : le pilote qui coupe les écarts les entend encore.

Ils sont rangés dans `reglages.json`, avec la langue et le dossier, sous la clé `ingenieur`. Une
famille ajoutée par une version suivante sera entendue tant qu'on ne l'a pas décochée. Le rejeu
d'une capture applique les mêmes réglages, et dit quelles familles sont coupées.

## Ce que la mémoire publie en course

Vérifié sur la course de sonde du 2026-11-09 (`sonde-course.bat`, détail dans
`docs/12-memoire-partagee.md`) :

* **Tout le plateau** : 38 voitures sur 38, chacune avec sa télémétrie, cinq fois par seconde.
* **Les écarts**, calculés par LMU dans la télémétrie du joueur, mis à jour cinq fois par seconde
  et comptés en négatif devant :
  * `mTimeGapPlaceAhead` et `mTimeGapPlaceBehind` donnent l'écart avec le rival de catégorie au
    classement, 0 en tête de la catégorie ;
  * `mTimeGapCarAhead` et `mTimeGapCarBehind` donnent l'écart avec la voiture la plus proche sur
    la piste, toutes catégories ;
  * `mTimeBehindNext` du classement est l'écart au général.
* **Les secteurs** de chaque voiture : publiés à la mise à jour même du passage de ligne (222
  passages sur 222), cumulés depuis la ligne comme partout dans le jeu. Le jeu numérote les secteurs
  1, 2, puis 0 pour le troisième.
* **Les jaunes** : `mSectorFlag[i]` porte le secteur i+1. Il vaut 11 quand la voie est libre et 1
  pour un jaune, qui dure tant qu'une voiture est lente : de 5 à 17 s pendant la course. Les
  valeurs 2 et 3 n'apparaissent qu'après le damier. Deux des trois jaunes venaient du pilote.
* **Les stands** : `mPitState` vaut 2 à l'entrée, 4 à l'arrêt, 5 à la sortie (l'en-tête annonce
  0 à 4). L'IA demande son arrêt (1) après l'arrivée.
* **Les limites de piste** : le compteur du pilote (`mTrackLimitsSteps`) avance par pas. Le
  scoring dit combien de pas font un point (4) et une pénalité (20).
* **Les pénalités** : seulement leur nombre, pas leur type (drive-through ou stop-and-go).
* **La fin d'une course au temps** : `mSessionTimeRemaining` devient négatif à l'échéance. La
  phase passe à 8 quand le leader passe la ligne ensuite. `mMaxLaps` vaut alors 2 147 483 647.
* **Le temps estimé du tour** (`mEstimatedLapTime`) est le même pour toutes les voitures : celui
  des plus rapides. Pour prévoir les passages d'une voiture, l'ingénieur prend son dernier tour, à
  défaut son meilleur.
* **L'énergie** : `mVirtualEnergy`, de 0 à 1, environ 4 % par tour en GT3 à Monza. `mFuelFraction`
  du classement reste figé pour le joueur : inutilisable.
* **Pas de drapeaux bleus** : `mFlag` est resté à 0 pour tout le monde, même pour un pilote pris
  d'un tour par les Hypercar. L'ingénieur s'en passe : l'écart en temps d'une voiture derrière le
  pilote, c'est la distance qui les sépare sur la piste, à la vitesse de cette voiture. Pour la
  voiture la plus proche, il diffère de 0,1 s en médiane de celui que calcule le jeu. Une catégorie
  est plus rapide quand son meilleur tour bat de plus de 1 % celui de la catégorie du pilote : à
  Monza, Hypercar 1:52,95, LMP2 1:56,17, GT3 1:59,27.
* **Pas de neutralisation** pendant la course : la phase 6 et `mYellowFlagState` restent à
  vérifier.

## La voix

**Tom** (`fr_FR-tom-medium`, dépôt `rhasspy/piper-voices`), choisi à l'écoute le 2026-11-09 parmi
trois voix d'homme. Les voix de Windows sonnaient trop robotiques. Au réglage d'origine, Tom parle
environ 15 % plus lentement que les autres : il est accéléré (`length_scale` 0,86).

* [Piper](http://github.com/OHF-voice/piper1-gpl) fait la synthèse sur la machine, sans réseau.
  Le modèle se charge en 3 à 4 s, une phrase se calcule en 0,15 à 0,4 s.
* La radio (`radio.py`) coupe sous 450 Hz et au-dessus de 2 900 Hz, sature légèrement, ajoute un
  souffle et le déclic du micro. Les filtres sont appliqués dans le domaine fréquentiel : même
  résultat qu'échantillon par échantillon, cent fois plus vite en Python.
* Le modèle pèse 63 Mo : il n'est ni dans le dépôt (`voix/` est ignoré par git) ni dans le .exe.
  On le cherche dans `%LOCALAPPDATA%\Telemetrie LMU\voix`, puis dans un dossier `voix` à côté du
  programme (`emplacements.dossiers_voix`). Sans lui, l'écran Ingénieur dit où le mettre.
* **Licence** : Piper est sous GPL-3.0. Le .exe ne l'embarque pas (`telemetrie-lmu.spec`) : le
  faire imposerait la GPL à l'exécutable qu'on partage, et le dépôt n'a pas encore de licence.
  C'est à trancher avant de livrer l'ingénieur dans le .exe, tout comme la voix elle-même : le
  jeu de données qui a servi à entraîner Tom est sous AGPL-3.0.

## Où est le code

```
ingenieur/
  course.py    l'état de la course à un instant, tiré des blocs bruts du jeu
  moteur.py    les règles : d'un instantané à l'autre, ce qui mérite d'être dit
  phrases.py   les phrases, les nombres en toutes lettres, les lieux
  annonces.py  la file : priorités, durées de vie, freinages ; les familles d'annonces
  reglages.py  le volume, le bavardage, les familles coupées
  radio.py     le son de la radio
  voix.py      Piper, et le haut-parleur qui parle dans son propre fil
  rejeu.py     rejouer une capture de la sonde
  service.py   le processus : lire le jeu à 20 Hz, juger, parler
  pilote.py    le côté interface : lancer, arrêter, relire ce qu'il a dit
```

Comme l'overlay avant lui, il tourne dans son propre processus, relancé par l'interface (`--ingenieur`
dans le .exe), et lui parle par une connexion locale. Si l'interface se ferme, il s'arrête. Le
moteur ne lit rien et ne dit rien lui-même : il reçoit des `Instantane` et rend des `Annonce`. Le
direct, le rejeu et les tests s'en servent de la même façon.

## Rejouer une course

```bash
.venv\Scripts\python.exe -m lmu_telemetry ingenieur --rejeu capture.bin --son ecoute.wav
```

Sur la course de sonde, il aurait dit ceci (temps de séance, formation comprise) :

```
0:08.0  Tour de formation. Chauffe bien les pneus.
1:08.0  Drapeau vert, drapeau vert !
2:02.4  Secteur un, la voiture devant te prend trois dixièmes.
2:07.2  Secteur un, tu prends une seconde un à la voiture derrière.
2:49.4  Secteur deux, tu reprends une seconde cinq à la voiture devant.
3:27.8  Tu es en tête. Derrière, neuf dixièmes.
3:31.6  Secteur trois, tu prends deux secondes six à la voiture derrière.
4:59.0  Secteur deux, la voiture derrière est plus rapide de quatre secondes un.
5:38.2  Secteur trois, tu reprends une seconde à la voiture devant.
5:43.4  Tu passes deuxième. Devant, un dixième. Derrière, deux secondes sept.
6:08.0  Plus que cinq minutes.
6:39.8  Tour invalidé.
6:41.8  Limites de piste à Lesmo 2. Un quart de point sur cinq.
9:08.0  Plus que deux minutes.
9:41.4  Tour invalidé.
9:48.8  Pénalité. Tu as une pénalité à purger.
11:18.4  Dernier tour !
11:20.4  Tu es quatorzième.
13:17.6  Drapeau à damier ! Tu termines quatorzième.
```

Le secteur deux perdu à 4:59 est celui de l'incident à Roggia. Les deux sorties du pilote, à Roggia
et à Ascari, ont allumé un jaune qui ne lui a pas été annoncé. Le troisième jaune (Naveen Rao à Lesmo 1) ne l'a
pas été non plus, à raison : le pilote venait de le dépasser, 34 m devant lui.

Une seconde course, le soir du même jour (Monza, 14 minutes, ingénieur allumé), a montré le trafic :
dernier des GT3, le pilote s'est fait prendre un tour par les onze Hypercar en une minute, puis par
les treize LMP2 en moins de deux. Annoncée pour chaque voiture, l'alerte revenait quinze fois. Une
fois par tour et par catégorie, elle se dit deux fois, 17 et 25 s avant le premier dépassement :

```
7:12.2  Hypercar derrière, à trois secondes.
9:37.0  LMP2 derrière, à trois secondes.
```

## Ce qui reste

* Changer les réglages en pleine course, pour vérifier qu'ils valent tout de suite.
* La neutralisation, jamais vue en course.
* Une voix anglaise.
* La livraison dans le .exe, avec la question de la licence.
