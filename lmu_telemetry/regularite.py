"""Régularité d'une session : dispersion des chronos et constance par virage.

--------------------------------------------------------------------------
Sur quoi classer les virages
--------------------------------------------------------------------------

Le brief demande l'écart-type du point de freinage et celui de la vitesse
minimale, puis un classement des virages « où tu es le moins constant ». Mais on
ne peut pas classer avec ces deux-là : l'un est en mètres, l'autre en km/h, et
rien ne dit que 5 m de dispersion au freinage pèsent plus ou moins que 3 km/h en
vitesse de passage.

Le classement se fait donc sur une troisième mesure, en **secondes** : la
dispersion du temps mis à parcourir la portion de piste qui revient au virage.
Elle est comparable d'un virage à l'autre, elle se lit sans conversion, et elle
répond directement à la question — c'est du temps.

Les deux écarts-types du brief restent affichés : ils disent *comment* on est
irrégulier, là où la dispersion en secondes dit *combien ça coûte*.

--------------------------------------------------------------------------
Pourquoi pas l'écart-type
--------------------------------------------------------------------------

Un écart-type se laisse détruire par un seul mauvais tour. Cas réel, virage 9 à
Spa, temps de passage sur neuf tours :

    13,71  13,64  29,09  14,26  13,68  13,82  13,62  13,55  14,57

Un tour à 29 s au lieu de 13,7 : un incident. L'écart-type vaut alors 5,09 s et
place ce virage en tête du classement — alors que sur les huit autres tours, ce
pilote y est parmi les plus réguliers du circuit. Le suivre reviendrait à
travailler le mauvais virage.

Le classement se fait donc sur l'**écart absolu médian**, remis à l'échelle d'un
écart-type. Il ignore un passage isolé et retient ce qui se répète. Sur le même
exemple, le classement passe de [9, 5, 1, 18, 8] à [5, 18, 7, 10, 1] — le
virage 9 en disparaît, à juste titre.

L'incident n'est pas caché pour autant : quand un passage isolé pèse lourd, le
virage est signalé, parce que perdre quinze secondes une fois mérite d'être su —
simplement, ce n'est pas un problème de régularité.

--------------------------------------------------------------------------
Le tour idéal
--------------------------------------------------------------------------

Chaque portion est parcourue plusieurs fois dans la session. En prenant le
meilleur passage de chacune, on obtient le tour qu'on aurait signé en enchaînant
ses propres meilleurs moments — sans rien améliorer, juste en étant régulier.

L'écart entre ce tour idéal et le meilleur tour réel est un chiffre motivant et
honnête : c'est du temps déjà à portée, pas une projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .donnees_tour import DonneesTour, charger
from .errors import ErreurTelemetrie
from .session import Session
from .virages import DefinitionCircuit, Virage, mesurer, secteurs

#: En dessous de ce nombre de tours valides, parler de régularité n'a pas de
#: sens : trois points ne dessinent pas une dispersion.
TOURS_MINIMUM = 3

#: Nombre de passages en dessous duquel on renonce à désigner un passage
#: aberrant.
#:
#: Avec trois passages, l'écart absolu médian se réduit à la plus petite des
#: deux déviations : il suffit que deux temps soient proches pour qu'il devienne
#: minuscule et que le seuil se déclenche. Constaté sur une session de trois
#: tours à Monza : la mention apparaissait sur quatre virages sur huit, où il
#: n'y avait pourtant aucun incident. Une mention qui s'affiche partout ne veut
#: plus rien dire.
PASSAGES_POUR_ABERRANT = 5

#: En dessous de ce nombre de tours, les dispersions restent indicatives : elles
#: sont calculées et affichées, mais l'interface prévient qu'il en faudrait
#: davantage pour les prendre au sérieux.
TOURS_POUR_FIABILITE = 5


@dataclass(frozen=True)
class PassageVirage:
    """Ce qu'un tour a fait dans un virage donné."""

    tour: int
    temps: float
    """Temps mis à parcourir la portion de piste du virage, en secondes."""

    debut_freinage: float | None
    vitesse_min: float


