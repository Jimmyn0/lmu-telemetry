"""L'index des sessions : ce qu'on sait sans rouvrir les fichiers."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from lmu_telemetry import emplacements
from lmu_telemetry.errors import SessionEnCours
from lmu_telemetry.domaine.donnees_tour import bilan, charger
from lmu_telemetry.domaine.session import Session
from lmu_telemetry.sources import catalogue
from lmu_telemetry.stockage import index as module_index
from lmu_telemetry.stockage.index import Index, ResumeSession, balayage, contour, resumer
from lmu_telemetry.web import reponses

NOM = "Circuit de test_P_2026-01-02T03_04_05Z.duckdb"


@pytest.fixture
def dossier(session_test: Path, tmp_path: Path) -> Path:
    """Un dossier de télémétrie avec une session."""
    shutil.copy(session_test, tmp_path / NOM)
    return tmp_path


def _contexte(dossier: Path) -> reponses.Contexte:
    return reponses.Contexte(dossier=dossier)


def _lire(dossier: Path) -> dict:
    """La liste des sessions, une fois le balayage terminé."""
    reponses.sessions(_contexte(dossier))
    balayage.attendre(60)
    return reponses.sessions(_contexte(dossier))


# ----------------------------------------------------------------------
# Une session
# ----------------------------------------------------------------------


def test_le_resume_reprend_ce_que_dit_la_session(dossier: Path) -> None:
    chemin = dossier / NOM
    session = Session.ouvrir(chemin)
    resume = resumer(chemin)
    meilleur = session.meilleur_tour
    assert resume.illisible is None
    assert resume.trace == session.info.trace
    assert resume.tours == len(session.tours)
    assert resume.valides == len(session.tours_valides)
    assert resume.meilleur == meilleur.chrono
    assert resume.tour_meilleur == meilleur.numero
    assert resume.longueur == session.longueur
    assert resume.duree == session.duree


def test_un_fichier_abime_est_retenu_comme_illisible(tmp_path: Path) -> None:
    chemin = tmp_path / "abime.duckdb"
    chemin.write_bytes(b"pas une base" * 100)
    resume = resumer(chemin)
    assert "abime.duckdb" in resume.illisible
    assert resume.tours == 0


def test_une_session_verrouillee_n_est_pas_retenue(dossier: Path, monkeypatch) -> None:
    """Le jeu l'écrit encore : ce qu'on en lirait serait incomplet."""

    def refuser(_chemin):
        raise SessionEnCours(dossier / NOM)

    monkeypatch.setattr(module_index.Session, "ouvrir", refuser)
    assert resumer(dossier / NOM) is None


def test_le_contour_tient_dans_un_carre_unite(dossier: Path) -> None:
    points = contour(resumer(dossier / NOM))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    assert len(points) == module_index.POINTS_CONTOUR
    assert min(xs) == 0 and min(ys) == 0
    assert max(max(xs), max(ys)) == pytest.approx(1.0)


def test_pas_de_contour_sans_tour_valide() -> None:
    assert contour(ResumeSession("x", 0, 0)) is None


# ----------------------------------------------------------------------
# Le fichier de l'index
# ----------------------------------------------------------------------


def test_une_ligne_se_relit_a_l_identique() -> None:
    ligne = ResumeSession("a.duckdb", 12, 34, trace="Monza", tours=3, valides=2, meilleur=95.5)
    Index().enregistrer([ligne])
    assert Index().lignes() == {"a.duckdb": ligne}


def test_un_index_abime_repart_de_zero() -> None:
    chemin = emplacements.fichier_index()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(b"pas une base sqlite" * 200)
    assert Index().lignes() == {}


def test_un_index_d_une_autre_version_se_reconstruit() -> None:
    Index().enregistrer([ResumeSession("a.duckdb", 1, 2)])
    connexion = sqlite3.connect(emplacements.fichier_index())
    connexion.execute("PRAGMA user_version = 999")
    connexion.commit()
    connexion.close()
    assert Index().lignes() == {}


# ----------------------------------------------------------------------
# Le balayage
# ----------------------------------------------------------------------


def test_la_liste_s_affiche_avant_d_etre_complete(dossier: Path, monkeypatch) -> None:
    """Le nom du fichier suffit : la page n'attend pas le balayage."""
    monkeypatch.setattr(balayage, "relancer", lambda *_: None)
    reponse = reponses.sessions(_contexte(dossier))
    assert reponse["restant"] == 1
    assert reponse["sessions"][0]["circuit"] == "Circuit de test"
    assert "tours" not in reponse["sessions"][0]


def test_le_balayage_complete_la_liste(dossier: Path) -> None:
    reponse = _lire(dossier)
    assert reponse["restant"] == 0
    session = reponse["sessions"][0]
    assert session["trace"] == "Circuit de test"
    assert session["valides"] > 0
    assert session["meilleur"] > 0


def test_une_session_deja_lue_ne_se_relit_pas(dossier: Path, monkeypatch) -> None:
    _lire(dossier)
    lues = []
    monkeypatch.setattr(module_index, "resumer", lambda c: lues.append(c))
    _lire(dossier)
    assert lues == []


def test_une_session_reecrite_se_relit(dossier: Path) -> None:
    _lire(dossier)
    connues = Index().lignes()
    chemin = dossier / NOM
    chemin.write_bytes(chemin.read_bytes() + b"\0" * 4096)
    a_lire = balayage.a_lire(catalogue.lister(dossier), connues)
    assert a_lire == [chemin]


