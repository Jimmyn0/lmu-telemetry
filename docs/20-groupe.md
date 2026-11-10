# Étape 20 — Le groupe : partager ses performances entre amis

C'est l'étape 4 du leaderboard ([19-leaderboard.md](19-leaderboard.md)) : chaque PC envoie les
performances de ses qualifs et courses en ligne à un petit service, et reçoit celles des autres
membres de son groupe.
Le leaderboard les mêle toutes.

**Statut : en ligne depuis le 2026-11-10.** Le service tourne sur Cloudflare, sa base en Europe
de l'Ouest (servie depuis Paris) ; son adresse est la constante `SERVICE` de
`lmu_telemetry/groupe/reglages.py`. Pour les tests, le même code tourne sur ce PC
(`service/local.mjs`) : aucun test ne parle au service en ligne.

---

## Le principe

* Un **service** sur Cloudflare (un Worker et sa base D1) garde ce que les membres partagent. Un
  seul service héberge tous les groupes ; un groupe, c'est un **code** de 8 caractères
  (`K7M2-QX9P`), sans I, O, 0 ni 1, pour qu'on ne se trompe pas en le recopiant.
* Chaque PC n'envoie que les **performances de son propriétaire en qualifs et en course, en
  ligne**, telles que les calcule `domaine/performances.py` : son nom de pilote dans le jeu, les
  circuits, voitures, chronos, secteurs, places. Rien d'autre : ni ses essais, ni ses séances
  contre l'IA, ni e-mail, ni nom de PC, ni fichier, ni les autres pilotes de ses séances. Plus
  les **contours** des tracés que sa télémétrie connaît, pour que les cartes des circuits d'un
  ami aient leur dessin.
* La **synchronisation** se fait toute seule : à l'ouverture de l'outil, dès qu'une séance en
  ligne s'ajoute aux résultats du jeu (regardé chaque minute), et toutes les cinq minutes pour
  recevoir celles des autres. Le bouton « Synchroniser maintenant » la lance à la main.
