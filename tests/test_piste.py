"""Tests de la reconstruction de la géométrie de piste.

Le circuit de test est un anneau circulaire de rayon et de largeur connus
(voir tests/fixtures/construire.py) : on sait donc exactement ce que la
reconstruction doit retrouver.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from lmu_telemetry.sources import catalogue
from lmu_telemetry.domaine.donnees_tour import charger
from lmu_telemetry.errors import ErreurTelemetrie, SessionEnCours
from lmu_telemetry.domaine.piste import MARGE_DEMI_TOUR, _demi_tour, _sur_piste, construire
from lmu_telemetry.domaine.session import Session
from tests.fixtures import construire as constructeur


@pytest.fixture
def geometrie(session_test: Path):
    # Les tours 1 et 3 passent de part et d'autre de l'axe : chacun renseigne
    # donc un bord différent, et les deux ensemble décrivent toute la piste.
    tours = [charger(session_test, 1), charger(session_test, 3)]
    fin = min(t.longueur for t in tours)
    return construire(tours, np.arange(0.0, fin, 1.0))


# ----------------------------------------------------------------------
# L'axe
# ----------------------------------------------------------------------


def test_axe_retrouve_le_cercle(geometrie) -> None:
    """L'axe reconstruit doit être le cercle de rayon connu."""
    rayon = np.hypot(geometrie.axe[:, 0], geometrie.axe[:, 1])
    assert np.allclose(rayon, constructeur.RAYON, atol=0.05)


def test_les_tours_retrouvent_le_meme_axe(geometrie) -> None:
    """Le contrôle de la méthode : deux trajectoires différentes, un seul axe.

    Les tours 1 et 3 roulent à 2 m et -3 m de l'axe. Si la reconstruction se
    trompait de signe ou de normale, leurs axes seraient distants de plusieurs
    mètres.
    """
    assert geometrie.ecart_axes < 0.05


def test_normale_perpendiculaire_a_laxe(geometrie) -> None:
    """Sur un cercle, la normale est radiale : elle doit être colinéaire au rayon."""
    radial = geometrie.axe / np.linalg.norm(geometrie.axe, axis=1)[:, None]
    produit = np.abs(np.sum(radial * geometrie.normale, axis=1))
    # On écarte les tout premiers et derniers points, où le lissage n'a pas de
    # voisinage complet.
    assert np.median(produit[20:-20]) == pytest.approx(1.0, abs=1e-3)


# ----------------------------------------------------------------------
# Les sorties de piste
# ----------------------------------------------------------------------


def test_passage_hors_piste_repere(session_test: Path) -> None:
    """La fixture met une seconde sur l'herbe au tour 3, et rien au tour 1."""
    fin = charger(session_test, 1).longueur
    distance = np.arange(0.0, fin, 1.0)

    assert _sur_piste(charger(session_test, 1), distance).all()

    utilisable = _sur_piste(charger(session_test, 3), distance)
    exclus = (~utilisable).sum()
    # Une seconde à environ 41 m/s, élargie de la marge des deux côtés.
    assert 50 < exclus < 90, f"{exclus} m écartés"


def test_une_sortie_ne_deplace_plus_laxe(session_test: Path) -> None:
    """LE test de non-régression du défaut trouvé à Monza.

    Là-bas, un tour sur quatre était parti dans le dégagement à la sortie de la
    première chicane : son `Path Lateral` descendait à -31 m alors que la piste
    en fait 10 de large. Comme l'axe est la moyenne de ce que chaque tour en
    déduit, ce seul tour tirait l'axe commun de plus de 8 m, fabriquait une
    courbure inexistante et changeait le nombre de virages du circuit.

    On rejoue exactement ça : on fausse `Path Lateral` sur une portion d'un
    tour, ce qui déplace l'axe que ce tour déduit, et on vérifie que l'axe
    commun ne bouge pas dès lors que la portion est signalée hors piste.

    L'excursion reste sous 2,5 demi-largeurs de l'axe : au-delà, la portion
    serait écartée d'office, signalée ou non (voir le test suivant), et ce test
    ne vérifierait plus rien du signalement.
    """
    from lmu_telemetry.domaine.donnees_tour import CANAL_HORS_PISTE

    tours = [charger(session_test, 1), charger(session_test, 3)]
    fin = min(t.longueur for t in tours)
    distance = np.arange(0.0, fin, 1.0)
    reference = construire(tours, distance).axe

    # Une excursion de 8 m sur une seconde, au milieu du tour 3 : de -3 à -11 m.
    abime = charger(session_test, 3)
    debut = len(abime.temps) // 2
    plage = slice(debut, debut + 100)  # 1 s à 100 Hz
    abime.canaux["Path Lateral"] = abime.canaux["Path Lateral"].copy()
    abime.canaux["Path Lateral"][plage] -= 8.0

    # Sans le signalement, l'axe doit être franchement faussé : c'est ce qui se
    # passait avant la correction.
    abime.canaux[CANAL_HORS_PISTE] = np.zeros_like(abime.temps)
    sans_signalement = construire([tours[0], abime], distance).axe
    dommage = np.hypot(*(sans_signalement - reference).T).max()
    assert dommage > 3.0, f"l'excursion ne fausse que de {dommage:.2f} m"

    # Avec le signalement, l'axe doit redevenir celui de référence.
    abime.canaux[CANAL_HORS_PISTE] = np.zeros_like(abime.temps)
    abime.canaux[CANAL_HORS_PISTE][plage] = 1.0
    corrige = construire([tours[0], abime], distance).axe
    residuel = np.hypot(*(corrige - reference).T).max()
    assert residuel < 0.5, f"il reste {residuel:.2f} m d'écart"


