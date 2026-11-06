# Étape 15 — Le moteur de conseils

**Statut : moteur, détecteurs et rejeu terminés.** L'overlay viendra ensuite, et la référence
personnelle après lui. Fait le 2026-11-06, seuils calés sur Monza en GT3.

---

## Ce que fait le moteur

Il reçoit la voiture 50 fois par seconde et rend, à la fin de chaque virage, au plus un conseil.

```
sources/   mémoire du jeu, capture de la sonde, fichier .duckdb  → même flux d'Echantillon
coach/     suivi.py      où en est la voiture sur le tour
           zones.py      quels virages forment un seul passage
           passage.py    les dernières secondes, découpées une fois la zone franchie
           detecteurs.py ce qui se mesure, et ce qui dépasse les seuils
           roues.py      blocage et patinage
           moteur.py     l'ensemble, un échantillon à la fois
           rejeu.py      rejouer une session
```

Le moteur ne sait pas d'où viennent les échantillons : ce qui est vérifié sur un enregistrement
vaut pour la piste.

| Source | Roues | Vérification |
|---|---|---|
| Capture de la sonde | oui | Même conversion que le direct, jusqu'à l'octet |
| Fichier `.duckdb` | non | Sur 3 sessions : mêmes passages que la capture tant qu'elle dure, à 0,02 s près |
| Direct | oui | Une capture rejouée dans une vraie mémoire partagée, lue en même temps par `flux_direct` : 18 événements sur 18 identiques à la relecture de la capture |

Le direct n'a pas encore tourné avec le jeu lui-même.

Distance estimée entre deux mises à jour à 5 Hz, comparée au `Lap Dist` à 10 Hz du fichier : 5 mm
d'écart médian, 0,6 m au 99e centile. Le moteur coûte 3,6 µs par échantillon en moyenne et 9 ms au
pire, à la fin d'une zone.

## Les zones

Deux virages séparés de moins de 100 m n'en font qu'un : un conseil 3 s après la sortie tomberait
sinon dans le virage suivant. À Monza, ça donne sept zones :

| Zone | Virages |
|---|---|
| Rettifilo | T1-2 |
| Curva Grande | T3 |
| Roggia | T4-5 |
| Lesmo 1 | T6 |
| Lesmo 2 | T7 |
| Ascari | T8-10 |
| Parabolica | T11 |

Une zone va du début du freinage à la sortie plus 100 m, sans mordre sur ses voisines. Elle peut
déborder de la ligne : un freinage commencé à la fin d'un tour reste entier.

Les noms sont dans le fichier du circuit, livré avec l'outil. Un découpage déjà recopié chez
l'utilisateur les reçoit à la lecture, sans que son fichier soit réécrit.

## Ce qui n'est pas jugé

Le pilote n'y conduit pas comme d'habitude : stands, tour de sortie des stands, plus de 0,2 s hors
piste, choc, passage sous 30 km/h. Le trafic ne se voit pas dans les données : un lever de pied
derrière une voiture lente passe pour une faute.

## Les détecteurs

Chaque seuil vient de `tools/bilan_coach.py`. L'outil compare chaque passage à la médiane de la même
zone dans la même session : même voiture, même piste, même pilote. Sur 81 sessions et 1 965 passages
à Monza en GT3 :

| Conseil | Mesure | Seuil | Passages | Temps perdu | Sortie |
|---|---|---:|---:|---:|---:|
| Roue libre avant le frein | Temps sans pédale avant le freinage | 0,25 s | 2,8 % | +0,21 s | −0,8 km/h |
| Correction de volant | Retour à contresens, en % de braquage | 10 % | 2,6 % | +0,06 s | −0,3 km/h |
| Gaz hésitants | Recul pendant la remise des gaz | 40 points | 2,4 % | +0,10 s | −1,5 km/h |
| Frein brutal | Baisse de pédale en 0,1 s | 60 points | 4,0 % | 0 | 0 |
| Roue libre en virage | Temps sans pédale après le frein | 1,5 s | 1,6 % | 0 | −0,5 km/h |

Soit 0,74 conseil par tour, et aucun sur la plupart des tours. Les conseils sont donnés dans cet
ordre de priorité, précédés du blocage. Le patinage vient juste après la correction.

