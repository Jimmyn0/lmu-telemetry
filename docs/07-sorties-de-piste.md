# Sorties de piste et sens des virages

**Statut : terminé.** Deux travaux enchaînés, partis d'une question simple —
« peut-on répertorier les chicanes, ou se fier à la numérotation officielle ? »
— dont la réponse a été : le problème était ailleurs.

La suite, elle, a bien répondu à la question : voir
[08-numerotation.md](08-numerotation.md).

Complété en novembre 2026 : les demi-tours et les dégagements bitumés, que le
jeu ne signale pas, sont écartés à leur tour (voir la dernière section).

Prérequis : [04-virages.md](04-virages.md).

---

## Le symptôme

Le test qui vérifie que deux sessions du même circuit se découpent pareil s'est
mis à échouer : **Monza donnait 8 virages dans une session et 7 dans une
autre**. Il ne s'agissait pas d'une régression — l'échec est apparu tout seul,
quand de nouvelles sessions sont entrées dans la fenêtre des trente plus
récentes que ce test examine.

Deux explications semblaient plausibles, et toutes deux étaient fausses :

* **un seuil de fusion mal réglé**, qui séparerait ou souderait la première
  chicane selon la trajectoire ;
* **une chicane mal comprise**, qu'il faudrait traiter à part.

---

## La vraie cause

Les axes de piste reconstruits par les deux sessions ont été comparés point par
point. Ils coïncident remarquablement bien — **écart médian 0,31 m, 95ᵉ centile
0,41 m** — sauf sur vingt mètres :

```
1020 m : écart  0,28 m
1040 m : écart  8,35 m      <-- une largeur de piste entière
1060 m : écart  6,77 m
1080 m : écart  0,30 m
```

En remontant à la source : dans la session qui trouvait 7 virages, **un tour
sur quatre a un `Path Lateral` qui descend à −31,4 m** entre 1010 et 1090 m. La
piste fait 10 m de large. Ce tour-là est parti dans le dégagement à la sortie
de la chicane.

L'axe étant la moyenne de ce que chaque tour en déduit, ce seul tour tirait
l'axe commun de plus de 8 m sur une vingtaine de mètres. La courbure calculée
dessus partait alors dans tous les sens — le cap tournait de 48° par mètre —,
ce qui fabriquait une inflexion inexistante entre la chicane et la courbe
suivante et les soudait en un seul virage.

Confirmation que ce n'était pas du bruit : le nombre de virages ne bougeait pas
avec le nombre de tours utilisés, de 2 à 10. Une moyenne ne dilue pas une
valeur fausse de 30 m.

### La correction

Les échantillons hors piste sont écartés de la reconstruction, tour par tour.
L'information existait déjà dans l'outil : `SurfaceTypes` donne la nature du
sol sous chaque roue, et `session.py` s'en sert depuis le début pour annoter
les tours. C'est seulement `piste.py` qui ne la consultait pas.

Deux détails qui ne se devinent pas :

* `SurfaceTypes` est un canal **par roue**, à 5 Hz, que le rééchantillonnage
  ordinaire refuse. Il faut d'abord le réduire à une valeur par instant, d'où
  le canal calculé `Hors Piste`.
* Le masque est **élargi de 11 m de chaque côté**. La direction de l'axe se
  calcule sur une base lissée : une position fausse contamine l'orientation
  bien au-delà d'elle-même.

### Une règle plus simple, essayée puis écartée

Être hors piste, c'est avoir `|Path Lateral| > |Track Edge|` — deux canaux déjà
chargés, aucun nouveau code. Mesuré sur 106 000 échantillons : cette règle
signale 3,2 % du temps contre 0,84 % pour `SurfaceTypes`, soit une **précision
de 23 %**. Elle attrape en réalité les **vibreurs**, qui débordent du bord de
piste sans être hors piste. Rouler sur un vibreur est normal et ne déplace
l'axe que d'un mètre ou deux : l'exclure aurait retiré de la donnée saine.

### Résultat

| | avant | après |
|---|---|---|
| Écart maximal entre les deux axes | 10,38 m | **0,75 m** |
| Écart dans la zone litigieuse | 8,35 m | 0,46 m |
| Virages détectés à Monza | 8 et 7 | **8 et 8** |

