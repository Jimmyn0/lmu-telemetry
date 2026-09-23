"""Tests de la page régularité.

Les statistiques par virage sont testées sur des passages construits à la main :
c'est là qu'on peut vérifier au chiffre près qu'un tour raté ne fausse pas le
classement. L'analyse complète est ensuite vérifiée sur la session de test.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lmu_telemetry.errors import ErreurTelemetrie
from lmu_telemetry.regularite import (
    PassageVirage,
    Regularite,
    StatistiquesVirage,
    analyser,
)
from lmu_telemetry.virages import DefinitionCircuit, Virage, detecter
from lmu_telemetry.donnees_tour import charger
from tests.fixtures import construire as constructeur


def _virage(numero: int = 1) -> Virage:
    return Virage(numero=numero, debut=100.0, fin=200.0, rayon_min=50.0)


def _stats(temps: list[float], freinages: list[float] | None = None):
    return StatistiquesVirage(
        virage=_virage(),
        passages=tuple(
            PassageVirage(
                tour=i + 1,
                temps=t,
                debut_freinage=None if freinages is None else freinages[i],
                vitesse_min=100.0,
            )
            for i, t in enumerate(temps)
        ),
    )


# ----------------------------------------------------------------------
# Statistiques par virage
# ----------------------------------------------------------------------


def test_mesures_de_base() -> None:
    s = _stats([10.0, 10.5, 11.0, 10.5, 10.0])
    assert s.temps_meilleur == pytest.approx(10.0)
    assert s.temps_median == pytest.approx(10.5)
    assert s.potentiel == pytest.approx(0.5)


def test_dispersion_robuste_du_meme_ordre_sans_valeur_aberrante() -> None:
    """Sans passage aberrant, les deux mesures doivent rester comparables.

    Le facteur d'échelle 1,4826 les fait coïncider exactement pour une
    distribution normale ; sur des chronos réels, qui ne le sont pas tout à
    fait, on se contente du même ordre de grandeur. C'est suffisant : la mesure
    robuste ne sert qu'à classer, pas à être rapportée comme un écart-type.
    """
    temps = [10.0, 10.2, 10.4, 10.6, 10.8, 11.0, 11.2]
    s = _stats(temps)
    assert 0.6 < s.dispersion_robuste / s.dispersion < 1.7
    assert s.passage_aberrant is False


def test_un_tour_rate_ne_domine_pas_le_classement() -> None:
    """Le cas réel qui a fait changer de mesure.

    Virage 9 à Spa : huit passages très réguliers et un incident à 29 s.
    L'écart-type explose et placerait ce virage en tête ; la mesure robuste
    l'ignore.
    """
    temps = [13.71, 13.64, 29.09, 14.26, 13.68, 13.82, 13.62, 13.55, 14.57]
    incident = _stats(temps)
    regulier = _stats([12.0, 12.4, 12.6, 12.1, 12.5, 12.3, 12.7, 12.2, 12.45])

    # À l'écart-type, l'incident écrase tout le reste.
    assert incident.dispersion > 10 * regulier.dispersion
    # À la mesure robuste, c'est l'inverse : c'est bien l'autre qui varie.
    assert incident.dispersion_robuste < regulier.dispersion_robuste


def test_passage_aberrant_signale() -> None:
    incident = _stats([13.7, 13.6, 29.1, 14.3, 13.7, 13.8, 13.6])
    assert incident.passage_aberrant is True
    assert incident.tour_le_plus_lent == 3

    propre = _stats([13.7, 13.6, 13.9, 14.3, 13.7, 13.8, 13.6])
    assert propre.passage_aberrant is False


def test_pas_daberrant_avec_trop_peu_de_passages() -> None:
    """Avec trois passages, la mesure robuste devient minuscule dès que deux
    temps se ressemblent, et le seuil se déclencherait sur du bruit.

    Constaté sur une vraie session de trois tours : la mention apparaissait sur
    quatre virages sur huit, sans le moindre incident.
    """
    assert _stats([13.7, 13.75, 15.0]).passage_aberrant is False
    assert _stats([13.7, 13.75, 13.8, 15.0]).passage_aberrant is False





def test_potentiel_insensible_a_un_incident() -> None:
    """Le potentiel se calcule sur la médiane : un incident ne le gonfle pas."""
    propre = _stats([10.0, 10.4, 10.5, 10.6, 10.5])
    avec_incident = _stats([10.0, 10.4, 10.5, 10.6, 10.5, 40.0])
    assert avec_incident.potentiel == pytest.approx(propre.potentiel, abs=0.06)


def test_dispersion_du_point_de_freinage() -> None:
    s = _stats([10.0] * 4, freinages=[100.0, 110.0, 90.0, 100.0])
    assert s.dispersion_freinage == pytest.approx(np.std([100, 110, 90, 100], ddof=1))


def test_pas_de_dispersion_de_freinage_sans_freinage() -> None:
    assert _stats([10.0, 10.1, 10.2]).dispersion_freinage is None


# ----------------------------------------------------------------------
# Statistiques de session
# ----------------------------------------------------------------------


def _regularite(chronos: list[float], virages) -> Regularite:
    return Regularite(
        circuit="X",
        type_session="Practice",
        voiture="V",
        numeros=tuple(range(1, len(chronos) + 1)),
        chronos=tuple(chronos),
        virages=tuple(virages),
    )


def test_dispersion_des_chronos() -> None:
    r = _regularite([90.0, 91.0, 92.0, 91.0], [])
    assert r.meilleur == pytest.approx(90.0)
    assert r.median == pytest.approx(91.0)
    assert r.ecart_meilleur_median == pytest.approx(1.0)
    assert r.ecart_type == pytest.approx(np.std([90, 91, 92, 91], ddof=1))


def test_tour_ideal_et_marge() -> None:
    """Le tour idéal enchaîne les meilleurs passages : il ne peut pas être plus
    lent que le meilleur tour réel."""
    virages = [
        _stats([30.0, 31.0, 30.5]),
        _stats([30.0, 29.5, 31.0]),
        _stats([30.0, 30.0, 29.0]),
    ]
    r = _regularite([90.0, 90.5, 90.5], virages)
    assert r.tour_ideal == pytest.approx(30.0 + 29.5 + 29.0)
    assert r.tour_ideal <= r.meilleur
    assert r.marge_de_regularite == pytest.approx(90.0 - 88.5)


def test_tendance() -> None:
    """Une session qui s'améliore régulièrement doit donner une pente négative."""
    assert _regularite([95.0, 94.0, 93.0, 92.0], []).tendance == pytest.approx(-1.0)
    assert _regularite([92.0, 92.0, 92.0], []).tendance == pytest.approx(0.0, abs=1e-9)
    assert _regularite([90.0, 91.0, 92.0], []).tendance == pytest.approx(1.0)


