# Étape 4 — Tableau par virage

**Statut : terminée.** Découpage automatique du circuit en virages, fichier de
définition modifiable à la main, et les huit métriques du brief comparées entre
deux tours.

Prérequis : [03-comparaison.md](03-comparaison.md), notamment la reconstruction
de la géométrie de la piste, sur laquelle repose tout ce qui suit.

---

## Deux méthodes essayées, deux méthodes écartées

Le brief proposait de détecter les virages par seuil d'accélération latérale ou
par angle volant. Les deux ont été implémentées et mesurées avant d'être
abandonnées.

**L'accélération latérale** n'est qu'à **10 Hz**. À 200 km/h, ça fait un point
tous les 5,5 m : trop grossier pour délimiter une entrée de virage.

**L'angle volant** est en **pourcentage de braquage**. Il dépend donc de la
démultiplication de la direction, c'est-à-dire de la voiture. Mesuré :

| Circuit | Session A | Session B | Verdict |
|---|---:|---:|---|
| Portimão | 11 virages | 12 virages | instable |
| Fuji | 8 | 9 | instable |
| Bahreïn | 4 | 5 | instable |
| Spa | 13 | 13 | centres à **584 m** les uns des autres |

Pire, sur une session de LMP2 à Monza, la détection manquait la première chicane
et prenait la Curva Grande à la place — un « virage » à 313 km/h.

---

## Ce qui marche : la courbure de la piste

On détecte sur la **courbure de l'axe de la piste**, reconstruit à l'étape 3.
C'est une propriété du **circuit** : elle ne dépend ni de la voiture, ni du
pilote, ni du tour. Un virage est une portion où le rayon descend sous 400 m.

À Monza, la détection retrouve exactement le circuit réel :

| # | Position | Rayon min | v. min | Virage réel |
|---:|---|---:|---:|---|
| 1 | 907–1007 m | 13 m | 50 km/h | Variante del Rettifilo |
| 2 | 1084–1156 m | 218 m | 136 km/h | sortie de chicane |
| 3 | 1292–1749 m | 191 m | 191 km/h | Curva Grande |
| 4 | 2124–2277 m | 19 m | 88 km/h | Variante della Roggia |
| 5 | 2486–2638 m | 56 m | 137 km/h | Lesmo 1 |
| 6 | 2841–2912 m | 33 m | 127 km/h | Lesmo 2 |
| 7 | 3918–4168 m | 34 m | 124 km/h | Variante Ascari |
| 8 | 5103–5488 m | 67 m | 133 km/h | Parabolica |

Et surtout, **c'est stable entre sessions et entre voitures** :

| Circuit | Session A | Session B | Écart des centres |
|---|---:|---:|---:|
| Monza | 8 virages | 8 | 7 m |
| Spa | 20 | 20 | 30 m |
| Portimão | 14 | 14 | 10 m |
| Bahreïn | 6 | 6 | 3 m |

Le seuil de 400 m de rayon retient la Curva Grande, qui se passe à fond mais
reste un virage qu'on peut mieux ou moins bien négocier. Un seuil plus serré la
ferait disparaître.

---

## Une définition par circuit, modifiable

Les virages sont détectés **une seule fois par circuit** et enregistrés dans
`virages/<Circuit>.json`. Deux raisons, dont une impérative :

1. **Comparer deux tours virage par virage n'a de sens que si les bornes sont
   les mêmes.** Redétecter à chaque tour donnerait des colonnes qui ne se
   correspondent pas d'un tour à l'autre.
2. Aucune détection automatique n'est parfaite. Fuji donne 8 ou 9 virages selon
   l'enchaînement retenu ; c'est au pilote de trancher.

Le fichier est du JSON lisible, avec un mode d'emploi à l'intérieur :

```json
{
  "circuit": "Autodromo Nazionale Monza",
  "longueur": 5779.8,
  "automatique": true,
  "virages": [
    { "numero": 1, "nom": "", "debut": 907.0, "fin": 1007.0, "rayon_min": 13.1 }
  ]
}
```

