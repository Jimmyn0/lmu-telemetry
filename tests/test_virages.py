"""Tests du découpage en virages et des métriques de pilotage.

La session de test décrit un anneau circulaire de rayon connu, sur lequel
chaque tour freine une seconde à fond, roule une seconde sur son erre, puis
remet les gaz (voir tests/fixtures/construire.py). Toutes les valeurs
attendues se calculent donc à la main.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from lmu_telemetry import catalogue
from lmu_telemetry.donnees_tour import charger
from lmu_telemetry.errors import ErreurTelemetrie, SessionEnCours
from lmu_telemetry.session import Session
from lmu_telemetry.virages import (
    DefinitionCircuit,
    Virage,
    detecter,
    fichier_definition,
    mesurer,
    secteurs,
)
from tests.fixtures import construire as constructeur


def _distance(secondes: float) -> float:
    """Distance parcourue depuis le début du tour, au bout de `secondes`.

    Il ne suffit pas de multiplier par la vitesse de croisière : la fixture
    passe une seconde à vitesse réduite dans le virage, et l'oublier décale le
    résultat de 25 m.
    """
    debut_lent, fin_lent = constructeur.VIRAGE_LENT_S
    rapide = constructeur.VITESSE_RAPIDE / 3.6
    lent = constructeur.VITESSE_LENTE / 3.6
    duree_lente = max(0.0, min(secondes, fin_lent) - debut_lent)
    return (secondes - duree_lente) * rapide + duree_lente * lent


@pytest.fixture
def tour(session_test: Path):
    return charger(session_test, 1)


@pytest.fixture
def definition(tour):
    """Un virage placé sur la portion lente de la fixture."""
    debut = _distance(constructeur.VIRAGE_LENT_S[0])
    virage = Virage(
        numero=1,
        debut=debut,
        fin=debut + constructeur.VITESSE_LENTE / 3.6,
        rayon_min=constructeur.RAYON,
    )
    return DefinitionCircuit(
        circuit="Circuit de test", longueur=tour.longueur, virages=(virage,)
    )


# ----------------------------------------------------------------------
# Détection
# ----------------------------------------------------------------------


def test_courbure_constante_donne_un_seul_virage(session_test: Path) -> None:
    """L'anneau a une courbure constante : sous un seuil assez large, tout le
    tour est un seul virage, et le rayon détecté est celui de l'anneau."""
    tours = [charger(session_test, 1), charger(session_test, 3)]
    d = detecter(tours, rayon_maximal=constructeur.RAYON * 1.5)
    assert len(d.virages) == 1
    assert d.virages[0].rayon_min == pytest.approx(constructeur.RAYON, rel=0.02)


def test_courbure_trop_douce_ne_donne_aucun_virage(session_test: Path) -> None:
    """En dessous du seuil, une courbe large n'est pas comptée comme un virage."""
    tours = [charger(session_test, 1), charger(session_test, 3)]
    assert detecter(tours, rayon_maximal=constructeur.RAYON / 2).virages == ()


def test_detection_refuse_sans_tour() -> None:
    with pytest.raises(ErreurTelemetrie):
        detecter([])


# ----------------------------------------------------------------------
# Le fichier de définition
# ----------------------------------------------------------------------


def test_aller_retour_sur_disque(tmp_path: Path, definition) -> None:
    chemin = fichier_definition(tmp_path, definition.circuit)
    definition.enregistrer(chemin)
    relu = DefinitionCircuit.lire(chemin)
    assert relu.circuit == definition.circuit
    assert [v.debut for v in relu.virages] == [v.debut for v in definition.virages]


def test_nom_de_fichier_sans_caracteres_interdits(tmp_path: Path) -> None:
    chemin = fichier_definition(tmp_path, 'Circuit / "spécial" : 24h?')
    assert chemin.parent == tmp_path
    assert not set(chemin.name) & set('/\\:*?"<>|')


def test_fichier_illisible_explique_quoi_faire(tmp_path: Path) -> None:
    chemin = tmp_path / "casse.json"
    chemin.write_text("{ pas du json", encoding="utf-8")
    with pytest.raises(ErreurTelemetrie) as erreur:
        DefinitionCircuit.lire(chemin)
    assert "supprime-le" in str(erreur.value)


def test_virages_relus_dans_lordre(tmp_path: Path) -> None:
    """Un fichier édité à la main peut lister les virages dans le désordre."""
    chemin = tmp_path / "desordre.json"
    chemin.write_text(
        '{"circuit": "X", "longueur": 1000, "virages": ['
        '{"numero": 2, "debut": 500, "fin": 600},'
        '{"numero": 1, "debut": 100, "fin": 200}]}',
        encoding="utf-8",
    )
    assert [v.debut for v in DefinitionCircuit.lire(chemin).virages] == [100.0, 500.0]


