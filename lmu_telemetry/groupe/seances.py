"""Le classement complet des courses, partagé avec le groupe : un membre ouvre dans l'onglet
Résultats la course d'un autre, avec tout ce que l'écran en montre (classement, rythme,
positions, statistiques, incidents, chat), sans en avoir le fichier sur son PC.

Demandé le 2026-11-14. C'est la seule chose partagée qui contient les autres pilotes d'une
séance : le classement d'une course ne se montre pas sans eux. Chaque PC envoie celui de ses
courses en ligne (`synchro.py`) ; le groupe n'en reçoit que la liste, et chacun télécharge
une course quand il l'ouvre, comme la télémétrie d'un tour (`tours.py`).

Une séance se désigne « seance:<membre>/<numéro> », le numéro étant celui de la performance
(« 1794245179-R ») ; « seance:local/<numéro> », la course d'un fichier de résultats de ce PC
dont la télémétrie n'a pas été enregistrée.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import json
import re
import zlib
from pathlib import Path

from ..sources.resultats import ResultatsSession, seance_depuis_json, seance_json
from ..textes import Message
from .service import ErreurGroupe

#: La version du format ; une séance d'un autre format ne se lit pas.
FORMAT = 1

PREFIXE = "seance:"

#: La source d'une séance de ce PC.
LOCAL = "local"

#: L'identifiant d'une performance de course ou de qualifs, comme le service l'accepte.
IDENTIFIANT = re.compile(r"\d{1,12}-[QR]")

_DESIGNATION = re.compile(r"seance:(local|[A-Z0-9]{1,24})/(\d{1,12}-[QR])")

#: Garde-fou à la lecture : 16 Mo une fois décompressée (une course de 42 voitures en fait 0,3).
TAILLE_MAX = 16 * 1024 * 1024


def est_seance(valeur: object) -> bool:
    return isinstance(valeur, str) and valeur.startswith(PREFIXE)


def designer_seance(source: str, identifiant: str) -> str:
    return f"{PREFIXE}{source}/{identifiant}"


def analyser_seance(valeur: str) -> tuple[str, str]:
    """La source (un membre, ou `LOCAL`) et le numéro de la séance que désigne `valeur`."""
    trouve = _DESIGNATION.fullmatch(valeur or "")
    if trouve is None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_seance_introuvable"), "seance_introuvable")
    return trouve.group(1), trouve.group(2)


def encoder_seance(seance: ResultatsSession) -> str:
    """Une séance de ce PC, prête à partir : JSON compressé (gzip), en base64."""
    texte = json.dumps({"format": FORMAT, "seance": seance_json(seance)}, separators=(",", ":"), allow_nan=False)
    return base64.b64encode(gzip.compress(texte.encode("utf-8"), compresslevel=9)).decode("ascii")


def _decompresser(brut: bytes) -> bytes:
    """Décompresse sans jamais dépasser TAILLE_MAX, même devant une bombe de compression."""
    flux = zlib.decompressobj(16 + zlib.MAX_WBITS)
    sortie = flux.decompress(brut, TAILLE_MAX)
    if flux.unconsumed_tail:
        raise ValueError("séance trop grosse")
    return sortie


def decoder_seance(donnees: str, designation: str) -> ResultatsSession:
    """La séance d'un ami telle que reçue, vérifiée de bout en bout (`seance_depuis_json`)."""
    try:
        if not isinstance(donnees, str):
            raise ValueError("texte attendu")
        charge = json.loads(_decompresser(base64.b64decode(donnees, validate=True)))
        if not isinstance(charge, dict) or charge.get("format") != FORMAT:
            raise ValueError("format")
        return seance_depuis_json(charge.get("seance"), Path("groupe") / designation.removeprefix(PREFIXE))
    except (ValueError, TypeError, KeyError, binascii.Error, zlib.error, EOFError, OverflowError, RecursionError):
        raise ErreurGroupe(Message("serveur.erreur.groupe_seance_illisible"), "seance_illisible") from None
