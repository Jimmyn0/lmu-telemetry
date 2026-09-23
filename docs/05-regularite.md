# Étape 5 — Page régularité

**Statut : terminée.** Dispersion des chronos, tour idéal, constance par virage,
classement des virages les moins réguliers, et évolution au fil de la session.

Prérequis : [04-virages.md](04-virages.md). Le découpage du circuit et le pavage
du tour y sont définis ; cette étape ne fait que les appliquer à tous les tours
d'une session au lieu de deux.

---

## Sur quoi classer les virages

Le brief demande l'écart-type du point de freinage et celui de la vitesse
minimale, puis un classement des virages « où tu es le moins constant ». Mais on
ne peut pas classer avec ces deux-là : **l'un est en mètres, l'autre en km/h**,
et rien ne dit que 5 m de dispersion au freinage pèsent plus ou moins que 3 km/h
en vitesse de passage.

Le classement se fait donc sur une troisième mesure, en **secondes** : la
dispersion du temps mis à parcourir la portion de piste qui revient au virage.
Elle est comparable d'un virage à l'autre, se lit sans conversion, et répond
directement à la question — c'est du temps.

Les deux écarts-types du brief restent affichés. Ils disent *comment* on est
irrégulier ; la dispersion en secondes dit *combien ça coûte*.

---

## Pourquoi pas l'écart-type

Un écart-type se laisse détruire par un seul mauvais tour. Cas réel, virage 9 à
Spa, temps de passage sur neuf tours de course :

```
13,71   13,64   29,09   14,26   13,68   13,82   13,62   13,55   14,57
```

Un tour à 29 s au lieu de 13,7 : un incident. L'écart-type vaut alors **5,09 s**
et place ce virage **en tête** du classement — alors que sur les huit autres
tours, ce pilote y est parmi les plus réguliers du circuit. Suivre ce classement
enverrait travailler le mauvais virage.

Le classement se fait donc sur l'**écart absolu médian**, remis à l'échelle d'un
écart-type par le facteur 1,4826. Il ignore un passage isolé et retient ce qui se
répète :

| Mesure | Cinq premiers du classement |
|---|---|
| Écart-type | 9, 5, 1, 18, 8 |
| **Écart absolu médian** | **5, 18, 7, 10, 1** |

Le virage 9 disparaît du haut du classement, à juste titre. Il n'est pas caché
pour autant : la ligne porte la mention « un passage isolé pèse lourd (tour 3) —
incident, pas irrégularité ». Perdre quinze secondes une fois mérite d'être su,
simplement ce n'est pas un problème de régularité.

### Le garde-fou sur le nombre de tours

Cette mention a d'abord été affichée sans condition, et elle est apparue sur
**quatre virages sur huit** d'une session de trois tours à Monza, où il n'y avait
pourtant aucun incident.

C'est arithmétique. Avec trois passages, les écarts à la médiane sont
`|a−b|`, `0` et `|c−b|` : leur médiane vaut donc la plus petite des deux. Il
suffit que deux temps se ressemblent pour que la mesure robuste devienne
minuscule et que le seuil se déclenche.

La mention exige désormais **au moins cinq passages**. En dessous, l'outil
affiche les dispersions mais prévient en tête de page qu'elles sont indicatives.

---

## Le tour idéal

Chaque portion du circuit est parcourue plusieurs fois dans une session. En
prenant le meilleur passage de chacune, on obtient le tour qu'on aurait signé en
enchaînant ses propres meilleurs moments — sans rien améliorer, juste en étant
régulier.

C'est possible parce que les portions **pavent le tour entier** (voir
[04-virages.md](04-virages.md)) : leur somme est donc bien un temps au tour.

Deux propriétés vérifiées par les tests :

* la somme des temps moyens par virage vaut le chrono moyen de la session ;
* le tour idéal ne peut pas être plus lent que le meilleur tour réel.

Sur une course de neuf tours à Spa : meilleur tour 2:25.736, tour idéal
2:24.158, soit **1,578 s déjà à portée** — pas une projection, du temps déjà
réalisé, mais jamais dans le même tour.

---

## Ce que la page affiche

* **Bandeau** : nombre de tours valides, meilleur, médian et son écart au
  meilleur, écart-type, tour idéal et la marge qu'il représente.
* **Graphique des chronos** : un point par tour, le meilleur en violet, et trois
  repères en pointillé — médian, meilleur, tour idéal. L'échelle part du tour
  idéal, sinon on ne verrait pas l'écart qu'il reste à combler.
* **Au fil de la session** : la pente des chronos en secondes par tour, et les
  médianes des deux moitiés de session.
* **Classement des virages**, du moins au plus constant, avec pour chacun le
  temps de passage habituel, la dispersion (barre proportionnelle), le temps à
  gagner en répétant son meilleur passage, et les deux écarts-types du brief.

Seuls les **tours valides** entrent dans les statistiques : les tours de stands,
les tours invalidés par le jeu et les tours non bouclés fausseraient toutes les
dispersions. Une session de course est signalée comme telle — trafic, stratégie
et drapeaux pèsent sur les chronos sans rien dire du pilotage.

### Ce que l'outil ne dit pas

La pente des chronos est décrite, jamais expliquée. Usure des pneus, baisse de
carburant et apprentissage s'y mélangent, et la télémétrie ne permet pas de les
démêler. La page l'écrit noir sur blanc plutôt que de laisser croire à une
interprétation.

---

## Tests

102 tests, dont 97 sans le jeu.

Les statistiques par virage sont testées sur des passages **construits à la
main** : c'est là qu'on peut vérifier au chiffre près qu'un tour raté ne fausse
pas le classement. Le test le plus important rejoue exactement le cas du
virage 9 à Spa et vérifie que l'écart-type place l'incident en tête tandis que
la mesure robuste ne le fait pas.

Sont aussi couverts : le tour idéal ne dépasse jamais le meilleur tour, la somme
des virages vaut le chrono moyen, la pente est bien négative sur une session qui
s'améliore, le potentiel reste insensible à un incident, et une session de moins
de trois tours valides est refusée avec un message qui dit quoi faire.

---

## Prochaine étape

**Étape 6 — finitions** : packaging, README pour quelqu'un qui n'est pas
développeur, et revue de la gestion d'erreurs — faite : voir
[10-distribution.md](10-distribution.md).