Sur les autres circuits, un passage au-dessus du seuil reste plus lent, mais l'écart varie : de 0,01
à 0,19 s pour la roue libre avant le frein. La roue libre en virage reste entre 0 et 0,07 s.

| Circuit | Sessions | Conseils par tour |
|---|---:|---:|
| Monza | 81 | 0,74 |
| Long Beach | 28 | 0,81 |
| Portimão | 34 | 1,84 |
| Spa | 60 | 2,64 |
| Le Mans | 60 | 3,58 |

Ces circuits sont moins roulés, et leurs sessions plus anciennes. Le frein brutal le montre : 60 % des
passages à Monza et 84 % au Mans en juillet, 1 % environ depuis septembre. Sur des sessions récentes,
il ne tombe presque plus.

### Deux conseils sans coût mesurable

**Le frein brutal et la roue libre en virage ne coûtent rien de visible sur ces tours.** Ils restent
parce que le brief les demande, mais passent en dernier.

La comparaison ne dit pas tout : elle oppose des tours du même pilote. S'il attend toujours 2 s à La
Source, elle ne peut pas montrer ce qu'il gagnerait à attendre 1 s. Ce sera le rôle de la référence.
En attendant, ce conseil tombe souvent dans les épingles : 61 % des passages à La Source. Si c'est
gênant, `roue_libre_virage` à 0 le désactive.

### Blocage et patinage

Ils ne se voient qu'avec les roues : en direct ou depuis une capture. Le rang et les seuils viennent
donc de trois sessions seulement. Sur ces captures : blocages en Hypercar, où ils étaient voulus, et
aucun en GT3, où le glissement tenu ne dépasse pas 5 % grâce à l'ABS.

## Ce que les données ont corrigé

* **Lever le pied n'est pas hésiter.** La première version comptait tout recul de l'accélérateur en
  sortie. À Spa, elle signalait 57 % des passages en T12-13 : un lever obligatoire, une fois le plein
  gaz atteint. Seul le recul pendant la remise des gaz compte désormais.
* **Une chicane se juge à sa sortie.** Le lever et l'attente entre ses deux moitiés font partie du
  geste. La roue libre et les gaz ne se mesurent que dans son dernier virage.
* **Une roue encore bloquée faussait l'étalonnage.** Après un tête-à-queue, aucune pédale n'agit et
  les roues restent arrêtées : la session entière semblait patiner de 20 %. Un rapport invraisemblable
  est maintenant ignoré.
* **Un freinage peut aller jusqu'au bout de la zone.** Cas réel au Mans, qui faisait planter le
  moteur. Les sessions du disque ont ensuite été rejouées sans la moindre exception : 576 sur 583,
  11 205 passages, les 7 autres n'ayant pas de découpage possible.

## Les seuils

Ils sont dans la section `coach` de `parametres.json`. Le fichier se complète seul au lancement, sans
toucher aux valeurs déjà réglées. Un seuil à 0 désactive son détecteur.

## Essayer

Les conseils qu'une session aurait donnés, sans le jeu :

```
.venv\Scripts\python.exe -m lmu_telemetry rejouer 5
```

Le numéro est celui de `sessions`. Le chemin d'un `.duckdb` ou le dossier d'une capture marchent
aussi. `--vitesse 1` rejoue au rythme de la session.

En direct, jeu lancé :

```
.venv\Scripts\python.exe -m lmu_telemetry direct
```

Recalculer les chiffres de cette page :

```
.venv\Scripts\python.exe -m tools.bilan_coach "Autodromo Nazionale Monza" --categorie GT3
```

## Ce qui reste à vérifier

| Point | Quand |
|---|---|
| Le direct avec le jeu lui-même | Dès que possible : `direct` en roulant |
| Le nom d'un tracé variante dans la mémoire, pour trouver le bon découpage | Étape Monza en conditions réelles |
| Les seuils hors GT3 : peu de tours valides en Hypercar et en LMP2 | Au fil des sessions, avec `bilan_coach` |
| Quand afficher le message, et comment ne pas se répéter | Overlay |