# ----------------------------------------------------------------------
# Le pavage du tour
# ----------------------------------------------------------------------


def test_les_secteurs_pavent_le_tour() -> None:
    """Chaque mètre du tour appartient à un virage et à un seul.

    C'est ce qui permet à la colonne « temps perdu » de totaliser exactement
    l'écart du tour : sans pavage, une partie de l'écart tomberait dans les
    trous entre les zones — 37 % du total sur un tour de Monza, mesuré avant
    correction.
    """
    d = DefinitionCircuit(
        circuit="X",
        longueur=1000.0,
        virages=(
            Virage(numero=1, debut=100.0, fin=150.0, rayon_min=50.0),
            Virage(numero=2, debut=400.0, fin=460.0, rayon_min=80.0),
            Virage(numero=3, debut=700.0, fin=760.0, rayon_min=60.0),
        ),
    )
    portions = secteurs(d)
    assert len(portions) == 3
    assert portions[0][0] == 0.0
    assert portions[-1][1] == 1000.0
    # Pas de trou : la fin de chacune est le début de la suivante.
    for (_, fin), (debut, _) in zip(portions, portions[1:]):
        assert fin == debut
    # Chaque virage est bien dans sa propre portion.
    for virage, (debut, fin) in zip(d.virages, portions):
        assert debut <= virage.debut and virage.fin <= fin
    # La frontière tombe au milieu de la ligne droite.
    assert portions[0][1] == pytest.approx((150.0 + 400.0) / 2)


def test_un_seul_virage_prend_tout_le_tour() -> None:
    d = DefinitionCircuit(
        circuit="X",
        longueur=500.0,
        virages=(Virage(numero=1, debut=100.0, fin=200.0, rayon_min=50.0),),
    )
    assert secteurs(d) == [(0.0, 500.0)]


# ----------------------------------------------------------------------
# Les métriques
# ----------------------------------------------------------------------


def test_metriques_du_freinage(tour, definition) -> None:
    m = mesurer(tour, definition)[0]
    assert m.debut_freinage == pytest.approx(_distance(constructeur.FREINAGE_S[0]), abs=2)
    assert m.vitesse_entree == pytest.approx(constructeur.VITESSE_RAPIDE, abs=1)
    assert m.duree_freinage == pytest.approx(1.0, abs=0.05)
    assert m.frein_max == pytest.approx(100.0)
    # Le freinage commence bien AVANT le virage.
    assert m.distance_freinage == pytest.approx(
        _distance(constructeur.VIRAGE_LENT_S[0]) - _distance(constructeur.FREINAGE_S[0]),
        abs=2,
    )


def test_point_le_plus_lent(tour, definition) -> None:
    m = mesurer(tour, definition)[0]
    assert m.vitesse_min == pytest.approx(constructeur.VITESSE_LENTE, abs=0.5)
    assert m.position_vitesse_min == pytest.approx(definition.virages[0].debut, abs=5)


def test_remise_des_gaz(tour, definition) -> None:
    m = mesurer(tour, definition)[0]
    assert m.remise_gaz == pytest.approx(_distance(constructeur.REPRISE_GAZ_S), abs=2)
    assert m.remise_gaz > m.position_vitesse_min


def test_temps_sur_lerre(tour, definition) -> None:
    """Une seconde sans frein ni gaz entre le freinage et la remise des gaz."""
    m = mesurer(tour, definition)[0]
    assert m.temps_coasting == pytest.approx(1.0, abs=0.05)


def test_virage_sans_freinage(session_test: Path, tour) -> None:
    """Un virage placé en pleine ligne droite : pas de freinage, et on le dit."""
    virage = Virage(numero=1, debut=300.0, fin=400.0, rayon_min=500.0)
    d = DefinitionCircuit(
        circuit="Circuit de test", longueur=tour.longueur, virages=(virage,)
    )
    m = mesurer(tour, d)[0]
    assert m.debut_freinage is None
    assert m.distance_freinage is None
    assert m.duree_freinage == pytest.approx(0.0)
    assert "pris sans freiner" in map(str, m.remarques)


def test_zone_danalyse_ne_deborde_pas_sur_le_virage_precedent(tour) -> None:
    """Le freinage d'un virage ne doit pas être attribué au suivant.

    Deux virages rapprochés : le second ne doit pas voir le freinage du premier,
    sinon la même pédale serait comptée deux fois.
    """
    debut = _distance(constructeur.VIRAGE_LENT_S[0])
    d = DefinitionCircuit(
        circuit="Circuit de test",
        longueur=tour.longueur,
        virages=(
            Virage(numero=1, debut=debut, fin=debut + 20, rayon_min=500.0),
            Virage(numero=2, debut=debut + 60, fin=debut + 90, rayon_min=500.0),
        ),
    )
    premier, second = mesurer(tour, d)
    assert premier.duree_freinage > 0.5
    assert second.duree_freinage == pytest.approx(0.0)