def test_moities_de_session() -> None:
    r = _regularite([95.0, 95.0, 90.0, 90.0], [])
    assert r.moitie_debut == pytest.approx(95.0)
    assert r.moitie_fin == pytest.approx(90.0)


def test_fiabilite_selon_le_nombre_de_tours() -> None:
    assert _regularite([90.0, 91.0, 92.0], []).fiable is False
    assert _regularite([90.0, 91.0, 92.0, 91.0, 90.5], []).fiable is True


def test_classement_du_moins_au_plus_constant() -> None:
    r = _regularite(
        [90.0, 90.0, 90.0],
        [
            StatistiquesVirage(virage=_virage(1), passages=_stats([10.0, 10.1, 10.0]).passages),
            StatistiquesVirage(virage=_virage(2), passages=_stats([10.0, 12.0, 11.0]).passages),
            StatistiquesVirage(virage=_virage(3), passages=_stats([10.0, 10.4, 10.2]).passages),
        ],
    )
    assert [v.virage.numero for v in r.classement] == [2, 3, 1]


# ----------------------------------------------------------------------
# Sur la session de test
# ----------------------------------------------------------------------


@pytest.fixture
def definition(session_test: Path) -> DefinitionCircuit:
    tours = [charger(session_test, 1), charger(session_test, 3)]
    return detecter(tours, rayon_maximal=constructeur.RAYON * 1.5)


def test_analyse_complete(session_test: Path, definition) -> None:
    r = analyser(session_test, definition)
    # Quatre tours valides dans la fixture : 1, 3, 4 et 5.
    assert r.numeros == (1, 3, 4, 5)
    assert r.chronos == pytest.approx((90.0, 92.0, 90.0, 90.0))
    assert r.meilleur == pytest.approx(90.0)


def test_somme_des_virages_vaut_le_tour(session_test: Path, definition) -> None:
    """Les portions pavent le tour : la somme de leurs temps moyens doit valoir
    le chrono moyen. C'est le contrôle qui prouve qu'aucun morceau de piste
    n'est oublié ni compté deux fois."""
    r = analyser(session_test, definition)
    somme = sum(v.temps_moyen for v in r.virages)
    assert somme == pytest.approx(float(np.mean(r.chronos)), abs=0.05)


def test_tour_ideal_reel(session_test: Path, definition) -> None:
    r = analyser(session_test, definition)
    assert r.tour_ideal <= r.meilleur + 1e-6


def test_refuse_une_session_trop_courte(tmp_path: Path, definition) -> None:
    """Trois points ne dessinent pas une dispersion : il faut le dire, pas
    sortir des chiffres qui ne veulent rien dire."""
    import duckdb

    chemin = tmp_path / "courte.duckdb"
    constructeur.construire(chemin)
    con = duckdb.connect(str(chemin))
    # On ne garde qu'un seul chrono : la session n'a plus qu'un tour valide.
    con.execute('DELETE FROM "Lap Time" WHERE ts > 300')
    con.close()

    with pytest.raises(ErreurTelemetrie) as erreur:
        analyser(chemin, definition)
    message = str(erreur.value)
    assert "au moins" in message
    assert "session plus longue" in message
