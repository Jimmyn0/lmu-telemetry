"""Les records partagés : la télémétrie du meilleur tour de chaque membre, sur chaque tracé
et dans chaque voiture, pour la comparer dans l'onglet Télémétrie.

Un tour partagé est rééchantillonné tous les mètres, comme l'axe de la comparaison
(`comparaison.PAS_DISTANCE`) : comparer son tour à celui d'un ami se fait au même pas
qu'entre deux tours de ce PC. Chaque canal devient une suite d'entiers (au millième, au
centième de km/h, au dix-millionième de degré pour la position) dont on garde les écarts
successifs, petits. Le tout, en JSON compressé, pèse 55 Ko pour un tour de Monza et
140 Ko pour Le Mans ; comparé à sa propre copie, un tour s'en écarte d'au plus 0,5 ms.

Ce qui part : le tour, le pilote, le tracé, la voiture et le débattement du volant. Jamais
le réglage de la voiture (`InfoSession.setup_brut`), ni le chemin du fichier.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
import math
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..domaine.donnees_tour import CANAL_GAZ_BRUT, CANAL_HORS_PISTE, CANAL_VOLANT, DonneesTour
from ..domaine.performances import _entier, _nombre, _texte
from ..domaine.session import Tour
from ..sources.reader import InfoSession
from ..textes import Message
from .service import ErreurGroupe

#: La version du format ; un tour d'un autre format ne se lit pas.
FORMAT = 1

#: Pas de l'axe de distance d'un tour partagé, en mètres.
PAS = 1.0

#: Ce qui désigne, pour la page, le record d'un ami : « groupe:<membre>/<numéro> ».
PREFIXE = "groupe:"

#: Garde-fous à la lecture : 40 km de piste, 32 Mo une fois décompressé.
NOMBRE_MAX = 40_000
TAILLE_MAX = 32 * 1024 * 1024

#: Les canaux d'un tour partagé, et l'échelle de chacun : la valeur est arrondie à
#: 1/échelle près. Les autres canaux ne partent pas, et ne se lisent pas.
ECHELLES = {
    "Ground Speed": 100,
    "Throttle Pos": 1000,
    CANAL_GAZ_BRUT: 1000,
    "Brake Pos": 1000,
    "Steering Pos": 1000,
    "Engine RPM": 1,
    "Fuel Level": 1000,
    "Virtual Energy": 1000,
    "GPS Latitude": 1e7,
    "GPS Longitude": 1e7,
    "Path Lateral": 1000,
    "Track Edge": 1000,
    "Gear": 1,
    CANAL_VOLANT: 10,
    CANAL_HORS_PISTE: 1,
}

#: Le temps, au millième de seconde.
ECHELLE_TEMPS = 1000

_DESIGNATION = re.compile(r"groupe:([A-Z0-9]{1,24})/([0-9a-f]{1,64})")


def identifiant_record(trace: str, voiture: str) -> str:
    """Le numéro d'un record : le même tracé et la même voiture gardent le même, et le
    meilleur tour remplace l'ancien."""
    return hashlib.sha1(f"{trace}|{voiture}".encode("utf-8")).hexdigest()[:16]


def identifiant_course(seance: str) -> str:
    """Le numéro du meilleur tour d'une course, d'après celui de sa performance
    (« 1794245179-R ») : le leaderboard le retrouve depuis la ligne de la course, sans que la
    liste des tours ait à le dire."""
    return hashlib.sha1(f"course|{seance}".encode("utf-8")).hexdigest()[:16]


def est_partage(valeur: object) -> bool:
    return isinstance(valeur, str) and valeur.startswith(PREFIXE)


def designer(membre: str, identifiant: str) -> str:
    return f"{PREFIXE}{membre}/{identifiant}"


def analyser(valeur: str) -> tuple[str, str]:
    """Le membre et le numéro du record que désigne `valeur`."""
    trouve = _DESIGNATION.fullmatch(valeur or "")
    if trouve is None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_tour_introuvable"), "tour_introuvable")
    return trouve.group(1), trouve.group(2)


