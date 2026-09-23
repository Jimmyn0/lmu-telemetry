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
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import DossierIntrouvable

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

#: Index déjà construit, avec la signature du dossier qui l'a produit.
#: Reconstruire coûte 0,4 s pour 414 fichiers : inutile de garder ça sur
#: disque, mais inutile aussi de le refaire à chaque page affichée.
_cache: dict[Path, tuple[tuple[int, float], dict[str, Voiture]]] = {}


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
    try:
        racine = Path(dossier) if dossier is not None else dossier_resultats()
    except DossierIntrouvable:
        return {}
    if not racine.is_dir():
        return {}

    signature = _signature(racine)
    connu = _cache.get(racine)
    if connu is not None and connu[0] == signature:
        return connu[1]

    index: dict[str, Voiture] = {}
    for fichier in racine.glob("*.xml"):
        try:
            racine_xml = ET.parse(fichier).getroot()
        except (ET.ParseError, OSError):
            continue  # fichier tronqué ou verrouillé : il en reste 413 autres
        for pilote in racine_xml.iter("Driver"):
            engagement = pilote.findtext("VehName")
            modele = pilote.findtext("CarType")
            if not engagement or not modele or engagement in index:
                continue
            index[engagement] = Voiture(
                engagement=engagement,
                modele=modele,
                classe=pilote.findtext("CarClass") or "",
                marque=marque(modele),
            )

    _cache[racine] = (signature, index)
    return index


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
