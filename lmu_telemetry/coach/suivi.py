"""Où en est la voiture sur le tour, à chaque échantillon.

--------------------------------------------------------------------------
Pourquoi une estimation
--------------------------------------------------------------------------

En direct, `mLapDist` n'arrive qu'à 5 Hz, soit un point tous les 15 m à 270 km/h :
beaucoup trop grossier pour situer un point de freinage. Entre deux mises à jour,
on repart de la dernière valeur et on ajoute le chemin parcouru à la vitesse
mesurée. Vérifié sur le jeu : 1 à 2 cm d'écart médian, moins de 2 m au 99e centile
(voir docs/12-memoire-partagee.md).

--------------------------------------------------------------------------
Deux distances
--------------------------------------------------------------------------

* `distance` part de la ligne : c'est celle des fichiers de virages.
* `parcouru` ne repart jamais de zéro. Elle traverse la ligne sans saut, si bien
  qu'un freinage commencé à la fin d'un tour pour un virage situé au début du
  suivant reste une seule portion de piste, sans cas particulier.

--------------------------------------------------------------------------
Les ruptures
--------------------------------------------------------------------------

L'horloge du jeu repart de zéro à chaque session. La voiture peut aussi être
replacée sans avoir roulé : retour au garage, retour en piste après une sortie.
Dans les deux cas, ce qui précède ne se raccorde plus à ce qui suit. Le suivi le
signale, et il n'invente aucun lien entre les deux.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..sources.echantillon import Echantillon

#: Écart (m) entre l'estimation et le jeu au-delà duquel ce n'est plus une erreur
#: d'estimation. Les coupes de chicane font sauter `mLapDist` de 22 m au plus.
ECART_RUPTURE = 150.0

#: Mises à jour successives en désaccord avant de croire le jeu. Une seule peut
#: venir du scoring qui a franchi la ligne avant la télémétrie : il repart de zéro
#: une fraction de seconde avant que le numéro de tour ne change.
DESACCORDS_TOLERES = 2

#: Trou dans le flux (s) au-delà duquel on ne sait plus ce qui s'est passé.
TROU_MAXIMAL = 0.5


@dataclass(frozen=True, slots=True)
class Position:
    """Ce que le suivi sait de la voiture à cet instant."""

    distance: float
    """Mètres depuis la ligne."""

    parcouru: float
    """Mètres depuis le début du suivi, sans remise à zéro à la ligne."""

    tour: int

    ligne: bool = False
    """La ligne vient d'être franchie."""

    rupture: bool = False
    """Ce qui précède ne se raccorde pas à cet échantillon."""


class SuiviTour:
    """Tient la position à jour, un échantillon après l'autre."""

    def __init__(self) -> None:
        self._temps: float | None = None
        self._vitesse = 0.0
        self._tour: int | None = None
        self._debut_tour = 0.0
        self._distance: float | None = None
        self._parcouru = 0.0
        self._desaccords = 0
        self._rompu = False

    def avancer(self, e: Echantillon) -> Position | None:
        """La position à cet échantillon. None tant que la distance n'est pas connue."""
        if self._temps is not None and (
            e.temps < self._temps or e.temps - self._temps > TROU_MAXIMAL
        ):
            self._rompu = True
            self._distance = None
            self._tour = None

        if self._distance is not None:
            # Trapèze : la vitesse varie de 10 km/h par échantillon au freinage.
            pas = (e.vitesse + self._vitesse) / 7.2 * (e.temps - self._temps)
            self._distance += pas
            self._parcouru += pas
        self._temps = e.temps
        self._vitesse = e.vitesse

        ligne = self._tour is not None and e.tour != self._tour
        if ligne:
            # Le jeu donne l'instant exact du franchissement, entre deux échantillons.
            self._distance = e.vitesse / 3.6 * (e.temps - e.debut_tour)
        self._tour = e.tour
        self._debut_tour = e.debut_tour

        if e.distance is not None and e.temps_distance >= self._debut_tour:
            self._recaler(e)
        if self._distance is None:
            return None
        rupture, self._rompu = self._rompu, False
        return Position(self._distance, self._parcouru, e.tour, ligne, rupture)

    def _recaler(self, e: Echantillon) -> None:
        """Repart de la valeur du jeu, ou note que la voiture a changé de place."""
        selon_le_jeu = e.distance + e.vitesse / 3.6 * (e.temps - e.temps_distance)
        if self._distance is None:
            self._distance = selon_le_jeu
            return
        ecart = selon_le_jeu - self._distance
        if abs(ecart) <= ECART_RUPTURE:
            self._desaccords = 0
            self._distance = selon_le_jeu
            self._parcouru += ecart
            return
        self._desaccords += 1
        if self._desaccords > DESACCORDS_TOLERES:
            self._desaccords = 0
            self._distance = selon_le_jeu
            self._rompu = True
