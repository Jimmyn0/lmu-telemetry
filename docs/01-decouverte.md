# Étape 1 — Découverte de la source de données

**Statut : terminée.** Tout ce qui suit a été vérifié en exécutant du code sur tes
fichiers, sur ta machine, le 2026-09-08. Rien n'est supposé.

---

## Le constat qui change le plan

Le brief prévoyait un daemon lisant la shared memory pendant que tu roules.
**Ce n'est pas nécessaire : LMU enregistre déjà ta télémétrie lui-même, sur disque.**

```
D:\SteamLibrary\steamapps\common\Le Mans Ultimate\UserData\Telemetry\
```

- **378 fichiers `.duckdb`**, un par session, 3,1 Go
- **35,8 heures de roulage** déjà enregistrées
- Nommage : `<Circuit>_<P|Q|R>_<date ISO>.duckdb`
- **377 fichiers sur 378 lus sans erreur** (le 378e est celui que le jeu écrivait
  pendant le test — voir « Limites » plus bas)

| Circuit | Sessions | Tours chronométrés | Meilleur (toutes voitures) |
|---|---:|---:|---|
| Spa-Francorchamps | 128 | 93 | 2:22.024 |
| Fuji | 103 | 166 | 1:44.087 |
| **Monza** | **71** | **79** | **1:32.963** |
| Le Mans (Sarthe) | 39 | 23 | 3:50.083 |
| Portimão | 25 | 53 | 1:48.147 |
| Bahreïn | 6 | 16 | 1:15.716 |
| Sebring | 3 | 0 | — |
| Interlagos | 1 | 1 | 1:42.637 |
| Losail | 1 | 0 | — |

Conséquence : **on peut développer et tester les étapes 3 à 6 tout de suite**, sur tes
vraies données, sans que tu aies besoin de rouler ni de lancer le jeu.
L'étape 2 « Enregistreur » du brief devient sans objet.

---

## Structure réelle d'un fichier

C'est une base DuckDB. Elle contient **trois formes de tables**, et cette distinction
est le point le plus important de toute la découverte.

### 1. Les tables descriptives

| Table | Contenu |
|---|---|
| `metadata` | paires clé/valeur : pilote, circuit, voiture, type de session, météo, date, et le setup complet en JSON |
| `channelsList` | les 58 canaux : nom, fréquence en Hz, unité |
| `eventsList` | les 40 événements : nom, unité |

Exemple de `metadata` réel :

```
Version           = 1
DriverName        = Jimmy Larbi
RecordingTime     = 2026-09-08T12_12_19Z
SessionTime       = 15:05:13
SessionType       = Practice
TrackName         = Autodromo Nazionale Monza
WeatherConditions = Clear
CarName           = Manthey Ema 2024 #91:LM
CarClass          = GT3
CarSetup          = <JSON de 38 391 caractères>
```

`Version = 1` est notre garde-fou : si une mise à jour de LMU change la structure,
cette valeur devrait bouger et l'outil pourra refuser proprement au lieu de sortir
n'importe quoi.

### 2. Les canaux — **sans horodatage**

Une table par canal, listée dans `channelsList`. Elle contient **uniquement une colonne
`value`**, une ligne par échantillon, dans l'ordre d'acquisition. Pas de colonne temps.

Les données par roue utilisent quatre colonnes `value1`…`value4` au lieu de `value`.

Le temps se reconstruit donc par calcul :

```
t(échantillon i) = t0 + i / fréquence
```

où `t0` est le `ts` du tout premier événement du fichier.

### 3. Les événements — horodatés, écrits au changement

Une table par événement, listée dans `eventsList`, avec une colonne `ts` (secondes,
DOUBLE) et une ou quatre colonnes de valeur. Une ligne est écrite **seulement quand la
valeur change**. D'où des tables très courtes : `Lap` fait 4 lignes pour 4 tours.

---

## Vérification du recalage temps

C'est l'hypothèse critique : les canaux n'ayant pas de temps, tout repose sur
`t = t0 + i / fréquence`. Test : à chaque début de tour donné par l'événement `Lap`,
le canal `Lap Dist` doit retomber à zéro.

```
t0 = 313.595 s   (ts du premier événement)
Lap Dist : 4151 échantillons à 10 Hz = 415,1 s, longueur max 5776 m (Monza ≈ 5793 m)

  tour 0   t=  0.00s   indice    0   Lap Dist =  108.7 m   (garage)
  tour 1   t=139.64s   indice 1396   Lap Dist = 5776.0 m   puis 2.0 m à l'indice suivant
  tour 2   t=254.47s   indice 2545   Lap Dist =    1.0 m
  tour 3   t=368.16s   indice 3682   Lap Dist =    0.0 m
```

**Recalage confirmé**, sans dérive sur 415 secondes. Contre-vérification indépendante :
la sortie des stands (`In Pits` 1→0, `Speed Limiter` True→False) tombe exactement là où
`Ground Speed` vaut 60,0 km/h — la vitesse du limiteur.

