# Étape 2 — Lecture d'une session et découpage en tours

**Statut : terminée.** Tous les seuils cités ici ont été calibrés sur les
435 tours chronométrés présents sur le disque, pas choisis à vue.

Prérequis : [01-decouverte.md](01-decouverte.md), qui décrit le format des
fichiers.

---

## Ce qui a été livré

| Module | Rôle | Connaît DuckDB ? |
|---|---|---|
| `lmu_telemetry/reader.py` | couche d'abstraction sur le format LMU | **oui, et lui seul** |
| `lmu_telemetry/session.py` | tours, chronos, validité | non |
| `lmu_telemetry/catalogue.py` | repérage des fichiers | non |
| `lmu_telemetry/errors.py` | erreurs explicites | non |
| `lmu_telemetry/cli.py` | ligne de commande | non |

La règle est stricte : si une mise à jour de LMU change la structure des
fichiers, seul `reader.py` doit être corrigé. C'est pour ça que `session.py` ne
manipule que des tableaux et des dataclasses, jamais du SQL.

Le garde-fou est la métadonnée `Version`. Si elle vaut autre chose que `"1"`,
l'outil refuse d'ouvrir le fichier et dit quoi faire, plutôt que de produire des
chiffres faux. Un test couvre ce cas.

---

## Trois choses que le jeu fait à notre place

### 1. Les frontières de tours

L'événement `Lap` donne l'instant exact de franchissement de la ligne et le
numéro du tour qui commence. Aucune détection à écrire.

### 2. Les chronos — attention au décalage

**Le chrono écrit à l'instant où commence le tour N est la durée du tour N−1.**

C'est le piège principal du format. Vérifié sur une course de 13 tours : le
chrono écrit au début du tour 2 vaut 111,859 s, et la durée mesurée du tour 1
entre deux événements `Lap` vaut 111,860 s.

Même décalage pour `Last Sector1` et `Last Sector2`, qui sont par ailleurs des
temps **cumulés** depuis la ligne, pas des durées de secteur. La durée du
secteur 2 s'obtient donc par `Last Sector2 − Last Sector1`, et celle du
secteur 3 par `chrono − Last Sector2`.

### 3. La validité

**Quand un tour est bouclé, hors des stands, mais que le jeu n'écrit aucun
chrono, c'est qu'il l'a invalidé** (limites de piste).

On prend ce verdict tel quel au lieu de recalculer les limites de piste
nous-mêmes. Contrôle de vraisemblance sur les 378 sessions : 71 % de ces tours
sans chrono contiennent des échantillons hors piste, contre 36 % des tours
validés. La corrélation est nette sans être totale — normal, LMU juge les
limites de piste sur les quatre roues à des endroits précis, pas sur un simple
contact avec l'herbe. Raison de plus pour ne pas essayer de le refaire.

Sur les 722 tours du disque : 433 chronométrés, 206 avec passage par les
stands, 83 invalidés par le jeu.

---

## Le contrôle d'intégrité : chrono contre durée mesurée

Deux chemins indépendants donnent le temps d'un tour : le chrono officiel écrit
par le jeu, et la différence entre deux événements `Lap`. Ils doivent coïncider.

C'est **le** test qui prouve que tout le reste est correct — recalage temporel
compris. La ligne de commande affiche les deux colonnes côte à côte pour que ce
contrôle reste visible.

Mesure sur les 435 tours chronométrés du disque :

```
médiane de l'écart : 0,0061 s
415 tours          : écart < 0,02 s
 20 tours          : écart de 55 à 132 s
```

La distribution est franchement bimodale, sans aucun cas intermédiaire. Et les
20 tours divergents sont **tous** des tours 0 de course : la voiture attend le
départ sur la grille, la fenêtre de télémétrie couvre l'attente alors que le
chrono ne compte qu'à partir du départ.

Ces tours sont donc marqués non comparables et écartés. Le seuil est fixé à
0,5 s — mais n'importe quelle valeur entre 0,05 s et 5 s isolerait exactement
les mêmes 20 tours. Il n'y a pas d'arbitraire ici.