* Une **copie** du groupe reste sur le PC (`groupe.json`, dans les données de l'outil) : le
  leaderboard s'affiche tout de suite, même sans connexion.
* Avec les performances, chaque PC partage la **télémétrie de ses records** de ces mêmes
  séances, un par tracé et par voiture : les amis s'y comparent dans l'onglet Télémétrie (voir
  « Les records partagés »).

## La sécurité

* Le code d'un groupe permet de le **rejoindre** : c'est une invitation, à ne donner qu'à ses
  amis. Tout le monde voit qui est dans le groupe.
* En rejoignant, chaque PC reçoit une **clé secrète**, rangée dans ses réglages
  (`reglages.json`, clé « groupe »). Elle seule permet de lire le groupe, et d'écrire ou
  d'effacer **ses** performances : personne ne peut toucher à celles d'un autre. Le service n'en
  garde que l'empreinte SHA-256.
* **Quitter** le groupe efface ses performances du service. Le dernier parti, le groupe
  disparaît. Si le service ne répond pas, le PC reste dans le groupe : ses performances ne
  doivent pas y rester à son insu.
* Pas d'administrateur dans cette première version : si un code fuite, on crée un autre groupe.
* Le service refuse ce qui dépasse ses **limites** : 50 membres par groupe, 200 performances et
  1 Mo par envoi, 8 Ko par performance, 20 000 performances par membre, des contours de 400
  points au plus. Un code divulgué ne peut pas faire déborder la base.
* Ce qui vient du réseau n'est jamais cru sur parole : `performances.depuis_json` vérifie
  chaque champ d'une performance reçue, et l'écran échappe tout ce qu'il affiche.

## Le service

`service/` : le code du Worker (`src/index.js`), le schéma de la base (`schema.sql`) et la
configuration de Cloudflare (`wrangler.toml`).

| Route | Ce qu'elle fait |
|---|---|
| `GET /v1/sante` | Le service répond qu'il est là |
| `POST /v1/groupes` | Crée un groupe ; renvoie son code, et le numéro et la clé de son premier membre |
| `POST /v1/groupes/{code}/membres` | Rejoint un groupe ; renvoie le numéro et la clé du nouveau membre |
| `GET /v1/groupes/{code}?depuis=N` | Les membres, et ce qui a changé depuis la version N : performances, contours, et la liste des records partagés |
| `PUT /v1/groupes/{code}/performances` | Envoie ses performances (et des contours) |
| `PUT /v1/groupes/{code}/tours` | Partage la télémétrie d'un record (voir « Les records partagés ») |
| `GET /v1/groupes/{code}/tours/{membre}/{id}` | La télémétrie d'un record, à la demande |
| `DELETE /v1/groupes/{code}/membres/{membre}` | Quitte le groupe, en effaçant ses performances et ses records |

Toutes sauf les deux premières demandent l'en-tête `Authorization: Membre <numéro>:<clé>`.

**Les versions.** Chaque écriture dans un groupe augmente sa version, et les lignes écrites la
portent ; la nouvelle version et ses lignes s'écrivent d'un bloc (`db.batch`, une transaction).
Un PC qui a déjà reçu la version N ne demande que les lignes plus récentes. Si la version du
service recule (une base refaite), le PC repart de zéro et renvoie tout.

**L'offre gratuite de Cloudflare**, vérifiée le 2026-11-10 : 100 000 requêtes par jour, 10 ms de
calcul par requête (l'attente de la base ne compte pas), 50 requêtes à la base par appel, 100
paramètres par requête, 2 Mo par valeur ; la base D1 lit 5 millions de lignes et en écrit 100 000
par jour, et garde 5 Go. D'où deux choix :

* un envoi entre dans la base en **une seule requête** : le tableau JSON des performances,
  lu par `json_each`, quel que soit leur nombre ;
* ce que le service renvoie reste **le texte rangé dans la base**, recopié sans être relu : pas
  de calcul pour des milliers de performances.

Une synchronisation coûte 2 ou 3 requêtes. Un groupe d'amis use une infime partie de l'offre ;
quelques centaines de joueurs aussi. Une limite connue : la première synchronisation reçoit tout
le groupe d'un coup ; au-delà de quelques dizaines de milliers de performances, il faudra la
découper en pages.

KV, l'autre stockage de Cloudflare, n'a pas été retenu : 1 000 écritures par jour en gratuit, et
jusqu'à une minute avant qu'une écriture se voie partout.

## Le client, dans l'outil

`lmu_telemetry/groupe/` :

| Fichier | Rôle |
|---|---|
| `reglages.py` | L'adresse du service, et la place de ce PC dans un groupe (code, numéro, clé, nom) |
| `service.py` | Les requêtes au service ; ses erreurs deviennent des phrases qui disent quoi faire |
| `synchro.py` | La copie du groupe, la synchronisation, et la tâche de fond (`Synchroniseur`) |

**L'adresse du service** se cherche dans la variable `LMU_SERVICE_GROUPE`, puis dans
`reglages.json` (« groupe » → « service »), puis dans la constante `SERVICE` de `reglages.py`.
Tant qu'elle est vide, l'écran Groupe dit que le service n'est pas encore en ligne.

**La synchronisation** (`synchroniser`) envoie les performances qui comptent (qualifs et
courses en ligne, `leaderboard.comptee`) et qui ont changé depuis leur dernier envoi (la copie
retient l'empreinte de chacune), par paquets de 100, avec les contours pas encore envoyés ; puis
elle reçoit ce qui a changé. Les performances de ce PC revenues du service sont ignorées : elles
viennent de ses fichiers. Celles d'un membre parti sont oubliées.

**La tâche de fond** démarre avec le serveur de l'outil (`servir`), pas avec les tests. Hors
d'un groupe, elle ne fait rien.

**Le leaderboard** (`reponses.leaderboard`) mêle les performances de ce PC et celles des autres
membres tirées de la copie ; les contours de ce PC passent avant ceux du groupe.

## L'écran

Une carte **Groupe** en tête de la colonne de gauche du Leaderboard ouvre l'écran du groupe :

* sans groupe : **Créer un groupe** (le nom proposé est le nom de pilote le plus roulé en ligne)
  ou **Rejoindre un groupe** avec son code, et ce qui est partagé ;
* dans un groupe : le **code**, à copier et à donner à ses amis ; les **membres**, avec la date
  à laquelle chacun a rejoint et sa dernière synchronisation ; l'état de la **synchronisation**
  et son bouton ; **Quitter le groupe**, en deux clics : le premier arme le bouton, le second
  quitte.

Onglet ouvert, l'écran regarde toutes les 30 s si la synchronisation a apporté du neuf, et se met
à jour de lui-même. L'en-tête des dernières courses dit le groupe : « Groupe K7M2-QX9P · 3 pilotes ».

## Les records partagés (étape 5 du leaderboard)

Demandé avec le groupe : « une comparaison complète dans l'onglet Télémétrie actuel avec les
temps partagés entre potes ». Fait le 2026-11-10.

**Ce qui part.** Pour chaque tracé et chaque voiture, le meilleur tour valide de ses qualifs
et courses **en ligne** dont la télémétrie a été enregistrée (`reponses.mes_records`) : comme pour
les performances, ni les essais ni une séance jouée contre l'IA ne partagent rien. Le même tracé
et la même voiture gardent le même numéro de record (`tours.identifiant_record`) : un meilleur
tour remplace l'ancien. Sur les fichiers du disque, 27 records avec les essais ; 14 sans (10 en
qualifs, 4 en course).

**Le format** (`groupe/tours.py`). Le tour est rééchantillonné tous les mètres, comme l'axe de
la comparaison. Chaque canal devient une suite d'entiers dont on garde les écarts successifs ;
le tout, en JSON compressé (gzip) puis en base64, pèse 55 Ko pour un tour de Monza et 140 Ko
pour Le Mans. Comparé à sa propre copie partagée, un tour s'en écarte d'au plus 0,5 ms. Partent
aussi le pilote, le tracé, la voiture, les temps intermédiaires et le débattement du volant ;
jamais le réglage de la voiture, ni le chemin du fichier.

**Les envois.** La synchronisation envoie, après les performances, les records nouveaux ou
battus depuis le dernier envoi (la copie retient la signature de chacun : fichier, tour, chrono),
20 au plus par passage : lire un tour prend un quart de seconde. Sur les fichiers du disque,
avec les essais : 20 records en 5 s, puis les 7 autres au passage suivant. Un fichier illisible
ne se retente pas.

**La réception.** Le groupe ne reçoit que la **liste** des records des autres (tracé, voiture,
pilote, chrono, date) : leur télémétrie se télécharge à la demande, quand on choisit le tour, et
se garde sur le disque (`groupe_tours/`, dans les données de l'outil) tant que le record ne
change pas. Quitter le groupe efface ce dossier. Un record d'essai reçu (la première version
de l'outil en partageait) est écarté.

**Un record demandé plusieurs fois à la fois** ne se télécharge qu'une fois : ouverte depuis le
leaderboard, la page Télémétrie le demande par plusieurs routes en même temps (la comparaison, la
session). Sans verrou, deux téléchargements se marchaient dessus, et Windows refusait d'effacer
le fichier que l'autre écrivait : la comparaison échouait. Un verrou par record, donc, et le
fichier s'écrit à côté avant d'être mis en place (`synchro.charger_partage`).

**La relecture** d'un tour reçu est vérifiée de bout en bout (`tours.decoder`) : format, nombre
de points (40 km au plus), décompression plafonnée à 32 Mo, longueurs, valeurs, temps qui ne
reculent pas ; un canal inconnu est ignoré. Le tour devient un `TourPartage`, un `DonneesTour`
qui se compare comme les tours de ce PC : courbes, écart cumulé, carte, vue de la route,
virage par virage.

**Dans l'onglet Télémétrie.** Les deux tours peuvent être le record d'un ami : la liste des
sessions du tracé propose, en dessous, les « Records de tes amis », pour la référence comme pour
le comparé ; sans tour comparé, le bouton « Comparer à un ami » prend le plus rapide d'entre eux.
**Depuis le leaderboard**, la page d'un circuit choisit la référence et le tour comparé parmi
les tours enregistrés, les siens ou ceux des amis (colonne Réf. / Comp.), et les ouvre ici (voir
[19-leaderboard.md](19-leaderboard.md), « Comparer deux tours du classement »). Pour la page, le record d'un ami se désigne `groupe:<membre>/<numéro>` : le
serveur le cherche lui-même dans la copie du groupe, d'après un motif strict, et jamais comme un
chemin du disque (`serveur._verifier_chemins` ne laisse passer que ces désignations-là en plus
des sessions du dossier).

**Les limites du service** : 300 records par membre, 1,5 Mo par record.

## Essayer le service sur ce PC

Node 22.5 ou plus suffit : le service tourne avec le SQLite de Node à la place de D1
(`service/d1_local.mjs`), sans rien télécharger.

```bash
node service/local.mjs --port 8787
```

Puis, avant de lancer l'outil : `set LMU_SERVICE_GROUPE=http://127.0.0.1:8787`. Sans `--base`,
la base vit en mémoire et disparaît avec le service.

## Mettre le service en ligne

Une seule fois, par le propriétaire du service. Il faut un compte Cloudflare gratuit
(cloudflare.com, « Sign up ») : seul toi peux le créer. Puis, dans le dossier `service` :

1. `npx wrangler login` : télécharge l'outil de Cloudflare (wrangler) et ouvre le navigateur
   pour l'autoriser sur ton compte.
2. `npx wrangler d1 create lmu-groupe` : crée la base ; recopie le `database_id` affiché dans
   `wrangler.toml`, à la place de `A-REMPLIR`.
3. `npx wrangler d1 execute lmu-groupe --remote --file=schema.sql` : crée les tables.
4. `npx wrangler deploy` : met le service en ligne. Au premier déploiement, Cloudflare demande
   un sous-domaine `workers.dev` : il apparaîtra dans l'adresse du service, et donc chez tes
   amis ; choisis-le neutre.
5. Vérifie : l'adresse affichée, suivie de `/v1/sante`, doit répondre `{"ok":true,"version":1}`.
6. L'adresse va dans la constante `SERVICE` de `lmu_telemetry/groupe/reglages.py` : le .exe
   l'emportera, et tes amis n'auront qu'à saisir le code du groupe.

Pour mettre à jour le service plus tard : `npx wrangler deploy`. Le schéma ne change pas sans
une migration écrite exprès.

### Ce qui s'est passé le 2026-11-10

* `npx wrangler login`, lancé par l'utilisateur, a installé wrangler 4.159.0 et l'a autorisé sur
  son compte. Les commandes suivantes ont pris cette installation (`npx --no-install`), avec
  `WRANGLER_SEND_METRICS=false` (pas de statistiques d'usage envoyées à Cloudflare) et
  `CI=true` (aucune question en attente de réponse).
* La base : `wrangler d1 create lmu-groupe --location=weur` ; son identifiant est dans
  `wrangler.toml`. Les tables : `d1 execute lmu-groupe --remote --file=schema.sql`.
* Le déploiement : sans compte `workers.dev`, et sans personne pour répondre, wrangler a pris le
  nom du Worker pour sous-domaine. D'où l'adresse en `lmu-groupe.lmu-groupe.workers.dev`, neutre.
  Il se change dans le tableau de bord de Cloudflare (Workers, « Subdomain ») ; l'adresse de
  `SERVICE` change alors avec lui.
* Les DNS ont mis 3 minutes à suivre. Puis un groupe d'essai a été créé, a reçu une performance,
  et a été quitté : il a disparu de la base, comme prévu.
* Un test sur cinq échouait : deux membres arrivés dans la même milliseconde se départageaient au
  hasard. Les membres sont désormais dans l'ordre de leur arrivée dans la base (`rowid`) ; le
  service corrigé a été redéployé et revérifié.

## Vérifié

* 10 tests du service (`tests/js/service_groupe.test.mjs`, lancés par Node avec SQLite) : santé,
  codes, créer et rejoindre, clés, envoi et réception par version, chacun ses performances, ce
  qui est refusé, quitter, groupe complet.
* 25 tests de l'outil (`tests/test_groupe.py`) : une performance qui fait l'aller-retour, celles
  qui ne se lisent pas, les réglages, la synchronisation contre un faux service (n'envoyer que ce
  qui change, recevoir les autres et pas soi, un membre parti, un service qui a oublié le groupe,
  une copie d'un autre groupe), puis contre le vrai service lancé sur ce PC : deux PC dans un
  groupe, les erreurs, un service qui ne répond pas, la tâche de fond, et les routes de l'écran.
* L'écran dans la vraie fenêtre, contre le service local : créer un groupe (336 séances en ligne
  envoyées), un ami simulé qui rejoint et envoie les siennes, la synchronisation (336 reçues), les
  dernières courses et Monza mêlés, puis quitter.
* Le service en ligne, par le client de l'outil (HTTPS) : santé, puis un groupe d'essai créé,
  lu, alimenté, relu et quitté, deux fois (avant et après la correction de l'ordre des membres).
* Les tests du service tournent 40 fois de suite sans échec.
* Les records partagés : 2 tests du service (la liste et le téléchargement, un meilleur tour
  qui remplace l'ancien, le départ ; ce qui est refusé) et 19 tests de l'outil (un tour qui fait
  l'aller-retour, ceux qui ne se lisent pas, les garde-fous dont une bombe de compression, la
  désignation, les records de ce PC en ligne seulement, leurs envois, la liste reçue, puis contre
  le service local la comparaison avec le record d'un ami et les routes de la page).
* Dans la vraie fenêtre, contre le service local : les 27 vrais records envoyés, un ami simulé,
  « Comparer à un ami » depuis un tour de Monza, la comparaison complète jusqu'au virage par
  virage. Puis le service en ligne mis à jour (la table `tours` par le même `schema.sql`, puis le
  code) et vérifié avec un tour de la session de test synthétique, relu sans écart.
* Puis, sans les essais : rien d'autre ne part que les qualifs et les courses, et un record
  d'essai reçu est écarté. Un record demandé par six routes à la fois ne se télécharge qu'une
  fois (le test reproduisait l'erreur de Windows avant la correction). Les deux tours choisis
  depuis le leaderboard : voir [19-leaderboard.md](19-leaderboard.md).
