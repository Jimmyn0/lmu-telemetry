# Étape 12 — La mémoire partagée, vérifiée sur le jeu en marche

**Statut : terminée, sauf les deux points listés à la fin.** Mesuré le 2026-11-06, jeu en
version 1.4200, sur deux sessions de 5 minutes à Monza : Mercedes-AMG LMGT3, puis Ferrari
499P. Outil : `tools/sonde_live.py`.

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

* `mTrackLimitsSteps` monte après une infraction, quelques secondes plus tard : de 0 à 9 à
  2 525 m en GT3, de 0 à 8 à 2 423 m en Hypercar, juste après la coupe de la Roggia. Il ne
  retombe pas à la ligne (constaté en Hypercar) : c'est sa montée pendant le tour qui compte,
  pas sa valeur. Vu une fois revenir à 0, aux stands.
* `mLastLapTime` vaut -1 à la ligne pour un tour non chronométré, comme l'absence de
  `Lap Time` dans le fichier.

## Autres pièges

* L'horloge repart de zéro à chaque session, et la mémoire garde l'ancienne voiture jusqu'au
  chargement. Le suivi en direct doit détecter ce retour en arrière.
* `mPhysicalSteeringWheelRange` et `mDeltaBest` sont toujours à 0. `mVisualSteeringWheelRange`
  vaut 719 sur les deux voitures : ce n'est pas leur débattement.
* `mTireLoad` et `mGripFract` sont remplis en Hypercar et à 0 en GT3 : aucun détecteur ne doit
  en dépendre.

## Ce qui reste à vérifier

1. **Un tour propre et chronométré.** Aucune des deux captures n'en contient : on n'a pas vu
   `mLastLapTime` positif en direct, ni `mTrackLimitsSteps` rester à 0 sur un tour entier.
2. **Le journal du jeu.** Il n'est lisible qu'à la fermeture du jeu. L'outil ne prend jamais le
   verrou et ne peut donc pas provoquer `Failed to acquire SharedMemoryLock` ; reste à constater
   l'absence de cette erreur sur ces sessions. SimHub tournait en même temps.