def test_un_degagement_bitume_ne_deplace_plus_laxe(session_test: Path) -> None:
    """Cas réel de la première chicane de Monza : un tour la coupe tout droit
    par l'échappatoire, jusqu'à 38 m de l'axe. L'échappatoire est bitumée : le
    jeu la compte comme de la route, et rien n'est signalé hors piste.

    Au-delà de 2,5 demi-largeurs de l'axe, la voiture n'est plus sur la piste,
    quoi qu'en dise le sol : la portion est écartée comme une sortie.
    """
    from lmu_telemetry.domaine.donnees_tour import CANAL_HORS_PISTE

    tours = [charger(session_test, 1), charger(session_test, 3)]
    fin = min(t.longueur for t in tours)
    distance = np.arange(0.0, fin, 1.0)
    reference = construire(tours, distance).axe

    # 25 m de plus sur une seconde, au milieu du tour 3, et aucun signalement.
    abime = charger(session_test, 3)
    debut = len(abime.temps) // 2
    plage = slice(debut, debut + 100)
    abime.canaux["Path Lateral"] = abime.canaux["Path Lateral"].copy()
    abime.canaux["Path Lateral"][plage] -= 25.0
    abime.canaux[CANAL_HORS_PISTE] = np.zeros_like(abime.temps)

    # Seul, ce tour déduit un axe faux de 25 m : c'est bien un passage à écarter.
    seul = construire([abime], distance).axe
    intact = construire([charger(session_test, 3)], distance).axe
    dommage = np.hypot(*(seul - intact).T).max()
    assert dommage > 20.0, f"l'excursion ne fausse que de {dommage:.2f} m"

    corrige = construire([tours[0], abime], distance).axe
    residuel = np.hypot(*(corrige - reference).T).max()
    assert residuel < 0.5, f"il reste {residuel:.2f} m d'écart"