⚠️ **Réserve à retenir :** à la frontière d'un tour, l'indice calculé peut être décalé
d'**un échantillon** (0,1 s à 10 Hz), comme au tour 1 ci-dessus. Le code de segmentation
s'appuiera sur la remise à zéro réelle de `Lap Dist`, pas sur l'indice théorique.
Deuxième réserve : les canaux à basse fréquence ont un nombre d'échantillons légèrement
différent (`Ambient Temperature` à 1 Hz couvre 416 s là où les autres couvrent 415,1 s).
Il ne faut donc jamais supposer que deux canaux ont la même longueur.

---

## Les 58 canaux disponibles, confrontés au brief

### Présents et exploitables

| Besoin du brief (§4.2) | Canal réel | Fréquence | Unité |
|---|---|---:|---|
| Vitesse | `Ground Speed` | 100 Hz | **km/h** |
| Régime moteur | `Engine RPM` | 100 Hz | RPM |
| Rapport engagé | `Gear` *(événement)* | — | — |
| Accélérateur | `Throttle Pos` (+ `Unfiltered`) | 50 Hz | **%** |
| Frein | `Brake Pos` (+ `Unfiltered`) | 50 Hz | **%** |
| Embrayage | `Clutch Pos` (+ `Unfiltered`) | 50 Hz | % |
| Angle volant | `Steering Pos` (+ `Unfiltered`) | 100 Hz | **%** de braquage |
| Distance sur le tour | `Lap Dist` | 10 Hz | m |
| Distance totale | `Total Dist` | 10 Hz | m |
| Accél. long. / lat. | `G Force Long` / `Lat` / `Vert` | 10 Hz | G |
| Position sur le circuit | `GPS Latitude` / `Longitude` | 10 Hz | deg |
| Écart à l'axe / au bord | `Path Lateral`, `Track Edge` | 10 Hz | m |
| Type de surface | `SurfaceTypes` ×4 | 5 Hz | — |
| Temp. pneu int/centre/ext | `TyresTempLeft` / `Centre` / `Right` ×4 | 100 Hz | °C |
| Temp. carcasse / gomme / jante | `TyresCarcassTemp`, `TyresRubberTemp`, `TyresRimTemp` ×4 | 5–50 Hz | °C |
| Pression pneu | `TyresPressure` ×4 | 10 Hz | kPa |
| Usure pneu | `Tyres Wear` ×4 | 10 Hz | % |
| Temp. frein | `Brakes Temp` ×4 | 50 Hz | °C |
| Effort frein | `Brakes Force` ×4 | 50 Hz | % |
| Débattement suspension | `Susp Pos` ×4 | 100 Hz | m |
| Hauteurs de caisse | `FrontRideHeight`, `RearRideHeight`, `RideHeights` ×4 | 100 Hz | m |
| Carburant | `Fuel Level` | 20 Hz | L |
| Temp. air / piste | `Ambient` / `Track Temperature` | 1 Hz | °C |
| Répartiteur de frein | `Brake Bias Rear` *(événement)* | — | — |
| Vent, humidité | `Wind Speed/Heading`, `OffpathWetness` | 1 Hz | — |
| Retour de force | `FFB Output`, `Steering Shaft Torque` | 100 Hz | % / Nm |

Bonus non demandés mais utiles plus tard : `TC`, `ABS`, `ABSLevel`, `TCLevel`,
`TCSlipAngle`, `Wheel Speed` ×4 (100 Hz — permettra de mesurer le blocage de roue),
`Turbo Boost Pressure`, `Regen Rate`, `Virtual Energy`.

### Absents

| Besoin | Situation |
|---|---|
| **Yaw rate** | Absent. N'existe que dans la shared memory. Hors périmètre v1 de toute façon (§5 : pas de diagnostic sous/survirage). Approximable par dérivation du cap GPS si besoin en v2. |
| **Charge par roue** | Absente. `Susp Pos` et `Brakes Force` en sont des substituts partiels. |
| Position X/Y cartésienne | Absente, mais `GPS Latitude/Longitude` permet de tracer la carte. Coordonnées locales fictives (origine ≈ 60°N, 0°E) — sans importance, seule la forme compte. |

### Fréquences plus basses qu'espéré

- `G Force Lat/Long` à **10 Hz** seulement. C'est trop lent pour détecter les virages par
  seuil d'accélération latérale de façon fiable. → *Mise à jour de l'étape 4 : l'angle
  volant, envisagé comme solution de repli, s'est révélé tout aussi inutilisable — il est
  en pourcentage de braquage, donc dépendant de la voiture. Les virages sont finalement
  détectés sur la **courbure de la piste**, voir [04-virages.md](04-virages.md).*