On peut y ajuster les bornes, nommer les virages (« Parabolica » plutôt que
« Virage 8 »), ou en supprimer. Une fois le fichier écrit, l'outil ne le
regénère jamais.

---

## Les huit métriques

Pour chaque virage et chaque tour, sur une zone d'analyse qui remonte jusqu'à
350 m en amont — sans jamais empiéter sur le virage précédent, sinon le même
freinage serait compté deux fois :

| Métrique | Définition retenue |
|---|---|
| Freinage avant | mètres entre la première pression sur le frein et l'entrée du virage |
| Vitesse d'entrée | vitesse à cet instant |
| Durée de frein | temps cumulé pédale enfoncée |
| Frein max | pic de pression |
| Vitesse mini | point le plus lent dans le virage, et sa position |
| Remise des gaz | distance où l'accélérateur repasse au-dessus de 15 %, **cherchée après le point le plus lent** — un coup de gaz en entrée de courbe n'est pas une remise des gaz |
| Vitesse de sortie | vitesse à la fin du virage |
| Sur l'erre | temps sans frein ni gaz : le « coasting » du brief |

### La colonne « temps perdu »

Elle répartit l'écart du tour sur les virages. Chaque mètre du tour compte pour
un virage et un seul, si bien que **la colonne totalise exactement l'écart
final** — vérifié à 0,0000 s près sur des comparaisons réelles. Une colonne qui
ne s'additionnerait pas serait trompeuse.

La frontière entre deux virages est posée au **milieu de la ligne droite** qui
les sépare. C'est une convention, et il faut la connaître : sur une longue ligne
droite, une bonne sortie continue de payer bien après le virage, et la seconde
moitié de ce gain revient au virage suivant. Aucun découpage ne peut faire
mieux, l'effet d'une sortie ne s'arrêtant pas à un endroit précis.

Une première version mesurait l'écart sur la seule zone d'analyse de chaque
virage, sans paver le tour. Résultat : la somme des colonnes ne faisait que
**63 %** de l'écart du tour à Monza, le reste tombant dans les longues lignes
droites laissées de côté. Le pavage a corrigé ça.

Ce que ça donne sur deux tours réels à Monza, pour 0,879 s d'écart :

```
virage 1  -0,253      virage 5  +0,045
virage 2  -0,006      virage 6  +0,746   <- Lesmo 2
virage 3  -0,030      virage 7  +0,062
virage 4  +0,190      virage 8  +0,125
                      somme     +0,879   = l'écart du tour
```

Un seul virage porte 85 % de l'écart du tour. C'est exactement le genre de
constat que le brief attend de l'outil : factuel, chiffré, et sans
interprétation.

### « Pris sans freiner »

Certains virages affichent un tiret dans toutes les colonnes de freinage. Ce
n'est pas une mesure manquante : le frein n'y est jamais touché.

À Monza, c'est le cas des virages 2 et 3. Vérifié sur un tour réel : pression
de frein maximale **0 %** dans les deux, et la vitesse ne fait qu'augmenter —
85 → 160 km/h dans le virage 2, 160 → 236 km/h dans le virage 3. Le premier est
la sortie de la première chicane, le second la Curva Grande, que la GT3 passe à
fond.

Ces virages portent donc une étiquette « sans freiner » dans la case du virage,
plutôt qu'une ligne de remarque en dessous : c'est une propriété du virage, pas
un incident, et une ligne à part se lisait comme un avertissement.

Un effet de bord à connaître : quand la voiture accélère d'un bout à l'autre du
virage, la « vitesse minimale » est celle de l'entrée.

### Ce que l'outil colore, et ce qu'il ne colore pas

L'écart avec le tour de référence est affiché sur chaque valeur. Il n'est coloré
en vert ou en rouge **que là où « mieux » a un sens** : une vitesse minimale ou
de sortie plus élevée est meilleure, du temps sur l'erre en moins est meilleur.

