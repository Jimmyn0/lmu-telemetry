"""Couche d'abstraction sur les fichiers de résultats de Le Mans Ultimate.

C'EST LE SEUL MODULE QUI CONNAÎT LE FORMAT XML DES RÉSULTATS.

C'est la deuxième source de données de l'outil, à côté de `reader.py` qui lit
les `.duckdb` de télémétrie. Les deux sont séparés exprès : une mise à jour du
jeu qui casserait l'un ne touche pas l'autre.

--------------------------------------------------------------------------
Pourquoi ce module existe
--------------------------------------------------------------------------

Le fichier de télémétrie ne contient PAS le modèle de la voiture. Son champ
`CarName` vaut par exemple :

    Manthey DK Engineering 2026 #91:WEC

C'est l'engagement — l'écurie, l'année, le numéro, le championnat — pas la
voiture. Le modèle réel se trouve dans les fichiers de résultats que le jeu
écrit à chaque session, sous UserData\\Log\\Results\\*.xml, où chaque pilote a
un bloc :

    <VehName>Manthey DK Engineering 2026 #91:WEC</VehName>   <- = CarName
    <CarType>Porsche 911 GT3 R LMGT3</CarType>               <- le modèle
    <CarClass>GT3</CarClass>

`VehName` est identique au `CarName` de la télémétrie : c'est la clé qui relie
les deux sources.

--------------------------------------------------------------------------
Format réel, vérifié le 2026-09-09 sur 414 fichiers
--------------------------------------------------------------------------

* Racine `<rFactorXML><RaceResults>`, suivie de 26 balises d'en-tête toujours
  présentes (`TrackVenue`, `TrackLength`, `DateTime`...), puis d'UN bloc de
  session dont le nom varie : `Practice1` (243 fichiers), `Race` (106),
  `Qualify` (64). D'autres noms sont possibles : on ne suppose donc rien et on
  prend tout enfant qui n'est pas une balise d'en-tête connue.

* `TrackVenue` reprend mot pour mot le `TrackName` de la télémétrie.

* `DateTime` est un horodatage Unix (donc UTC, sans ambiguïté) et `TimeString`
  la même date en heure locale. Vérifié : l'écart vaut exactement +2 h sur les
  59 fichiers testés, ce qui est le fuseau de la machine, pas une propriété du
  format. C'est donc `DateTime` qui ferait foi si on datait ces fichiers.

* Un fichier sur 414 est syntaxiquement invalide (écriture interrompue). La
  lecture doit l'ignorer sans faire échouer le reste.

--------------------------------------------------------------------------
Le classement d'une séance
--------------------------------------------------------------------------

Chaque fichier donne aussi la séance entière : le classement, la grille, et
chaque tour de chaque voiture, avec sa position, son chrono, ses secteurs, sa
vitesse de pointe et ses gommes (`lire_session`). C'est ce que montre l'écran
Résultats : le `.duckdb` ne connaît que la voiture du joueur.

Vérifié le 2026-11-09 sur 571 fichiers :

* un tour sans temps s'écrit « --.---- », et ses secteurs manquent alors en
  partie (12 871 tours sur 32 524 sans troisième secteur) ;
* les secteurs ne sont pas cumulés : leur somme fait le tour ;
* un tour passé aux stands porte `pit="1"` ;
* les gommes s'écrivent « 0,Medium », « 1,Wet » ; « 15,N/A » quand le jeu
  n'en sait rien ;
* `FinishStatus` vaut « Finished Normally », « DNF », « DQ », ou « None »
  hors course ;
* une course au temps a `Laps` = 2147483647 et sa durée dans `Minutes` ;
* l'horodatage d'un tour (`et`) est celui de son départ, sur l'horloge de la
  séance : en course, tous les premiers tours partent au drapeau vert, et le
  temps à l'arrivée (`FinishTime`) se compte depuis lui.

Le journal de la séance (`Stream`) donne les incidents (`evenements`) :

* « A(4) reported contact (115.48) with another vehicle B(17) » : un contact
  entre deux voitures, que chacune rapporte ; « … with Immovable » (le décor),
  « Post », « Sign », « Wheel », « Wing », « Cone » : un contact avec un objet ;
* `TrackLimits` : une sortie des limites de piste, et la suite que le jeu lui
  donne (« No Further Action » dans 87 % des cas, « Warning », « Invalid Lap
  Cut Track », une pénalité) ;
* `Penalty` : une pénalité reçue (type, motif, durée en attributs), ou purgée
  (« A served 1st Drive Thru penalty… », sans attributs) ;
* `ChatMessage` : un message du chat, « Auteur: texte » (1 300 sur le disque, tous
  dans des séances en ligne).

Une séance en ligne a `Setting` = « Multiplayer » (342 fichiers), une séance seul
contre l'IA « Race Weekend » (225). En ligne, le fichier marque tous les humains
comme joueurs (`isPlayer`).
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from ..cache import CacheBorne
from ..errors import DossierIntrouvable

#: Variable d'environnement pour forcer l'emplacement des résultats.
VARIABLE_ENV = "LMU_RESULTATS"

#: Chemin des résultats relativement au dossier `UserData` du jeu.
SOUS_DOSSIER = ("Log", "Results")

#: Marques reconnues dans un `CarType`, avec le début de chaîne qui les
#: identifie. Établie sur les 32 modèles réellement présents dans les fichiers
#: du jeu, pas de mémoire.
#:
#: Deux cas ne se devinent pas :
#:   « Corvette C8.R GTE » ne commence pas par le nom du constructeur ;
#:   « Mercedes-AMG LMGT3 » porte le nom de l'écurie de course, pas de la marque.
#: Les préfixes sont testés du plus long au plus court, pour que
#: « Aston Martin » l'emporte sur un éventuel « Aston ».
MARQUES = (
    ("isotta fraschini", "Isotta Fraschini"),
    ("aston martin", "Aston Martin"),
    ("mercedes-amg", "Mercedes"),
    ("lamborghini", "Lamborghini"),
    ("chevrolet", "Chevrolet"),
    ("mercedes", "Mercedes"),
    ("duqueine", "Duqueine"),
    ("corvette", "Chevrolet"),
    ("cadillac", "Cadillac"),
    ("mclaren", "McLaren"),
    ("ferrari", "Ferrari"),
    ("genesis", "Genesis"),
    ("ginetta", "Ginetta"),
    ("peugeot", "Peugeot"),
    ("porsche", "Porsche"),
    ("alpine", "Alpine"),
    ("ligier", "Ligier"),
    ("toyota", "Toyota"),
    ("adess", "ADESS"),
    ("oreca", "Oreca"),
    ("lexus", "Lexus"),
    ("ford", "Ford"),
    ("bmw", "BMW"),
)


@dataclass(frozen=True)
class Voiture:
    """Ce qu'on sait d'une voiture, une fois les deux sources recoupées."""

    engagement: str  # `VehName` / `CarName` : l'écurie et le numéro
    modele: str  # `CarType` : la voiture elle-même
    classe: str  # `CarClass` : GT3, Hyper, LMP2...
    marque: str  # déduite du modèle


# ----------------------------------------------------------------------
# Emplacement
# ----------------------------------------------------------------------


def dossier_resultats(
    force: Path | str | None = None, telemetrie: Path | str | None = None
) -> Path:
    """Trouve le dossier des résultats de LMU.

    Ordre : le chemin passé en argument, puis la variable d'environnement
    LMU_RESULTATS, puis — et c'est le cas normal — le dossier déduit de celui
    de la télémétrie, les deux étant frères sous `UserData`.
    """
    if force is not None:
        chemin = Path(force)
        if not chemin.is_dir():
            raise DossierIntrouvable(chemin)
        return chemin

    if depuis_env := os.environ.get(VARIABLE_ENV):
        chemin = Path(depuis_env)
        if chemin.is_dir():
            return chemin
        raise DossierIntrouvable(chemin)

    if telemetrie is None:
        from . import catalogue

        telemetrie = catalogue.dossier_telemetrie()
    return Path(telemetrie).parent.joinpath(*SOUS_DOSSIER)


# ----------------------------------------------------------------------
# Index des voitures
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class SeanceIndexee:
    """Une séance de l'index : de quoi la relier à une session de télémétrie, et les
    joueurs qui y ont roulé, tours compris, pour leurs performances."""

    debut: float  # horodatage Unix du début de la séance
    minutes: int  # durée prévue ; 0 si le fichier ne la donne pas
    fichier: Path
    engagements_joueur: frozenset[str]
    pilotes_joueurs: frozenset[str] = frozenset()
    en_ligne: bool = False
    resultats: dict[str, tuple[int | None, str]] = field(default_factory=dict)
    """Pilote -> (place dans sa catégorie, statut d'arrivée)."""

    circuit: str = ""
    parcours: str = ""
    type: str = ""
    joueurs: tuple[Engage, ...] = ()
    """Les voitures que le fichier marque comme celles d'un joueur : le propriétaire
    du PC seul contre l'IA, tous les humains en ligne."""

    engages: int = 0
    par_classe: dict[str, int] = field(default_factory=dict)
    """Catégorie -> nombre de voitures engagées."""


@dataclass
class _Index:
    voitures: dict[str, Voiture] = field(default_factory=dict)
    seances: dict[tuple[str, str], list[SeanceIndexee]] = field(default_factory=dict)
    """(circuit, type de séance) -> les séances de ce circuit et de ce type."""


#: Index déjà construit, avec la signature du dossier qui l'a produit.
#: Reconstruire coûte 0,4 s pour 414 fichiers : inutile de garder ça sur
#: disque, mais inutile aussi de le refaire à chaque page affichée.
_cache: dict[Path, tuple[tuple[int, float], _Index]] = {}


def _index(dossier: Path | str | None) -> _Index | None:
    """Les voitures et les séances de tous les fichiers, lus en un seul passage."""
    try:
        racine = Path(dossier) if dossier is not None else dossier_resultats()
    except DossierIntrouvable:
        return None
    if not racine.is_dir():
        return None

    signature = _signature(racine)
    connu = _cache.get(racine)
    if connu is not None and connu[0] == signature:
        return connu[1]

    index = _Index()
    for fichier in racine.glob("*.xml"):
        try:
            racine_xml = ET.parse(fichier).getroot()
        except (ET.ParseError, OSError):
            continue  # fichier tronqué ou verrouillé : il en reste 413 autres
        for pilote in racine_xml.iter("Driver"):
            engagement = pilote.findtext("VehName")
            modele = pilote.findtext("CarType")
            if not engagement or not modele or engagement in index.voitures:
                continue
            index.voitures[engagement] = Voiture(
                engagement=engagement,
                modele=modele,
                classe=pilote.findtext("CarClass") or "",
                marque=marque(modele),
            )
        entete = racine_xml.find("RaceResults")
        if entete is None:
            continue
        for bloc, type_ in _blocs_de_session(entete):
            debut = _nombre(bloc.findtext("DateTime"))
            if debut is None:
                continue
            pilotes = bloc.findall("Driver")
            joueurs = [d for d in pilotes if d.findtext("isPlayer") == "1"]
            index.seances.setdefault((entete.findtext("TrackVenue") or "", type_), []).append(
                SeanceIndexee(
                    debut,
                    _entier(bloc.findtext("Minutes")) or 0,
                    fichier,
                    frozenset(d.findtext("VehName") or "" for d in joueurs),
                    frozenset(d.findtext("Name") or "" for d in joueurs),
                    entete.findtext("Setting") == "Multiplayer",
                    {
                        d.findtext("Name") or "": (
                            _entier(d.findtext("ClassPosition")), d.findtext("FinishStatus") or ""
                        )
                        for d in pilotes
                    },
                    entete.findtext("TrackVenue") or "",
                    entete.findtext("TrackCourse") or "",
                    type_,
                    tuple(_engage(d) for d in joueurs),
                    len(pilotes),
                    dict(Counter(d.findtext("CarClass") or "" for d in pilotes)),
                )
            )

    _cache[racine] = (signature, index)
    return index


def index_voitures(dossier: Path | str | None = None) -> Mapping[str, Voiture]:
    """Associe chaque engagement (`CarName`) à la voiture correspondante.

    L'index se construit en lisant TOUS les fichiers de résultats : un même
    engagement peut apparaître dans n'importe quelle session, y compris une où
    l'on n'était pas au volant. Vérifié sur les 414 fichiers présents : 347
    engagements distincts, et aucun ne correspond à deux modèles différents.

    Un dossier absent renvoie un index vide plutôt qu'une erreur. Le modèle de
    la voiture est un agrément, pas une donnée dont dépend l'analyse : son
    absence ne doit pas empêcher d'ouvrir une session.
    """
    index = _index(dossier)
    return index.voitures if index is not None else {}


def voiture(engagement: str, dossier: Path | str | None = None) -> Voiture | None:
    """La voiture correspondant à un `CarName` de télémétrie, si on la connaît."""
    return index_voitures(dossier).get(engagement)


def marque(modele: str) -> str:
    """Marque déduite d'un nom de modèle.

    Le premier mot suffit dans 30 cas sur 32 ; les deux exceptions sont dans
    `MARQUES`. Un modèle inconnu retombe sur son premier mot plutôt que sur
    rien : une marque nouvelle après une mise à jour du jeu s'affichera
    correctement sans qu'on ait à toucher au code.
    """
    reduit = modele.strip().lower()
    for prefixe, nom in MARQUES:
        if reduit.startswith(prefixe):
            return nom
    mots = modele.split()
    return mots[0] if mots else ""


def _signature(racine: Path) -> tuple[int, float]:
    """Nombre de fichiers et date du plus récent : de quoi détecter une session
    ajoutée sans relire les fichiers eux-mêmes."""
    nombre = 0
    dernier = 0.0
    with os.scandir(racine) as entrees:
        for entree in entrees:
            if entree.name.endswith(".xml"):
                nombre += 1
                dernier = max(dernier, entree.stat().st_mtime)
    return nombre, dernier


# ----------------------------------------------------------------------
# Une séance complète
# ----------------------------------------------------------------------

#: Type de séance d'un bloc, comme la lettre des fichiers de télémétrie
#: (`..._R_2026-11-09T17_26_30Z.duckdb`). Le bloc s'appelle `Practice1`,
#: `Qualify` ou `Race` : on regarde le début du nom.
TYPES_SEANCE = (("Practice", "P"), ("Qualify", "Q"), ("Race", "R"), ("Warmup", "W"))

#: Au-delà, un nombre de tours n'en est pas un : une course au temps en a 2147483647.
TOURS_SANS_LIMITE = 100_000


@dataclass(frozen=True)
class TourResultat:
    """Un tour d'une voiture, tel que le fichier de résultats le donne."""

    numero: int
    position: int | None
    """Place au général à la fin du tour."""

    debut: float | None
    """Temps de séance au départ du tour (s) : au drapeau vert pour le premier tour d'une course."""

    chrono: float | None
    """None : le jeu ne l'a pas chronométré (« --.---- »)."""

    secteurs: tuple[float | None, float | None, float | None]
    """Temps de chaque secteur, non cumulés."""

    vitesse_max: float | None
    """km/h."""

    stands: bool
    gomme: str | None
    """Le composé à l'avant, nommé par le jeu : « Medium », « Soft », « Wet »..."""


@dataclass(frozen=True)
class Engage:
    """Une voiture engagée dans la séance, et son pilote."""

    nom: str
    engagement: str  # `VehName`, comme le `CarName` de la télémétrie
    modele: str
    marque: str
    classe: str
    numero: str
    equipe: str
    joueur: bool
    grille: int | None
    place: int | None
    grille_classe: int | None
    place_classe: int | None
    meilleur_tour: float | None
    temps_total: float | None
    """En course, le temps à l'arrivée (s)."""

    tours: int
    arrets: int
    statut: str
    """« Finished Normally », « DNF », « DQ », ou « None » hors course."""

    tours_detail: tuple[TourResultat, ...]


@dataclass(frozen=True)
class Evenement:
    """Un incident du journal de la séance."""

    genre: str
    """« contact », « limites », « penalite » (reçue) ou « purge » (purgée)."""

    instant: float
    """Temps de séance (s), sur la même horloge que les tours."""

    pilote: str
    autre: str | None = None
    """Contact entre deux voitures : le pilote de l'autre."""

    objet: str | None = None
    """Contact avec un objet, nommé par le jeu : « Immovable », « Post », « Sign »..."""

    intensite: float | None = None
    """Force du contact, telle que le jeu la mesure."""

    suite: str | None = None
    """Limites de piste : la suite que le jeu donne, en anglais (« Warning »...)."""

    penalite: str | None = None
    """Pénalité : son type, en anglais (« Stop/Go », « Drive Thru », « Time »...)."""

    motif: str | None = None
    secondes: float | None = None


@dataclass(frozen=True)
class Message:
    """Un message du chat d'une séance en ligne."""

    instant: float
    auteur: str
    texte: str


@dataclass(frozen=True)
class ResultatsSession:
    """Une séance : son circuit, sa durée, et ses voitures dans l'ordre du classement."""

    fichier: Path
    type: str  # "P", "Q", "R" (ou "W" pour un warm-up)
    circuit: str  # `TrackVenue`, comme le `TrackName` de la télémétrie
    parcours: str
    longueur: float | None
    debut: datetime | None
    minutes: int | None
    tours_prevus: int | None
    """Course au nombre de tours ; None pour une course au temps."""

    engages: tuple[Engage, ...]
    evenements: tuple[Evenement, ...] = ()
    messages: tuple[Message, ...] = ()
    en_ligne: bool = False


def _blocs_de_session(entete: ET.Element):
    """Les blocs de séance d'un fichier (un seul en pratique), avec leur type."""
    for bloc in entete:
        if bloc.find("Driver") is None:
            continue
        type_ = next((code for debut, code in TYPES_SEANCE if bloc.tag.startswith(debut)), None)
        yield bloc, type_ or bloc.tag[:1].upper()


def _nombre(texte: str | None) -> float | None:
    """Un nombre du fichier ; None s'il manque ou s'écrit « --.---- »."""
    if not texte:
        return None
    try:
        return float(texte)
    except ValueError:
        return None


def _entier(texte: str | None) -> int | None:
    valeur = _nombre(texte)
    return int(valeur) if valeur is not None else None


def _temps(texte: str | None) -> float | None:
    """Une durée : un temps nul ou négatif n'en est pas un."""
    valeur = _nombre(texte)
    return valeur if valeur is not None and valeur > 0 else None


def _gomme(brut: str | None) -> str | None:
    """« 0,Medium » -> « Medium » ; « 15,N/A » -> None."""
    nom = (brut or "").partition(",")[2] or (brut or "")
    return None if nom in ("", "N/A") else nom


def _tour(element: ET.Element) -> TourResultat:
    a = element.attrib
    return TourResultat(
        numero=_entier(a.get("num")) or 0,
        position=_entier(a.get("p")),
        debut=_temps(a.get("et")),
        chrono=_temps(element.text),
        secteurs=(_temps(a.get("s1")), _temps(a.get("s2")), _temps(a.get("s3"))),
        vitesse_max=_temps(a.get("topspeed")),
        stands=a.get("pit") == "1",
        gomme=_gomme(a.get("fcompound")),
    )


def _engage(pilote: ET.Element) -> Engage:
    texte = pilote.findtext
    modele = texte("CarType") or ""
    return Engage(
        nom=texte("Name") or "",
        engagement=texte("VehName") or "",
        modele=modele,
        marque=marque(modele) if modele else "",
        classe=texte("CarClass") or "",
        numero=texte("CarNumber") or "",
        equipe=texte("TeamName") or "",
        joueur=texte("isPlayer") == "1",
        grille=_entier(texte("GridPos")),
        place=_entier(texte("Position")),
        grille_classe=_entier(texte("ClassGridPos")),
        place_classe=_entier(texte("ClassPosition")),
        meilleur_tour=_temps(texte("BestLapTime")),
        temps_total=_temps(texte("FinishTime")),
        tours=_entier(texte("Laps")) or 0,
        arrets=_entier(texte("Pitstops")) or 0,
        statut=texte("FinishStatus") or "",
        tours_detail=tuple(_tour(t) for t in pilote.findall("Lap")),
    )


_CONTACT = re.compile(
    r"^(?P<pilote>.*?)\(\d+\) reported contact \((?P<force>[\d.]+)\) with "
    r"(?:another vehicle (?P<autre>.*)\(\d+\)|(?P<objet>\w+))\s*$"
)
_PURGE = re.compile(r"^(?P<pilote>.+?) served \S+ (?P<penalite>.+?) penalty")


def _evenement(element: ET.Element) -> Evenement | None:
    """Un incident du journal ; None pour le reste (scores, meilleurs secteurs, chat)."""
    instant = _nombre(element.get("et"))
    texte = (element.text or "").strip()
    if instant is None:
        return None
    if element.tag == "Incident":
        trouve = _CONTACT.match(texte)
        if trouve is None or not trouve["pilote"]:
            return None
        return Evenement(
            "contact", instant, trouve["pilote"], autre=trouve["autre"], objet=trouve["objet"],
            intensite=_nombre(trouve["force"]),
        )
    if element.tag == "TrackLimits" and element.get("Driver"):
        return Evenement("limites", instant, element.get("Driver"), suite=texte or None)
    if element.tag == "Penalty":
        if element.get("Driver"):
            return Evenement(
                "penalite", instant, element.get("Driver"), penalite=element.get("Penalty"),
                motif=element.get("Reason"), secondes=_temps(element.get("Time")),
            )
        trouve = _PURGE.match(texte)
        if trouve is not None:
            return Evenement("purge", instant, trouve["pilote"], penalite=trouve["penalite"])
    return None


def _message(element: ET.Element) -> Message | None:
    """Un message du chat, « Auteur: texte » ; None pour le reste du journal."""
    instant = _nombre(element.get("et"))
    if element.tag != "ChatMessage" or instant is None:
        return None
    auteur, separateur, texte = (element.text or "").strip().partition(": ")
    return Message(instant, auteur, texte) if separateur else Message(instant, "", auteur)


#: Séances déjà lues, par fichier et par version du fichier.
_seances_lues: CacheBorne[tuple[str, int, int], "ResultatsSession | None"] = CacheBorne(8)


def lire_session(fichier: Path | str) -> ResultatsSession | None:
    """La séance d'un fichier de résultats, classement et tours compris.

    None si le fichier est illisible ou n'a pas de bloc de séance.
    """
    chemin = Path(fichier)
    try:
        etat = chemin.stat()
    except OSError:
        return None
    return _seances_lues.obtenir(
        (str(chemin), etat.st_mtime_ns, etat.st_size), lambda: _lire_session(chemin)
    )


def _lire_session(chemin: Path) -> ResultatsSession | None:
    try:
        entete = ET.parse(chemin).getroot().find("RaceResults")
    except (ET.ParseError, OSError):
        return None
    if entete is None:
        return None
    for bloc, type_ in _blocs_de_session(entete):
        debut = _nombre(bloc.findtext("DateTime"))
        tours = _entier(bloc.findtext("Laps"))
        journal = bloc.find("Stream")
        engages = sorted(
            (_engage(p) for p in bloc.findall("Driver")),
            key=lambda e: (e.place is None, e.place or 0),
        )
        return ResultatsSession(
            fichier=chemin,
            type=type_,
            circuit=entete.findtext("TrackVenue") or "",
            parcours=entete.findtext("TrackCourse") or "",
            longueur=_temps(entete.findtext("TrackLength")),
            debut=datetime.fromtimestamp(debut, timezone.utc) if debut is not None else None,
            minutes=_entier(bloc.findtext("Minutes")),
            tours_prevus=tours if tours is not None and 0 < tours < TOURS_SANS_LIMITE else None,
            engages=tuple(engages),
            evenements=tuple(
                e for e in map(_evenement, journal if journal is not None else ()) if e is not None
            ),
            messages=tuple(
                m for m in map(_message, journal if journal is not None else ()) if m is not None
            ),
            en_ligne=entete.findtext("Setting") == "Multiplayer",
        )
    return None


# ----------------------------------------------------------------------
# Retrouver la séance d'une session de télémétrie
# ----------------------------------------------------------------------

#: Une séance peut commencer jusqu'à ce délai (s) après le début de la télémétrie :
#: l'enregistrement démarre parfois avant le départ.
AVANCE_TELEMETRIE = 300

#: Délai (s) laissé après la durée prévue d'une séance, pour une séance prolongée.
MARGE_SEANCE = 600


def trouver_session(
    circuit: str,
    type_: str,
    debut: datetime,
    engagement: str | None = None,
    dossier: Path | str | None = None,
) -> Path | None:
    """Le fichier de résultats de la séance qu'une session de télémétrie a enregistrée.

    Le fichier date la séance de son début, la télémétrie de la sortie du garage,
    parfois une heure plus tard en essais. On prend donc la dernière séance du même
    circuit et du même type commencée avant la sortie. Elle doit contenir la voiture
    du joueur, ou au moins couvrir sa sortie : vérifié sur 586 sessions, 579 y
    retrouvent sa voiture ; les 7 autres sont des essais où il en a changé en cours
    de séance, et le fichier ne garde que la dernière.
    """
    return Seances(dossier).trouver(circuit, type_, debut, engagement)


class Seances:
    """Les séances de tous les fichiers de résultats, pour en retrouver beaucoup d'un coup.

    S'assurer que le dossier n'a pas changé demande de passer sur ses 571 fichiers : le
    faire pour chacune des 587 sessions de la colonne coûtait 0,6 s par liste. On ne le
    fait qu'une fois, en créant cet objet.
    """

    def __init__(self, dossier: Path | str | None = None) -> None:
        self._index = _index(dossier)

    def toutes(self) -> list[SeanceIndexee]:
        """Toutes les séances du dossier, des plus anciennes aux plus récentes."""
        if self._index is None:
            return []
        return sorted(
            (s for liste in self._index.seances.values() for s in liste), key=lambda s: s.debut
        )

    def seance(
        self, circuit: str, type_: str, debut: datetime, engagement: str | None = None
    ) -> SeanceIndexee | None:
        """La séance d'une session de télémétrie : voir `trouver_session`."""
        if self._index is None:
            return None
        instant = debut.timestamp()
        avant = [
            s
            for s in self._index.seances.get((circuit, type_), [])
            if s.debut <= instant + AVANCE_TELEMETRIE
        ]
        if not avant:
            return None
        seance = max(avant, key=lambda s: s.debut)
        couvre = instant <= seance.debut + seance.minutes * 60 + MARGE_SEANCE
        return seance if engagement in seance.engagements_joueur or couvre else None

    def trouver(
        self, circuit: str, type_: str, debut: datetime, engagement: str | None = None
    ) -> Path | None:
        seance = self.seance(circuit, type_, debut, engagement)
        return seance.fichier if seance is not None else None

    def etiquettes(
        self,
        circuit: str,
        type_: str,
        debut: datetime,
        engagement: str | None = None,
        pilote: str | None = None,
    ) -> dict | None:
        """Ce que la colonne des sessions dit de la séance d'une session de télémétrie :
        en ligne, et victoire (premier de sa catégorie à l'arrivée d'une course). None si le
        jeu n'a pas écrit de résultats pour elle.

        Le pilote est retrouvé par son nom ; à défaut, s'il est le seul joueur du fichier.
        """
        seance = self.seance(circuit, type_, debut, engagement)
        if seance is None:
            return None
        resultat = seance.resultats.get(pilote) if pilote else None
        if resultat is None and len(seance.pilotes_joueurs) == 1:
            resultat = seance.resultats.get(next(iter(seance.pilotes_joueurs)))
        return {
            "en_ligne": seance.en_ligne,
            "victoire": type_ == "R" and resultat == (1, "Finished Normally"),
        }