def _avec_demi_tour(tour, debut_s: float, recul: float = 20.0):
    """Le même tour, avec un demi-tour sur un dégagement bitumé.

    Le scénario du Raidillon, à Spa : à `debut_s` secondes, la voiture dérive
    vers l'extérieur jusqu'à 11 m de l'axe, s'arrête, puis fait demi-tour en
    recoupant la piste — sa distance recule de `recul` mètres pendant qu'elle
    passe à 9 m de l'autre côté —, avant de repartir. Rien n'est signalé hors
    piste, et la voiture reste à moins de 2,5 demi-largeurs de l'axe : seule la
    règle du recul peut écarter ce passage.

    Position GPS, écart latéral et bord restent cohérents entre eux, comme dans
    un vrai fichier. La vitesse n'entre pas dans la géométrie : la voiture
    rattrape d'un coup le temps perdu, pour rejoindre le reste du tour intact.
    """
    pas = float(tour.temps[1] - tour.temps[0])
    i = int(np.searchsorted(tour.temps, debut_s))
    derive, arret, retour, reprise = (int(round(s / pas)) for s in (2.0, 1.0, 3.0, 4.0))
    j = i + derive + arret + retour + reprise

    distance = np.array(tour.distance, dtype=float)
    lateral = np.array(tour.canal("Path Lateral"), dtype=float)
    demi_tour = distance[i] + 60.0
    distance[i:j] = np.concatenate(
        [
            np.linspace(distance[i], demi_tour, derive, endpoint=False),
            np.full(arret, demi_tour),
            np.linspace(demi_tour, demi_tour - recul, retour, endpoint=False),
            np.linspace(demi_tour - recul, distance[j], reprise, endpoint=False),
        ]
    )
    lateral[i:j] = np.concatenate(
        [
            np.linspace(lateral[i], 11.0, derive, endpoint=False),
            np.full(arret, 11.0),
            np.linspace(11.0, -9.0, retour, endpoint=False),
            np.linspace(-9.0, lateral[j], reprise, endpoint=False),
        ]
    )

    # Sur l'anneau, la position se déduit de la distance et de l'écart à l'axe,
    # comme le fait la fixture (tests/fixtures/construire.py).
    angle = 2 * math.pi * distance[i:j] / constructeur.LONGUEUR_TOUR
    rayon = constructeur.RAYON + lateral[i:j]
    k = math.cos(math.radians(float(np.mean(tour.canal("GPS Latitude")))))
    canaux = dict(tour.canaux)
    canaux["Path Lateral"] = lateral
    for nom, valeurs in (
        ("GPS Latitude", rayon * np.cos(angle) / constructeur.METRES_PAR_DEGRE),
        ("GPS Longitude", rayon * np.sin(angle) / (constructeur.METRES_PAR_DEGRE * k)),
        ("Track Edge", np.where(lateral[i:j] < 0, -1.0, 1.0) * constructeur.DEMI_LARGEUR),
    ):
        canaux[nom] = np.array(tour.canal(nom), dtype=float)
        canaux[nom][i:j] = valeurs
    return replace(tour, distance=distance, canaux=canaux)


def test_un_demi_tour_ne_deplace_plus_laxe(session_test: Path) -> None:
    """LE test de non-régression du défaut trouvé à Spa.

    En haut du Raidillon, deux tours d'une course avaient fait demi-tour sur le
    bitume du dégagement, que le jeu ne signale pas. Le rééchantillonnage sur
    la distance ne garde que les instants où la voiture progresse : sa position
    y sautait d'un bord à l'autre en moins d'un mètre, l'axe déduit de ce tour
    s'écartait de 26 m, et trois virages inexistants apparaissaient.
    """
    tour1, tour3 = charger(session_test, 1), charger(session_test, 3)
    distance = np.arange(0.0, min(tour1.longueur, tour3.longueur), 1.0)
    reference = construire([tour1, tour3], distance).axe
    abime = _avec_demi_tour(tour1, debut_s=20.0)

    # Le même tour, sa distance aplatie : le rééchantillonnage en tire
    # exactement les mêmes points, mais le recul ne se voit plus. C'est ce que
    # voyait l'outil avant la correction, et l'axe doit en être faussé.
    aplati = replace(abime, distance=np.maximum.accumulate(abime.distance))
    dommage = np.hypot(*(construire([aplati, tour3], distance).axe - reference).T).max()
    assert dommage > 5.0, f"le demi-tour ne fausse que de {dommage:.2f} m"

    corrige = construire([abime, tour3], distance).axe
    residuel = np.hypot(*(corrige - reference).T).max()
    assert residuel < 0.5, f"il reste {residuel:.2f} m d'écart"


def test_seule_la_portion_parcourue_deux_fois_est_ecartee(session_test: Path) -> None:
    """Un demi-tour écarte ce que la voiture a parcouru deux fois, plus sa marge.

    Un arrêt ne recule pas : le tour 3 de la fixture passe deux secondes à
    l'arrêt, et rien n'est écarté. Une voiture arrêtée qui recule de quelques
    décimètres avant de repartir non plus : elle repasse au même endroit.
    """
    tour1 = charger(session_test, 1)
    distance = np.arange(0.0, tour1.longueur, 1.0)

    ecarte = _demi_tour(_avec_demi_tour(tour1, debut_s=20.0, recul=20.0), distance)
    assert ecarte.sum() == pytest.approx(20.0 + 2 * MARGE_DEMI_TOUR, abs=2)

    assert not _demi_tour(charger(session_test, 3), distance).any()

    recule = np.array(tour1.distance)
    i = int(np.searchsorted(tour1.temps, 30.0))
    recule[i : i + 50] = recule[i] - np.linspace(0.0, 0.5, 50)  # 50 cm en arrière,
    recule[i + 50 : i + 100] = np.linspace(recule[i] - 0.5, recule[i + 100], 50)  # puis il repart
    assert not _demi_tour(replace(tour1, distance=recule), distance).any()