@dataclass(frozen=True)
class Record:
    """Un record de ce PC à partager : où est son tour, et ce qu'en montre la liste."""

    id: str
    trace: str
    circuit: str
    voiture: str
    """Le modèle (« Porsche 911 GT3 R LMGT3 »), ou l'engagement s'il est inconnu."""

    marque: str | None
    classe: str | None
    pilote: str
    date: str
    type: str
    chemin: str
    numero: int
    chrono: float

    @property
    def signature(self) -> str:
        """Ce qui change quand le record change : un autre tour, ou un autre fichier."""
        return f"{self.chemin}|{self.numero}|{self.chrono}"

    def meta(self) -> dict:
        return {
            "id": self.id,
            "trace": self.trace,
            "circuit": self.circuit,
            "voiture": self.voiture,
            "marque": self.marque,
            "classe": self.classe,
            "pilote": self.pilote,
            "date": self.date,
            "type": self.type,
            "numero": self.numero,
            "chrono": self.chrono,
        }


@dataclass(frozen=True)
class TourPartage(DonneesTour):
    """Le record d'un ami, reçu du groupe : il se compare comme un tour de ce PC."""

    identifiant: str = ""
    """« groupe:<membre>/<numéro> » : ce que la page demande pour le revoir."""

    voiture: dict = field(default_factory=dict)
    """Le modèle, la marque et la catégorie, tels que le PC de l'ami les connaît."""


# ----------------------------------------------------------------------
# Encoder un tour de ce PC
# ----------------------------------------------------------------------


def _compacter(valeurs: np.ndarray, echelle: float) -> dict:
    entiers = np.round(np.asarray(valeurs, dtype=np.float64) * echelle)
    if not np.isfinite(entiers).all():
        # Un canal à trous (rare) : ses valeurs telles quelles, les trous à null.
        return {"v": [int(v) if math.isfinite(v) else None for v in entiers]}
    return {"d": np.diff(entiers.astype(np.int64), prepend=0).tolist()}


def encoder(donnees: DonneesTour) -> str:
    """Un tour de ce PC, prêt à partir : JSON compressé (gzip), en base64."""
    distance = np.arange(0.0, donnees.longueur, PAS)
    if not 2 <= distance.size <= NOMBRE_MAX:
        raise ValueError(f"tour de {donnees.longueur:.0f} m")
    canaux = donnees.sur_distance(distance, tuple(ECHELLES))
    tour, info = donnees.tour, donnees.info
    charge = {
        "format": FORMAT,
        "pas": PAS,
        "nombre": int(distance.size),
        "tour": {
            "numero": tour.numero,
            "chrono": tour.chrono,
            "cumul_s1": tour.cumul_s1,
            "cumul_s2": tour.cumul_s2,
            "vitesse_min": tour.vitesse_min,
            "duree_quasi_arret": tour.duree_quasi_arret,
            "duree_hors_piste": tour.duree_hors_piste,
            "contacts": tour.contacts,
        },
        "info": {
            "pilote": info.pilote,
            "circuit": info.circuit,
            "trace": info.trace,
            "type_session": info.type_session,
            "voiture": info.voiture,
            "categorie": info.categorie,
            "debattement_volant": info.debattement_volant,
            "angle_roues_max": info.angle_roues_max,
        },
        "temps": _compacter(donnees.temps_a_distance(distance), ECHELLE_TEMPS),
        "canaux": {nom: _compacter(valeurs, ECHELLES[nom]) for nom, valeurs in canaux.items()},
    }
    texte = json.dumps(charge, separators=(",", ":"), allow_nan=False)
    return base64.b64encode(gzip.compress(texte.encode("utf-8"), compresslevel=9)).decode("ascii")


# ----------------------------------------------------------------------
# Relire le tour d'un ami
# ----------------------------------------------------------------------


def _decompresser(brut: bytes) -> bytes:
    """Décompresse sans jamais dépasser TAILLE_MAX, même devant une bombe de compression."""
    flux = zlib.decompressobj(16 + zlib.MAX_WBITS)
    sortie = flux.decompress(brut, TAILLE_MAX)
    if flux.unconsumed_tail:
        raise ValueError("tour trop gros")
    return sortie


