"""Tests de la conversion de l'angle volant, du pourcentage vers les degrés.

C'est la modification la plus délicate des trois, parce qu'elle repose sur une
INTERPRÉTATION de la donnée du jeu : le pourcentage est une fraction du
braquage maximal d'un côté, soit la moitié du débattement annoncé.

Cette interprétation a été vérifiée sur les vraies sessions — `Steering Pos`
sature à exactement 100,000 % et ne dépasse jamais — mais elle reste une
interprétation. Les tests ci-dessous la figent : si quelqu'un la change par
inadvertance, ils cassent.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from lmu_telemetry.donnees_tour import CANAL_BRAQUAGE, CANAL_VOLANT, _ajouter_volant
from lmu_telemetry.reader import InfoSession, _debattement


def _setup(valeur: str) -> str:
    return json.dumps({"VM_STEER_LOCK": {"caption": "Wheel Range (Lock)",
                                         "stringValue": valeur}})


# ----------------------------------------------------------------------
# Lecture du réglage
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "brut, volant, roues",
    [
        # Les trois écritures réellement rencontrées sur les 26 voitures.
        ("584 (20.3) deg", 584.0, 20.3),  # la plus courante
        ("524deg (18.5deg)", 524.0, 18.5),  # McLaren 720S
        ("516 deg(19.7 )", 516.0, 19.7),  # BMW M4
        ("440 (17) deg", 440.0, 17.0),  # entiers
        ("336 (13) deg", 336.0, 13.0),  # Oreca 07, le plus petit débattement
    ],
)
def test_debattement_lu_quelle_que_soit_la_ponctuation(
    brut: str, volant: float, roues: float
) -> None:
    """La chaîne n'a pas de format stable : on extrait les nombres sans rien
    supposer des espaces ni des parenthèses."""
    assert _debattement(_setup(brut)) == (volant, roues)


@pytest.mark.parametrize(
    "brut",
    [
        "",  # réglage vide
        "deg",  # aucun nombre
        "584 deg",  # un seul nombre : on ne sait pas lequel
        "5 (2) deg",  # débattement invraisemblable
        "9000 (20) deg",  # idem, dans l'autre sens
    ],
)
def test_reglage_incomprehensible_refuse(brut: str) -> None:
    """Mieux vaut afficher des pourcentages que des degrés faux."""
    volant, _ = _debattement(_setup(brut))
    assert volant is None


def test_setup_absent_ou_casse() -> None:
    assert _debattement(None) == (None, None)
    assert _debattement("") == (None, None)
    assert _debattement("{ pas du json") == (None, None)
    assert _debattement('{"autre": 1}') == (None, None)


def test_demultiplication() -> None:
    """292° au volant pour 20,3° aux roues : 14,4:1, l'ordre de grandeur
    attendu d'une GT3. C'est ce recoupement qui confirme que le premier nombre
    est bien le débattement TOTAL et pas celui d'un seul côté."""
    info = _info(584.0, 20.3)
    assert info.demultiplication == pytest.approx(14.38, abs=0.01)


def _info(volant: float | None, roues: float | None = None) -> InfoSession:
    return InfoSession(
        pilote="", circuit="", trace="", type_session="Practice", voiture="",
        categorie="", meteo="", enregistree_le=None, version_schema="1",
        setup_brut=None, debattement_volant=volant, angle_roues_max=roues,
    )


# ----------------------------------------------------------------------
# Conversion du canal
# ----------------------------------------------------------------------


def test_conversion_en_degres() -> None:
    """100 % = butée = la MOITIÉ du débattement total, parce que le
    débattement se compte d'une butée à l'autre."""
    valeurs = {CANAL_BRAQUAGE: np.array([0.0, 50.0, 100.0, -100.0])}
    _ajouter_volant(valeurs, _info(584.0))
    assert valeurs[CANAL_VOLANT] == pytest.approx([0.0, 146.0, 292.0, -292.0])


def test_deux_voitures_au_meme_pourcentage_ne_braquent_pas_pareil() -> None:
    """C'est la raison d'être de la conversion : 40 % ne veulent pas dire la
    même chose sur une Porsche et sur une Oreca."""
    porsche = {CANAL_BRAQUAGE: np.array([40.0])}
    oreca = {CANAL_BRAQUAGE: np.array([40.0])}
    _ajouter_volant(porsche, _info(584.0))
    _ajouter_volant(oreca, _info(336.0))
    assert porsche[CANAL_VOLANT][0] == pytest.approx(116.8)
    assert oreca[CANAL_VOLANT][0] == pytest.approx(67.2)


def test_pas_de_degres_sans_debattement() -> None:
    """Sans le réglage, on ne convertit pas : le pourcentage reste affiché."""
    valeurs = {CANAL_BRAQUAGE: np.array([40.0])}
    _ajouter_volant(valeurs, _info(None))
    assert CANAL_VOLANT not in valeurs
    assert CANAL_BRAQUAGE in valeurs


def test_le_pourcentage_reste_disponible() -> None:
    """On ajoute un canal, on n'en remplace aucun : ce qui vient du jeu reste
    accessible tel quel."""
    valeurs = {CANAL_BRAQUAGE: np.array([40.0])}
    _ajouter_volant(valeurs, _info(584.0))
    assert valeurs[CANAL_BRAQUAGE] == pytest.approx([40.0])


# ----------------------------------------------------------------------
# Sur un vrai fichier
# ----------------------------------------------------------------------


def test_debattement_present_sur_toutes_les_vraies_sessions(dossier_lmu) -> None:
    """Vérifié sur les 388 sessions du disque : le réglage est toujours lisible.
    Si une mise à jour du jeu changeait ce champ, ce test le dirait."""
    if dossier_lmu is None:
        pytest.skip("Le Mans Ultimate n'est pas installé sur cette machine")

    from lmu_telemetry import catalogue
    from lmu_telemetry.errors import ErreurTelemetrie
    from lmu_telemetry.reader import FichierSession

    lus = manquants = 0
    for fichier in catalogue.lister(dossier_lmu)[:40]:
        try:
            with FichierSession(fichier.chemin) as session:
                info = session.info
        except ErreurTelemetrie:
            continue
        lus += 1
        if info.debattement_volant is None:
            manquants += 1
    assert lus > 0
    assert manquants == 0, f"{manquants} sessions sur {lus} sans débattement lisible"
