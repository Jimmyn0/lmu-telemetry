"""Fixtures partagées par les tests.

Aucun test n'a besoin que Le Mans Ultimate soit installé ni lancé : la session
de test est fabriquée par `tests/fixtures/construire.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from tests.fixtures import construire as constructeur  # noqa: E402


@pytest.fixture(autouse=True)
def donnees_isolees(tmp_path_factory, monkeypatch) -> Path:
    """Les tests ne touchent jamais au vrai dossier de données de l'utilisateur.

    Sans ça, un test qui choisit un dossier de télémétrie ou recopie un
    découpage écrirait dans `%LOCALAPPDATA%\\Telemetrie LMU` pour de bon.
    """
    dossier = tmp_path_factory.mktemp("donnees")
    monkeypatch.setenv("LMU_DONNEES", str(dossier))
    return dossier


@pytest.fixture(scope="session")
def session_test() -> Path:
    """Chemin de la session synthétique, construite si elle manque."""
    chemin = constructeur.SORTIE
    if not chemin.exists():
        constructeur.construire()
    return chemin


@pytest.fixture(scope="session")
def dossier_lmu() -> Path | None:
    """Vrai dossier de télémétrie de LMU, ou None s'il n'existe pas ici.

    Sert aux tests de bout en bout sur de vraies données. Ils sont ignorés sur
    une machine où le jeu n'est pas installé — les tests de logique métier, eux,
    tournent partout.
    """
    from lmu_telemetry import catalogue
    from lmu_telemetry.errors import DossierIntrouvable

    try:
        return catalogue.dossier_telemetrie()
    except DossierIntrouvable:
        return None
