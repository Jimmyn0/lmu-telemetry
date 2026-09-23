"""Analyse de télémétrie pour Le Mans Ultimate."""

#: Version de l'outil, affichée dans l'interface et gravée dans le .exe.
#: À augmenter à chaque version distribuée (voir NOTES-DE-VERSION.md) :
#: le dernier chiffre pour une correction, celui du milieu pour un ajout.
__version__ = "1.0.0"

from .errors import ErreurTelemetrie
from .reader import ROUES, FichierSession, InfoCanal, InfoEvenement, InfoSession
from .session import Session, Tour

__all__ = [
    "__version__",
    "ErreurTelemetrie",
    "FichierSession",
    "InfoCanal",
    "InfoEvenement",
    "InfoSession",
    "ROUES",
    "Session",
    "Tour",
]