Le point de freinage, la vitesse d'entrée et la remise des gaz restent en gris.
**Freiner plus tard n'est pas meilleur en soi** — ça dépend entièrement de ce
qu'on fait ensuite. L'outil montre l'écart, il ne le juge pas.

---

## Un exemple réel

Deux tours consécutifs à Monza, GT3, 1:53.414 contre 1:54.326 :

```
virage  freinage  v.entrée  durée fr.  frein max  v.min  remise gaz  v.sortie  sur l'erre
     1     121 m       265      3.35 s       100%     50       975 m        85      2.48 s
     2         —         —      0.00 s         0%    136      1084 m       161      0.13 s
     4     136 m       250      2.60 s       100%     88      2174 m       135      2.30 s
     6      49 m       188      1.07 s        83%    127      2939 m       127      2.17 s
```

Deux choses sautent aux yeux, et aucune n'est une interprétation de l'outil :

* **8,1 s sur l'erre pour un tour de 114 s**, soit 7 % du temps sans frein ni
  gaz.
* Le virage 6, Lesmo 2, en concentre 2,2 s à lui seul. Sur l'autre tour, 1,5 s
  de moins au même endroit — et 9,1 km/h de plus en sortie.

Contrôle de vraisemblance sur le virage 1 : freiner de 265 à 50 km/h en 121 m
demande 2,2 g de décélération. C'est exactement ce qu'un GT3 avec appui produit
à cette vitesse.

---

## Tests

83 tests, dont 78 sans le jeu.

La session de test est un anneau de rayon connu où chaque tour freine une
seconde à fond, roule une seconde sur son erre, puis remet les gaz. Toutes les
valeurs attendues se calculent donc à la main, et la vérification tombe juste :

```
début du freinage : 1833,0 m   (attendu 1833,3)
durée du freinage :    1,01 s  (attendu 1,00)
vitesse minimale  :   60,0 km/h
remise des gaz    : 1892,0 m
temps sur l'erre  :    1,00 s  (attendu 1,00)
```

Sont notamment couverts : une courbure constante donne un seul virage dont le
rayon détecté est celui de l'anneau ; une courbe trop douce n'en donne aucun ;
un virage sans freinage est signalé ; **le freinage d'un virage n'est jamais
attribué au suivant** ; un fichier de définition édité dans le désordre est relu
trié ; un fichier corrompu dit quoi faire.

Un test de bout en bout vérifie sur les vraies sessions du disque que deux
sessions d'un même circuit donnent le même nombre de virages, aux mêmes
endroits à 60 m près.

---

## Où l'écart se creuse vraiment

Question posée en cours de route : l'écart entre deux tours se joue-t-il
uniquement dans les virages, leur entrée et leur sortie ? Mesuré, en comparant
la variation du delta à l'intérieur des zones de virage et en dehors :

| Circuit | Dans les virages | Sur les lignes droites |
|---|---:|---:|
| Spa | 99 % | 1 % |
| Portimão | 99 % | 1 % |
| Fuji | 98 % | 2 % |
| Le Mans | 97 % | 3 % |
| **Monza** | **87 %** | **13 %** |

La réponse est oui, très largement. Monza est le cas le moins net, et pour une
raison précise : c'est le circuit aux plus longues lignes droites. Une meilleure
vitesse de sortie continue d'y creuser l'écart pendant des centaines de mètres
après le virage. Le tronçon 3 000–3 200 m, en pleine ligne droite après le
Lesmo 2, portait encore 0,30 s à lui seul.

C'est pour cette raison que la colonne « temps perdu » pave tout le tour au lieu
de se limiter aux abords des virages : sinon le gain d'une bonne sortie
disparaîtrait du tableau.

## Prochaine étape

**Étape 5 — page régularité** : distribution des chronos sur une session,
écart-type du point de freinage et de la vitesse minimale par virage, et le
classement des virages où l'on est le moins constant.

Le tableau par virage fournit déjà toute la matière : il suffit de le calculer
sur tous les tours valides d'une session au lieu de deux, et d'en prendre la
dispersion.
