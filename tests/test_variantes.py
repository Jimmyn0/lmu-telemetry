"""Tests des variantes de tracé d'un même circuit.

LMU propose plusieurs tracés du même circuit — « Monza Curva Grande Circuit »
à côté d'« Autodromo Nazionale Monza » — qui portent le MÊME `TrackName`, donc
le même nom de fichier sur le disque. Seul `TrackLayout` les distingue.

C'est une source d'erreur silencieuse : les deux Monza partageaient le même
fichier de découpage en virages, alors que la variante n'a pas la Variante del
Rettifilo et compte 9 virages au lieu de 11.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from lmu_telemetry.reader import FichierSession
from lmu_telemetry.virages import DefinitionCircuit, detecter, fichier_definition
from lmu_telemetry.donnees_tour import charger
from tests.fixtures import construire as constructeur


@pytest.fixture
def variante(tmp_path: Path) -> Path:
    """Une copie de la session de test, même circuit mais autre tracé."""
    chemin = tmp_path / "variante.duckdb"
    constructeur.construire(chemin)
    con = duckdb.connect(str(chemin))
    con.execute(
        "UPDATE metadata SET value = 'Circuit de test Variante' "
        "WHERE key = 'TrackLayout'"
    )
    con.close()
    return chemin


def test_le_trace_est_distinct_du_circuit(variante: Path) -> None:
    with FichierSession(variante) as f:
        assert f.info.circuit == "Circuit de test"
        assert f.info.trace == "Circuit de test Variante"


def test_le_decoupage_porte_le_trace(session_test: Path, variante: Path) -> None:
    """C'est le correctif : sans lui, deux tracés écrivent dans le même
    fichier de virages et le second écrase le découpage du premier."""
    normal = detecter([charger(session_test, 1), charger(session_test, 3)])
    autre = detecter([charger(variante, 1), charger(variante, 3)])
    assert normal.circuit == "Circuit de test"
    assert autre.circuit == "Circuit de test Variante"


def test_les_fichiers_de_virages_sont_distincts(tmp_path: Path) -> None:
    a = fichier_definition(tmp_path, "Autodromo Nazionale Monza")
    b = fichier_definition(tmp_path, "Monza Curva Grande Circuit")
    assert a != b


def test_relecture_conserve_le_trace(tmp_path: Path, variante: Path) -> None:
    definition = detecter([charger(variante, 1), charger(variante, 3)])
    chemin = fichier_definition(tmp_path, definition.circuit)
    definition.enregistrer(chemin)
    assert DefinitionCircuit.lire(chemin).circuit == "Circuit de test Variante"