# ----------------------------------------------------------------------
# Les bords
# ----------------------------------------------------------------------


def test_largeur_de_piste(geometrie) -> None:
    assert geometrie.largeur_mediane == pytest.approx(2 * constructeur.DEMI_LARGEUR, abs=0.05)


def test_les_deux_bords_sont_mesures(geometrie) -> None:
    """Deux tours de part et d'autre renseignent les deux bords.

    Pas tout à fait partout, pour deux raisons :

    * les deux tours ne finissent pas exactement à la même distance, si bien
      que les derniers points de l'axe commun manquent d'un côté — deux points
      sur 3 725 ;
    * le tour 3 passe une seconde sur l'herbe (la fixture le prévoit exprès).
      Ce passage est écarté, avec sa marge de part et d'autre, soit une
      soixantaine de mètres où seul le tour 1 renseigne son bord.
    """
    assert geometrie.part_mesuree > 0.98


def test_bords_de_part_et_dautre_de_laxe(geometrie) -> None:
    rayon_gauche = np.hypot(*geometrie.bord_gauche.T)
    rayon_droit = np.hypot(*geometrie.bord_droit.T)
    interieur = min(np.median(rayon_gauche), np.median(rayon_droit))
    exterieur = max(np.median(rayon_gauche), np.median(rayon_droit))
    assert interieur == pytest.approx(constructeur.RAYON - constructeur.DEMI_LARGEUR, abs=0.1)
    assert exterieur == pytest.approx(constructeur.RAYON + constructeur.DEMI_LARGEUR, abs=0.1)


def test_bord_estime_quand_un_seul_cote_est_vu(session_test: Path) -> None:
    """Avec un seul tour, un seul bord est mesuré ; l'autre est reporté.

    C'est le cas courant sur de vraies données : on reste du même côté sur une
    trajectoire de course. La largeur médiane mesurée sert alors d'estimation,
    et `mesure` dit où c'est le cas.
    """
    tour = charger(session_test, 1)
    g = construire([tour], np.arange(0.0, tour.longueur, 1.0))
    assert g.part_mesuree == pytest.approx(0.0)
    largeurs = np.hypot(*(g.bord_droit - g.bord_gauche).T)
    # Le bord estimé est placé à la largeur médiane, faute de mieux.
    assert np.median(largeurs) == pytest.approx(g.largeur_mediane, abs=0.1)


def test_refuse_sans_tour() -> None:
    with pytest.raises(ValueError):
        construire([], np.arange(0.0, 100.0, 1.0))


# ----------------------------------------------------------------------
# Sur de vraies sessions
# ----------------------------------------------------------------------


def test_geometrie_sur_vraies_sessions(dossier_lmu: Path | None) -> None:
    """Sur de vraies données, les axes déduits de tours différents doivent
    coïncider, et la largeur trouvée doit être celle d'un circuit.

    Ce sont les deux seuls contrôles possibles : on ne dispose d'aucune vérité
    de référence sur la géométrie réelle des circuits.
    """
    if dossier_lmu is None:
        pytest.skip("Le Mans Ultimate n'est pas installé sur cette machine")

    verifiees = 0
    for fichier in catalogue.lister(dossier_lmu)[:20]:
        try:
            session = Session.ouvrir(fichier.chemin)
        except (SessionEnCours, ErreurTelemetrie):
            continue
        valides = [t.numero for t in session.tours_valides if t.chrono][:3]
        if len(valides) < 2:
            continue
        tours = [charger(fichier.chemin, k) for k in valides]
        fin = min(t.longueur for t in tours)
        g = construire(tours, np.arange(0.0, fin, 1.0))

        assert g.ecart_axes < 2.0, f"{fichier.chemin.name} : axes incohérents"
        assert 6.0 < g.largeur_mediane < 25.0, (
            f"{fichier.chemin.name} : largeur de piste invraisemblable "
            f"({g.largeur_mediane:.1f} m)"
        )
        verifiees += 1
        if verifiees >= 4:
            return
    if not verifiees:
        pytest.skip("aucune session avec deux tours valides")


