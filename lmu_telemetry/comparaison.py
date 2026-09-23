"""Comparaison de deux tours : traces superposées et delta cumulé.

--------------------------------------------------------------------------
Ce qu'est le delta cumulé
--------------------------------------------------------------------------

À chaque point du circuit, on regarde depuis combien de temps chaque tour est
parti de la ligne. La différence est le delta cumulé :

    delta(d) = temps_du_tour_comparé(d) - temps_du_tour_de_référence(d)

* delta positif  : à cet endroit, le tour comparé a déjà perdu du temps.
* delta négatif  : il est en avance.
* delta qui MONTE : on perd du temps ici, maintenant.
* delta qui DESCEND : on en gagne ici.

C'est la PENTE qui dit où se joue le chrono, pas la hauteur. Une courbe qui
monte fort sur cinquante mètres pointe l'endroit exact à travailler ; un palier,
même très haut, veut dire qu'on y roule aussi vite que la référence — le retard
a été pris avant.

En bout de tour, le delta vaut nécessairement la différence des deux chronos.
C'est le contrôle du calcul, et il est vérifié par les tests. Mesuré sur des
comparaisons réelles : l'écart entre le delta final et la différence des chronos
reste sous 0,035 s.

--------------------------------------------------------------------------
Une formulation séduisante mais fausse
--------------------------------------------------------------------------

On lit souvent que le delta s'obtient en intégrant la différence des inverses
de vitesse le long de la distance : delta(d) = ∫ (1/v_comparé - 1/v_référence).
C'est plus lisse, parce que la vitesse est à 100 Hz alors que la distance n'est
qu'à 10 Hz.

Testé, et écarté : cette formulation DÉRIVE. Elle intègre la vitesse de la
voiture, qui mesure la distance réellement parcourue, alors que l'axe est
l'avancement le long de la piste ; l'écart entre les deux ne se compense pas
entre deux tours. Sur huit comparaisons réelles, l'erreur finale allait de
0,004 s à 6,9 s, contre 0,035 s au pire pour la formulation par la distance.
Un delta plus joli mais faux ne vaut rien.

--------------------------------------------------------------------------
Le plancher de bruit
--------------------------------------------------------------------------

`Lap Dist` est à 10 Hz. Comme dt/dd vaut 1/v, une imprécision de distance pèse
d'autant plus que la voiture est lente : à 46 km/h, un demi-mètre d'erreur fait
0,04 s de delta. Dans les virages les plus lents, la courbe porte donc un bruit
de l'ordre de ±0,03 s au mètre.

Ce bruit n'est pas lissé, et c'est délibéré. Vérifié sur un tour entier : 1 084
pas de `Lap Dist` sur 1 122 sont déjà cohérents avec la vitesse au dixième près,
l'irrégularité est locale et non générale. Lisser réduirait le bruit de 30 %
mais décalerait la position de plusieurs mètres — on perdrait plus qu'on ne
gagnerait. Retenir simplement qu'une oscillation de quelques centièmes dans un
virage lent est du bruit, pas du pilotage.

--------------------------------------------------------------------------
Pourquoi l'alignement se fait sur la distance
--------------------------------------------------------------------------

Voir `donnees_tour.py`. Comparer deux tours instant par instant n'aurait aucun
sens : dix secondes après la ligne, les deux voitures ne sont pas au même
endroit. On les compare donc au même point de la piste.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .donnees_tour import DonneesTour, charger
from .errors import ErreurTelemetrie
from .textes import Message

#: Pas de l'axe de distance, en mètres.
#:
#: À 227 km/h, les canaux à 100 Hz donnent un point tous les 63 cm : un pas de
#: 1 m ne perd donc presque rien en ligne droite. Dans un virage lent à 60 km/h
#: il y a au contraire six échantillons par mètre, et le pas fait office de
#: lissage. Un tour de Monza tient en 5 776 points, ce qui s'affiche sans peine.
PAS_DISTANCE = 1.0


@dataclass(frozen=True)
class Comparaison:
    """Deux tours ramenés sur un axe de distance commun."""

    reference: DonneesTour
    compare: DonneesTour

    distance: np.ndarray
    """Axe commun, en mètres depuis la ligne."""

    delta: np.ndarray
    """Delta cumulé en secondes. Positif = le tour comparé est en retard."""

    traces: dict[str, tuple[np.ndarray, np.ndarray]]
    """Par canal : (valeurs de la référence, valeurs du tour comparé)."""

    # ------------------------------------------------------------------

    @property
    def ecart_final(self) -> float:
        """Delta au bout du tour, en secondes."""
        return float(self.delta[-1])

    @property
    def ecart_chronos(self) -> float | None:
        """Différence des chronos officiels du jeu, si les deux existent."""
        a, b = self.compare.tour.chrono, self.reference.tour.chrono
        return None if a is None or b is None else a - b

    @property
    def avertissements(self) -> tuple[Message, ...]:
        """Ce qui doit être dit avant de lire la courbe.

        Un tour où la voiture s'est arrêtée casse la comparaison par distance :
        pendant l'arrêt le temps passe alors que la distance n'avance plus, si
        bien que le delta fait un saut vertical à cet endroit. Mesuré sur un cas
        réel : 6,4 s d'un mètre au suivant, pour un tour arrêté 5 s à Spa. Ce
        n'est pas une erreur de calcul, c'est ce que la comparaison par distance
        ne sait pas représenter — autant le dire.
        """
        messages = []
        if self.reference.info.voiture != self.compare.info.voiture:
            messages.append(
                Message(
                    "serveur.avert.voitures",
                    {"ref": self.reference.info.voiture, "cmp": self.compare.info.voiture},
                )
            )
        for cle, donnees in (
            ("serveur.avert.arret_reference", self.reference),
            ("serveur.avert.arret_compare", self.compare),
        ):
            tour = donnees.tour
            if tour.quasi_arret:
                messages.append(
                    Message(
                        cle,
                        {
                            "n": tour.numero,
                            "vitesse": f"{tour.vitesse_min:.0f}",
                            "duree": f"{tour.duree_quasi_arret:.1f}",
                        },
                    )
                )
        return tuple(messages)

    @property
    def coherent(self) -> bool:
        """Le delta final retombe-t-il bien sur la différence des chronos ?

        C'est le contrôle du calcul. La tolérance vient de deux sources : les
        deux tours ne font pas exactement la même longueur de `Lap Dist`, et
        l'axe commun s'arrête donc un peu avant la ligne.
        """
        attendu = self.ecart_chronos
        return attendu is None or abs(self.ecart_final - attendu) <= 0.1

    def perte_par_troncon(self, longueur: float = 100.0) -> list[tuple[float, float]]:
        """Temps gagné ou perdu par tronçon de piste.

        Rend une liste de (distance du début du tronçon, delta gagné dessus).
        Un tronçon positif est un endroit où l'on perd du temps.

        C'est la lecture chiffrée de la pente du delta cumulé, et c'est ce qui
        répond à « où est-ce que je perds ? » sans avoir à interpréter une
        courbe à l'œil.
        """
        bornes = np.arange(0.0, self.distance[-1], longueur)
        deltas = np.interp(bornes, self.distance, self.delta)
        fins = np.interp(
            np.append(bornes[1:], self.distance[-1]), self.distance, self.delta
        )
        return list(zip(bornes.tolist(), (fins - deltas).tolist()))


# ----------------------------------------------------------------------


def comparer(
    reference: DonneesTour, compare: DonneesTour, pas: float = PAS_DISTANCE
) -> Comparaison:
    """Aligne deux tours sur la distance et calcule le delta cumulé."""
    # Le tracé, pas le circuit : deux variantes du même circuit n'ont ni la
    # même longueur ni les mêmes virages, les superposer n'aurait aucun sens.
    if reference.info.trace != compare.info.trace:
        raise ErreurTelemetrie.de(
            "serveur.erreur.circuits_differents",
            ref=reference.info.trace,
            cmp=compare.info.trace,
        )

    # Les deux tours ne couvrent jamais exactement la même longueur : le dernier
    # échantillon ne tombe pas au même endroit. On s'arrête au plus court.
    fin = min(reference.longueur, compare.longueur)
    if fin <= pas:
        raise ErreurTelemetrie.de("serveur.erreur.tours_trop_courts")

    distance = np.arange(0.0, fin, pas)

    delta = compare.temps_a_distance(distance) - reference.temps_a_distance(distance)

    valeurs_ref = reference.sur_distance(distance)
    valeurs_cmp = compare.sur_distance(distance)
    traces = {
        nom: (valeurs_ref[nom], valeurs_cmp[nom])
        for nom in valeurs_ref
        if nom in valeurs_cmp
    }

    return Comparaison(
        reference=reference,
        compare=compare,
        distance=distance,
        delta=delta,
        traces=traces,
    )


def comparer_fichiers(
    chemin_reference: Path | str,
    tour_reference: int,
    chemin_compare: Path | str,
    tour_compare: int,
    pas: float = PAS_DISTANCE,
) -> Comparaison:
    """Raccourci : charge les deux tours puis les compare."""
    return comparer(
        charger(chemin_reference, tour_reference),
        charger(chemin_compare, tour_compare),
        pas=pas,
    )
