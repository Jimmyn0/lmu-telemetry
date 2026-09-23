# Sorties de piste et sens des virages

**Statut : terminé.** Deux travaux enchaînés, partis d'une question simple —
« peut-on répertorier les chicanes, ou se fier à la numérotation officielle ? »
— dont la réponse a été : le problème était ailleurs.

La suite, elle, a bien répondu à la question : voir
[08-numerotation.md](08-numerotation.md).

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
sur une portion d'un tour, on vérifie que l'axe est bien abîmé de plus de 5 m
sans le signalement, et qu'il revient à moins de 0,5 m avec.

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

## Tests

Le plus important est le test de non-régression décrit plus haut : on fausse
`Path Lateral` sur une portion d'un tour, on vérifie que l'axe est bien abîmé
de plus de 5 m sans le signalement, et qu'il revient à moins de 0,5 m avec.

S'y ajoutent la convention de signe vérifiée sur des arcs construits à la main,
et la relecture d'un fichier de circuit écrit avant l'ajout du sens.