### Pourquoi les deux colonnes ne sont jamais identiques au millième

Sur un tour normal, l'écart fait quelques centièmes — par exemple +0,010 s puis
−0,009 s sur deux tours consécutifs à Monza. Ce n'est pas une erreur de lecture,
et le sens du calcul l'exclut : les horodatages `Lap` tombent sur une grille de
2,5 ms, mais l'événement n'est **inscrit qu'au cycle de mise à jour suivant** le
franchissement réel, alors que le chrono du jeu est l'instant interpolé exact.

Chaque frontière de tour porte donc un retard, et la durée mesurée — différence
de deux frontières — porte la différence de deux retards.

Mesure sur les 415 tours cohérents :

```
écart signé : min -18,96 ms   max +18,75 ms
              moyenne +0,19 ms   écart-type 7,87 ms
```

Moyenne nulle et bornes symétriques à ±19 ms : c'est exactement la signature
d'une différence de deux retards tirés uniformément dans un même cycle. Un
cycle de 20 ms donne une loi triangulaire de bornes ±20 ms et d'écart-type
20/√6 = **8,2 ms**, contre 7,87 ms observés.

**Le chrono du jeu fait foi. La durée mesurée ne vaut qu'à ±0,02 s près**, et
c'est bien assez pour son rôle : détecter une divergence de plusieurs dizaines
de secondes. La ligne de commande l'affiche donc au centième, pas au millième —
l'afficher au millième laissait croire à une précision inexistante.

---

## Ce qui est signalé sans invalider

Un tour que le jeu a chronométré reste valide même s'il s'y est passé quelque
chose. L'outil le signale et laisse décider. C'est le principe « descriptif
avant prescriptif » du brief.

### Hors piste

`SurfaceTypes` donne la surface sous chaque roue à 5 Hz. Le codage n'est
documenté nulle part, il a été déterminé statistiquement en croisant chaque
valeur avec `Path Lateral`, l'écart à l'axe de la piste :

| Valeur | Occurrences | Écart médian à l'axe | Écart p90 | Interprétation |
|---:|---:|---:|---:|---|
| 0 | 310 599 | 2,73 m | 6,08 m | piste |
| 5 | 6 191 | 6,56 m | 8,99 m | vibreur |
| 6 | 3 011 | 5,02 m | 9,07 m | bordure |
| 2 | 2 973 | 10,75 m | 27,82 m | herbe |
| 4 | 1 600 | 22,48 m | 29,27 m | gravier |

L'ordre est sans ambiguïté : plus la valeur est « hors piste », plus la voiture
est loin de l'axe. Les valeurs 2, 3 et 4 sont donc comptées comme hors piste,
les vibreurs non.

### Chocs

`LastImpactMagnitude` bascule à `True` à chaque impact. La valeur présente à t0
est l'état initial et non un choc — elle est écartée.

Répartition sur les tours valides : 89 % sans aucun choc, 11 % avec au moins
un. Ce n'est donc pas du bruit de vibreur, c'est bien un signal utile.

### Quasi-arrêt en piste

Le brief demandait de détecter les tête-à-queue par un yaw rate anormal.
**Le yaw rate n'existe pas dans ces fichiers**, il n'est que dans la shared
memory.

J'ai tenté de le reconstruire à partir de la trajectoire GPS. **Ça ne marche
pas, et je l'ai mesuré avant de l'abandonner :**

* la position GPS est quantifiée à **0,42 m** et échantillonnée à 10 Hz ;
* l'indicateur obtenu corrèle à **0,11** avec la référence physique `a_lat / v`,
  quel que soit le lissage appliqué ;
* en virage il annonce 4,7 °/s là où la physique en donne 21,9 ;
* et il signalait des tête-à-queue imaginaires sur des tours parfaitement
  propres.

À la place, l'outil signale un fait mesurable et non ambigu : **la vitesse
minimale du tour**. Sur un tour normal c'est le virage le plus lent ; très bas,
c'est un incident.

