# Étape 13 — Restructuration pour la v2

**Statut : terminée.** Rien ne change pour l'utilisateur, sauf les corrections listées ici.
Fait le 2026-11-06.

Contrôle : les réponses de l'API sur 10 vraies sessions (53 réponses) ont été enregistrées
avant, puis comparées champ par champ après. Toute différence est expliquée ci-dessous.

---

## Nouvelle organisation

| Dossier | Contenu | Règle |
|---|---|---|
| `sources/` | fichiers `.duckdb`, `.xml`, mémoire partagée | seuls modules à connaître les formats du jeu |
| `domaine/` | tours, virages, comparaison, régularité, circuits | aucune connaissance de l'interface |
| `web/` | `serveur.py` (HTTP), `reponses.py` (JSON), `statique/` | aucun calcul de pilotage |

`web/serveur.py` passe de 970 à environ 370 lignes. Le découpage d'un circuit et l'écart par
virage, enfermés dans le serveur, sont dans `domaine/` : le direct en aura besoin.

## Ce qui a été corrigé dans les mesures

**Le point de freinage.** On prenait le premier instant où la pédale dépassait le seuil dans
la zone. Deux erreurs en découlaient, vérifiées sur des tours réels :

* un frein enfoncé pour le virage SUIVANT passait pour le freinage de celui-ci. À Portimão,
  le T3 finit à 606 m et le freinage relevé était à 642 m. 47 mesures sur 10 sessions ;
* une pédale déjà enfoncée à l'entrée de la zone donnait le début de zone comme point de
  freinage. Le virage porte désormais la remarque « freinage commencé avant ce virage ».

On cherche maintenant une attaque de la pédale, avant le point le plus lent.

**La remise des gaz.** Elle était annoncée comme durable mais prenait le premier
franchissement du seuil. À Spa, le T16 donnait 6 635 m pour un coup de gaz de 26 % relâché
aussitôt. Il faut maintenant tenir 0,3 s.

**Le geste du pilote.** `Throttle Pos` porte les coupures automatiques du changement de
rapport et de l'antipatinage : 100, 0, 100 en sortie de T1 à Spa. La remise des gaz et le
temps sur l'erre lisent `Throttle Pos Unfiltered`. Le temps sur l'erre baisse donc de 3 % en
moyenne : ces coupures n'étaient pas de la roue libre.

## Les autres différences relevées

* **Daytona et Road Atlanta, au millième.** Le découpage détecté était gardé en mémoire sans
  l'arrondi du fichier : les chiffres changeaient au redémarrage de l'outil. C'est le fichier
  qui fait foi désormais. Les circuits dont le découpage est livré sont strictement inchangés.
* **Une sortie de piste de 0,6 s tout rond** est désormais signalée à Monza. Elle tombait
  juste sous le seuil par arrondi, en additionnant des durées d'échantillons.
* `Track Edge`, `Path Lateral` et `Hors Piste` ne sont plus envoyés à la page, qui ne les
  utilise pas.

## Fichiers abîmés

Un fichier qui n'est pas une base DuckDB levait une erreur non gérée, et un seul fichier
faisait échouer tout un lot de la liste. Il est maintenant signalé dans sa ligne, et le reste
de la liste s'affiche.

## Performances

Temps cumulés sur les 10 sessions, serveur tout juste lancé :

| Route | Avant | Après |
|---|---:|---:|
| `/api/virages` | 8,9 s | 0,4 s |
| `/api/regularite` | 19,2 s | 2,4 s |
| `/api/resumes` | 0,97 s | 0,04 s |
| `/api/comparaison` | 7,8 s | 5,7 s |

Chaque tour rouvrait le fichier deux fois et redécoupait toute la session. Désormais un fichier
ne s'ouvre qu'une fois pour tous ses tours, et sessions et tours restent en cache.

**Piège du cache.** Les tours gardés en mémoire sont partagés entre les requêtes : chacun reçoit
son propre dictionnaire de canaux, et les tableaux sont en lecture seule. Une écriture
accidentelle lève une erreur au lieu de fausser une autre analyse.

## Les seuils

`parametres.json`, créé au premier lancement, règle les seuils de mesure d'un virage. Une faute
de frappe donne un message qui désigne le fichier. La v2 y ajoutera les seuils de détection
d'erreurs.

Restent dans le code, parce qu'ils sont calés par mesure et ne sont pas des préférences : les
constantes de détection des virages et les seuils d'annotation d'un tour (`SEUIL_QUASI_ARRET`,
`DUREE_SORTIE_SIGNALEE`).
