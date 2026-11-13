"""GhostLine for LMU : analyse de télémétrie pour Le Mans Ultimate."""

#: Version de l'outil, affichée dans l'interface et gravée dans le .exe.
#: À augmenter à chaque version distribuée (voir NOTES-DE-VERSION.md) : le dernier
#: chiffre pour une correction, celui du milieu pour un ajout, le premier pour un grand
#: changement (2.0.0 : le nouveau nom).
__version__ = "2.0.1"

from .errors import ErreurTelemetrie
from .sources.reader import ROUES, FichierSession, InfoCanal, InfoEvenement, InfoSession
from .domaine.session import Session, Tour

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