- `Lap Dist` à **10 Hz** : à 250 km/h, ça fait un point tous les 7 mètres. Pour l'axe de
  distance des graphiques et l'alignement de deux tours, j'interpolerai `Lap Dist` à
  100 Hz en m'appuyant sur `Ground Speed` qui, lui, est à 100 Hz.

---

## Les 40 événements

Le jeu nous donne directement ce qu'on aurait dû calculer :

| Événement | Usage pour nous |
|---|---|
| `Lap` | **frontières de tours** — plus besoin de détecter le franchissement de ligne |
| `Lap Time`, `Best LapTime`, `Current LapTime` | chronos, vérifiables contre l'affichage du jeu |
| `Last/Best/Current Sector1`, `Sector2` | temps aux secteurs |
| `Current Sector` | secteur en cours |
| `Sector1/2/3 Flag` | drapeaux — utile pour la validité en course |
| `In Pits`, `Speed Limiter` | exclure stands et tours d'entrée/sortie |
| `Gear` | rapport engagé |
| `Brake Bias Rear`, `Brake Migration` | réglages de freinage |
| `ABS`, `TC`, `TCCut`, `ABSLevel`, `TCLevel` | déclenchements des aides |
| `LastImpactMagnitude`, `WheelsDetached` | **contacts** — validité de tour |
| `Yellow Flag State` | drapeaux jaunes |
| `TyresCompound` | composé monté |
| `Finish Status` | fin de session |

Un détail vérifié qui simplifie la validité des tours : **le jeu n'écrit pas de
`Lap Time` pour un tour non chronométré**. Dans la session Monza testée, 4 tours mais
seulement 2 chronos — le tour de garage et le tour de sortie des stands sont omis
d'office par le jeu.

---

## Limites et pièges identifiés

1. **Fichier verrouillé pendant que tu joues.** Le fichier de la session en cours est
   ouvert en écriture par `Le Mans Ultimate.exe` et illisible. Vérifié : le scan a
   échoué sur exactement ce fichier, LMU tournant en PID 9900 au moment du test.
   → L'outil détectera ce cas et affichera « cette session est en cours d'enregistrement,
   quitte LMU pour l'analyser », pas une stacktrace.

2. **Trois fichiers `.wal` orphelins** (Portimão 06/09, Monza 19/08, plus celui en cours).
   Un `.wal` est le journal d'écriture. S'il subsiste, c'est que le jeu n'a pas fermé
   proprement la base — plantage ou Alt+F4. Ces sessions sont partielles.
   → L'outil les signalera au lieu de les ignorer silencieusement.

3. **Beaucoup de sessions très courtes.** 71 sessions à Monza mais 79 tours chronométrés
   au total. Une session sur deux ne contient aucun tour chronométré. La liste d'accueil
   devra pouvoir masquer les sessions sans tour exploitable.

4. **Lecture sur place, comme tu l'as demandé.** Aucune copie n'est faite. Rappel du
   risque : un « Vérifier l'intégrité des fichiers » sur Steam, ou une grosse mise à jour,
   peut effacer ces 3,1 Go. Dis-le-moi quand tu veux, j'ajoute l'archivage.

5. **Les horodatages sont en UTC.** `RecordingTime` et le nom de fichier se
   terminent par un `Z` : `2026-09-08T12_12_19Z`. Une session roulée à 14 h 12
   en France est donc datée de 12 h 12 dans le fichier. L'outil convertit à
   l'heure locale pour l'affichage.

6. **Unités contre-intuitives.** `Ground Speed` est en **km/h** et non en m/s ;
   `Steering Pos` est en **%** de braquage et non en degrés (plage observée : −60 à +45 %).
   J'ai failli me tromper sur la vitesse : j'ai cru à des m/s jusqu'à ce que le limiteur
   de stand affiche exactement 60,0 — ce qui n'a de sens qu'en km/h. C'est précisément
   pourquoi on vérifie au lieu de supposer.

---

## Environnement vérifié sur ta machine

| Élément | Constat |
|---|---|
| LMU | `D:\SteamLibrary\steamapps\common\Le Mans Ultimate` |
| DuckDB du jeu | v1.4.0 (`duckdb.dll` à la racine) |
| DuckDB côté outil | module Python 1.5.5 — lit sans problème les fichiers écrits en 1.4.0 (377 fichiers vérifiés) |
| Python | 3.14.5, environnement virtuel dans `.venv` |
| « Enable external plugins » | déjà à `true` — aucune action requise de ta part |
| Plugin rF2 Shared Memory | déjà installé et activé (posé par CrewChief ou SimHub). Inutilisé en v1, disponible pour la v2. |
| Volant | Simagic Alpha EVO + volant GT Neo |

---

## Outils livrés à cette étape

| Fichier | Rôle |
|---|---|
| `tools/discover.py` | dump la structure réelle d'un fichier + contrôle de cohérence du recalage temps |
| `tools/inventory.py` | balaye tout le dossier, vérifie que chaque fichier est lisible, sort l'inventaire par circuit |
