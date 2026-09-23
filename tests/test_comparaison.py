"""Tests de l'axe de distance et du delta cumulé."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lmu_telemetry import catalogue
from lmu_telemetry.comparaison import comparer, comparer_fichiers
from lmu_telemetry.donnees_tour import TourIntrouvable, charger
from lmu_telemetry.errors import ErreurTelemetrie, SessionEnCours
from lmu_telemetry.session import Session
from tests.fixtures import construire as constructeur

# La session synthétique : voir tests/fixtures/construire.py.
# Le tour 1 dure 90 s (89 s à 150 km/h + 1 s à 60), le tour 3 dure 92 s et
# couvre la même distance en s'arrêtant 2 s. Longueur commune : 3 725 m.
LONGUEUR = 150 / 3.6 * 89 + 60 / 3.6 * 1


# ----------------------------------------------------------------------
# Chargement d'un tour
# ----------------------------------------------------------------------


def test_axe_de_distance(session_test: Path) -> None:
    tour = charger(session_test, 1)
    assert tour.distance[0] == pytest.approx(0.0)
    assert tour.longueur == pytest.approx(LONGUEUR, rel=0.002)
    assert tour.duree == pytest.approx(90.0, abs=0.02)


def test_distance_toujours_croissante(session_test: Path) -> None:
    """L'inversion distance → temps n'a de sens que sur un signal croissant."""
    for numero in (1, 3):
        tour = charger(session_test, numero)
        assert np.all(np.diff(tour.distance) >= 0)


def test_grille_a_100_hz(session_test: Path) -> None:
    tour = charger(session_test, 1)
    pas = np.diff(tour.temps)
    assert pas.min() == pytest.approx(0.01)
    assert pas.max() == pytest.approx(0.01)


def test_les_bords_ne_sont_pas_figes(session_test: Path) -> None:
    """`Lap Dist` s'arrête avant la ligne : la fin du tour ne doit pas stagner.

    Sans extrapolation, le dernier dixième de seconde du tour garderait la
    dernière distance connue — jusqu'à 5 m perdus à 227 km/h sur un vrai tour.
    """
    tour = charger(session_test, 1)
    derniers = np.diff(tour.distance[-12:])
    assert derniers.min() > 0.0


def test_rapport_engage_en_escalier(session_test: Path) -> None:
    """Le rapport est un événement : on ne doit pas inventer de 3,5e vitesse."""
    tour = charger(session_test, 1)
    assert set(np.unique(tour.canal("Gear"))) <= {0.0, 3.0}


def test_canal_discontinu_jamais_interpole(session_test: Path) -> None:
    """`Track Edge` saute d'un bord de piste à l'autre : on ne l'interpole pas.

    Le tour 2 de la fixture traverse l'axe de la piste. La valeur passe donc de
    -5 m à +5 m d'un coup. Une interpolation linéaire fabriquerait des positions
    de bord au milieu de la route — ce qui, sur de vraies données, creusait un
    créneau dans le corridor 26 fois par tour.
    """
    from tests.fixtures.construire import DEMI_LARGEUR

    tour = charger(session_test, 2)
    for valeurs in (
        tour.canal("Track Edge"),
        tour.sur_distance(np.arange(0.0, tour.longueur, 1.0))["Track Edge"],
    ):
        assert set(np.unique(np.round(valeurs, 3))) == {-DEMI_LARGEUR, DEMI_LARGEUR}


def test_canal_continu_toujours_interpole(session_test: Path) -> None:
    """À l'inverse, l'écart latéral est continu : lui doit bien être interpolé."""
    tour = charger(session_test, 2)
    lateral = tour.canal("Path Lateral")
    # Le tour traversant dérive régulièrement de +3 m à -3 m.
    assert lateral[0] == pytest.approx(3.0, abs=0.05)
    assert lateral[-1] == pytest.approx(-3.0, abs=0.05)
    assert len(np.unique(np.round(lateral, 2))) > 100


def test_tour_inexistant(session_test: Path) -> None:
    with pytest.raises(TourIntrouvable) as erreur:
        charger(session_test, 99)
    assert "0, 1, 2, 3" in str(erreur.value)


def test_tour_non_boucle_refuse(session_test: Path) -> None:
    dernier = len(constructeur.FRONTIERES) - 1
    with pytest.raises(ErreurTelemetrie) as erreur:
        charger(session_test, dernier)
    assert "pas été bouclé" in str(erreur.value)


# ----------------------------------------------------------------------
# Delta cumulé
# ----------------------------------------------------------------------


def test_delta_dun_tour_avec_lui_meme(session_test: Path) -> None:
    """Contrôle le plus simple : comparé à lui-même, un tour ne perd rien."""
    tour = charger(session_test, 1)
    c = comparer(tour, tour)
    assert np.abs(c.delta).max() == pytest.approx(0.0, abs=1e-9)
    assert c.ecart_final == pytest.approx(0.0)


def test_delta_part_de_zero(session_test: Path) -> None:
    c = comparer_fichiers(session_test, 1, session_test, 3)
    assert c.delta[0] == pytest.approx(0.0)


def test_delta_final_vaut_la_difference_des_chronos(session_test: Path) -> None:
    """Le contrôle du calcul : en bout de tour, le delta EST l'écart de chrono."""
    c = comparer_fichiers(session_test, 1, session_test, 3)
    # Le tour 3 met 2 s de plus que le tour 1 pour la même distance.
    assert c.ecart_chronos == pytest.approx(2.0)
    assert c.ecart_final == pytest.approx(c.ecart_chronos, abs=0.05)
    assert c.coherent is True


