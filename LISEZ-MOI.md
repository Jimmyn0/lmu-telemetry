# Analyse de télémétrie — Le Mans Ultimate

🇬🇧 *English version: [README.md](README.md)*

Un outil local pour regarder ce que tu fais au volant, à partir des
enregistrements que Le Mans Ultimate produit déjà tout seul.

L'outil **montre**, il ne juge pas. Pas de conseil de réglage, pas de
diagnostic automatique : uniquement des faits mesurés.

> **Version 1.1.0 — les six étapes du brief sont terminées, et l'outil existe
> en anglais.**
> L'outil liste tes sessions, découpe chacune en tours, **compare deux tours**
> (traces superposées, delta cumulé, vue de la route), donne le **détail virage
> par virage** et analyse ta **régularité**. Il existe en **.exe autonome** à
> partager. Historique des versions : [NOTES-DE-VERSION.md](NOTES-DE-VERSION.md).

**Télécharger l'outil :** [dernière version](https://github.com/Jimmyn0/lmu-telemetry/releases/latest)
— prends le fichier `.zip`, il contient le `.exe` et son mode d'emploi.

**Tu as reçu `Telemetrie-LMU.exe` ?** Tout ce qu'il te faut est dans
[distribution/LISEZ-MOI.txt](distribution/LISEZ-MOI.txt) : double-clic, et c'est parti. La suite de ce
document s'adresse à qui a le code source.

---

## Ce qu'il faut savoir avant de commencer

**Tu n'as rien à installer dans le jeu, ni à activer.** Le Mans Ultimate
enregistre déjà ta télémétrie tout seul, dans un fichier par session, ici :

```
<ton dossier Steam>\steamapps\common\Le Mans Ultimate\UserData\Telemetry
```

L'outil lit ces fichiers **sur place et en lecture seule**. Il n'écrit rien,
ne déplace rien, ne supprime rien.

⚠️ Ces fichiers sont dans le dossier de Steam. Un « Vérifier l'intégrité des
fichiers » ou une grosse mise à jour peut donc les effacer. Si tu tiens à ton
historique, copie ce dossier ailleurs de temps en temps.

---

## Installation

Il te faut **Python 3.11 ou plus récent**. Pour vérifier, ouvre un terminal et
tape :

```bash
py --version
```

