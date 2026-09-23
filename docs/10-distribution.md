# Étape 6 — Finitions : le .exe, et l'outil hors de la machine de développement

**Statut : terminé.** Tu as choisi un **.exe autonome** : tu comptes partager
l'outil avec des gens qui ne sauront pas forcément se servir d'un `.bat`, et
tu veux pouvoir le mettre à jour quand tu auras des correctifs.

Ce choix change plus de choses qu'il n'y paraît. Jusqu'ici, l'outil tournait
sur UNE machine — la tienne —, lancé depuis son dossier, par quelqu'un qui
sait taper une commande. Chez un ami, rien de tout ça n'est vrai.

---

## Ce qui ne marchait que chez toi

| Hypothèse cachée | Pourquoi elle tombe chez un ami |
|---|---|
| Le jeu est sur `D:\SteamLibrary` | quatre chemins étaient essayés en dur ; un ami a sa bibliothèque Steam ailleurs |
| Les découpages et logos sont dans le dossier d'où on lance l'outil | le .exe s'extrait dans un dossier temporaire, **effacé à chaque fermeture** : une retouche y serait perdue |
| On indique un dossier avec `--dossier` | un double-clic ne passe aucune option |
| Les messages peuvent dire « relance la commande » | il n'y a pas de commande |
| Un seul lancement à la fois | un double-clic de trop, et l'outil échouait sur un port occupé |

## Trouver le jeu

Steam tient la liste de ses **bibliothèques** — un dossier par disque où des
jeux sont installés — dans `steamapps\libraryfolders.vdf`. Sur ta machine :
Steam est sur `C:`, Le Mans Ultimate (numéro Steam 2399420) sur `D:`.
L'outil lit l'emplacement de Steam dans le registre, puis ce fichier, et
cherche le jeu dans chaque bibliothèque. Vérifié sur ta machine : il retrouve
`D:\SteamLibrary\...\Telemetry` sans aucun chemin écrit en dur.

Trois cas d'échec, trois messages différents :

* le jeu est installé mais **n'a encore rien enregistré** (pas de dossier
  `Telemetry`) : il faut rouler une première session ;
* le jeu est **introuvable** : l'interface affiche un écran « Où sont tes
  sessions ? » avec la marche à suivre dans Steam ;
* un dossier choisi a **disparu** (disque débranché) : on retente la
  détection au lieu de rester bloqué.

L'écran de choix refuse un dossier sans aucune session, et reconnaît l'erreur
la plus probable — choisir le dossier du jeu au lieu de `UserData\Telemetry` —
pour dire quel sous-dossier prendre.

## Où vont les fichiers

Deux sortes de fichiers, deux endroits (voir `lmu_telemetry/emplacements.py`) :

* les **ressources livrées** — page web, découpages de référence, logos
  libres, icône — dans `lmu_telemetry/ressources/`, embarquées dans le .exe,
  en lecture seule ;
* les **données de l'utilisateur** — découpages retouchés, logos personnels,
  réglages — dans `%LOCALAPPDATA%\Telemetrie LMU`, qui survit au remplacement
  du .exe.

Un découpage livré est recopié dans les données la première fois qu'il sert.
C'est la copie qu'on retouche, et elle fait foi ensuite. Tes six découpages
(Algarve, Monza, Monza Curva Grande, Sarthe, Spa, Long Beach) partent donc
avec le .exe : tes amis ont les mêmes numéros de virages que toi.

Tes 20 logos ont été répartis selon leur licence : les 10 libres de droits
(Commons) sont livrés avec l'outil, les 10 en « usage équitable » (Wikipédia)
sont dans ton dossier de données, et ne partent pas avec le .exe.

## Le lancement

`lmu_telemetry/lanceur.py`, appelé au double-clic :

1. si l'outil est **déjà ouvert**, il réaffiche sa page et s'arrête ;
2. sinon il prend le port 8770, ou le suivant s'il est tenu par un autre
   programme ;
