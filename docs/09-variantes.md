# Les variantes de tracé

**Statut : terminé.** Un même circuit peut avoir plusieurs tracés dans LMU. Ils
sont désormais traités comme des circuits différents, dans la liste des
sessions comme dans le découpage en virages.

---

## Le défaut

Signalé par l'utilisateur : « dans LMU il y a plusieurs versions de certains
circuits, comme Monza et Monza version Curva Grande ». Vérification sur les
388 sessions enregistrées — trois circuits ont bien deux tracés :

| `TrackName` | `TrackLayout` | sessions | longueur |
|---|---|---|---|
| Autodromo Nazionale Monza | Autodromo Nazionale Monza | 33 | 5 780 m |
| Autodromo Nazionale Monza | **Monza Curva Grande Circuit** | **47** | 5 745 m |
| Bahrain International Circuit | Bahrain International Circuit | 3 | 5 383 m |
| Bahrain International Circuit | **Bahrain Outer Circuit** | 3 | 3 510 m |
| Circuit de la Sarthe | Circuit de la Sarthe | 38 | 13 621 m |
| Circuit de la Sarthe | **Circuit de la Sarthe Mulsanne** | 1 | 13 557 m |

Et ce n'était pas cosmétique. Détection sur chacun des deux Monza :

```
Autodromo Nazionale Monza   5 780 m   11 virages
Monza Curva Grande Circuit  5 745 m    9 virages
```

La variante **n'a pas la Variante del Rettifilo** : on entre directement dans la
Curva Grande. Ses T1 et T2 n'existent pas, et toute la numérotation est décalée.

Or le découpage était enregistré sous le `TrackName`. Les deux tracés
partageaient donc `virages/Autodromo Nazionale Monza.json`, et **47 sessions
étaient analysées avec le découpage de l'autre tracé** : virages placés au
mauvais endroit, temps par virage faux, classement de régularité faux.

C'est le genre de défaut qui ne se voit pas : les chiffres restent plausibles.

---

## La correction

Le tracé remplace le circuit partout où il s'agit d'identifier la piste :

* le **fichier de découpage** porte le nom du tracé — `virages/Monza Curva
  Grande Circuit.json` à côté de `virages/Autodromo Nazionale Monza.json` ;
* la **comparaison de deux tours** refuse deux tracés différents, avec un
  message qui prévient que deux variantes portent le même nom dans le jeu ;
* le **menu « comparé à »** ne propose que les sessions du même tracé ;
* la **page régularité** et l'**en-tête de session** affichent le tracé.

Les fichiers déjà enregistrés restent valides : pour un circuit sans variante,
`TrackLayout` est égal à `TrackName`.

---

## Le tracé n'est pas dans le nom du fichier

C'est ce qui rend l'affaire pénible. Le jeu nomme ses fichiers
`<TrackName>_<P|Q|R>_<date>.duckdb` : **les deux Monza s'appellent pareil sur le
disque**. Seule la table `metadata` distingue les tracés, et il faut ouvrir le
fichier pour la lire.

Or la liste des sessions est construite à partir des seuls noms de fichiers,
justement pour être instantanée (voir [03-comparaison.md](03-comparaison.md)).
Mesuré : ouvrir les 388 sessions pour n'y lire que `metadata` coûte **9,7 s**,
soit 25 ms par fichier — l'essentiel étant l'ouverture de la base, pas la
lecture.

Trois solutions ont été pesées :

1. **Tout ouvrir au démarrage** : 9,7 s d'attente avant d'afficher quoi que ce
   soit. Écarté.
2. **Déduire le tracé des fichiers de résultats**, 25 fois moins chers à lire
   (0,39 s pour les 414). Écarté aussi : il faudrait apparier chaque session à
   son fichier de résultats par recoupement d'horaires, et une erreur
   d'appariement donnerait le mauvais découpage. Trop risqué pour une clé dont
   dépend la justesse des chiffres.
3. **Lire en tâche de fond**, retenu.

Le serveur balaye les sessions dans un fil séparé dès la première demande, et
la page redemande toutes les 1,5 s jusqu'à ce que ce soit fini. La liste
s'affiche immédiatement d'après les noms de fichiers, et les variantes
apparaissent dans le menu au bout d'une dizaine de secondes. Un tracé pas
encore lu retombe sur le nom du circuit, ce qui est exact pour tous les
circuits sans variante.

---

## Deux défauts trouvés en chemin

**Un plantage sur les sessions vides.** Deux sessions de la variante Curva
Grande ont des tours « valides » dont la distance parcourue vaut −1 m. La
reconstruction de la géométrie s'y écrasait sur une erreur numpy
incompréhensible (`a cannot be empty`). Le découpage refuse maintenant un tour
de moins de 100 m avec un message qui dit quoi faire, et la dilatation du
masque hors piste gère les portions plus courtes que la dilatation elle-même.

**Une régression introduite par la correction.** Le menu « comparé à » filtrait
sur `x.circuit === s.circuit`. En passant l'écran de session au tracé sans
toucher à la liste, les deux ne parlaient plus de la même chose : le menu se
retrouvait vide, et l'interface demandait une session au chemin vide. Attrapée
en essayant le parcours complet sur la variante.

---

## Tests

Quatre tests dédiés, sur une copie de la session de test dont seul
`TrackLayout` est modifié : le tracé est bien distinct du circuit, le découpage
porte le tracé, deux tracés donnent deux fichiers de virages différents, et la
relecture conserve le tracé.

Un cinquième, dans les tests de comparaison, vérifie que deux variantes du même
circuit sont refusées — c'est le cas qui passait silencieusement.
