"""Lance les tests de la page, et vérifie que chaque fichier JavaScript se lit.

Node n'est pas nécessaire pour utiliser l'outil : sans lui, ces tests sont ignorés.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lmu_telemetry.web import serveur

NODE = shutil.which("node")
RACINE = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(NODE is None, reason="Node n'est pas installé")


@pytest.mark.parametrize("fichier", ["format.test.mjs", "service_groupe.test.mjs"])
def test_les_tests_javascript(fichier: str) -> None:
    """Les calculs de la page, et le service du groupe (`service/`) sur le SQLite de Node."""
    resultat = subprocess.run(
        [NODE, "--test", str(RACINE / "tests" / "js" / fichier)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr


@pytest.mark.parametrize("fichier", sorted(Path(serveur.STATIQUE).glob("*.js")), ids=lambda f: f.name)
def test_chaque_fichier_se_lit(fichier: Path) -> None:
    """Une erreur de syntaxe dans un fichier laisse toute la page blanche."""
    resultat = subprocess.run(
        [NODE, "--check", str(fichier)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert resultat.returncode == 0, resultat.stderr
