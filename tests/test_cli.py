"""Tests de la mise en forme et de la ligne de commande."""

from __future__ import annotations

from pathlib import Path

import pytest

from lmu_telemetry.cli import chrono, main


def test_format_chrono() -> None:
    assert chrono(93.709) == "1:33.709"
    assert chrono(114.81) == "1:54.810"
    assert chrono(9.5) == "0:09.500"
    assert chrono(None) == "—"


def test_duree_mesuree_affichee_au_centieme() -> None:
    """La durée mesurée ne vaut qu'à ±0,02 s près : pas de fausse précision.

    L'afficher au millième laisserait croire que le décalage de quelques
    centièmes avec le chrono du jeu est une anomalie, alors qu'il vient de la
    granularité d'inscription des événements.
    """
    assert chrono(114.8203, decimales=2) == "1:54.82"
    assert chrono(113.7001, decimales=2) == "1:53.70"


def test_date_du_nom_de_fichier_est_en_utc(tmp_path: Path) -> None:
    """Le jeu horodate ses fichiers en UTC ; la liste doit le savoir.

    Sans cette information, une session enregistrée à 14 h 12 en France
    s'affichait à 12 h 12 dans la liste, alors que le détail de la session — qui
    lit la métadonnée, elle correctement marquée — affichait bien 14 h 12.
    """
    from lmu_telemetry.catalogue import lister

    (tmp_path / "Circuit de test_P_2026-09-08T12_12_19Z.duckdb").write_bytes(b"")
    repere = lister(tmp_path)[0]
    assert repere.enregistre_le is not None
    assert repere.enregistre_le.tzinfo is not None
    assert repere.enregistre_le.utcoffset().total_seconds() == 0
    assert repere.enregistre_le.hour == 12


def test_commande_tours(session_test: Path, capsys: pytest.CaptureFixture) -> None:
    code = main(["tours", str(session_test)])
    sortie = capsys.readouterr().out
    assert code == 0
    assert "Circuit de test" in sortie
    assert "1:30.000" in sortie  # chrono du jeu, au millième
    assert "1:30.00" in sortie  # durée mesurée, au centième
    assert "invalidé par le jeu" in sortie


def test_erreur_affichee_sans_stacktrace(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Le brief l'exige : un message qui dit quoi faire, pas une trace Python."""
    code = main(["tours", str(tmp_path / "absent.duckdb")])
    capture = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in capture.err
    assert "Vérifie le chemin" in capture.err
