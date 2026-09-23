"""Tests du découpage en virages numérotés : un par apex.

Les formes sont construites ici, à la main. Un arc dont on sait qu'il tourne à
gauche est le seul moyen de vérifier une convention de signe sans se fier à ce
qu'on croit savoir d'un circuit réel ; une chicane synthétique est le seul
moyen de vérifier qu'elle donne bien deux virages et non un.
"""

from __future__ import annotations

import numpy as np
import pytest

from lmu_telemetry.virages import (
    ANGLE_MINIMAL,
    ECART_FUSION,
    RAYON_MAXIMAL,
    Virage,
    _angle_balaye,
    _apex,
    _sens_et_chicane,
    courbure,
    courbure_signee,
)

SEUIL = 1.0 / RAYON_MAXIMAL


def _arc(rayon: float, sens: int, longueur: float = 300.0, pas: float = 1.0):
    """Arc de cercle parcouru dans le sens de marche, échantillonné au mètre.

    `sens` vaut +1 pour un virage à gauche, -1 pour un virage à droite.
    """
    angles = np.arange(0.0, longueur, pas) / rayon
    # Départ vers l'est. À gauche, le centre est au nord ; à droite, au sud.
    x = rayon * np.sin(angles)
    y = sens * rayon * (1.0 - np.cos(angles))
    return np.column_stack([x, y])


def _profil(morceaux) -> np.ndarray:
    """Courbure signée fabriquée morceau par morceau : (longueur en m, rayon).

    Un rayon nul décrit une ligne droite ; un rayon négatif, un virage à droite.
    """
    parties = []
    for longueur, rayon in morceaux:
        valeur = 0.0 if rayon == 0 else 1.0 / rayon
        parties.append(np.full(int(longueur), valeur))
    return np.concatenate(parties)


# ----------------------------------------------------------------------
# Le signe de la courbure
# ----------------------------------------------------------------------


def test_gauche_est_positif() -> None:
    assert np.median(courbure_signee(_arc(80.0, +1))[30:-30]) > 0


def test_droite_est_negatif() -> None:
    assert np.median(courbure_signee(_arc(80.0, -1))[30:-30]) < 0


def test_le_rayon_est_retrouve() -> None:
    """Le signe ne doit pas abîmer l'intensité : 1/|courbure| reste le rayon."""
    k = courbure_signee(_arc(80.0, -1))
    assert 1.0 / abs(np.median(k[30:-30])) == pytest.approx(80.0, rel=0.05)


def test_courbure_est_la_valeur_absolue() -> None:
    axe = _arc(120.0, -1)
    assert np.allclose(courbure(axe), np.abs(courbure_signee(axe)))


def test_angle_balaye() -> None:
    """100 m sur un rayon de 100 m, c'est un radian, soit 57,3°."""
    assert _angle_balaye(_profil([(100, 100.0)]), 0, 100, 1.0) == pytest.approx(
        57.3, abs=0.1
    )


# ----------------------------------------------------------------------
# Le découpage en apex
# ----------------------------------------------------------------------


def test_une_chicane_donne_deux_virages() -> None:
    """LE point de la numérotation par apex : à Monza, la Variante del
    Rettifilo compte pour deux virages, pas un. On freine pour le premier et on
    ressort du second ; les lire séparément est tout l'intérêt."""
    profil = _profil([(200, 0), (60, 20.0), (10, 0), (60, -20.0), (200, 0)])
    assert len(_apex(profil, SEUIL, ecart=int(ECART_FUSION))) == 2


def test_les_deux_moities_ne_se_recollent_jamais() -> None:
    """Même collées, deux moitiés de chicane restent distinctes : le recollage
    ne joue qu'entre virages de MÊME sens."""
    profil = _profil([(100, 0), (60, 20.0), (60, -20.0), (100, 0)])
    assert len(_apex(profil, SEUIL, ecart=1000)) == 2


def test_courbe_qui_se_relache_reste_un_seul_virage() -> None:
    """Cas réel de la Curva Grande de Monza : la corde se relâche en son
    milieu, et le virage se découpait en deux."""
    profil = _profil([(100, 0), (80, 200.0), (30, 5000.0), (80, 200.0), (100, 0)])
    assert len(_apex(profil, SEUIL, ecart=int(ECART_FUSION))) == 1


def test_deux_virages_de_meme_sens_bien_separes_restent_deux() -> None:
    """Les deux Lesmo tournent du même côté et comptent pour deux (6 et 7)."""
    profil = _profil([(100, 0), (80, 60.0), (250, 0), (80, 40.0), (100, 0)])
    assert len(_apex(profil, SEUIL, ecart=int(ECART_FUSION))) == 2


def test_virage_serre_et_court_est_garde() -> None:
    """Un virage de 14 m de rayon qui tourne de 90° ne mesure que 22 m. Un
    seuil en LONGUEUR le jetait ; le seuil en angle le garde.

    Constaté à Portimão : la moitié d'une chicane disparaissait, et les deux
    virages qui l'encadraient se retrouvaient collés.
    """
    profil = _profil([(200, 0), (22, 14.0), (200, 0)])
    assert len(_apex(profil, SEUIL, ecart=int(ECART_FUSION))) == 1


