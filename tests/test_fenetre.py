"""Le calcul des gestes de la fenêtre. Les gestes eux-mêmes ont été vérifiés avec de
vrais événements de souris (voir docs/14-redesign.md) : ils ne se testent pas sans
écran."""

from __future__ import annotations

import pytest

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
