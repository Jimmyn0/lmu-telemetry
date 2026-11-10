# Étape 12 — La mémoire partagée, vérifiée sur le jeu en marche

**Statut : abandonné le 2026-11-10**, avec l'ingénieur de course (étape 17) : la lecture du jeu
en direct est retirée de l'outil, sans archive (`memoire_lmu.py`, les flux et les sondes n'existent
plus). Les mesures ci-dessous restent valables. Mesuré le 2026-11-06, jeu en version 1.4200, sur
trois sessions de 5 minutes à Monza : Mercedes-AMG LMGT3, Ferrari 499P, puis Ferrari 296 LMGT3 Evo
pour un tour propre. Outil : `tools/sonde_live.py`. Les tableaux portent sur les deux premières.

---

## Quelle source

LMU publie sa propre mémoire, `LMU_Data`, documentée par les en-têtes de
`<jeu>\Support\SharedMemoryInterface`. Le plugin rF2 tiers n'est pas nécessaire. Les
en-têtes interdisent la redistribution : seuls les décalages utiles sont dans
`lmu_telemetry/memoire_lmu.py`.

| Mesure | GT3 | Hypercar |
|---|---:|---:|
| Taille de la vue | 327 680 octets (324 824 arrondis à la page) | idem |
| Télémétrie | 100 Hz | 100 Hz |
| `mLapDist` | 5 Hz | 5 Hz |
| Durée d'une lecture, médiane / p99 | 57 / 133 µs | 60 / 135 µs |
| Lectures déchirées | 9 sur 85 674 | 3 sur 59 284 |
| Blocs abandonnés | 0 | 0 |

La double copie suffit : aucune lecture n'a dû être abandonnée.

## Le direct et les fichiers du jeu disent la même chose

Comparé au `.duckdb` écrit pendant la même session : même horloge, décalage nul.

| Mémoire | Fichier | Conversion | Corrélation |
|---|---|---|---:|
| norme de `mLocalVel` | `Ground Speed` | × 3,6 | 1,0000 |
| `mUnfilteredThrottle` | `Throttle Pos Unfiltered` | × 100 | 1,0000 |
| `mUnfilteredBrake` | `Brake Pos Unfiltered` | × 100 | 1,0000 |
| `mFilteredSteering` | `Steering Pos` | × 100 | 1,0000 |
| `mFilteredThrottle` | `Throttle Pos` | × 100 | 0,98 à 0,997 |

Conséquence : un rejeu depuis un `.duckdb` nourrit les détecteurs avec les mêmes valeurs
que le direct, sauf pour les roues.

## `Wheel Speed` ne mesure pas la rotation des roues

C'est `mLongitudinalGroundVel` : la vitesse du sol sous la roue. Cas réel, Hypercar, roues
bloquées à t = 111,76 s :

| Source | AVG | AVD | ARG | ARD |
|---|---:|---:|---:|---:|
| `mRotation` × rayon (m/s) | 0,0 | 0,0 | 0,0 | 0,6 |
| `mLongitudinalGroundVel` | 40,0 | 40,0 | 40,0 | 40,0 |
| `Wheel Speed` du fichier | 40,0 | 40,0 | 40,0 | 40,0 |

**Le blocage et le patinage ne se détectent donc que sur `mRotation`**, en direct ou depuis
une capture de la sonde, jamais depuis un `.duckdb`.

Le rayon statique (`mStaticUndeflectedRadius`) n'est qu'approché : il faut le recaler roue
par roue, sur les moments sans pédale. Facteur mesuré : 1,00 à 1,03.

| Événements | GT3 (ABS actif sur 50 % du freinage) | Hypercar (sans ABS, blocages voulus) |
|---|---:|---:|
| Glissement > 25 % pendant ≥ 0,15 s, au frein | 0 | 10 |
| Glissement max au frein | 11 % | 100 % |
| Patinage > 20 % pendant ≥ 0,1 s | 4 | 6 |

Le patinage relevé est en première, TC actif. Une partie a lieu dans l'herbe : les
détecteurs doivent ignorer les passages hors piste.

## La distance se maintient entre deux mises à jour

