"""Ce que l'outil lit du jeu en roulant, d'où que ça vienne.

Trois sources donnent la voiture du joueur : la mémoire partagée du jeu en direct,
une capture de la sonde, et un fichier `.duckdb` rejoué. Toutes produisent le même
flux d'`Echantillon`, à la même cadence et dans les mêmes unités : ce qui a été
vérifié sur un enregistrement vaut donc pour le direct.

--------------------------------------------------------------------------
Ce qui diffère d'une source à l'autre
--------------------------------------------------------------------------

Une seule chose : `roues`. Le canal `Wheel Speed` des fichiers n'est pas la
rotation des roues mais la vitesse du sol (voir docs/12-memoire-partagee.md).
Un rejeu de `.duckdb` ne peut donc voir ni blocage ni patinage.

La distance suit partout le rythme du direct, où `mLapDist` n'arrive qu'à 5 Hz :
un rejeu la donne au même rythme qu'en piste.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Fréquence de lecture, en Hz. Les pédales n'existent qu'à 50 Hz dans les
#: fichiers du jeu : lire plus vite n'apporterait rien.
FREQUENCE_LECTURE = 50


@dataclass(slots=True)
class Echantillon:
    """L'état de la voiture à un instant."""

    temps: float
    """Horloge de la session, en secondes. Elle repart de zéro à chaque session."""

    tour: int
    """Numéro du tour en cours, celui que donne le jeu."""

    debut_tour: float
    """Instant où ce tour a commencé, sur la même horloge."""

    vitesse: float
    """En km/h."""

    gaz: float
    """Accélérateur en %, tel que le pilote l'actionne : sans les coupures
    automatiques du changement de rapport et de l'antipatinage."""

    frein: float
    """Frein en %, tel que le pilote l'actionne."""

    volant: float
    """Braquage en % de la butée, positif à droite."""

    distance: float | None = None
    """`mLapDist` en mètres, seulement quand il vient de changer."""

    temps_distance: float = 0.0
    """Instant auquel `distance` a été mesurée."""

    hors_piste: bool = False
    """Au moins une roue sur l'herbe, la terre ou le gravier."""

    stands: bool = False
    """Dans la voie des stands ou au garage."""

    dernier_choc: float = -1.0
    """Instant du dernier choc, -1 s'il n'y en a pas eu."""

    dernier_chrono: float | None = None
    """Chrono du tour précédent. None s'il n'a pas été chronométré."""

    roues: tuple[float, float, float, float] | None = None
    """Vitesse de rotation × rayon de chaque roue, en km/h, AVG, AVD, ARG, ARD."""