def _deplier(brut: object, echelle: float, nombre: int) -> np.ndarray:
    if not isinstance(brut, dict):
        raise ValueError(brut)
    if "d" in brut:
        ecarts = brut["d"]
        if not isinstance(ecarts, list) or len(ecarts) != nombre:
            raise ValueError("longueur")
        valeurs = np.cumsum(np.array(ecarts, dtype=np.float64))
    else:
        bruts = brut.get("v")
        if not isinstance(bruts, list) or len(bruts) != nombre:
            raise ValueError("longueur")
        valeurs = np.array([np.nan if v is None else float(v) for v in bruts], dtype=np.float64)
    if np.isinf(valeurs).any():
        raise ValueError("infini")
    return valeurs / echelle


def _positif(valeur: object) -> float:
    nombre = _nombre(valeur)
    if nombre is None or nombre < 0:
        raise ValueError(valeur)
    return nombre


def _tour(brut: dict, temps: np.ndarray) -> Tour:
    chrono = _nombre(brut.get("chrono"))
    numero = _entier(brut.get("numero"))
    contacts = _entier(brut.get("contacts")) or 0
    if numero is None or numero < 0 or contacts < 0 or (chrono is not None and not 0 < chrono < 3600):
        raise ValueError(brut)
    return Tour(
        numero=numero,
        index=0,
        debut=0.0,
        # La durée du tour est son chrono : le tour partagé ne garde ni l'avant ni l'après.
        fin=chrono if chrono is not None else float(temps[-1]),
        chrono=chrono,
        cumul_s1=_nombre(brut.get("cumul_s1")),
        cumul_s2=_nombre(brut.get("cumul_s2")),
        stands=False,
        contacts=contacts,
        duree_hors_piste=_positif(brut.get("duree_hors_piste", 0.0)),
        vitesse_min=_positif(brut.get("vitesse_min")),
        duree_quasi_arret=_positif(brut.get("duree_quasi_arret", 0.0)),
    )


def _info(brut: dict) -> InfoSession:
    return InfoSession(
        pilote=_texte(brut["pilote"], 64),
        circuit=_texte(brut["circuit"]),
        trace=_texte(brut["trace"]),
        type_session=_texte(brut["type_session"], 40),
        voiture=_texte(brut["voiture"]),
        categorie=_texte(brut.get("categorie") or "", 40, vide=True),
        meteo="",
        enregistree_le=None,
        version_schema="partage",
        setup_brut=None,
        debattement_volant=_nombre(brut.get("debattement_volant")),
        angle_roues_max=_nombre(brut.get("angle_roues_max")),
    )


def decoder(donnees: str, identifiant: str, voiture: dict | None = None) -> TourPartage:
    """Le tour d'un ami tel que reçu, vérifié de bout en bout : ce qui ne se lit pas,
    ou dépasse les garde-fous, est refusé."""
    try:
        if not isinstance(donnees, str):
            raise ValueError("texte attendu")
        charge = json.loads(_decompresser(base64.b64decode(donnees, validate=True)))
        if not isinstance(charge, dict) or charge.get("format") != FORMAT or charge.get("pas") != PAS:
            raise ValueError("format")
        nombre = charge.get("nombre")
        if isinstance(nombre, bool) or not isinstance(nombre, int) or not 2 <= nombre <= NOMBRE_MAX:
            raise ValueError("nombre")
        temps = _deplier(charge["temps"], ECHELLE_TEMPS, nombre)
        if np.isnan(temps).any() or (np.diff(temps) < 0).any():
            raise ValueError("temps")
        canaux_bruts = charge.get("canaux")
        if not isinstance(canaux_bruts, dict):
            raise ValueError("canaux")
        canaux = {
            nom: _deplier(valeurs, ECHELLES[nom], nombre)
            for nom, valeurs in canaux_bruts.items()
            if nom in ECHELLES
        }
        tour = _tour(charge["tour"], temps)
        info = _info(charge["info"])
    except (ValueError, TypeError, KeyError, binascii.Error, zlib.error, EOFError, OverflowError):
        raise ErreurGroupe(Message("serveur.erreur.groupe_tour_illisible"), "tour_illisible") from None
    return TourPartage(
        tour=tour,
        info=info,
        chemin=Path("groupe") / identifiant.removeprefix(PREFIXE),
        temps=temps,
        distance=np.arange(nombre, dtype=np.float64) * PAS,
        canaux=canaux,
        identifiant=identifiant,
        voiture=voiture or {"engagement": info.voiture, "modele": None, "marque": None, "classe": None},
    )
