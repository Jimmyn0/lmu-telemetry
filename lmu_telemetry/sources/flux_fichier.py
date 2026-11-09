"""Le flux d'échantillons d'un fichier `.duckdb`, comme si la session se déroulait.

Le but est de donner ce que le direct aurait donné, ni plus ni moins :

* une valeur par canal, tenue jusqu'à la suivante, sans rien interpoler ;
* la distance à 5 Hz alors que le fichier la donne à 10 Hz, comme en piste ;
* pas de `roues` : le fichier ne les a pas, voir `echantillon.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np

from .echantillon import FREQUENCE_LECTURE, Echantillon
from .reader import FichierSession, valeur_a_instant

#: Une mise à jour de la distance sur combien : le fichier est à 10 Hz, le jeu
#: publie `mLapDist` à 5 Hz.
PAS_DISTANCE = 2


def _tenir(temps: np.ndarray, instants: np.ndarray, valeurs: np.ndarray) -> np.ndarray:
    """Valeur en vigueur à chaque instant : la dernière écrite avant lui."""
    indices = np.clip(np.searchsorted(instants, temps, side="right") - 1, 0, None)
    return valeurs[indices]


def _canal(fichier: FichierSession, temps: np.ndarray, *noms: str) -> np.ndarray:
    """Le premier canal disponible : les anciens fichiers n'ont pas les canaux bruts."""
    nom = next(n for n in noms if n in fichier.canaux)
    return _tenir(temps, fichier.temps_canal(nom), fichier.canal(nom))


def flux_fichier(
    chemin: Path | str, frequence: int = FREQUENCE_LECTURE
) -> Iterator[Echantillon]:
    """Les échantillons d'une session enregistrée, dans l'ordre du temps."""
    with FichierSession(chemin) as fichier:
        temps = fichier.t0 + np.arange(int(fichier.duree * frequence)) / frequence

        instants_tours, numeros = fichier.evenement("Lap")
        if instants_tours.size == 0:
            return
        rang = np.clip(np.searchsorted(instants_tours, temps, side="right") - 1, 0, None)
        chronos_tour, valeurs_chrono = fichier.evenement("Lap Time")
        # Le chrono du tour qui s'achève est écrit à l'instant où le suivant
        # commence. Un tour non chronométré n'écrit rien : à ne pas confondre
        # avec le chrono d'avant, resté en place.
        chronos = [
            valeur_a_instant(chronos_tour, valeurs_chrono, float(instant))
            for instant in instants_tours
        ]

        stands = np.zeros(temps.shape, dtype=bool)
        for debut, fin in fichier.intervalles_stands():
            stands |= (temps >= debut) & (temps < fin)

        dehors = np.zeros(temps.shape, dtype=bool)
        if (releve := fichier.hors_piste()) is not None:
            dehors = _tenir(temps, *releve)

        chocs = fichier.instants_chocs()
        dernier_choc = (
            _tenir(temps, chocs, chocs) * (temps >= chocs[0]) - (temps < chocs[0])
            if chocs.size
            else np.full(temps.shape, -1.0)
        )

        instants_distance = fichier.temps_canal("Lap Dist")[::PAS_DISTANCE].tolist()
        distances = fichier.canal("Lap Dist")[::PAS_DISTANCE].tolist()
        suivante = 0

        colonnes = zip(
            temps.tolist(),
            rang.tolist(),
            _canal(fichier, temps, "Ground Speed").tolist(),
            _canal(fichier, temps, "Throttle Pos Unfiltered", "Throttle Pos").tolist(),
            _canal(fichier, temps, "Brake Pos Unfiltered", "Brake Pos").tolist(),
            _canal(fichier, temps, "Steering Pos").tolist(),
            dehors.tolist(),
            stands.tolist(),
            dernier_choc.tolist(),
        )
        tours = numeros.tolist()
        debuts = instants_tours.tolist()
        for instant, r, vitesse, gaz, frein, volant, hors, aux_stands, choc in colonnes:
            echantillon = Echantillon(
                temps=instant,
                tour=int(tours[r]),
                debut_tour=debuts[r],
                vitesse=vitesse,
                gaz=gaz,
                frein=frein,
                volant=volant,
                hors_piste=hors,
                stands=aux_stands,
                dernier_choc=choc,
                dernier_chrono=chronos[r],
            )
            while suivante < len(distances) and instants_distance[suivante] <= instant:
                echantillon.distance = distances[suivante]
                echantillon.temps_distance = instants_distance[suivante]
                suivante += 1
            yield echantillon