@dataclass(frozen=True)
class StatistiquesVirage:
    """La constance d'un pilote sur un virage, sur toute une session."""

    virage: Virage
    passages: tuple[PassageVirage, ...]

    @property
    def temps(self) -> np.ndarray:
        return np.array([p.temps for p in self.passages])

    @property
    def temps_moyen(self) -> float:
        return float(self.temps.mean())

    @property
    def temps_meilleur(self) -> float:
        return float(self.temps.min())

    @property
    def temps_median(self) -> float:
        """Temps de passage habituel. Préféré à la moyenne pour l'affichage :
        un seul incident déplace la moyenne, pas la médiane."""
        return float(np.median(self.temps))

    @property
    def dispersion(self) -> float:
        """Écart-type du temps de passage, en secondes.

        Affiché pour information, mais PAS utilisé pour le classement : un seul
        tour raté suffit à l'emballer.
        """
        return float(self.temps.std(ddof=1)) if len(self.passages) > 1 else 0.0

    @property
    def dispersion_robuste(self) -> float:
        """Écart absolu médian, remis à l'échelle d'un écart-type.

        Le facteur 1,4826 fait qu'il vaut le même chiffre que l'écart-type
        quand les données sont bien réparties, tout en ignorant les passages
        isolés. C'est la mesure sur laquelle les virages sont classés.
        """
        if len(self.passages) < 2:
            return 0.0
        temps = self.temps
        return 1.4826 * float(np.median(np.abs(temps - np.median(temps))))

    @property
    def passage_aberrant(self) -> bool:
        """Un passage isolé écrase-t-il la statistique ?

        L'écart-type très supérieur à la dispersion robuste signe un incident
        ponctuel plutôt qu'un manque de régularité.

        Il faut assez de passages pour l'affirmer : avec trois, la mesure
        robuste devient si petite que le seuil se déclenche sur du bruit.
        """
        if len(self.passages) < PASSAGES_POUR_ABERRANT:
            return False
        return self.dispersion > 3 * max(self.dispersion_robuste, 0.02)

    @property
    def tour_le_plus_lent(self) -> int:
        return self.passages[int(np.argmax(self.temps))].tour

    @property
    def potentiel(self) -> float:
        """Temps qui sépare le passage habituel du meilleur passage.

        C'est ce que la régularité seule rapporterait sur ce virage, sans rien
        améliorer d'autre. Calculé sur la médiane et non la moyenne, pour ne pas
        être gonflé par un incident isolé.
        """
        return self.temps_median - self.temps_meilleur

    @property
    def dispersion_freinage(self) -> float | None:
        """Écart-type du point de freinage, en mètres."""
        points = [p.debut_freinage for p in self.passages if p.debut_freinage is not None]
        if len(points) < 2:
            return None
        return float(np.std(points, ddof=1))

    @property
    def dispersion_vitesse_min(self) -> float:
        """Écart-type de la vitesse au point le plus lent, en km/h."""
        if len(self.passages) < 2:
            return 0.0
        return float(np.std([p.vitesse_min for p in self.passages], ddof=1))


