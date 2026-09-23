"""Tests du découpage en tours et de la validité.

Le scénario de la session synthétique est décrit dans
`tests/fixtures/construire.py` : chaque cas y a été construit exprès.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lmu_telemetry.errors import SessionEnCours
from lmu_telemetry.session import TOLERANCE_CHRONO, Session
from tests.fixtures import construire as constructeur


@pytest.fixture
def session(session_test: Path) -> Session:
    return Session.ouvrir(session_test)


# ----------------------------------------------------------------------
# Découpage
# ----------------------------------------------------------------------


def test_un_tour_par_franchissement(session: Session) -> None:
    attendus = len(constructeur.FRONTIERES)
    assert len(session.tours) == attendus
    assert [t.numero for t in session.tours] == list(range(attendus))
    assert [t.debut for t in session.tours] == list(constructeur.FRONTIERES)


def test_dernier_tour_non_boucle(session: Session) -> None:
    dernier = session.tours[-1]
    assert dernier.complet is False
    assert dernier.fin is None
    assert dernier.duree_mesuree is None
    assert dernier.valide is False
    assert "non bouclé" in " ".join(map(str, dernier.remarques))


# ----------------------------------------------------------------------
# Chronos : le décalage d'un tour est le piège principal du format
# ----------------------------------------------------------------------


def test_chrono_decale_dun_tour(session: Session) -> None:
    """Le chrono écrit à l'instant où commence le tour N est celui du tour N-1."""
    assert session.tours[1].chrono == pytest.approx(90.0)
    # Le tour 3 met 2 s de plus : il s'arrête deux secondes en piste.
    assert session.tours[3].chrono == pytest.approx(92.0)
    # Le tour 0 (sortie des stands) et le tour 2 (invalidé) n'en ont aucun.
    assert session.tours[0].chrono is None
    assert session.tours[2].chrono is None


def test_chrono_et_duree_mesuree_concordent(session: Session) -> None:
    """Contrôle croisé : deux chemins indépendants doivent donner le même temps."""
    for tour in session.tours:
        if tour.chrono is not None and tour.duree_mesuree is not None:
            assert tour.ecart_chrono == pytest.approx(0.0, abs=TOLERANCE_CHRONO)
            assert tour.coherent is True


def test_secteurs_obtenus_par_difference(session: Session) -> None:
    """Le jeu donne des temps CUMULÉS ; les durées se déduisent par soustraction."""
    s1, s2, s3 = session.tours[1].secteurs
    assert (s1, s2, s3) == pytest.approx((30.0, 30.0, 30.0))
    assert s1 + s2 + s3 == pytest.approx(session.tours[1].chrono)


def test_pas_de_secteurs_sans_chrono(session: Session) -> None:
    assert session.tours[2].secteurs == (None, None, None)


# ----------------------------------------------------------------------
# Validité
# ----------------------------------------------------------------------


def test_tour_de_sortie_des_stands_ecarte(session: Session) -> None:
    tour = session.tours[0]
    assert tour.stands is True
    assert tour.valide is False
    assert "stands" in " ".join(map(str, tour.remarques))


def test_tour_invalide_par_le_jeu(session: Session) -> None:
    """Un tour bouclé hors des stands mais sans chrono : le jeu l'a invalidé."""
    tour = session.tours[2]
    assert tour.complet is True
    assert tour.stands is False
    assert tour.chronometre is False
    assert tour.valide is False
    assert "invalidé par le jeu" in " ".join(map(str, tour.remarques))


def test_tours_valides(session: Session) -> None:
    # Le 0 passe par les stands, le 2 est invalidé par le jeu, le dernier
    # n'est pas bouclé.
    assert [t.numero for t in session.tours_valides] == [1, 3, 4, 5]


def test_meilleur_tour_parmi_les_valides(session: Session) -> None:
    meilleur = session.meilleur_tour
    assert meilleur is not None
    assert meilleur.numero == 1  # 90 s contre 92 s pour le tour 3


# ----------------------------------------------------------------------
# Incidents observés : des constats, pas des interprétations
# ----------------------------------------------------------------------


def test_hors_piste_mesure(session: Session) -> None:
    assert session.tours[3].duree_hors_piste == pytest.approx(1.0, abs=0.21)
    assert session.tours[1].duree_hors_piste == pytest.approx(0.0)


def test_chocs_sans_compter_letat_initial(session: Session) -> None:
    """La valeur présente à t0 est l'état de départ, pas un choc."""
    assert session.tours[3].contacts == 2
    assert session.tours[0].contacts == 0


def test_quasi_arret(session: Session) -> None:
    tour = session.tours[3]
    assert tour.vitesse_min == pytest.approx(0.0)
    assert tour.duree_quasi_arret == pytest.approx(2.0, abs=0.02)
    assert tour.quasi_arret is True
    assert "quasi-arrêt" in " ".join(map(str, tour.remarques))


def test_un_incident_ne_disqualifie_pas_un_tour_chronometre(session: Session) -> None:
    """Le jeu arbitre la validité ; l'outil se contente de signaler ce qu'il voit."""
    tour = session.tours[3]
    assert tour.contacts == 2
    assert tour.quasi_arret is True
    assert tour.valide is True  # le jeu l'a chronométré


def test_virage_lent_nest_pas_un_arret(session: Session) -> None:
    tour = session.tours[1]
    assert tour.vitesse_min == pytest.approx(60.0)
    assert tour.quasi_arret is False
    assert tour.remarques == ()


# ----------------------------------------------------------------------
# Sur de vraies sessions, si le jeu est installé sur cette machine
# ----------------------------------------------------------------------


def test_coherence_sur_vraies_sessions(dossier_lmu: Path | None) -> None:
    """Sur les vraies données, chrono du jeu et durée mesurée doivent coller.

    Seule exception connue et vérifiée sur les 435 tours du disque : le tour 0
    d'une course, où la voiture attend le départ sur la grille. Ces tours sont
    justement ceux que `coherent` écarte.
    """
    if dossier_lmu is None:
        pytest.skip("Le Mans Ultimate n'est pas installé sur cette machine")

    fichiers = sorted(dossier_lmu.glob("*.duckdb"))[:30]
    if not fichiers:
        pytest.skip("aucune session enregistrée")

    compares = 0
    for chemin in fichiers:
        try:
            session = Session.ouvrir(chemin)
        except SessionEnCours:
            continue
        for tour in session.tours:
            if tour.ecart_chrono is None:
                continue
            compares += 1
            if tour.coherent:
                assert tour.ecart_chrono < TOLERANCE_CHRONO
            else:
                # Divergence franche, jamais un entre-deux ambigu.
                assert tour.ecart_chrono > 5.0
                assert tour.valide is False
    assert compares > 0, "aucun tour chronométré à comparer"