Un test de non-régression rejoue exactement le cas : on fausse `Path Lateral`
sur une portion d'un tour, on vérifie que l'axe est bien abîmé de plusieurs
mètres sans le signalement, et qu'il revient à moins de 0,5 m avec.

---

## Le sens des virages, et les chicanes

`courbure()` renvoyait une valeur absolue : **le sens des virages était jeté**.
Il est désormais conservé.

La convention — positif à gauche — a été vérifiée sur des arcs construits à la
main, puis recoupée sur deux virages dont le sens ne fait aucun doute : la
Variante del Rettifilo sort en droite puis gauche, la Curva Grande est une
droite.

Contrôle sur des virages connus, à Monza : la Parabolica et les deux Lesmo
sortent bien en droite, et les trois chicanes changent bien de sens en leur
milieu.

Ce signe est ce qui a rendu possible l'étape suivante — découper les chicanes
en virages distincts et les numéroter, voir
[08-numerotation.md](08-numerotation.md). L'interface affiche ↰ ou ↱ à côté du
numéro du virage, dans le tableau de comparaison comme dans le classement de
régularité.

---

## Conséquence sur les fichiers de circuit

Les définitions déjà enregistrées dans `virages/` ont été produites avec
l'ancienne géométrie : elles ont été **régénérées**.

La régénération refuse de toucher à un fichier marqué `"automatique": false` ou
dont un virage porte un nom écrit à la main.

---

## Suite : les demi-tours et les dégagements bitumés

### Le symptôme

Après des courses à Spa, le 13/11/2026, le même test s'est remis à échouer, de
lui-même encore : **20 virages pour une course, 18 pour les qualifications**.
Pas une régression : l'échec se reproduit sur la version publiée d'avant.

### La cause

Les trois virages en trop tombaient en haut du Raidillon, entre 1 247 et
1 320 m — droite, gauche, droite, de 13 à 25 m de rayon, sur une portion
presque droite. Ils venaient de deux tours de la course, et d'eux seuls :

* au tour 3, la voiture part à droite jusqu'à **25,6 m de l'axe**, s'arrête
  quatre secondes, puis fait **demi-tour** en recoupant la piste : la distance
  du tour **recule de 20,7 m** ;
* au tour 4, même endroit : arrêt, demi-tour jusqu'à 16,8 m de l'autre côté,
  et la distance recule de 9,5 m.

Sous les quatre roues, du **bitume** : le dégagement du Raidillon est revêtu,
et `SurfaceTypes` le compte comme de la route. La règle des sorties de piste ne
voyait rien.

Le dommage vient du rééchantillonnage sur la distance, qui ne garde que les
instants où la voiture progresse. Sur la portion parcourue deux fois, la
position saute d'un coup de l'aller au retour — de 25,5 m à droite à 9,8 m à
gauche, en moins d'un mètre. La direction lissée n'est plus celle de la piste,
et l'axe déduit de ce tour s'écarte de **26 m**. Moyenné sur quatre tours, il
en reste plus de 6 : assez pour dessiner un zigzag.

Contre-épreuve : la même course, sur ses tours 1, 5, 6 et 7, donne 17 virages.
Ce n'étaient donc ni le trafic ni les trajectoires de course.

En cherchant d'autres sessions touchées, un cousin est apparu à Monza : un tour
coupe la première chicane tout droit par l'échappatoire, **bitumée** elle
aussi, jusqu'à **38 m de l'axe**. Pas de demi-tour cette fois, mais le même
angle mort de `SurfaceTypes`.

### La correction

Deux règles s'ajoutent à celle des sorties de piste, dans `piste.py` :

* **les demi-tours** — là où la distance d'un tour recule de plus d'un mètre,
  toute la portion qu'il a parcourue deux fois est écartée, avec 16,5 m de
  marge de chaque côté ;
* **les dégagements bitumés** — au-delà de 2,5 demi-largeurs de l'axe, la
  voiture n'est plus sur la piste, quel que soit le sol. C'est le seuil qui
  écartait déjà les bords de piste aberrants.