# ----------------------------------------------------------------------
# Les bords : chacun suit ses propres mesures
# ----------------------------------------------------------------------


def _ecarts(g):
    """Écart latéral de chaque bord à l'axe, mesuré le long de la normale."""
    gauche = np.einsum("ij,ij->i", g.bord_gauche - g.axe, g.normale)
    droit = np.einsum("ij,ij->i", g.bord_droit - g.axe, g.normale)
    return gauche, droit


def _zone(tour, debut, fin):
    return (tour.distance >= debut) & (tour.distance < fin)


def test_un_bord_evase_n_entraine_pas_l_autre(session_test: Path) -> None:
    """Cas réel de l'épingle de Long Beach : au sommet, le bord extérieur
    s'écarte de 6 m, et personne ne longe le bord intérieur.

    Le bord intérieur était déduit de l'extérieur en reportant la largeur de
    piste : il se trouvait tiré de 6 m vers la trajectoire, et dessinait une
    encoche en travers de la route. Il doit rester où ses propres mesures,
    d'avant et d'après, le placent.
    """
    distance = np.arange(0.0, 3700.0, 1.0)
    reference = construire([charger(session_test, 1), charger(session_test, 3)], distance)

    evase = charger(session_test, 1)
    zone = _zone(evase, 1500, 1600)
    evase.canaux["Track Edge"] = evase.canaux["Track Edge"].copy()
    evase.canaux["Track Edge"][zone] *= 11.0 / 5.0  # de 5 m à 11 m

    muet = charger(session_test, 3)
    zone = _zone(muet, 1500, 1600)
    muet.canaux["Track Edge"] = muet.canaux["Track Edge"].copy()
    muet.canaux["Track Edge"][zone] = np.nan  # personne de ce côté-là

    modifiee = construire([evase, muet], distance)
    avant_g, avant_d = _ecarts(reference)
    apres_g, apres_d = _ecarts(modifiee)
    milieu = slice(1520, 1580)
    variations = sorted(
        [np.abs(apres_g - avant_g)[milieu].max(), np.abs(apres_d - avant_d)[milieu].max()]
    )
    # Un bord a bougé de 6 m — l'évasement, bien réel, reste affiché —,
    # l'autre n'a pas bougé.
    assert variations[1] == pytest.approx(6.0, abs=0.5)
    assert variations[0] < 0.5, f"le bord non longé a bougé de {variations[0]:.1f} m"


def test_un_bord_aberrant_est_ecarte(session_test: Path) -> None:
    """Cas réel à la sortie de l'épingle de Long Beach : le bord passe de
    6,5 m à 21,9 m sur une dizaine de mètres — l'entrée des stands, que le jeu
    compte comme surface roulable — et la route se dessinait sur 28 m."""
    distance = np.arange(0.0, 3700.0, 1.0)
    reference = construire([charger(session_test, 1), charger(session_test, 3)], distance)

    pic = charger(session_test, 1)
    zone = _zone(pic, 1500, 1510)
    pic.canaux["Track Edge"] = pic.canaux["Track Edge"].copy()
    pic.canaux["Track Edge"][zone] *= 5.0  # de 5 m à 25 m

    modifiee = construire([pic, charger(session_test, 3)], distance)
    avant_g, avant_d = _ecarts(reference)
    apres_g, apres_d = _ecarts(modifiee)
    ecart = max(
        np.abs(apres_g - avant_g)[1495:1515].max(),
        np.abs(apres_d - avant_d)[1495:1515].max(),
    )
    assert ecart < 1.0, f"le pic est passé : {ecart:.1f} m"


def test_trou_comble_a_travers_la_ligne() -> None:
    """Le tour est une boucle : un trou qui chevauche la ligne se comble entre
    la dernière mesure et la première, pas en figeant la valeur du bout."""
    from lmu_telemetry.domaine.piste import _completer

    bord = np.full(100, np.nan)
    bord[10:21] = 5.0
    bord[80:91] = 7.0
    comble = _completer(bord, np.arange(100, dtype=float))
    # À mi-chemin entre l'indice 90 (7 m) et l'indice 110, soit 10 (5 m).
    assert comble[95] == pytest.approx(6.5, abs=0.01)
    assert comble[5] == pytest.approx(5.5, abs=0.01)


def test_bord_jamais_mesure() -> None:
    from lmu_telemetry.domaine.piste import _completer

    assert _completer(np.full(50, np.nan), np.arange(50, dtype=float)) is None
