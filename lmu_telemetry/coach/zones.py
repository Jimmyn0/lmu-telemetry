"""Les portions de piste sur lesquelles le moteur juge un passage.

--------------------------------------------------------------------------
Pourquoi regrouper des virages
--------------------------------------------------------------------------

Un conseil arrive environ 3 s après la sortie d'un virage. Dans une chicane, à ce
moment-là, on est déjà au virage suivant, voire au-delà : mesuré à Monza, c'est le
cas de T1, T4, T8 et T9. Deux virages trop proches n'en font donc qu'un pour le
moteur, avec un seul conseil à la sortie du dernier.

La règle est la distance qui les sépare, ce qui donne à Monza T1-2, T4-5 et T8-10.

--------------------------------------------------------------------------
Ce que couvre une zone
--------------------------------------------------------------------------

Du début du freinage à la sortie du dernier virage plus `prolongement_sortie`.
C'est la même règle que `virages.zone_analyse`, à une différence près : une zone
peut déborder de la ligne. Un freinage commencé avant la ligne pour un virage
placé juste après n'est pas tronqué, et `debut` est alors négatif.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domaine.virages import DefinitionCircuit, Virage
from ..parametres import SeuilsCoach, SeuilsVirage


@dataclass(frozen=True)
class Zone:
    """Un virage, ou plusieurs trop proches pour être séparés."""

    virages: tuple[Virage, ...]

    debut: float
    """Début de l'observation, en mètres depuis la ligne. Négatif si le freinage
    commence avant la ligne."""

    fin: float
    """Fin de l'observation. Peut dépasser la longueur du tour."""

    @property
    def sortie(self) -> float:
        """Sortie du dernier virage de la zone."""
        return self.virages[-1].fin

    @property
    def libelle(self) -> str:
        """Le nom du virage, ou ses numéros si la zone n'en a pas un seul.

        « Lesmo 2 », « Variante Ascari », « T6 », « T1-2 ».
        """
        noms = {v.nom for v in self.virages}
        if len(noms) == 1 and (nom := noms.pop()):
            return nom
        premier, dernier = self.virages[0].numero, self.virages[-1].numero
        return f"T{premier}" if premier == dernier else f"T{premier}-{dernier}"


def _regrouper(virages: tuple[Virage, ...], ecart: float) -> list[tuple[Virage, ...]]:
    groupes: list[list[Virage]] = []
    for virage in virages:
        if groupes and virage.debut - groupes[-1][-1].fin <= ecart:
            groupes[-1].append(virage)
        else:
            groupes.append([virage])
    return [tuple(g) for g in groupes]


def zones(
    definition: DefinitionCircuit,
    seuils: SeuilsCoach = SeuilsCoach(),
    virages: SeuilsVirage = SeuilsVirage(),
) -> tuple[Zone, ...]:
    """Les zones d'un circuit, dans l'ordre du tour."""
    groupes = _regrouper(definition.virages, seuils.ecart_groupe)
    longueur = definition.longueur
    resultat = []
    for i, groupe in enumerate(groupes):
        # Le circuit boucle : le groupe d'avant le premier est le dernier du tour.
        precedent = groupes[i - 1][-1].fin - (longueur if i == 0 else 0.0)
        suivant = groupes[(i + 1) % len(groupes)][0].debut + (
            longueur if i == len(groupes) - 1 else 0.0
        )
        resultat.append(
            Zone(
                virages=groupe,
                debut=max(groupe[0].debut - virages.remontee_freinage, precedent),
                fin=max(
                    min(groupe[-1].fin + virages.prolongement_sortie, suivant),
                    groupe[-1].fin,
                ),
            )
        )
    return tuple(resultat)
