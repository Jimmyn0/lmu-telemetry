"""La mémoire du moteur : les dernières secondes, et ce qu'on en extrait pour un virage.

Un passage n'est découpé qu'une fois la zone franchie, dans un historique qui garde
tout ce qui vient d'être lu. Rien n'a besoin de savoir à l'avance dans quelle zone
se trouve la voiture, et les détecteurs travaillent sur des tableaux entiers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..sources.echantillon import Echantillon
from .suivi import Position, TROU_MAXIMAL
from .zones import Zone

#: Durée gardée, en secondes. Une zone se franchit en 30 s au plus à l'allure d'une
#: course ; au-delà, la voiture s'est arrêtée et le passage n'a plus de sens.
DUREE_HISTORIQUE = 60.0

#: Cadence la plus élevée attendue : celle de la sonde et du canal de vitesse.
FREQUENCE_MAXIMALE = 100

#: Part de la zone à avoir vue pour la juger : le moteur peut démarrer en plein
#: milieu d'un virage, ou la voiture y être replacée.
COUVERTURE_MINIMALE = 0.95

(_TEMPS, _DISTANCE, _PARCOURU, _VITESSE, _GAZ, _FREIN, _VOLANT, _HORS_PISTE, _STANDS,
 _CHOC, _R1, _R2, _R3, _R4) = range(14)
_COLONNES = 14


@dataclass(frozen=True)
class Passage:
    """Tout ce qui s'est passé sur une zone, à une ligne par échantillon."""

    zone: Zone
    tour: int

    temps: np.ndarray
    distance: np.ndarray
    """Mètres depuis la ligne du tour de la zone : négative avant la ligne."""

    vitesse: np.ndarray
    gaz: np.ndarray
    frein: np.ndarray
    volant: np.ndarray
    hors_piste: np.ndarray
    stands: np.ndarray

    dernier_choc: float
    """Instant du dernier choc connu à la fin du passage, -1 s'il n'y en a pas eu."""

    roues: np.ndarray | None
    """Vitesses des roues, en km/h, une colonne par roue. None si la source ne les a pas."""

    @property
    def temps_sortie(self) -> float:
        """Instant où la sortie du dernier virage a été franchie."""
        return float(np.interp(self.zone.sortie, self.distance, self.temps))

    def bornes(self, debut: float, fin: float) -> slice:
        """Les indices d'une portion de la zone, en mètres depuis la ligne."""
        return slice(
            int(np.searchsorted(self.distance, debut)),
            int(np.searchsorted(self.distance, fin, side="right")),
        )


class Historique:
    """Les derniers échantillons, en mémoire circulaire."""

    def __init__(self) -> None:
        self._capacite = int(DUREE_HISTORIQUE * FREQUENCE_MAXIMALE)
        self._lignes = np.zeros((self._capacite, _COLONNES))
        self._suivante = 0
        self._nombre = 0

    def vider(self) -> None:
        self._suivante = 0
        self._nombre = 0

    def ajouter(self, e: Echantillon, position: Position) -> None:
        roues = e.roues or (np.nan, np.nan, np.nan, np.nan)
        self._lignes[self._suivante] = (
            e.temps, position.distance, position.parcouru, e.vitesse, e.gaz, e.frein,
            e.volant, e.hors_piste, e.stands, e.dernier_choc, *roues,
        )
        self._suivante = (self._suivante + 1) % self._capacite
        self._nombre = min(self._nombre + 1, self._capacite)

    def _dans_l_ordre(self) -> np.ndarray:
        if self._nombre < self._capacite:
            return self._lignes[: self._nombre]
        return np.concatenate(
            (self._lignes[self._suivante :], self._lignes[: self._suivante])
        )

    def extraire(self, zone: Zone, tour: int, ligne: float) -> Passage | None:
        """Le passage sur une zone, ou None s'il n'a pas été vu en entier.

        `ligne` est le `parcouru` du franchissement de la ligne de ce tour.
        """
        lignes = self._dans_l_ordre()
        if lignes.shape[0] < 2:
            return None
        # Un recalage peut faire reculer l'estimation de quelques centimètres : la
        # recherche par dichotomie veut des valeurs qui ne redescendent jamais.
        parcouru = np.maximum.accumulate(lignes[:, _PARCOURU])
        debut = int(np.searchsorted(parcouru, ligne + zone.debut))
        fin = int(np.searchsorted(parcouru, ligne + zone.fin, side="right"))
        extrait = lignes[debut:fin]
        if extrait.shape[0] < 2:
            return None

        vu = parcouru[fin - 1] - parcouru[debut]
        if vu < COUVERTURE_MINIMALE * (zone.fin - zone.debut):
            return None
        if np.diff(extrait[:, _TEMPS]).max() > TROU_MAXIMAL:
            return None

        return Passage(
            zone=zone,
            tour=tour,
            temps=extrait[:, _TEMPS].copy(),
            distance=parcouru[debut:fin] - ligne,
            vitesse=extrait[:, _VITESSE].copy(),
            gaz=extrait[:, _GAZ].copy(),
            frein=extrait[:, _FREIN].copy(),
            volant=extrait[:, _VOLANT].copy(),
            hors_piste=extrait[:, _HORS_PISTE] > 0,
            stands=extrait[:, _STANDS] > 0,
            dernier_choc=float(extrait[-1, _CHOC]),
            roues=None if np.isnan(extrait[0, _R1]) else extrait[:, _R1 : _R4 + 1].copy(),
        )