@dataclass(frozen=True)
class Regularite:
    """La régularité d'une session, tours valides uniquement."""

    circuit: str
    type_session: str
    voiture: str
    numeros: tuple[int, ...]
    chronos: tuple[float, ...]
    virages: tuple[StatistiquesVirage, ...]

    # ------------------------------------------------------------------
    # Dispersion des chronos
    # ------------------------------------------------------------------

    @property
    def meilleur(self) -> float:
        return min(self.chronos)

    @property
    def median(self) -> float:
        return float(np.median(self.chronos))

    @property
    def ecart_type(self) -> float:
        return float(np.std(self.chronos, ddof=1)) if len(self.chronos) > 1 else 0.0

    @property
    def ecart_meilleur_median(self) -> float:
        """Ce qui sépare le meilleur tour du tour médian.

        Un pilote régulier a un médian proche de son meilleur ; un pilote
        irrégulier signe parfois un beau tour et roule loin derrière le reste
        du temps.
        """
        return self.median - self.meilleur

    # ------------------------------------------------------------------
    # Tour idéal
    # ------------------------------------------------------------------

    @property
    def tour_ideal(self) -> float:
        """Somme des meilleurs passages de chaque virage.

        Les portions pavent le tour entier, donc leur somme est bien un temps au
        tour — c'est ce que donnerait l'enchaînement de ses propres meilleurs
        moments.
        """
        return sum(v.temps_meilleur for v in self.virages)

    @property
    def marge_de_regularite(self) -> float:
        """Écart entre le meilleur tour réel et le tour idéal.

        Du temps déjà à portée : il ne demande aucun progrès, seulement de
        répéter ce qu'on a déjà fait, mais dans le même tour.
        """
        return self.meilleur - self.tour_ideal

    # ------------------------------------------------------------------
    # Évolution sur la session
    # ------------------------------------------------------------------

    @property
    def tendance(self) -> float:
        """Pente des chronos au fil de la session, en secondes par tour.

        Négative, on s'améliore ; positive, on se dégrade. C'est une droite
        ajustée sur les chronos : elle décrit, elle n'explique pas — l'usure
        des pneus, la baisse de carburant et l'apprentissage s'y mélangent.
        """
        if len(self.chronos) < 2:
            return 0.0
        return float(np.polyfit(np.arange(len(self.chronos)), self.chronos, 1)[0])

    @property
    def moitie_debut(self) -> float:
        moitie = max(1, len(self.chronos) // 2)
        return float(np.median(self.chronos[:moitie]))

    @property
    def moitie_fin(self) -> float:
        moitie = len(self.chronos) // 2
        return float(np.median(self.chronos[moitie:]))

    # ------------------------------------------------------------------

    @property
    def fiable(self) -> bool:
        """Y a-t-il assez de tours pour que les dispersions veuillent dire
        quelque chose ?"""
        return len(self.chronos) >= TOURS_POUR_FIABILITE

    @property
    def classement(self) -> tuple[StatistiquesVirage, ...]:
        """Virages du moins constant au plus constant.

        Classés sur la dispersion robuste : voir l'explication en tête de
        module sur ce qu'un seul tour raté ferait à un écart-type.
        """
        return tuple(sorted(self.virages, key=lambda v: -v.dispersion_robuste))


# ----------------------------------------------------------------------


def analyser(
    chemin: Path | str, definition: DefinitionCircuit, maximum_tours: int = 40
) -> Regularite:
    """Mesure la régularité d'une session, sur ses tours valides.

    Les tours écartés — stands, tours invalidés par le jeu, tours non bouclés —
    ne sont jamais comptés : ils fausseraient toutes les dispersions.
    """
    session = Session.ouvrir(chemin)
    numeros = [t.numero for t in session.tours_valides if t.chrono][:maximum_tours]
    if len(numeros) < TOURS_MINIMUM:
        raise ErreurTelemetrie(
            f"Cette session ne contient que {len(numeros)} tour(s) valide(s). "
            f"Il en faut au moins {TOURS_MINIMUM} pour parler de régularité : "
            "avec moins, une dispersion ne veut rien dire.\n"
            "Choisis une session plus longue, ou roule quelques tours de plus."
        )

    tours = [charger(chemin, n) for n in numeros]
    portions = secteurs(definition)

    passages: dict[int, list[PassageVirage]] = {v.numero: [] for v in definition.virages}
    for tour in tours:
        temps = _temps_par_portion(tour, portions)
        mesures = {m.virage.numero: m for m in mesurer(tour, definition)}
        for virage, duree in zip(definition.virages, temps):
            mesure = mesures.get(virage.numero)
            if mesure is None or duree is None:
                continue
            passages[virage.numero].append(
                PassageVirage(
                    tour=tour.tour.numero,
                    temps=duree,
                    debut_freinage=mesure.debut_freinage,
                    vitesse_min=mesure.vitesse_min,
                )
            )

    return Regularite(
        circuit=session.info.trace,
        type_session=session.info.type_session,
        voiture=session.info.voiture,
        numeros=tuple(t.tour.numero for t in tours),
        chronos=tuple(float(t.tour.chrono) for t in tours),
        virages=tuple(
            StatistiquesVirage(virage=v, passages=tuple(passages[v.numero]))
            for v in definition.virages
            if len(passages[v.numero]) >= TOURS_MINIMUM
        ),
    )


def _temps_par_portion(
    tour: DonneesTour, portions: list[tuple[float, float]]
) -> list[float | None]:
    """Temps mis à parcourir chaque portion du tour.

    Les portions pavant le tour, la somme des temps redonne la durée du tour.
    """
    bornes = np.array([p[0] for p in portions] + [portions[-1][1]])
    bornes = np.clip(bornes, 0.0, tour.longueur)
    instants = tour.temps_a_distance(bornes)
    return [
        float(fin - debut) if fin > debut else None
        for debut, fin in zip(instants, instants[1:])
    ]