Calibration sur les tours valides, par circuit :

| Circuit | Tours | v.min médiane | Tours sous 30 km/h |
|---|---:|---:|---:|
| Fuji | 162 | 57,7 km/h | 13,6 % |
| Spa | 88 | 54,4 km/h | 17,0 % |
| Monza | 81 | 68,7 km/h | 16,0 % |
| Portimão | 50 | 56,8 km/h | 12,0 % |
| Le Mans | 22 | 62,5 km/h | 18,2 % |
| Bahreïn | 16 | 56,1 km/h | 18,8 % |

Le virage le plus lent ne descend jamais sous 54 km/h en médiane. Un seuil à
**30 km/h** sépare donc proprement le virage lent de l'incident, sur tous les
circuits.

Contrôle fait au passage : sur un tour contenant un arrêt de 6,8 s, le chrono
du jeu et la durée mesurée continuaient de coïncider à 0,01 s près, et
`Lap Dist` restait figé pendant l'arrêt. Le recalage temporel tient donc même
quand la voiture est immobile — ce n'est pas une pause du jeu.

L'outil dit « quasi-arrêt en piste », pas « tête-à-queue » : la cause peut être
un tête-à-queue, une sortie, un abandon de tour ou du trafic en course, et la
télémétrie ne permet pas de trancher.

---

## Tests

33 tests, dont 31 **sans avoir besoin du jeu**.

La session de test est fabriquée par `tests/fixtures/construire.py`. Elle
reproduit exactement la structure d'un fichier LMU — canaux sans horodatage,
événements horodatés, colonnes `value1..value4` par roue — avec un scénario aux
résultats connus d'avance :

| Tour | Contenu | Attendu |
|---|---|---|
| 0 | sortie des stands | écarté, remarque « stands » |
| 1 | propre, 90,000 s, secteurs 30/30/30 | valide, meilleur tour |
| 2 | bouclé mais sans chrono | écarté, « invalidé par le jeu » |
| 3 | 90,000 s, 1 s hors piste, 2 chocs, 2 s à l'arrêt | valide, trois remarques |
| 4 | non bouclé | écarté, « fin de session » |

Sont notamment couverts : le décalage d'un tour des chronos, le recalage
`t = t0 + indice / fréquence`, la remise à zéro de `Lap Dist` aux
franchissements, le refus d'une version de schéma inconnue, le fichier
verrouillé par le jeu (reproduit avec un vrai second processus, parce que dans
le même processus DuckDB renvoie une autre erreur), et le fait que la lecture ne
modifie pas le fichier.

Deux tests supplémentaires s'exécutent sur de vraies sessions quand LMU est
installé, et sont ignorés sinon : ils rejouent le contrôle de recalage et le
contrôle chrono/durée mesurée sur les 20 à 30 sessions les plus récentes.

---

## Écarts par rapport au brief, et pourquoi

| Prévu au brief | Ce qui a été fait |
|---|---|
| §4.3 détection du franchissement de ligne | inutile, le jeu fournit `Lap` |
| §4.3 détection des limites de piste | inutile, le jeu invalide lui-même |
| §4.3 détection de tête-à-queue par yaw rate | impossible : pas de yaw rate dans les fichiers, et le GPS est trop grossier pour le reconstruire (mesuré). Remplacé par la vitesse minimale du tour. |
| §4.1 daemon d'enregistrement | sans objet : le jeu enregistre déjà |

---

## Prochaine étape

**Étape 3 — comparaison de deux tours** : traces superposées et courbe de delta
cumulé, alignées par distance parcourue.

Point technique déjà identifié : `Lap Dist` n'est qu'à 10 Hz, soit un point tous
les 7 m à 250 km/h. Pour aligner deux tours proprement il faudra reconstruire la
distance à 100 Hz en intégrant `Ground Speed`, qui est à 100 Hz, et en la
recalant sur `Lap Dist` pour éviter la dérive.