Si la commande n'est pas reconnue, installe Python depuis
[python.org](https://www.python.org/downloads/) en cochant bien
« Add Python to PATH » pendant l'installation.

Ensuite, place-toi dans le dossier du projet et lance ces trois commandes,
une par une :

```bash
py -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python.exe -m lmu_telemetry sessions
```

La première crée un environnement isolé (un dossier `.venv`) pour que les
bibliothèques de l'outil ne se mélangent pas au reste de ta machine. La
deuxième installe ces bibliothèques. La troisième affiche tes sessions : si tu
vois une liste, tout fonctionne.

---

## Partager l'outil : le .exe

Tes amis n'ont pas besoin de Python : ils reçoivent un seul fichier,
`Telemetrie-LMU.exe`, qui contient tout.

### Le construire

Double-clique sur **`construire-exe.bat`**, dans le dossier du projet (un
double-clic sur `tools\construire_exe.py` fait la même chose). Il installe les
outils de construction la première fois, **passe tous les tests** (une version
qui échoue n'est jamais construite), fabrique le .exe, puis ouvre le dossier
`dist`. La fenêtre reste ouverte à la fin, pour que tu puisses lire le
résultat : appuie sur Entrée pour la fermer. Le dossier `dist` contient :

| Fichier | À quoi il sert |
|---|---|
| `Telemetrie-LMU.exe` | l'outil, pour toi |
| `Telemetrie-LMU-1.1.0.zip` | **ce que tu envoies** : le .exe et ses deux modes d'emploi |
| `LISEZ-MOI.txt`, `README.txt` | le mode d'emploi en français et en anglais, écrit pour quelqu'un qui n'a jamais vu l'outil |

Ces deux modes d'emploi se modifient dans le dossier `distribution/` du projet.
Ce document-ci est la version française du `README.md` en anglais qu'affiche
GitHub.

Compte une minute et demie. Le .exe pèse 32 Mo : trop pour une pièce jointe
Discord sans abonnement. Passe par un lien Google Drive,
WeTransfer ou équivalent.

### Ce qu'il y a dedans, et ce qu'il n'y a pas

Le .exe embarque la page web, les **découpages de circuits** que tu as déjà
(tes amis ont les mêmes numéros de virages que toi), et les **logos libres de
droits**. Il n'embarque pas tes logos personnels, qui ne peuvent pas être
redistribués : chez tes amis, ces marques gardent leur pastille colorée.

### Le mettre à jour

Quand tu as corrigé ou ajouté quelque chose :

1. augmente le numéro de version dans `lmu_telemetry/__init__.py` — le dernier
   chiffre pour une correction (1.0.0 → 1.0.1), celui du milieu pour un ajout
   (1.0.1 → 1.1.0) ;
2. note ce qui change dans [NOTES-DE-VERSION.md](NOTES-DE-VERSION.md) ;
3. relance `construire-exe.bat` ;
4. publie-la sur GitHub : envoie le code (`git add -A`, `git commit -m "…"`,
   `git push`), puis sur la page du dépôt, **Releases › Draft a new release** :
   une étiquette `v1.0.1` (le numéro de version), un titre, le texte de
   NOTES-DE-VERSION.md, et le `.zip` de `dist` glissé dans la zone des
   fichiers. Le lien « dernière version » pointe aussitôt sur elle.

Tes amis remplacent simplement l'ancien .exe par le nouveau. Leurs réglages et
leurs découpages retouchés sont rangés ailleurs (voir ci-dessous) : une mise à
jour ne les efface pas. Le numéro de version s'affiche en haut à droite de
l'outil, pour savoir qui a quelle version.

### Windows et les antivirus

Un .exe qui ne vient pas d'un éditeur connu déclenche au premier lancement
l'écran bleu « Windows a protégé votre ordinateur » : il faut cliquer sur
« Informations complémentaires » puis « Exécuter quand même ». Certains
antivirus le signalent aussi par erreur — c'est fréquent avec les programmes
fabriqués par PyInstaller. Le mode d'emploi l'explique à tes amis. Seule une
signature de code payante ferait disparaître ces avertissements.

---

## Où l'outil range ses fichiers

L'outil **lit** tes sessions là où le jeu les écrit, sans jamais les modifier.
Ce qu'il **écrit** — et que tu peux retoucher — va dans ton dossier de données :

```
%LOCALAPPDATA%\Telemetrie LMU\
    reglages.json      le dossier de télémétrie, si tu l'as choisi dans l'outil
    virages\           le découpage de chaque circuit, modifiable
    logos\             tes logos de marque personnels
    pays.json          drapeaux des circuits ajoutés (facultatif)
```

Colle `%LOCALAPPDATA%\Telemetrie LMU` dans la barre d'adresse de
l'Explorateur pour l'ouvrir ; le chemin complet s'affiche aussi en survolant
le numéro de version, en haut à droite de l'outil.

Ce dossier ne dépend pas de l'endroit d'où l'outil est lancé : le code source
et le .exe partagent les mêmes réglages et les mêmes découpages, et une
nouvelle version les retrouve. Le découpage d'un circuit livré avec l'outil y
est recopié la première fois qu'il sert — c'est cette copie que tu retouches.

### Trouver le jeu

L'outil lit la liste des **bibliothèques Steam** de la machine
(`libraryfolders.vdf`) et y cherche Le Mans Ultimate, sur n'importe quel
disque. S'il ne le trouve pas — jeu hors Steam, installation inhabituelle —,
l'outil affiche un écran qui demande le dossier et explique comment le trouver
depuis Steam. Le choix est retenu. Un lien **« changer de dossier »**, sous la
liste des sessions, permet d'en changer.

---

## Utilisation

### L'interface graphique

C'est la façon normale de se servir de l'outil :

```bash
.venv\Scripts\python.exe -m lmu_telemetry web
```

Le navigateur s'ouvre tout seul. Tu y trouves tes sessions, puis les tours de
la session choisie, puis la comparaison de deux tours.

L'interface existe en **français et en anglais** : le bouton **FR | EN**, en
haut à droite, change la langue sans perdre l'écran en cours, et le choix est
retenu. Au premier lancement, l'outil prend la langue du navigateur. Tout est
traduit, y compris les remarques sur les tours, les avertissements et les
messages d'erreur : le serveur n'écrit pas de phrases, il envoie une clé que la
page traduit. Les textes sont dans `lmu_telemetry/web/statique/langues/` ; un
test vérifie que les deux langues ont exactement les mêmes phrases. La ligne de
commande, elle, reste en français.

Les couleurs ont toujours le même sens, d'un écran à l'autre :

| couleur | signification |
|---|---|
| bleu | le tour de référence |
| orange | le tour comparé |
| vert | du temps gagné, le tour idéal |
| rouge | du temps perdu |
| violet | le meilleur de la session : meilleur tour, et meilleur temps de chaque secteur (comme sur les écrans de chrono en course) |

Le type de session est une étiquette colorée : **Essais** en turquoise,
**Qualifs** en ambre, **Course** en rose. Le dégradé indigo-rose sert
uniquement à l'interface (bouton principal, écran en cours) : il ne représente
jamais une donnée.

Le tour comparé peut venir d'une **autre session** que le tour de référence :
une autre de tes sorties sur le même tracé, ou le fichier `.duckdb` d'un autre
pilote déposé dans le dossier de télémétrie. Le menu ne propose que les
sessions du **même tracé** : une sortie à Monza et une sortie sur la variante
Curva Grande ne se comparent pas, elles n'ont ni la même longueur ni les mêmes
virages. L'outil te prévient si les deux
tours ne sont pas dans la même voiture — le delta mesurerait alors surtout un
écart de matériel.

La liste n'affiche que les **10 sessions les plus récentes**, avec un bouton pour
en charger 10 de plus. C'est volontaire : lire le nom d'un fichier est
instantané, mais compter ses tours oblige à l'ouvrir, et ouvrir les 388 sessions
du disque prend une douzaine de secondes.

Deux menus en haut de la liste :

* **Circuit** ne garde que les sessions d'un circuit, avec leur nombre entre
  parenthèses. La liste se construit toute seule à partir de tes sessions : un
  circuit roulé une fois y apparaît sans rien avoir à déclarer. Les **variantes
  de tracé** y figurent séparément — « Monza Curva Grande Circuit » à côté
  d'« Autodromo Nazionale Monza », « Bahrain Outer Circuit » à côté du tracé
  complet. Elles n'ont pas les mêmes virages, et l'outil les traite comme des
  circuits différents.
* **Trier par** classe soit par date, soit par **meilleur chrono**.

Le tri par chrono demande d'ouvrir chaque fichier, puisque le meilleur tour ne
se lit pas dans son nom. L'outil s'en charge par paquets et affiche
l'avancement ; le classement se précise au fur et à mesure au lieu de figer
l'écran. Compte une dizaine de secondes la première fois pour un circuit où tu
as beaucoup roulé, puis c'est instantané — les résultats sont gardés en
mémoire. **Choisis un circuit d'abord** : trier tous les circuits ensemble
oblige à tout ouvrir.

Un mot sur ce classement : il compare des **chronos bruts**, donc des voitures
de catégories différentes. À Monza, tes tours en Hypercar passeront devant tes
tours en GT3, ce qui est normal et n'a rien à voir avec ton pilotage. La colonne
Voiture est là pour que ça se voie.

Sur l'écran de comparaison :

* Le **delta cumulé**, en haut, est le retard accumulé par le tour comparé.
  C'est la **pente** qui compte : là où la courbe monte, tu perds du temps ; là
  où elle descend, tu en gagnes. Un palier veut dire que tu vas aussi vite que
  la référence à cet endroit.
* En dessous, **vitesse, frein, accélérateur, angle volant, rapport** des deux
  tours superposés — le tour de référence en bleu, le tour comparé en orange.
* Passe la souris sur n'importe quel graphique : un curseur apparaît sur tous
  les autres en même temps, les valeurs chiffrées s'affichent à droite, et un
  point se place sur la carte du circuit.
* La carte est colorée selon l'endroit où l'écart se creuse : rouge là où tu
  perds, vert là où tu gagnes.
* La **vue de la route** montre de près la portion de circuit sous le curseur,
  orientée dans le sens de marche, avec les deux trajectoires et la position des
  deux voitures. C'est là qu'on voit *où* passe chaque tour, alors que le delta
  dit seulement *combien* il perd. Chaque bord de piste est en trait plein là
  où un des deux tours l'a longé, en pointillé là où il est estimé à partir de
  ses mesures d'avant et d'après.

Sous les graphiques, le tableau **virage par virage** donne pour chaque virage
le **temps perdu ou gagné** — cette colonne répartit l'écart du tour entre les
virages et totalise donc exactement l'écart final —, puis le point de freinage, vitesse d'entrée, durée et pression de freinage, vitesse
minimale, point de remise des gaz, vitesse de sortie, et le temps passé **sur
l'erre** — ni frein ni gaz, ce qui en dit long chez un débutant. Chaque valeur
est accompagnée de l'écart avec le tour de référence, et **cliquer sur une ligne
zoome les graphiques sur ce virage**.

L'écart n'est coloré que là où « mieux » a un sens : une vitesse de sortie plus
haute ou du temps sur l'erre en moins sont des progrès. Le point de freinage
reste en gris — freiner plus tard n'est pas meilleur en soi, ça dépend de ce que
tu fais ensuite.

Pour zoomer : **glisser** sur un graphique pour encadrer une zone, ou la
**molette** pour grossir autour du point visé — celui qui est sous le curseur ne
bouge pas. Le bandeau au-dessus des graphiques indique la portion de circuit
affichée, et le bouton **« Voir le tour entier »** revient à la vue complète (le
double-clic sur un graphique fait la même chose).

Rien ne sort de ta machine : le serveur n'écoute que sur `127.0.0.1` et la page
ne charge aucune ressource extérieure. L'outil fonctionne sans connexion.

Tout ce qui suit est la version en ligne de commande des mêmes données.

### La page régularité

Depuis l'écran d'une session, le bouton **« Régularité de la session »** analyse
tous tes tours valides d'un coup.

* Le **tour idéal** enchaîne tes meilleurs passages dans chaque virage. L'écart
  avec ton meilleur tour réel, c'est du temps déjà à ta portée : tu l'as déjà
  fait, jamais dans le même tour.
* Le **graphique des chronos** montre chaque tour, ton meilleur en violet, et les
  repères médian et idéal.
* **Au fil de la session** dit si tes chronos dérivent, et dans quel sens.
* Le **classement des virages** te donne ceux où tu es le moins constant — c'est
  là qu'il y a le plus à gagner. Pour chacun : le temps de passage habituel, la
  dispersion en secondes, ce qu'il y a à gagner, et les dispersions du point de
  freinage et de la vitesse minimale.

Seuls les tours valides comptent. Il en faut au moins trois, et l'outil prévient
en dessous de cinq : avec trop peu de tours, une dispersion ne veut pas dire
grand-chose.

### Mettre les vrais logos des constructeurs

À côté de chaque voiture, l'outil affiche une pastille colorée avec les
initiales de la marque — un rond rouge « P » pour Porsche. Ce n'est pas un
choix esthétique : les logos des constructeurs sont des marques déposées, et
les redessiner à la main donnerait des imitations approximatives.

Les logos viennent de deux endroits :

* **livrés avec l'outil** (`lmu_telemetry/ressources/logos/`) : les 10 marques
  dont le logo est libre de droits sur Wikimedia Commons — Alpine, BMW, Ford,
  Isotta Fraschini, Lexus, Ligier, McLaren, Mercedes, Oreca, Toyota. Ils sont
  dans le .exe ;
* **les tiens**, dans le dossier `logos` de ton dossier de données (voir « Où
  l'outil range ses fichiers ») : les 10 autres, tirés de Wikipédia, où ils ne
  sont utilisés qu'au titre de l'usage équitable. Ils sont là pour ton usage
  perso et **ne sont pas mis dans le .exe**.

Les tiens l'emportent sur ceux livrés. Pour en ajouter ou en changer un,
dépose un fichier nommé d'après la marque telle qu'elle s'affiche :

```
logos\
  Porsche.png
  Ferrari.svg
  Aston Martin.png
```

Les formats acceptés sont `.svg`, `.png`, `.webp`, `.jpg` et `.gif`. Relance
l'outil : les fichiers trouvés remplacent les pastilles. Seul ADESS n'a de
logo nulle part. D'où vient chacun, et sous quelle licence : le fichier
`SOURCES.md` de chacun des deux dossiers.

Beaucoup de logos sont noirs (Aston Martin, McLaren, le cheval Ferrari…) et
disparaîtraient sur le fond sombre. L'outil les corrige tout seul à
l'affichage, sans toucher aux fichiers : un logo noir ou gris foncé passe en
clair, un logo de couleur trop sombre (le bleu marine d'Oreca) est éclairci, et
un logo sans transparence (un JPG sur fond blanc) perd son fond. Ça vaut aussi
pour les logos que tu ajoutes : dépose-les tels quels, de préférence en PNG
transparent.

### La numérotation des virages

Les virages sont numérotés **T1, T2, T3…** dans l'ordre du tour, et les deux
moitiés d'une chicane comptent pour deux virages : à Monza, la Variante del
Rettifilo est T1 et T2, la Variante Ascari est T8, T9 et T10. C'est la
numérotation des cartes de circuit, et c'est aussi ce qui permet de lire
séparément le freinage d'entrée et la réaccélération de sortie.

Les mêmes numéros sont posés **sur la carte du circuit**, en bas de la page de
comparaison, dans une pastille à l'extérieur de chaque virage.

Une flèche indique le sens : ↱ à droite, ↰ à gauche. Tout est déduit de la
forme du circuit, rien d'une table.

À Monza, l'outil retrouve exactement les 11 virages officiels. Ailleurs, le
compte peut différer : le nombre officiel d'un circuit est une convention et
inclut parfois des coudes très légers. Si un découpage ne te convient pas,
ouvre le fichier du circuit dans le dossier `virages` de ton dossier de
données — son chemin exact est rappelé sous le tableau par virage : tu peux y déplacer les
bornes, supprimer un virage, ou remplir le champ `nom` pour qu'il s'affiche
« T3 — Curva Grande ». Ce que tu écris n'est jamais écrasé.

### Le drapeau du circuit

Le drapeau vient d'une table écrite à la main, qui couvre les seize circuits
livrés avec le jeu. Un circuit ajouté plus tard n'aura pas de drapeau tant que
tu ne l'auras pas déclaré. Pour l'ajouter, crée `pays.json` dans ton dossier
de données :

```json
{
  "nordschleife": "DE",
  "zandvoort": "NL"
}
```

À gauche, un morceau du nom du circuit en minuscules ; à droite, le code du
pays sur deux lettres. Un fichier mal écrit est ignoré sans rien casser.

### L'angle volant

Le jeu n'enregistre le braquage qu'en **pourcentage** de la butée, ce qui ne se
compare pas d'une voiture à l'autre : 40 % font 117° sur ta Porsche mais 67°
sur une Oreca, parce que les volants n'ont pas le même débattement. L'outil lit
le débattement de la voiture dans le fichier et affiche donc des **degrés**.

Si le réglage est illisible — ça n'est jamais arrivé sur tes 388 sessions, mais
une mise à jour du jeu pourrait le changer —, l'affichage retombe sur le
pourcentage plutôt que de montrer un angle faux.

### Voir ses sessions

```bash
.venv\Scripts\python.exe -m lmu_telemetry sessions
```

```
  n°  date             circuit                         type    taille
------------------------------------------------------------------------
   1  2026-09-08 13:02 Autodromo Nazionale Monza       P         9.6M
   2  2026-09-08 12:52 Autodromo Nazionale Monza       P         9.9M
   4  2026-09-08 12:12 Autodromo Nazionale Monza       P         9.0M
```

`P` = essais, `Q` = qualifications, `R` = course.

Pour ne voir qu'un circuit, ou qu'un type de session :

```bash
.venv\Scripts\python.exe -m lmu_telemetry sessions --circuit monza --type P
```

Les numéros de la première colonne ne dépendent pas du filtre : le numéro 4
désigne la même session que tu filtres ou non.

En revanche ils sont attribués par date, du plus récent au plus ancien : **ils
se décalent dès que tu roules une nouvelle session.** Ils sont faits pour taper
vite, pas pour être notés quelque part. Pour désigner une session de façon
durable, utilise son chemin de fichier complet.

### Voir les tours d'une session

```bash
.venv\Scripts\python.exe -m lmu_telemetry tours 4
```

```
 tour      chrono  mesuré ±0,02       S1       S2       S3   v.min     remarques
----------------------------------------------------------------------------------
    4           —       2:19.64        —        —        —      0  ✗  passage par les stands
    5    1:54.326       1:54.32   37.321   39.431   37.573     50  ✓  hors piste 1.8 s
    6    1:53.414       1:53.41   37.582   38.358   37.474     46  ★
```

* **chrono** — le temps officiel, celui que le jeu t'a affiché.
* **mesuré** — le même temps, recalculé par l'outil entre deux franchissements
  de ligne. Les deux colonnes doivent coïncider : c'est le contrôle qui prouve
  que l'outil lit correctement tes données. Quelques centièmes d'écart sont
  normaux — l'événement de franchissement n'est inscrit qu'à ±0,02 s près, d'où
  l'affichage au centième. Un écart de plusieurs secondes, lui, veut dire que le
  tour n'est pas comparable aux autres (typiquement le tour de départ d'une
  course, où la voiture attend sur la grille).
* **S1 / S2 / S3** — les temps aux trois secteurs.
* **v.min** — la vitesse la plus basse du tour, en km/h. Sur un tour normal
  c'est ton virage le plus lent. Une valeur très basse veut dire que tu t'es
  quasiment arrêté.
* **★** meilleur tour, **✓** tour valide, **✗** tour écarté des statistiques.

Un tour est écarté s'il passe par les stands, s'il n'est pas bouclé, ou si le
jeu ne l'a pas chronométré — dans ce dernier cas c'est le jeu lui-même qui l'a
invalidé, pour dépassement des limites de piste.

Un tour peut être valide **et** porter des remarques : un contact ou un passage
sur l'herbe n'annule pas un tour que le jeu a chronométré. L'outil signale ce
qu'il voit et te laisse décider.

### Voir la structure brute d'un fichier

```bash
.venv\Scripts\python.exe -m lmu_telemetry info 4
```

Liste les 58 canaux et les 40 événements du fichier, avec leur fréquence et
leur unité. Utile si un jour une mise à jour du jeu change quelque chose.

---

## Problèmes courants

**« Cette session est en cours d'enregistrement par le jeu »**
Le Mans Ultimate garde le fichier de la session en cours ouvert en écriture.
Quitte la session (ou le jeu), puis réessaie.

**L'outil demande « Où sont tes sessions ? »**
Il n'a pas trouvé le jeu dans tes bibliothèques Steam. Indique le dossier
`UserData\Telemetry` du jeu : l'écran explique comment le trouver, et le choix
est retenu. En ligne de commande, l'option `--dossier` fait la même chose :

```bash
.venv\Scripts\python.exe -m lmu_telemetry --dossier "E:\Jeux\Le Mans Ultimate\UserData\Telemetry" sessions
```

**« L'outil ne répond plus »**
La fenêtre de l'outil a été fermée alors que la page était encore ouverte.
Relance l'outil, puis recharge la page (F5).

**« Version de format non reconnue »**
Une mise à jour du jeu a changé la structure des fichiers. Un seul fichier de
l'outil est à corriger, `lmu_telemetry/reader.py` — c'est fait exprès.

**« L'outil a rencontré un problème inattendu »**
C'est un défaut de l'outil, pas une erreur de manipulation. Le message donne
un détail technique, et la trace complète s'affiche dans la fenêtre de
l'outil : c'est ce qu'il faut regarder pour corriger.

**Un ⚠ « journal .wal » à côté d'une session**
Le jeu n'a pas refermé cette session proprement (plantage ou Alt+F4). Les
données présentes restent lisibles, mais la fin peut manquer.

**Le delta fait un saut vertical**
Un des deux tours s'est arrêté en piste. Pendant l'arrêt la distance n'avance
plus alors que le temps continue : la comparaison par distance ne sait pas
représenter ça. L'outil te prévient en haut de l'écran quand c'est le cas.

**La courbe de delta oscille de quelques centièmes dans un virage lent**
C'est du bruit, pas du pilotage. La distance n'est mesurée qu'à 10 Hz par le
jeu, et à basse vitesse un demi-mètre d'imprécision fait quatre centièmes de
seconde. Un décrochage de plusieurs dixièmes, lui, est réel.

**Le port 8770 est déjà utilisé**
Le .exe s'en charge seul : si l'outil est déjà ouvert, il réaffiche sa page ;
si un autre programme tient le port, il prend le suivant. En ligne de
commande, choisis-en un autre : `python -m lmu_telemetry web --port 8790`.

**« Cette session ne contient que N tour(s) valide(s) »**
La page régularité a besoin d'au moins trois tours propres pour dire quoi que ce
soit d'une dispersion. Choisis une session plus longue, ou roule quelques tours
de plus.

**Un virage est mal découpé**
Le découpage de chaque circuit est enregistré dans `virages\<Circuit>.json`, dans
ton dossier de données, un fichier texte fait pour être modifié. Tu peux y ajuster les distances de début
et de fin, donner un nom à un virage (« Parabolica » plutôt que « Virage 8 »),
ou en supprimer un qui ne t'intéresse pas. Une fois le fichier créé, l'outil ne
le regénère jamais — supprime-le si tu veux repartir de la détection
automatique.

---

## Pour développer

```bash
.venv\Scripts\python.exe -m pytest
```

Les tests tournent **sans le jeu** : la session de test est fabriquée par
`tests/fixtures/construire.py`, avec un scénario aux résultats connus d'avance
(sortie des stands, tour propre, tour invalidé, tour avec incident, tour non
bouclé). Quelques tests supplémentaires s'exécutent en plus sur de vraies
sessions quand LMU est installé sur la machine, et sont ignorés sinon.

### Organisation du code

| Fichier | Rôle |
|---|---|
| `lmu_telemetry/reader.py` | **le seul module qui connaît le format des `.duckdb` de télémétrie.** Si LMU change ce format, c'est ici et nulle part ailleurs. |
| `lmu_telemetry/resultats.py` | **le seul module qui connaît le format des `.xml` de résultats.** C'est de là que vient le modèle de la voiture. |
| `lmu_telemetry/pays.py` | pays de chaque circuit, pour le drapeau. Table écrite à la main, complétable sans toucher au code. |
| `lmu_telemetry/session.py` | découpage en tours, chronos, validité. Ne sait rien de DuckDB. |
| `lmu_telemetry/donnees_tour.py` | extrait un tour sur un axe de distance. |
| `lmu_telemetry/comparaison.py` | aligne deux tours et calcule le delta cumulé. |
| `lmu_telemetry/piste.py` | reconstruit la géométrie de la route (axe, bords) pour la vue rapprochée. |
| `lmu_telemetry/virages.py` | découpe le circuit en virages et mesure le pilotage sur chacun. |
| `lmu_telemetry/regularite.py` | dispersion des chronos, constance par virage, tour idéal. |
| `lmu_telemetry/web/` | serveur local et interface. Graphiques écrits à la main en canvas, aucune bibliothèque à télécharger. |
| `lmu_telemetry/catalogue.py` | repérage des fichiers sur le disque, et du jeu dans les bibliothèques Steam. |
| `lmu_telemetry/emplacements.py` | où vont les ressources livrées et les données de l'utilisateur. |
| `lmu_telemetry/lanceur.py` | ce qui se passe au double-clic sur le .exe. |
| `lmu_telemetry/textes.py` | les messages que le serveur envoie à traduire, et le français de la ligne de commande. |
| `lmu_telemetry/web/statique/langues/` | toutes les phrases de l'outil, en français et en anglais. |
| `lmu_telemetry/ressources/` | livré avec l'outil : découpages de référence, logos libres, icône. |
| `lmu_telemetry/errors.py` | messages d'erreur qui disent quoi faire. |
| `lmu_telemetry/cli.py` | la ligne de commande. |
| `tools/discover.py` | dump la structure réelle d'un fichier. |
| `tools/inventory.py` | balaye tout le dossier et vérifie que chaque fichier est lisible. |
| `construire-exe.bat`, `tools/construire_exe.py`, `telemetrie-lmu.spec` | la fabrication du .exe. |
| `tools/icone.py` | dessine l'icône du .exe à partir de l'emblème de la page. |

### Documentation

* [docs/01-decouverte.md](docs/01-decouverte.md) — le format des fichiers LMU,
  vérifié sur 377 sessions : structure des tables, recalage temporel, liste des
  canaux, pièges.
* [docs/02-lecture-tours.md](docs/02-lecture-tours.md) — comment les tours et
  les chronos sont reconstruits, et comment les seuils ont été calibrés.
* [docs/03-comparaison.md](docs/03-comparaison.md) — l'axe de distance, le calcul
  du delta cumulé, et ce que la courbe ne sait pas représenter.
* [docs/04-virages.md](docs/04-virages.md) — comment le circuit est découpé, et
  pourquoi ni l'angle volant ni l'accélération latérale ne pouvaient servir.
* [docs/05-regularite.md](docs/05-regularite.md) — sur quoi les virages sont
  classés, et pourquoi pas sur un écart-type.
* [docs/06-voiture-et-volant.md](docs/06-voiture-et-volant.md) — où le jeu
  cache le modèle des voitures, pourquoi les coordonnées GPS sont factices, et
  comment l'échelle du braquage a été établie.
* [docs/07-sorties-de-piste.md](docs/07-sorties-de-piste.md) — comment un seul
  tour parti dans le dégagement faussait le découpage d'un circuit entier.
* [docs/09-variantes.md](docs/09-variantes.md) — pourquoi deux tracés du même
  circuit portent le même nom de fichier, et ce que ça faussait.
* [docs/08-numerotation.md](docs/08-numerotation.md) — un numéro par apex,
  chicanes séparées : comment le seuil a été réglé, et pourquoi le compte
  officiel n'est atteint qu'à Monza.
* [docs/10-distribution.md](docs/10-distribution.md) — le .exe : ce qu'il
  contient, où il range ses fichiers, comment il trouve le jeu chez les
  autres, et les défauts que ce travail a fait apparaître.
* [docs/11-langues.md](docs/11-langues.md) — le français et l'anglais : où sont
  les textes, comment en ajouter ou en corriger un, et ce que vérifient les tests.
