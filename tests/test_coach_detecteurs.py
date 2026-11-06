"""Les détecteurs, sur des passages dont on connaît la réponse.

Chaque passage part d'un virage propre, où rien ne doit être relevé, et n'y change
qu'une chose : la faute qu'on veut voir, ou le geste qu'il ne faut pas confondre avec
elle.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from lmu_telemetry.coach.detecteurs import Mesures, constats, mesurer
from lmu_telemetry.coach.passage import Passage
from lmu_telemetry.coach.zones import Zone
from lmu_telemetry.domaine.virages import Virage
from lmu_telemetry.parametres import SeuilsCoach

FREQUENCE = 50
DEBUT = 100.0

#: La voiture avance de 50 m par seconde sur l'axe des distances : le virage va de la
#: quatrième à la huitième seconde du passage.
METRES_PAR_SECONDE = 50.0
VIRAGE = Virage(numero=1, debut=200.0, fin=400.0, rayon_min=40.0, sens=-1)
ZONE = Zone(virages=(VIRAGE,), debut=0.0, fin=600.0)

GAZ = ((0, 100), (2.0, 100), (2.1, 0), (4.5, 0), (6.5, 100), (12, 100))
FREIN = ((0, 0), (2.05, 0), (2.2, 100), (3.5, 100), (4.5, 0), (12, 0))
VOLANT = ((0, 0), (3.5, 0), (5.5, 40), (8, 0), (12, 0))
VITESSE = ((0, 250), (2, 250), (5, 100), (12, 180))


def passage(
    gaz=GAZ,
    frein=FREIN,
    volant=VOLANT,
    vitesse=VITESSE,
    zone=ZONE,
    roues=None,
    hors_piste=None,
    frequence=FREQUENCE,
) -> Passage:
    secondes = np.arange(0, 12, 1 / frequence)

    def courbe(points) -> np.ndarray:
        return np.interp(secondes, *zip(*points))

    return Passage(
        zone=zone,
        tour=3,
        temps=DEBUT + secondes,
        distance=secondes * METRES_PAR_SECONDE,
        vitesse=courbe(vitesse),
        gaz=courbe(gaz),
        frein=courbe(frein),
        volant=courbe(volant),
        hors_piste=np.zeros(secondes.size, dtype=bool) if hors_piste is None else hors_piste(secondes),
        stands=np.zeros(secondes.size, dtype=bool),
        dernier_choc=-1.0,
        roues=None if roues is None else roues(secondes, courbe(vitesse)),
    )


def codes(m: Mesures, seuils: SeuilsCoach = SeuilsCoach()) -> list[str]:
    return [c.code for c in constats(m, "T1", seuils)]


def test_un_virage_propre_ne_donne_rien():
    m = mesurer(passage())
    assert codes(m) == []
    assert m.roue_libre_avant < 0.05
    assert m.roue_libre_virage < 0.2
    assert m.creux_gaz == 0.0
    assert m.correction == 0.0


def test_les_mesures_ne_dependent_pas_de_la_cadence():
    """Le direct lit à 50 Hz, la sonde à 100 Hz : un seuil doit valoir pour les deux."""
    gaz = ((0, 100), (1.6, 100), (1.65, 0), (4.5, 0), (5.2, 70), (5.8, 20), (6.5, 100), (12, 100))
    a = mesurer(passage(gaz=gaz, frequence=50))
    b = mesurer(passage(gaz=gaz, frequence=100))
    assert a.roue_libre_avant == pytest.approx(b.roue_libre_avant, abs=0.03)
    assert a.creux_gaz == pytest.approx(b.creux_gaz, abs=1.5)
    assert a.chute_frein == pytest.approx(b.chute_frein, abs=2)


# ----------------------------------------------------------------------
# Roue libre
# ----------------------------------------------------------------------


def test_roue_libre_avant_de_freiner():
    # Le pied quitte l'accélérateur 0,4 s avant de toucher le frein.
    gaz = ((0, 100), (1.6, 100), (1.65, 0), (4.5, 0), (6.5, 100), (12, 100))
    m = mesurer(passage(gaz=gaz))
    assert m.roue_libre_avant == pytest.approx(0.4, abs=0.05)
    assert codes(m) == ["roue_libre_avant"]


def test_le_gaz_et_le_frein_qui_se_croisent_ne_sont_pas_de_la_roue_libre():
    gaz = ((0, 100), (2.1, 100), (2.4, 0), (4.5, 0), (6.5, 100), (12, 100))
    assert mesurer(passage(gaz=gaz)).roue_libre_avant < 0.05


def test_un_freinage_qui_court_jusqu_au_bout_de_la_zone_n_a_pas_de_sortie():
    # Vu au Mans : le frein reste enfoncé jusqu'à la fin de la portion observée.
    m = mesurer(passage(frein=((0, 0), (2.05, 0), (2.2, 100), (12, 100))))
    assert m.roue_libre_virage == 0.0
    assert m.creux_gaz == 0.0


def test_un_virage_pris_sans_freiner_n_a_pas_de_roue_libre():
    # Un simple lever de pied dans une courbe rapide fait partie du pilotage.
    gaz = ((0, 100), (3, 100), (3.2, 0), (5, 0), (5.5, 100), (12, 100))
    m = mesurer(passage(gaz=gaz, frein=((0, 0), (12, 0))))
    assert m.roue_libre_avant == 0.0
    assert m.roue_libre_virage == 0.0


def test_roue_libre_entre_le_frein_et_les_gaz():
    gaz = ((0, 100), (2.0, 100), (2.1, 0), (6.5, 0), (7.5, 100), (12, 100))
    m = mesurer(passage(gaz=gaz))
    assert m.roue_libre_virage == pytest.approx(2.0, abs=0.1)
    assert codes(m) == ["roue_libre_virage"]


def test_dans_une_chicane_on_n_attend_les_gaz_que_dans_le_dernier_virage():
    # Le frein s'arrête dans le premier virage, les gaz attendent le second : c'est
    # le temps passé dans le second qui compte.
    zone = Zone(
        virages=(
            Virage(1, 100.0, 300.0, 20.0, sens=-1),
            Virage(2, 300.0, 400.0, 20.0, sens=1),
        ),
        debut=0.0,
        fin=600.0,
    )
    gaz = ((0, 100), (1.9, 100), (2.0, 0), (6.5, 0), (7.0, 100), (12, 100))
    frein = ((0, 0), (1.95, 0), (2.1, 100), (3.0, 100), (3.3, 0), (12, 0))
    m = mesurer(passage(gaz=gaz, frein=frein, volant=((0, 0), (12, 0)), zone=zone))
    assert m.roue_libre_virage == pytest.approx(0.5, abs=0.1)


# ----------------------------------------------------------------------
# Frein
# ----------------------------------------------------------------------


def test_relacher_le_frein_d_un_coup_est_brutal():
    frein = ((0, 0), (2.05, 0), (2.2, 100), (4.0, 100), (4.04, 0), (12, 0))
    m = mesurer(passage(frein=frein))
    assert m.chute_frein > 90
    assert codes(m) == ["frein_brutal"]


def test_relacher_le_frein_progressivement_ne_l_est_pas():
    assert mesurer(passage()).chute_frein == pytest.approx(10, abs=1)


def test_un_effleurement_de_frein_n_est_pas_un_freinage():
    # Assez court pour ne pas compter : il ne doit pas voler sa place au vrai freinage.
    frein = ((0, 0), (2.05, 0), (2.2, 100), (3.5, 100), (4.5, 0), (9, 0), (9.05, 10), (9.1, 0), (12, 0))
    m = mesurer(passage(frein=frein))
    assert m.chute_frein == pytest.approx(10, abs=1)


# ----------------------------------------------------------------------
# Accélérateur
# ----------------------------------------------------------------------


def test_gaz_hesitant_en_sortie():
    gaz = ((0, 100), (2.0, 100), (2.1, 0), (4.5, 0), (5.2, 70), (5.8, 20), (6.5, 100), (12, 100))
    m = mesurer(passage(gaz=gaz))
    assert m.creux_gaz == pytest.approx(50, abs=1)
    assert codes(m) == ["gaz_hesitant"]


def test_un_petit_ajustement_de_pied_n_est_pas_une_hesitation():
    gaz = ((0, 100), (2.0, 100), (2.1, 0), (4.5, 0), (5.2, 70), (5.5, 60), (6.5, 100), (12, 100))
    m = mesurer(passage(gaz=gaz))
    assert m.creux_gaz == pytest.approx(10, abs=1)
    assert codes(m) == []


def test_lever_le_pied_apres_avoir_mis_plein_gaz_n_est_pas_une_hesitation():
    # À Spa, un virage en double courbe impose un lever une fois le plein gaz atteint.
    gaz = ((0, 100), (2.0, 100), (2.1, 0), (4.5, 0), (6, 100), (8, 100), (8.3, 10), (9, 100), (12, 100))
    assert mesurer(passage(gaz=gaz)).creux_gaz == 0.0


def test_un_lever_sans_reprise_prepare_le_virage_suivant():
    gaz = ((0, 100), (2.0, 100), (2.1, 0), (4.5, 0), (6, 80), (6.5, 0), (12, 0))
    assert mesurer(passage(gaz=gaz)).creux_gaz == 0.0


def test_dans_une_chicane_le_lever_au_changement_d_appui_ne_compte_pas():
    zone = Zone(
        virages=(
            Virage(1, 100.0, 275.0, 20.0, sens=-1),
            Virage(2, 275.0, 400.0, 20.0, sens=1),
        ),
        debut=0.0,
        fin=600.0,
    )
    # Le pied arrive encore enfoncé au second virage, se lève, puis repart d'une traite.
    gaz = ((0, 100), (1.9, 100), (2.0, 0), (4.0, 0), (5.5, 70), (6.5, 10), (7.5, 100), (12, 100))
    frein = ((0, 0), (1.95, 0), (2.1, 100), (3.0, 100), (3.3, 0), (12, 0))
    assert mesurer(passage(gaz=gaz, frein=frein, zone=zone, volant=((0, 0), (12, 0)))).creux_gaz == 0.0


# ----------------------------------------------------------------------
# Volant
# ----------------------------------------------------------------------


def test_grosse_correction_de_volant():
    # Virage à droite, volant positif : il monte à 40, revient à 25 en 0,3 s, repart.
    volant = ((0, 0), (3.5, 0), (5.0, 40), (5.3, 25), (5.8, 42), (8, 0), (12, 0))
    m = mesurer(passage(volant=volant))
    assert m.correction == pytest.approx(15, abs=1.5)
    assert codes(m) == ["correction"]


def test_un_retour_lent_est_un_ajustement_de_trajectoire():
    # 15 % en 2 s dans une longue courbe : pas un rattrapage.
    volant = ((0, 0), (3.5, 0), (4.5, 40), (6.5, 25), (7.5, 30), (8, 0), (12, 0))
    assert mesurer(passage(volant=volant)).correction == 0.0


def test_le_bruit_du_volant_n_est_pas_une_correction():
    secondes = np.arange(0, 12, 0.1)
    bruit = 1.2 * np.sin(secondes * 11)
    points = tuple(zip(secondes, np.interp(secondes, *zip(*VOLANT)) + bruit))
    assert mesurer(passage(volant=points)).correction == 0.0


def test_changer_d_appui_dans_une_chicane_n_est_pas_une_correction():
    zone = Zone(
        virages=(
            Virage(1, 200.0, 300.0, 20.0, sens=-1),
            Virage(2, 300.0, 400.0, 20.0, sens=1),
        ),
        debut=0.0,
        fin=600.0,
    )
    volant = ((0, 0), (3.5, 0), (5.0, 45), (6.2, -60), (8, 0), (12, 0))
    assert mesurer(passage(volant=volant, zone=zone)).correction == 0.0


def test_un_virage_a_gauche_se_lit_a_l_envers():
    virage = replace(VIRAGE, sens=1)
    zone = replace(ZONE, virages=(virage,))
    volant = ((0, 0), (3.5, 0), (5.0, -40), (5.3, -25), (5.8, -42), (8, 0), (12, 0))
    assert mesurer(passage(volant=volant, zone=zone)).correction == pytest.approx(15, abs=1.5)


# ----------------------------------------------------------------------
# Roues
# ----------------------------------------------------------------------


def roues_libres(_secondes: np.ndarray, vitesse: np.ndarray) -> np.ndarray:
    return np.column_stack([vitesse] * 4)


def blocage(debut: float, duree: float, indices=(0, 1)):
    def calculer(secondes: np.ndarray, vitesse: np.ndarray) -> np.ndarray:
        roues = roues_libres(secondes, vitesse)
        pendant = (secondes >= debut) & (secondes < debut + duree)
        for i in indices:
            roues[pendant, i] = 0.0
        return roues

    return calculer


def patinage(debut: float, duree: float, surplus: float = 1.4):
    def calculer(secondes: np.ndarray, vitesse: np.ndarray) -> np.ndarray:
        roues = roues_libres(secondes, vitesse)
        pendant = (secondes >= debut) & (secondes < debut + duree)
        roues[pendant, 2:] *= surplus
        return roues

    return calculer


def test_sans_les_roues_rien_n_est_dit_du_blocage():
    m = mesurer(passage())
    assert m.blocage is None
    assert m.patinage is None
    assert codes(m) == []


def test_des_roues_qui_suivent_la_voiture_ne_donnent_rien():
    m = mesurer(passage(roues=roues_libres))
    assert m.blocage == pytest.approx(0.0, abs=0.1)
    assert m.patinage == pytest.approx(0.0, abs=0.1)


def test_blocage_de_l_avant():
    m = mesurer(passage(roues=blocage(3.0, 0.3)))
    assert m.blocage == pytest.approx(100.0)
    assert m.blocage_avant
    assert [c.message.cle for c in constats(m, "T1")] == ["coach.blocage_avant"]


def test_blocage_de_l_arriere():
    m = mesurer(passage(roues=blocage(3.0, 0.3, indices=(2, 3))))
    assert not m.blocage_avant
    assert [c.message.cle for c in constats(m, "T1")] == ["coach.blocage_arriere"]


def test_un_blocage_trop_bref_ne_compte_pas():
    assert codes(mesurer(passage(roues=blocage(3.0, 0.1)))) == []


def test_un_blocage_sans_frein_n_en_est_pas_un():
    # Dans un tête-à-queue, une roue peut rester arrêtée sans que le pied y soit pour rien.
    assert mesurer(passage(roues=blocage(9.0, 0.5))).blocage == 0.0


def test_l_etalonnage_des_roues_est_applique():
    # Une roue annoncée 3 % trop lente ne doit pas passer pour un début de blocage.
    def lentes(_s: np.ndarray, vitesse: np.ndarray) -> np.ndarray:
        return np.column_stack([vitesse * 0.97] * 4)

    assert mesurer(passage(roues=lentes), np.full(4, 0.97)).blocage == pytest.approx(0.0, abs=0.1)


def test_patinage_en_sortie():
    m = mesurer(passage(roues=patinage(6.5, 0.3)))
    assert m.patinage == pytest.approx(40.0)
    assert codes(m) == ["patinage"]


def test_le_patinage_dans_l_herbe_ne_compte_pas():
    m = mesurer(passage(roues=patinage(6.5, 0.3), hors_piste=lambda s: (s >= 6.3) & (s < 7.0)))
    assert m.patinage == 0.0


# ----------------------------------------------------------------------
# Constats
# ----------------------------------------------------------------------


def test_le_plus_important_passe_d_abord():
    m = Mesures(
        roue_libre_avant=0.5,
        roue_libre_virage=2.0,
        chute_frein=90.0,
        creux_gaz=60.0,
        correction=20.0,
        blocage=60.0,
        patinage=40.0,
    )
    assert codes(m) == [
        "blocage",
        "roue_libre_avant",
        "correction",
        "patinage",
        "gaz_hesitant",
        "frein_brutal",
        "roue_libre_virage",
    ]


def test_les_seuils_viennent_des_reglages():
    m = Mesures(roue_libre_avant=0.5)
    assert codes(m, SeuilsCoach(roue_libre_avant=0.6)) == []
    assert codes(m, SeuilsCoach(roue_libre_avant=0.4)) == ["roue_libre_avant"]


def test_un_seuil_a_zero_desactive_le_detecteur():
    assert codes(Mesures(creux_gaz=90.0), SeuilsCoach(creux_gaz=0.0)) == []


def test_le_message_nomme_le_virage_et_s_ecrit_dans_chaque_langue():
    (constat,) = constats(Mesures(roue_libre_avant=0.43), "Lesmo 2")
    assert str(constat.message) == "Lesmo 2 : roue libre de 0,4 s avant de freiner"
    assert constat.message.dans("en") == "Lesmo 2: 0.4 s coasting before the brakes"