def test_virage_doux_fragmente_est_retrouve() -> None:
    """Un virage doux dont la courbure oscille autour du seuil se fragmente en
    morceaux de même sens, chacun trop petit pour compter. Réunis, ils forment
    pourtant un vrai virage.

    Cas réel de Long Beach, à 62 m de la ligne : 21 à 23° de virage, détecté
    dans une session sur trois seulement tant qu'on triait avant de recoller.
    """
    # Trois morceaux de 8° environ, séparés par de courts passages sous le seuil.
    morceau = (np.radians(8) * 300.0, 300.0)
    profil = _profil([(200, 0), morceau, (10, 5000.0), morceau, (10, 5000.0),
                      morceau, (200, 0)])
    assert len(_apex(profil, SEUIL, ecart=int(ECART_FUSION))) == 1


def test_fremissement_dans_une_chicane_ne_la_coupe_pas() -> None:
    """Le cas inverse, qu'il ne faut pas casser en réglant le précédent : une
    bribe de sens opposé, trop petite pour être un virage, au milieu d'une
    courbe. Cas réel de la chicane de Monza, qui donnait quatre virages."""
    profil = _profil([(200, 0), (60, -30.0), (6, 40.0), (40, -30.0),
                      (5, 0), (60, 20.0), (200, 0)])
    plages = _apex(profil, SEUIL, ecart=int(ECART_FUSION))
    assert len(plages) == 2


def test_coude_long_mais_mou_est_ecarte() -> None:
    """L'erreur inverse : 30 m sur un rayon de 395 m ne tournent que 4°. C'est
    une inflexion de ligne droite, pas un virage."""
    profil = _profil([(200, 0), (30, 395.0), (200, 0)])
    assert _apex(profil, SEUIL, ecart=int(ECART_FUSION)) == []


def test_ligne_droite_ne_donne_aucun_virage() -> None:
    assert _apex(_profil([(500, 0)]), SEUIL, ecart=int(ECART_FUSION)) == []


def test_angle_minimal_respecte() -> None:
    """Juste en dessous du seuil, rien ; juste au-dessus, un virage."""
    rayon = 100.0
    court = np.radians(ANGLE_MINIMAL - 2) * rayon
    long = np.radians(ANGLE_MINIMAL + 2) * rayon
    assert _apex(_profil([(100, 0), (court, rayon), (100, 0)]), SEUIL, 40) == []
    assert len(_apex(_profil([(100, 0), (long, rayon), (100, 0)]), SEUIL, 40)) == 1


# ----------------------------------------------------------------------
# Sens
# ----------------------------------------------------------------------


def test_virage_simple_a_un_sens() -> None:
    assert _sens_et_chicane(np.full(50, +0.01)) == {"sens": 1, "chicane": False}
    assert _sens_et_chicane(np.full(50, -0.01)) == {"sens": -1, "chicane": False}


def test_le_sens_est_celui_du_virage_pas_du_fremissement() -> None:
    """Un virage à droite traversé par un frémissement très courbé vers la
    gauche reste un virage à droite. Cas réel du T1 de Portimão, qui
    s'affichait comme une chicane."""
    signee = np.concatenate([np.full(60, -0.02), np.full(4, +0.08), np.full(60, -0.02)])
    assert _sens_et_chicane(signee) == {"sens": -1, "chicane": False}


def test_zone_vide() -> None:
    assert _sens_et_chicane(np.array([])) == {"sens": 0, "chicane": False}


def test_libelles_du_sens() -> None:
    assert Virage(1, 0, 10, 50, sens=1).sens_libelle == "gauche"
    assert Virage(1, 0, 10, 50, sens=-1).sens_libelle == "droite"


# ----------------------------------------------------------------------
# Les libellés
# ----------------------------------------------------------------------


def test_libelle_est_le_numero() -> None:
    """Numéro, pas nom : c'est lui qui sert à se repérer d'un tableau à l'autre
    et à parler d'un virage sans ambiguïté."""
    assert Virage(3, 100, 200, 50.0).libelle == "T3"


def test_nom_ecrit_a_la_main_complete_le_numero() -> None:
    """Le numéro reste devant : un nom ajouté dans le fichier du circuit vient
    en complément, il ne le remplace pas."""
    assert Virage(3, 100, 200, 50.0, nom="Curva Grande").libelle == "T3 — Curva Grande"


# ----------------------------------------------------------------------
# Écriture et relecture du fichier de circuit
# ----------------------------------------------------------------------


def test_sens_survit_a_lenregistrement(tmp_path) -> None:
    from lmu_telemetry.virages import DefinitionCircuit

    definition = DefinitionCircuit(
        circuit="Test",
        longueur=1000.0,
        virages=(
            Virage(1, 100, 200, 30.0, nom="Mon virage", sens=1),
            Virage(2, 400, 500, 80.0, sens=-1),
        ),
    )
    chemin = tmp_path / "Test.json"
    definition.enregistrer(chemin)
    relu = DefinitionCircuit.lire(chemin)
    assert relu.virages[0].sens == 1
    assert relu.virages[0].nom == "Mon virage"
    assert relu.virages[1].sens == -1


def test_ancien_fichier_sans_sens_reste_lisible(tmp_path) -> None:
    """Les fichiers écrits avant l'ajout du sens ne doivent pas devenir
    illisibles : on perd l'information, pas le découpage."""
    import json

    from lmu_telemetry.virages import DefinitionCircuit

    chemin = tmp_path / "Ancien.json"
    chemin.write_text(
        json.dumps(
            {
                "circuit": "Ancien",
                "longueur": 1000.0,
                "virages": [
                    {
                        "numero": 1,
                        "nom": "",
                        "debut": 100,
                        "fin": 200,
                        "rayon_min": 30.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    relu = DefinitionCircuit.lire(chemin)
    assert relu.virages[0].sens == 0
    assert relu.virages[0].chicane is False
