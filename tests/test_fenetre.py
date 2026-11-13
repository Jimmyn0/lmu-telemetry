"""Le calcul des gestes de la fenêtre. Les gestes eux-mêmes ont été vérifiés avec de
vrais événements de souris (voir docs/14-redesign.md) : ils ne se testent pas sans
écran."""

from __future__ import annotations

import pytest

import os
import sys
import types

from lmu_telemetry import fenetre
from lmu_telemetry.fenetre import Rectangle, redimensionne

DEPART = Rectangle(100, 100, 1500, 1000)
MINIMA = {"largeur_min": 1120, "hauteur_min": 680}


@pytest.mark.parametrize(
    "bord, dx, dy, attendu",
    [
        ("e", 50, 999, Rectangle(100, 100, 1550, 1000)),
        ("o", -50, 999, Rectangle(50, 100, 1500, 1000)),
        ("s", 999, 50, Rectangle(100, 100, 1500, 1050)),
        ("n", 999, -50, Rectangle(100, 50, 1500, 1000)),
        ("se", 50, 60, Rectangle(100, 100, 1550, 1060)),
        ("no", -50, -60, Rectangle(50, 40, 1500, 1000)),
        ("ne", 50, -60, Rectangle(100, 40, 1550, 1000)),
        ("so", -50, 60, Rectangle(50, 100, 1500, 1060)),
    ],
)
def test_seul_le_bord_tire_bouge(bord, dx, dy, attendu) -> None:
    assert redimensionne(DEPART, bord, dx, dy, **MINIMA) == attendu


@pytest.mark.parametrize(
    "bord, dx, dy, attendu",
    [
        ("e", -3000, 0, Rectangle(100, 100, 1220, 1000)),
        ("o", 3000, 0, Rectangle(380, 100, 1500, 1000)),
        ("s", 0, -3000, Rectangle(100, 100, 1500, 780)),
        ("n", 0, 3000, Rectangle(100, 320, 1500, 1000)),
    ],
)
def test_le_minimum_arrete_le_bord_sans_pousser_le_cote_oppose(bord, dx, dy, attendu) -> None:
    assert redimensionne(DEPART, bord, dx, dy, **MINIMA) == attendu


def test_les_dimensions_d_un_rectangle() -> None:
    assert DEPART.largeur == 1400
    assert DEPART.hauteur == 900


# ----------------------------------------------------------------------
# Un outil décompressé depuis un zip téléchargé
# ----------------------------------------------------------------------


def _marquer(fichier) -> None:
    """Ce que Windows écrit sur chaque fichier d'un zip téléchargé."""
    with open(f"{fichier}:Zone.Identifier", "w", encoding="ascii") as flux:
        flux.write("[ZoneTransfer]\r\nZoneId=3\r\n")


def test_la_marque_internet_est_retiree_des_bibliotheques(tmp_path) -> None:
    (tmp_path / "pythonnet").mkdir()
    for nom in ("pythonnet/Python.Runtime.dll", "_ctypes.pyd", "GhostLine.exe", "base_library.zip"):
        (tmp_path / nom).write_bytes(b"x")
        _marquer(tmp_path / nom)
    assert fenetre.retirer_marque_internet(tmp_path) == 3
    marques = {p.name for p in tmp_path.rglob("*") if os.path.exists(f"{p}:Zone.Identifier")}
    assert marques == {"base_library.zip"}
    # Au lancement suivant, il n'y a plus rien à faire.
    assert fenetre.retirer_marque_internet(tmp_path) == 0


def test_hors_du_exe_aucun_fichier_n_est_touche(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert fenetre.retirer_marque_internet() == 0


def test_la_cause_d_une_fenetre_qui_ne_s_ouvre_pas_est_gardee(monkeypatch) -> None:
    faux = types.ModuleType("webview")
    faux.create_window = lambda *args, **kwargs: types.SimpleNamespace(events=None)

    def demarrer(*args, **kwargs):
        raise RuntimeError("Failed to resolve Python.Runtime.Loader.Initialize")

    faux.start = demarrer
    monkeypatch.setitem(sys.modules, "webview", faux)
    assert fenetre.ouvrir("http://127.0.0.1:1/") is False
    assert "Failed to resolve Python.Runtime.Loader.Initialize" in fenetre.ERREUR