3. il ouvre le navigateur, et la fenêtre noire dit qu'il faut la laisser
   ouverte, et que la fermer arrête l'outil ;
4. en cas d'erreur, le message reste affiché jusqu'à Entrée — sans cette pause,
   la fenêtre se fermerait avant qu'on puisse le lire.

## Les défauts que ce travail a fait apparaître

Trois défauts réels, trouvés en simulant la machine d'un ami, et couverts
chacun par un test :

1. **La page refusait de s'afficher sans dossier de télémétrie.** Chaque
   requête — y compris celle de la page elle-même — commençait par chercher le
   dossier, pour vérifier les chemins demandés. Sans dossier, l'écran censé
   permettre de l'indiquer ne pouvait donc pas s'afficher. La vérification n'a
   maintenant lieu que si la requête désigne un fichier.
2. **Deux lancements pouvaient se partager le port 8770.** La bibliothèque
   standard active `SO_REUSEADDR`, qui sous Windows laisse un second programme
   s'installer sur un port déjà pris ; le navigateur tombait alors sur l'un ou
   l'autre au hasard. Le serveur demande maintenant l'usage exclusif du port.
3. **Un fichier de virages mal retouché donnait « Requête incomplète : 'circuit' ».**
   Un champ effacé ou un nombre écrit « 120 m » produisent maintenant un
   message qui désigne le fichier et dit quoi faire.

## La revue des messages d'erreur

* Plus aucun message affiché dans l'interface ne parle de « commande »,
  d'option ou de module Python. Ce qui ne concerne que la ligne de commande
  (l'option `--dossier`) n'est ajouté que par la ligne de commande.
* Une erreur **inattendue** — un défaut de l'outil — ne montre plus une
  exception brute : la page dit que ce n'est pas la faute de l'utilisateur et
  quoi transmettre, et la trace complète part dans la fenêtre noire.
* Si la fenêtre de l'outil est fermée, la page ne dit plus « Failed to fetch »
  mais que l'outil ne répond plus, et comment le relancer.
* Le bloc d'erreur, placé en bas de page, défile jusqu'à être visible : sur un
  long tableau, un clic semblait sinon n'avoir rien fait.

## Sécurité de la nouvelle route

Choisir le dossier est la seule action qui **modifie** quelque chose (le
fichier de réglages). Une page web quelconque ouverte dans le navigateur
pourrait tenter d'appeler `http://127.0.0.1:8770/api/dossier` à ton insu. La
route exige donc l'en-tête `Origin` de la page de l'outil elle-même, que les
navigateurs ne laissent pas falsifier, et un corps en JSON, qui impose au
navigateur une vérification préalable que le serveur n'accorde pas. Testé de
bout en bout sur un vrai serveur.

## Vérifié sur le .exe lui-même

Construit avec PyInstaller 6.22.3 : **32 Mo**, en une minute et demie, tests
compris. Lancé avec un dossier de données vierge, comme chez un ami qui
l'ouvre pour la première fois :

* le jeu est trouvé tout seul (441 sessions listées) ;
* seuls les 10 logos libres sont présents, les autres marques ont leur
  pastille ;
* comparaison, tableau par virage et régularité fonctionnent ; le découpage de
  Long Beach est recopié dans le dossier de données à la première comparaison ;
* un second lancement répond « L'outil est déjà ouvert » et réaffiche la page ;
* les propriétés du fichier affichent « Télémétrie LMU », version 1.0.0.

## Limites connues

* **Avertissements Windows et antivirus.** Un .exe non signé déclenche l'écran
  SmartScreen au premier lancement, et PyInstaller est souvent pris à tort pour
  un virus. Seule une signature de code payante y remédierait. Le mode d'emploi
  explique quoi faire.
* **Démarrage de quelques secondes** : le .exe s'extrait à chaque lancement.
* **Pas de mise à jour automatique.** Il faudrait un endroit où publier les
  versions (par exemple une page GitHub) ; en attendant, le numéro affiché en
  haut à droite dit qui a quelle version.
