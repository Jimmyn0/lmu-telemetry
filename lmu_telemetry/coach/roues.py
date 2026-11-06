"""Blocage et patinage : la vitesse des roues comparée à celle de la voiture.

Ce module ne sert qu'avec une source qui voit les roues, le direct ou une capture :
le canal `Wheel Speed` des fichiers est la vitesse du sol, il ne bouge pas quand une
roue se bloque (voir docs/12-memoire-partagee.md).

--------------------------------------------------------------------------
Pourquoi étalonner
--------------------------------------------------------------------------

Le rayon que publie le jeu n'est qu'approché, et différent à l'avant et à l'arrière :
une roue libre tourne de 0 à 3 % plus vite que ce qu'il annonce. On mesure donc le
rapport sur le moment, là où aucune pédale n'agit et où le volant est droit.
"""

from __future__ import annotations

import numpy as np

from ..parametres import SeuilsCoach
from ..sources.echantillon import Echantillon
from .passage import Passage

#: Conditions d'une roue libre : pas de frein, pas trop de gaz, volant presque droit,
#: et assez de vitesse pour que le rapport ait un sens.
VITESSE_ETALONNAGE = 54.0
FREIN_ETALONNAGE = 2.0
GAZ_ETALONNAGE = 50.0
VOLANT_ETALONNAGE = 10.0

#: Rapports crédibles pour une roue libre. Une roue peut rester bloquée après le frein,
#: dans un tête-à-queue par exemple : sans ce filtre, ces moments faussaient l'étalonnage
#: de 10 %, et la session entière semblait patiner.
RAPPORT_PLAUSIBLE = (0.93, 1.10)

#: Poids minimal d'une nouvelle observation : le rapport bouge peu mais la pression et
#: l'usure le font glisser au fil d'un relais.
PAS_MINIMAL = 0.002

#: Vitesses (km/h) au-dessous desquelles le rapport entre la roue et la voiture n'a
#: plus de sens.
VITESSE_MINIMALE_BLOCAGE = 54.0
VITESSE_MINIMALE_PATINAGE = 36.0

#: Pédales à partir desquelles on parle de freinage et d'accélération.
FREIN_ROUES = 5.0
GAZ_ROUES = 20.0


class EtalonnageRoues:
    """Le rapport entre la vitesse annoncée de chaque roue et celle de la voiture."""

    def __init__(self) -> None:
        self.echelle = np.ones(4)
        self._vus = 0

    def observer(self, e: Echantillon) -> None:
        if (
            e.roues is None
            or e.vitesse < VITESSE_ETALONNAGE
            or e.frein > FREIN_ETALONNAGE
            or e.gaz > GAZ_ETALONNAGE
            or abs(e.volant) > VOLANT_ETALONNAGE
        ):
            return
        rapports = np.array(e.roues) / e.vitesse
        if rapports.min() < RAPPORT_PLAUSIBLE[0] or rapports.max() > RAPPORT_PLAUSIBLE[1]:
            return
        self._vus += 1
        self.echelle += max(1.0 / self._vus, PAS_MINIMAL) * (rapports - self.echelle)


def _tenu(valeurs: np.ndarray, largeur: int) -> float:
    """Le niveau le plus haut maintenu sur `largeur` échantillons d'affilée."""
    if valeurs.size < largeur:
        return 0.0
    return float(np.lib.stride_tricks.sliding_window_view(valeurs, largeur).min(axis=1).max())


def glissements(
    p: Passage, echelle: np.ndarray, c: SeuilsCoach
) -> tuple[float, bool, float]:
    """Glissement tenu au freinage, s'il vient de l'avant, et tenu à l'accélération.

    Hors piste, les roues patinent sans que le pilote y soit pour rien.
    """
    assert p.roues is not None
    # Positif quand la roue tourne moins vite que la voiture n'avance.
    glissement = (1.0 - p.roues / echelle / np.maximum(p.vitesse, 1.0)[:, None]) * 100.0
    pas = float(np.median(np.diff(p.temps)))
    sur_piste = ~p.hors_piste

    au_frein = (p.vitesse >= VITESSE_MINIMALE_BLOCAGE) & (p.frein > FREIN_ROUES) & sur_piste
    largeur = max(1, int(round(c.duree_blocage / pas)))
    par_roue = [_tenu(np.where(au_frein, glissement[:, i], 0.0), largeur) for i in range(4)]

    aux_gaz = (
        (p.vitesse >= VITESSE_MINIMALE_PATINAGE)
        & (p.gaz > GAZ_ROUES)
        & (p.frein < FREIN_ROUES)
        & sur_piste
    )
    largeur = max(1, int(round(c.duree_patinage / pas)))
    arriere = np.where(aux_gaz, -glissement[:, 2:].min(axis=1), 0.0)

    return max(par_roue), max(par_roue[:2]) >= max(par_roue[2:]), _tenu(arriere, largeur)
