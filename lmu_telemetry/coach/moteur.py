"""Le moteur : du flux d'échantillons aux événements de la session.

Le direct et le rejeu passent tous les deux ici, un échantillon à la fois. Ce qui
a été vérifié sur un enregistrement vaut donc pour la piste.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from ..domaine.virages import DefinitionCircuit
from ..parametres import SeuilsCoach, SeuilsVirage
from ..sources.echantillon import Echantillon
from .detecteurs import Constat, Mesures, constats, mesurer
from .passage import Historique, Passage
from .roues import EtalonnageRoues
from .suivi import Position, SuiviTour
from .zones import Zone, zones

#: Temps laissé au jeu pour publier le chrono (s). Mesuré : 0,03 s après la ligne,
#: mais il passe par le scoring, qui n'est mis à jour que toutes les 0,2 s.
DELAI_CHRONO = 0.5

#: Pourquoi un passage n'est pas jugé.
ECARTE_SORTIE_STANDS = "sortie_stands"
ECARTE_STANDS = "stands"
ECARTE_HORS_PISTE = "hors_piste"
ECARTE_CHOC = "choc"
ECARTE_ARRET = "arret"


@dataclass(frozen=True)
class TourTermine:
    """La ligne vient d'être franchie."""

    tour: int
    temps: float
    chrono: float | None
    """None si le jeu n'a pas chronométré ce tour."""


@dataclass(frozen=True)
class Rupture:
    """Ce qui suit ne se raccorde pas à ce qui précède : nouvelle session, voiture replacée."""

    temps: float


@dataclass(frozen=True)
class BilanPassage:
    """Ce que le moteur conclut d'un passage."""

    passage: Passage

    mesures: Mesures | None = None
    """None si le passage a été écarté."""

    constats: tuple[Constat, ...] = ()
    """Le plus important d'abord."""

    ecarte: str | None = None
    """Pourquoi ce passage n'a pas été jugé. None s'il l'a été."""

    @property
    def conseil(self) -> Constat | None:
        """L'unique conseil à donner, s'il y en a un."""
        return self.constats[0] if self.constats else None


@dataclass(frozen=True)
class _ZoneAttendue:
    seuil: float
    """`parcouru` à partir duquel la zone est franchie."""

    zone: Zone
    tour: int
    ligne: float
    """`parcouru` de la ligne de ce tour."""


class Moteur:
    """Découpe le flux en passages et rend ce qu'il en conclut."""

    def __init__(
        self,
        definition: DefinitionCircuit,
        coach: SeuilsCoach = SeuilsCoach(),
        virages: SeuilsVirage = SeuilsVirage(),
    ) -> None:
        self.definition = definition
        self.coach = coach
        self.virages = virages
        self.zones = zones(definition, coach, virages)
        self._suivi = SuiviTour()
        self._historique = Historique()
        self._etalonnage = EtalonnageRoues()
        self._attendues: deque[_ZoneAttendue] = deque()
        self._tour_a_clore: tuple[int, float] | None = None
        self._en_route = False
        self._tour_aux_stands: int | None = None

    def traiter(self, e: Echantillon) -> list:
        """Ce que cet échantillon a déclenché : le plus souvent, rien."""
        position = self._suivi.avancer(e)
        if position is None:
            return []
        evenements: list = []
        if position.rupture:
            self._historique.vider()
            self._attendues.clear()
            self._etalonnage = EtalonnageRoues()
            self._tour_a_clore = None
            self._en_route = False
            evenements.append(Rupture(e.temps))
        self._historique.ajouter(e, position)
        self._etalonnage.observer(e)
        if e.stands:
            self._tour_aux_stands = e.tour

        if position.ligne:
            # Rien de ce tour ne viendra plus : ce qui manque à une zone manquera.
            self._fermer_zones(evenements, position.parcouru, fin_de_tour=True)
            self._tour_a_clore = (position.tour - 1, e.temps)
        if position.ligne or not self._en_route:
            self._planifier(position)
        self._fermer_zones(evenements, position.parcouru)

        if self._tour_a_clore and e.temps - self._tour_a_clore[1] >= DELAI_CHRONO:
            tour, instant = self._tour_a_clore
            evenements.append(TourTermine(tour, instant, e.dernier_chrono))
            self._tour_a_clore = None
        return evenements

    def _planifier(self, position: Position) -> None:
        """Les zones à franchir sur ce tour."""
        ligne = position.parcouru - position.distance
        self._en_route = True
        self._attendues.extend(
            _ZoneAttendue(ligne + zone.fin, zone, position.tour, ligne)
            for zone in self.zones
            if ligne + zone.fin > position.parcouru
        )

    def _fermer_zones(
        self, evenements: list, parcouru: float, fin_de_tour: bool = False
    ) -> None:
        longueur = self.definition.longueur
        while self._attendues:
            attendue = self._attendues[0]
            finie = parcouru >= attendue.seuil or (fin_de_tour and attendue.zone.fin <= longueur)
            if not finie:
                return
            self._attendues.popleft()
            passage = self._historique.extraire(attendue.zone, attendue.tour, attendue.ligne)
            if passage is not None:
                evenements.extend(self.juger(passage))

    def _raison_d_ecarter(self, p: Passage) -> str | None:
        """Ce qui fausserait le jugement : le pilote n'y conduit pas comme d'habitude."""
        if p.stands.any():
            return ECARTE_STANDS
        # Pneus froids, freins à chauffer : ce tour-là ne se pilote pas à la limite.
        if p.tour == self._tour_aux_stands:
            return ECARTE_SORTIE_STANDS
        if p.vitesse.min() < self.coach.vitesse_minimale:
            return ECARTE_ARRET
        # Rien ne dit que le jeu oublie le dernier choc au changement de session, et
        # l'horloge, elle, repart de zéro : seul un choc pendant le passage compte.
        if p.temps[0] <= p.dernier_choc <= p.temps[-1]:
            return ECARTE_CHOC
        if np.diff(p.temps, prepend=p.temps[0])[p.hors_piste].sum() > self.coach.hors_piste_tolere:
            return ECARTE_HORS_PISTE
        return None

    def juger(self, passage: Passage) -> list:
        raison = self._raison_d_ecarter(passage)
        if raison is not None:
            return [BilanPassage(passage, ecarte=raison)]
        mesures = mesurer(passage, self._etalonnage.echelle, self.coach, self.virages)
        trouves = constats(mesures, passage.zone.libelle, self.coach)
        return [BilanPassage(passage, mesures, tuple(trouves))]