def test_un_fichier_abime_ne_bloque_pas_les_autres(dossier: Path) -> None:
    (dossier / "Abime_P_2026-01-03T03_04_05Z.duckdb").write_bytes(b"pas une base" * 100)
    reponse = _lire(dossier)
    assert reponse["restant"] == 0
    par_nom = {s["nom"]: s for s in reponse["sessions"]}
    assert "Abime" in par_nom["Abime_P_2026-01-03T03_04_05Z.duckdb"]["indisponible"]
    assert par_nom[NOM]["indisponible"] is None


def test_une_session_en_cours_ne_fait_pas_tourner_la_page_en_rond(
    dossier: Path, monkeypatch
) -> None:
    """Le jeu tient un fichier ouvert : la page ne doit pas attendre sans fin."""
    monkeypatch.setattr(module_index, "resumer", lambda _: None)
    reponses.sessions(_contexte(dossier))
    balayage.attendre(60)
    assert reponses.sessions(_contexte(dossier))["restant"] == 0


# ----------------------------------------------------------------------
# Les records
# ----------------------------------------------------------------------


#: Temps au tour ne compte que les qualifs et les courses : la session de test y entre en
#: qualifs.
QUALIFS = "Circuit de test_Q_2026-01-03T03_04_05Z.duckdb"


@pytest.fixture
def qualifs(session_test: Path, tmp_path: Path) -> Path:
    """Un dossier de télémétrie avec une session de qualifs."""
    shutil.copy(session_test, tmp_path / QUALIFS)
    return tmp_path


def _records(dossier: Path) -> dict:
    _lire(dossier)
    return reponses.circuits(_contexte(dossier))


def test_les_records_regroupent_les_sessions_d_un_trace(qualifs: Path, session_test: Path) -> None:
    shutil.copy(session_test, qualifs / "Circuit de test_R_2026-01-04T03_04_05Z.duckdb")
    circuits = _records(qualifs)["circuits"]
    assert [c["circuit"] for c in circuits] == ["Circuit de test"]
    trace = circuits[0]["traces"][0]
    assert trace["sessions"] == 2
    # Même voiture dans les deux sessions : un seul record.
    assert len(trace["records"]) == 1
    assert trace["records"][0]["chrono"] == Session.ouvrir(qualifs / QUALIFS).meilleur_tour.chrono


def test_les_essais_ne_comptent_pas_dans_temps_au_tour(dossier: Path, session_test: Path) -> None:
    """Demandé le 2026-11-14 : en essais, on roule pour régler, pas pour le chrono."""
    assert _records(dossier)["circuits"] == []
    shutil.copy(session_test, dossier / QUALIFS)
    trace = _records(dossier)["circuits"][0]["traces"][0]
    assert trace["sessions"] == 1
    assert [r["type"] for r in trace["records"]] == ["Q"]
    assert {m["type"] for m in trace["meilleurs"]} == {"Q"}


def test_le_record_designe_le_tour_a_ouvrir(qualifs: Path) -> None:
    record = _records(qualifs)["circuits"][0]["traces"][0]["records"][0]
    meilleur = Session.ouvrir(qualifs / QUALIFS).meilleur_tour
    assert record["session"] == str(qualifs / QUALIFS)
    assert record["tour"] == meilleur.numero
    assert record["type"] == "Q"
    assert len(record["secteurs"]) == 3


def test_le_contour_accompagne_le_trace(qualifs: Path) -> None:
    trace = _records(qualifs)["circuits"][0]["traces"][0]
    assert len(trace["contour"]) == module_index.POINTS_CONTOUR


def test_le_pilote_est_celui_des_sessions(qualifs: Path) -> None:
    assert _records(qualifs)["pilote"] == "Pilote de test"


def test_une_session_sans_tour_valide_compte_sans_faire_de_record(qualifs: Path) -> None:
    Index().enregistrer([])
    _lire(qualifs)
    lignes = Index().lignes()
    chemin = str(qualifs / QUALIFS)
    ligne = lignes[chemin]
    sans = ResumeSession(ligne.chemin, ligne.mtime_ns, ligne.taille, trace=ligne.trace, tours=2)
    Index().enregistrer([sans])
    trace = reponses.circuits(_contexte(qualifs))["circuits"][0]["traces"][0]
    assert trace["sessions"] == 1
    assert trace["tours"] == 2
    assert trace["records"] == []


# ----------------------------------------------------------------------
# Le bilan d'un tour
# ----------------------------------------------------------------------


def test_le_bilan_d_un_tour(session_test: Path) -> None:
    tour = charger(session_test, 1)
    resultat = bilan(tour)
    assert resultat.vitesse_max == pytest.approx(tour.canaux["Ground Speed"].max())
    assert resultat.vitesse_moyenne == pytest.approx(tour.longueur / tour.duree * 3.6)


def test_le_bilan_sans_carburant_ne_l_invente_pas(session_test: Path) -> None:
    resultat = bilan(charger(session_test, 1))
    assert resultat.carburant is None
    assert resultat.energie is None


def test_la_fin_des_secteurs_est_une_distance(session_test: Path) -> None:
    tour = charger(session_test, 1)
    resultat = bilan(tour)
    if tour.tour.cumul_s1 is None:
        assert resultat.fin_s1 is None
    else:
        assert 0 < resultat.fin_s1 < resultat.fin_s2 < tour.longueur


def test_un_tour_se_compare_seul(session_test: Path) -> None:
    """La page peut n'afficher qu'un tour de référence."""
    resultat = reponses.comparaison(
        reponses.Contexte(), {"ref": [str(session_test)], "tour_ref": ["1"]}
    )
    assert resultat["ecart_final"] == 0
    assert resultat["reference"]["numero"] == resultat["compare"]["numero"] == 1
    assert len(resultat["reference"]["temps"]) == resultat["distance"]["nombre"]