La seconde n'est pas la règle `|Path Lateral| > |Track Edge|` écartée plus
haut : à 12,5 m de l'axe d'une piste de 10 m, on est 7,5 m au-delà du bord,
bien après les vibreurs.

Pourquoi 16,5 m de marge autour d'un demi-tour, contre 11 m pour une sortie :
la position y saute, et la direction est lissée trois fois de suite — sur la
trajectoire, puis à chacune des deux passes sur l'axe —, sur 11 m à chaque
fois. Sur un demi-tour simulé, la marge d'une sortie laissait 0,67 m d'écart
juste après le point de demi-tour ; celle-ci en laisse 0,21.

Une autre piste a été mesurée, puis écartée : ne détecter les virages que sur
des tours sans quasi-arrêt. Elle jette des tours entiers, en prend d'autres à
la place, et dégrade 4 sessions pour 8 corrigées.

### Résultat

Mesuré sur les 162 sessions enregistrées qui ont deux tours valides, sur leurs
quatre premiers tours, comme le test :

| | avant | après |
|---|---:|---:|
| Sessions hors du nombre de virages habituel de leur tracé | 30 | **17** |
| … corrigées | — | 13 |
| … dégradées | — | **0** |

| Tracé | avant | après |
|---|---|---|
| Fuji | 12 ×25, 13, 14, 15 ×2, 16 ×2 | **12 ×31** |
| Spa | 17 ×18, 18 ×4, 19 ×2, 20 | 17 ×21, 18 ×4 |
| Long Beach | 12 ×8, 14 ×2 | **12 ×10** |
| Algarve | 14 ×11, 15 | **14 ×12** |
| Monza | 11 ×41, 12 ×12, 13 | 11 ×42, 12 ×11, 13 |

Les autres tracés ne bougent pas. 135 sessions donnent exactement le même
découpage qu'avant ; dans 14, des bornes se déplacent, de 1 à 4 m le plus
souvent. Les plus grands déplacements rapprochent le découpage de celui livré
avec l'outil : la chicane de Monza retombe sur 907–954 et 955–1007 m (livré :
907–954 et 954–1006).

Les deux règles écartent 0,12 % des échantillons de plus que les sorties de
piste, qui en écartent 0,42 %.

Les « 18 » de Spa qui restent sont un vrai coude, vers 5,4 km, qui tourne de 16
à 17° et passe le seuil de 15° selon la session : l'écart d'un virage que le
test tolère. Les « 12 » de Monza n'ont pas été examinés.

### Conséquence sur les fichiers de circuit

Aucune pour les tracés livrés avec l'outil, dont Spa. Un découpage détecté
avant la correction, sur une session à incident, reste tel quel : l'outil ne
le regénère jamais. Pour le refaire, supprimer le fichier du tracé dans
`virages/`.

---

## Tests

Le plus important est le test de non-régression décrit plus haut : on fausse
`Path Lateral` sur une portion d'un tour, on vérifie que l'axe est bien abîmé
de plusieurs mètres sans le signalement, et qu'il revient à moins de 0,5 m
avec. L'écart faussé est de 8 m depuis la suite : au-delà de 2,5 demi-largeurs,
la règle des dégagements écarterait la portion d'elle-même, et le test ne
vérifierait plus rien du signalement.

S'y ajoutent la convention de signe vérifiée sur des arcs construits à la main,
et la relecture d'un fichier de circuit écrit avant l'ajout du sens.

Pour la suite :

* un **demi-tour simulé** sur l'anneau de test — dérive à 11 m de l'axe, arrêt,
  demi-tour jusqu'à 9 m de l'autre côté, la distance reculant de 20 m —, avec
  position, écart latéral et bord cohérents comme dans un vrai fichier. Sans
  voir le recul, l'axe commun s'écarte de 6,3 m ; avec, de 0,21 m ;
* un **dégagement bitumé**, à 25 m au-delà de l'axe sans aucun signalement :
  l'axe commun ne bouge que de 0,07 m ;
* seule la portion parcourue deux fois est écartée : un arrêt sur place, ou une
  voiture qui recule de 50 cm avant de repartir, n'écarte rien.