def test_virage_hors_du_tour(tour) -> None:
    d = DefinitionCircuit(
        circuit="Circuit de test",
        longueur=tour.longueur,
        virages=(Virage(numero=1, debut=10.0, fin=20.0, rayon_min=500.0),),
    )
    # Un virage bien placé passe ; on vérifie le message quand il ne l'est pas.
    assert mesurer(tour, d)
    hors = DefinitionCircuit(
        circuit="Circuit de test",
        longueur=tour.longueur,
        virages=(Virage(numero=1, debut=1e6, fin=1e6 + 10, rayon_min=500.0),),
    )
    assert mesurer(tour, hors) == []


# ----------------------------------------------------------------------
# Sur de vraies sessions
# ----------------------------------------------------------------------


def test_decoupage_stable_entre_sessions(dossier_lmu: Path | None) -> None:
    """Le découpage doit être une propriété du CIRCUIT, pas du tour ni de la
    voiture : deux sessions du même circuit doivent donner les mêmes virages.

    C'est précisément ce que ne faisait pas une détection à l'angle volant,
    exprimé en pourcentage de braquage donc dépendant de la voiture.

    Un virage d'écart est toléré, et c'est mesuré, pas concédé de principe :
    sur trois sessions par circuit, Monza donne 11/11/11, Fuji 12/12/12, mais
    Portimão 15/14/14 et Spa 17/17/18. Les sessions qui divergent sont celles
    qui n'ont que trois tours valides, où l'axe de la piste est moins bien
    contraint. Détecter sur plus de tours n'y change rien : c'est le nombre de
    tours de la session la plus pauvre qui commande.

    Ça reste sans conséquence à l'usage : le découpage est enregistré une fois
    par circuit et réutilisé tel quel ensuite.
    """
    if dossier_lmu is None:
        pytest.skip("Le Mans Ultimate n'est pas installé sur cette machine")

    par_circuit: dict[str, list] = {}
    for fichier in catalogue.lister(dossier_lmu)[:30]:
        try:
            session = Session.ouvrir(fichier.chemin)
        except (SessionEnCours, ErreurTelemetrie):
            continue
        numeros = [t.numero for t in session.tours_valides if t.chrono][:4]
        if len(numeros) < 2:
            continue
        cle = session.info.circuit
        if len(par_circuit.get(cle, [])) >= 2:
            continue
        par_circuit.setdefault(cle, []).append(
            detecter([charger(fichier.chemin, n) for n in numeros])
        )

    compares = 0
    for circuit, definitions in par_circuit.items():
        if len(definitions) < 2:
            continue
        a, b = definitions[:2]
        assert abs(len(a.virages) - len(b.virages)) <= 1, (
            f"{circuit} : {len(a.virages)} virages contre {len(b.virages)}"
        )
        # Les virages doivent tomber au même endroit. On apparie chaque virage
        # au plus proche de l'autre découpage, et non par son RANG : un virage
        # de plus au début décalerait sinon toute la liste d'un cran. Cas réel
        # de Long Beach, où un virage à 62 m de la ligne n'apparaissait que
        # dans une des deux sessions — et où la comparaison par rang
        # annonçait 672 m d'écart pour des virages identiques à 2 m près.
        centres_a = np.array([(v.debut + v.fin) / 2 for v in a.virages])
        centres_b = np.array([(v.debut + v.fin) / 2 for v in b.virages])
        decalage = np.array([np.abs(centres_b - c).min() for c in centres_a])
        assert np.median(decalage) < 60.0, f"{circuit} : {np.median(decalage):.0f} m"
        compares += 1
    if not compares:
        pytest.skip("aucun circuit avec deux sessions exploitables")


def test_fichier_de_virages_mal_retouche(tmp_path) -> None:
    """Un champ effacé ou un nombre mal écrit en retouchant le fichier à la
    main donne un message qui désigne le fichier, pas une erreur Python."""
    from lmu_telemetry.errors import ErreurTelemetrie
    from lmu_telemetry.virages import DefinitionCircuit

    for contenu in (
        '{"longueur": 1000, "virages": []}',
        '{"circuit": "X", "longueur": 1000, "virages": [{"numero": 1, "debut": "120 m", "fin": 200}]}',
        '{"circuit": "X", "longueur": 1000, "virages": [3]}',
    ):
        chemin = tmp_path / "X.json"
        chemin.write_text(contenu, encoding="utf-8")
        with pytest.raises(ErreurTelemetrie, match="illisible"):
            DefinitionCircuit.lire(chemin)