Repartir de `mLapDist` et intégrer la vitesse donne, sur 0,2 s : 1 à 2 cm d'erreur médiane,
1,1 à 1,7 m au 99e centile. Ces deux sessions comptaient beaucoup de sorties de piste
volontaires.

Les pires écarts, 18 et 22 m, tombent tous les deux vers 2 172 m : la sortie de la chicane
Roggia, à l'endroit où elle a été coupée. `mLapDist` est une projection sur la piste, elle
saute donc en avant. L'estimation se recale à la mise à jour suivante.

## Savoir si un tour compte

`mLapInvalidated` n'a jamais bougé, y compris sur les tours que le jeu n'a pas chronométrés.
Trois autres champs le remplacent :

* **`mCountLapFlag`, le bon signal.** Il vaut 2 quand le tour compte, 1 sinon, et il change
  à l'instant de l'infraction : à 2 150, 2 158, 2 165 et 2 197 m (chicane Roggia), et à
  999 m (première chicane). Il vaut 1 pendant tout le tour de sortie des stands. Il repasse
  à 2 à la ligne. Le jeu peut aussi pardonner en cours de tour : deux cas où il est remonté
  à 2 après 2 et 9 secondes. Seule sa valeur à la ligne fait donc foi.
* **`mLastLapTime`** vaut -1 à la ligne pour un tour non chronométré. Pour le tour propre, il
  vaut 115,204, soit le chrono du fichier (115,2037), 0,03 s après la ligne.
* `mTrackLimitsSteps` compte les points de pénalité, pas les tours : de 0 à 9 à 2 525 m, de 0
  à 8 à 2 423 m, sans retomber à la ligne, et il ne bouge pas à chaque infraction (aucun
  changement sur la coupe à 2 150 m de la troisième session).

## Autres pièges

* L'horloge repart de zéro à chaque session, et la mémoire garde l'ancienne voiture jusqu'au
  chargement. Le suivi en direct doit détecter ce retour en arrière.
* `mLapDist` vaut un peu moins de zéro juste après la ligne : le suivi doit le tolérer.
* `mDeltaBest` reste à 0 tant qu'il n'y a pas de meilleur tour dans la session, puis se remplit.
* `mPhysicalSteeringWheelRange` est toujours à 0. `mVisualSteeringWheelRange` vaut 719 sur
  toutes les voitures : ce n'est pas leur débattement.
* `mTireLoad` et `mGripFract` sont remplis en Hypercar et à 0 en GT3 : aucun détecteur ne doit
  en dépendre.

## Le jeu n'est pas gêné

Le journal du jeu couvrant les trois sessions de mesure, soit 29 minutes, ne contient aucune
erreur `Failed to acquire SharedMemoryLock`, avec SimHub ouvert en même temps. La seule
occurrence relevée date de la veille, avant que cet outil existe.

## Les autres voitures, vérifiées en course

L'ingénieur de course a besoin de tout le plateau : places, écarts, temps par secteur, stands,
pénalités, drapeaux. Les trois premières sondes ont été faites seul en piste, avec une seule voiture
en mémoire.

La sonde relève maintenant le scoring de toutes les voitures, à chaque mise à jour, et en fait le
bilan dans `rapport.json`. `sonde-course.bat` la lance pour 15 minutes de roulage, le temps d'une
course contre l'IA.

Course de sonde du 2026-11-09 : Monza, 38 voitures (11 Hypercar, 13 LMP2, 14 GT3), 10 minutes au
temps, 4 019 mises à jour du classement. La mémoire publie les 38 voitures, chacune avec sa
télémétrie. Les écarts y sont mis à jour cinq fois par seconde, et les temps de secteur au passage
même de la ligne. Les drapeaux de secteur, les stands, les pénalités et l'arrivée de chacun sont
lisibles. Les conventions relevées (numéros de secteur, valeurs des drapeaux, états aux stands, écarts
calculés par LMU) sont dans `docs/17-ingenieur.md`.

Les décalages des nouveaux champs viennent des en-têtes. Recoupés sur une image prise le 2026-11-06 :
nom du pilote, voiture, catégorie, place, températures et temps restant y sont cohérents. Le temps
restant vaut bien la fin de session moins l'horloge. Un piège au passage : un pointeur de 8 octets suit
`mLapDist` dans le scoring, et tout ce qui vient après est décalé d'autant.