def test_signe_du_delta(session_test: Path) -> None:
    """Un delta positif veut dire que le tour comparé est en retard.

    On fabrique le cas en comparant un tour à lui-même décalé : le tour 3 de la
    fixture contient un arrêt de 2 s, il est donc en retard sur le tour 1 à
    partir de là.
    """
    c = comparer_fichiers(session_test, 1, session_test, 3)
    assert c.delta.max() > 1.5  # les 2 secondes d'arrêt ressortent
    assert c.delta[10] == pytest.approx(0.0, abs=0.05)  # avant l'arrêt, rien
    assert np.all(np.diff(c.delta) >= -1e-9)  # le tour 3 ne reprend jamais de temps


def test_traces_sur_laxe_commun(session_test: Path) -> None:
    c = comparer_fichiers(session_test, 1, session_test, 3)
    for nom, (ref, cmp) in c.traces.items():
        assert len(ref) == c.distance.size, nom
        assert len(cmp) == c.distance.size, nom


def test_axe_commun_limite_au_plus_court(session_test: Path) -> None:
    a, b = charger(session_test, 1), charger(session_test, 3)
    c = comparer(a, b)
    assert c.distance[-1] <= min(a.longueur, b.longueur)


def test_avertissement_si_arret(session_test: Path) -> None:
    """Un tour arrêté rend la comparaison par distance discontinue : il faut le dire."""
    c = comparer_fichiers(session_test, 1, session_test, 3)
    assert any("arrêté" in str(a) for a in c.avertissements)
    assert any("saut vertical" in str(a) for a in c.avertissements)


def test_pas_davertissement_sans_incident(session_test: Path) -> None:
    tour = charger(session_test, 1)
    assert comparer(tour, tour).avertissements == ()


def test_troncons(session_test: Path) -> None:
    c = comparer_fichiers(session_test, 1, session_test, 3)
    troncons = c.perte_par_troncon(500.0)
    assert troncons[0][0] == 0.0
    # La somme des tronçons redonne le delta final : rien ne se perd en route.
    assert sum(v for _, v in troncons) == pytest.approx(c.ecart_final, abs=0.05)


def test_circuits_differents_refuses(session_test: Path, tmp_path: Path) -> None:
    autre = tmp_path / "autre.duckdb"
    constructeur.construire(autre)
    import duckdb

    con = duckdb.connect(str(autre))
    con.execute("UPDATE metadata SET value = 'Ailleurs' WHERE key = 'TrackLayout'")
    con.close()

    with pytest.raises(ErreurTelemetrie) as erreur:
        comparer_fichiers(session_test, 1, autre, 1)
    assert "même circuit" in str(erreur.value)


def test_variantes_du_meme_circuit_refusees(session_test: Path, tmp_path: Path) -> None:
    """Deux VARIANTES d'un circuit portent le même `TrackName` et ne se
    comparent pourtant pas.

    Cas réel : « Monza Curva Grande Circuit » fait 5 745 m et compte 9 virages,
    « Autodromo Nazionale Monza » 5 780 m et 11 — la Variante del Rettifilo n'y
    est pas. Les deux s'appellent pareil sur le disque.
    """
    variante = tmp_path / "variante.duckdb"
    constructeur.construire(variante)
    import duckdb

    con = duckdb.connect(str(variante))
    # Même TrackName, tracé différent : exactement le cas de Monza.
    con.execute(
        "UPDATE metadata SET value = 'Circuit de test Variante' "
        "WHERE key = 'TrackLayout'"
    )
    con.close()

    with pytest.raises(ErreurTelemetrie) as erreur:
        comparer_fichiers(session_test, 1, variante, 1)
    assert "Circuit de test Variante" in str(erreur.value)


# ----------------------------------------------------------------------
# Sur de vraies sessions
# ----------------------------------------------------------------------


def test_delta_reel_retombe_sur_les_chronos(dossier_lmu: Path | None) -> None:
    """Le contrôle qui compte : sur de vraies données, le delta final doit
    valoir la différence des chronos officiels du jeu.

    La tolérance de 0,05 s vient de ce que les deux tours ne couvrent pas
    exactement la même longueur de `Lap Dist` : l'axe commun s'arrête un peu
    avant la ligne. Mesuré sur les sessions du disque, l'écart reste sous
    0,035 s.
    """
    if dossier_lmu is None:
        pytest.skip("Le Mans Ultimate n'est pas installé sur cette machine")

    compares = 0
    for fichier in catalogue.lister(dossier_lmu)[:25]:
        try:
            session = Session.ouvrir(fichier.chemin)
        except (SessionEnCours, ErreurTelemetrie):
            continue
        valides = [t.numero for t in session.tours_valides if t.chrono]
        for a, b in zip(valides, valides[1:]):
            c = comparer_fichiers(fichier.chemin, a, fichier.chemin, b)
            assert c.ecart_final == pytest.approx(c.ecart_chronos, abs=0.05), (
                f"{fichier.chemin.name} tours {a}/{b}"
            )
            assert c.delta[0] == pytest.approx(0.0)
            compares += 1
            if compares >= 12:
                return
    if not compares:
        pytest.skip("aucune paire de tours valides à comparer")
