# Étape 16 — L'overlay

**Statut : abandonné le 2026-11-09, après l'essai en piste.** Son code était sur la branche
locale `archive/conseils`, supprimée le 2026-11-10. La détection du jeu, gardée un temps (voir
« Un jeu fermé peut sembler en piste »), est partie avec l'ingénieur de course le même jour
(étape 17).

---

## Ce qui s'affiche

Un message à la fois, en haut de l'écran : le virage, puis le conseil, dans l'identité de
l'application. Il est dessiné une fois par message, avec Pillow, et la fenêtre ne redessine rien entre
deux messages. Sans message, elle est cachée : elle ne coûte rien au jeu.

```
overlay/
  planning.py   quand un conseil s'affiche et quand il disparaît
  rendu.py      le dessin du message
  calque.py     la fenêtre Windows
  service.py    le processus : lire, juger, afficher
  pilote.py     le côté interface : lancer, arrêter, savoir où il en est
```

## La fenêtre

| Propriété | Pourquoi | Vérifié |
|---|---|---|
| Transparence par pixel | On voit le jeu autour de la carte | Sur une fenêtre de test rouge : le fond passe exactement à 89 % d'opacité |
| Les clics la traversent | Ils vont au jeu | `WindowFromPoint` au centre du message ne la trouve pas |
| Toujours devant | Réaffirmé à chaque message | Style lu sur la fenêtre |
| Ne prend pas le clavier | Un jeu qui perd le focus se met en pause | Fenêtre active inchangée après un message |
| Absente d'Alt+Tab et de la barre des tâches | Style de fenêtre outil | Style lu sur la fenêtre |

Un message s'affiche en 10 ms et disparaît en 1 ms, plus 40 ms de dessin. L'overlay marche en fenêtre
et en plein écran sans bordure, pas en plein écran exclusif : Windows n'y affiche rien par-dessus.

Il va sur l'écran du jeu, trouvé par son processus, et sur l'écran principal si le jeu n'est pas lancé.
La taille suit la hauteur de l'écran : le message occupe la même part de l'image en 1080p et en 1440p.

## Les règles d'affichage

Sur 60 sessions à Monza en GT3, rejouées au tour près :

| Mesure | Résultat |
|---|---:|
| Conseils du moteur | 147 |
| Messages affichés | 128 |
| Affichés pendant un freinage | 0 |
| Affichés dans un virage freiné | 0 |
| Temps à l'écran le plus court | 1,8 s |
| Affichés pendant leurs 3 s entières | 87 % |
| Délai après la sortie, médiane | 3,2 s |
| Délai après la sortie, 90 % des cas | 6,6 s |

Les 19 conseils qui ne s'affichent pas se répétaient d'un tour à l'autre, ou n'ont pas trouvé de moment
avant d'être périmés.

* **Jamais pendant un freinage :** le message disparaît au premier appui.
* **Pas de message à moitié lu :** s'il reste moins de 1,5 s avant le prochain freinage, il attend la
  sortie du virage suivant. Le prochain point de freinage est celui du tour d'avant.
* **Tout l'espace entre le freinage et la sortie est bloqué.** Vérifier seulement le prochain point de
  freinage laissait passer un cas : le pilote qui freine 3 m plus tard qu'au tour d'avant. Le point était
  dépassé, le suivant était 19 s plus loin, et le message tombait une fraction de seconde avant le
  frein. C'était le cas de 26 messages à Lesmo 1.
* **Un conseil ne se répète pas au tour suivant,** au même virage. Le pilote l'a lu, il lui faut un tour
  pour l'essayer. Il peut revenir le tour d'après.
* **Il est oublié au bout de 12 s :** il ne parlerait plus du virage qu'on vient de passer.

## Deux processus

L'interface lit des fichiers de plusieurs dizaines de mégaoctets. Dans le même processus, ces calculs
retarderaient la lecture à 50 Hz. L'overlay tourne donc à part, et l'interface le pilote par une
connexion locale. Si elle se ferme, il le voit et s'arrête : il ne reste pas d'overlay orphelin.

Le .exe est le même programme, relancé avec `--overlay`. Vérifié depuis un .exe construit à part :
exemple, attente du jeu, rejeu et arrêt, sans processus restant. Pillow le fait passer de 38,7 à 48 Mo,
et il démarre toujours en 3,4 s.

## Un jeu fermé peut sembler en piste

La mémoire `LMU_Data` survit au jeu tant qu'un programme la tient ouverte. C'est le cas de SimHub : elle
montrait encore la dernière voiture, et l'outil annonçait « En piste » jeu fermé. Il vérifie maintenant
que le processus `Le Mans Ultimate.exe` tourne, et ne croit qu'une mémoire qui change.

## Les réglages

Dans l'onglet Overlay : position, en faisant glisser le message sur la miniature, taille, durée
d'affichage et délai après le virage. Le bouton « Montrer à l'écran » affiche un exemple au bon endroit.
Le reste est dans la section `overlay` de `parametres.json` :

| Réglage | Défaut | Rôle |
|---|---:|---|
| `lecture_minimale` | 1,5 s | Temps sous lequel un message n'a pas pu être lu |
| `frein_masque` | 5 % | Pression de frein qui fait disparaître le message |
| `peremption` | 12 s | Temps après lequel un conseil est oublié |
| `tours_sans_repetition` | 1 | Tours avant de répéter un conseil au même virage |

## Essayer sans le jeu

L'onglet Overlay rejoue une session sur l'écran, à ×1, ×2 ou ×4. Le rejeu commence au premier tour
lancé : le tour de sortie des stands ne dit rien et peut durer deux minutes.

En ligne de commande :

```
.venv\Scripts\python.exe -m lmu_telemetry overlay --rejeu <fichier> --vitesse 4
```

## Ce qui reste à vérifier en piste

| Point | Pourquoi |
|---|---|
| Le message passe bien devant le jeu | Seul le vrai jeu le dira |
| Pas de saccade quand il apparaît | Windows peut changer de mode d'affichage quand une fenêtre recouvre le jeu |
| La position par défaut ne cache rien d'utile | Elle dépend de ta disposition en jeu |
| Le moment d'affichage convient | Les délais viennent des enregistrements, pas d'un pilote qui lit |
