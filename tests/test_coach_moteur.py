"""Le suivi du tour, les zones et le moteur, sur un circuit tracé pour l'occasion.

Le circuit fait 3 000 m. La voiture roule à 60 m/s, freine 200 m avant chaque virage
et remet les gaz à sa sortie. Une faute se glisse à un tour et un virage donnés, ce
qui vérifie que le moteur la voit là, et nulle part ailleurs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from lmu_telemetry.coach.moteur import BilanPassage, Moteur, Rupture, TourTermine
from lmu_telemetry.coach.suivi import SuiviTour
from lmu_telemetry.coach.zones import Zone, zones
from lmu_telemetry.domaine.virages import DefinitionCircuit, Virage
from lmu_telemetry.parametres import SeuilsCoach, SeuilsVirage
from lmu_telemetry.sources.echantillon import Echantillon

LONGUEUR = 3000.0
VITESSE = 60.0
PAS = 0.02

T1 = Virage(1, 1000.0, 1200.0, 40.0, nom="Première", sens=-1)
T2 = Virage(2, 2300.0, 2400.0, 40.0, sens=1)
CIRCUIT = DefinitionCircuit("Essai", LONGUEUR, (T1, T2))


def pedales(d: float) -> tuple[float, float]:
    """Gaz et frein d'un tour propre, selon la distance depuis la ligne."""
    for virage in CIRCUIT.virages:
        if virage.debut - 200 <= d < virage.debut - 60:
            return 0.0, 100.0
        if virage.debut - 60 <= d < virage.debut:
            return 0.0, (virage.debut - d) / 60 * 100.0
        if virage.debut <= d < virage.fin:
            return (d - virage.debut) / (virage.fin - virage.debut) * 100.0, 0.0
    return 100.0, 0.0


def rouler(
    tours: int = 3,
    frequence: int = 50,
    faute: Callable[[int, float, Echantillon], None] | None = None,
    depart: float = 0.0,
    dernier_chrono: Callable[[int], float | None] = lambda tour: 50.0,
    circuit: DefinitionCircuit = CIRCUIT,
) -> Iterator[Echantillon]:
    """Le flux d'une session : distance à 5 Hz, comme en direct."""
    pas = 1.0 / frequence
    temps, tour, debut_tour, d = 0.0, 0, 0.0, depart
    prochaine_distance = 0.0
    while tour < tours:
        gaz, frein = pedales(d)
        e = Echantillon(
            temps=temps,
            tour=tour,
            debut_tour=debut_tour,
            vitesse=VITESSE * 3.6,
            gaz=gaz,
            frein=frein,
            volant=0.0,
            dernier_chrono=dernier_chrono(tour - 1) if tour else None,
        )
        if temps >= prochaine_distance:
            e.distance = d
            e.temps_distance = temps
            prochaine_distance += 0.2
        if faute:
            faute(tour, d, e)
        yield e
        temps += pas
        d += VITESSE * pas
        if d >= circuit.longueur:
            d -= circuit.longueur
            tour += 1
            debut_tour = temps - d / VITESSE


def bilans(evenements: list) -> list[BilanPassage]:
    return [e for e in evenements if isinstance(e, BilanPassage)]


def traiter(flux: Iterator[Echantillon], circuit: DefinitionCircuit = CIRCUIT, **seuils) -> list:
    moteur = Moteur(circuit, SeuilsCoach(**seuils))
    return [evenement for e in flux for evenement in moteur.traiter(e)]


# ----------------------------------------------------------------------
# Suivi du tour
# ----------------------------------------------------------------------


def test_la_distance_avance_entre_deux_mises_a_jour():
    suivi = SuiviTour()
    distances = [
        suivi.avancer(Echantillon(t, 1, 0.0, 216.0, 0, 0, 0, distance=100.0 if t == 0 else None))
        for t in (0.0, 0.1, 0.2)
    ]
    assert distances[0].distance == pytest.approx(100.0)
    assert distances[2].distance == pytest.approx(112.0)


def test_rien_n_est_rendu_tant_que_la_distance_n_est_pas_connue():
    assert SuiviTour().avancer(Echantillon(1.0, 1, 0.0, 216.0, 0, 0, 0)) is None


def test_une_mise_a_jour_recale_l_estimation():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=100.0))
    p = suivi.avancer(
        Echantillon(0.2, 1, 0.0, 216.0, 0, 0, 0, distance=115.0, temps_distance=0.15)
    )
    assert p.distance == pytest.approx(118.0)
    assert not p.rupture


def test_la_ligne_remet_la_distance_a_zero_mais_pas_le_parcouru():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=2990.0))
    avant = suivi.avancer(Echantillon(0.1, 1, 0.0, 216.0, 0, 0, 0))
    p = suivi.avancer(Echantillon(0.2, 2, 0.17, 216.0, 0, 0, 0))
    assert p.ligne
    assert p.tour == 2
    assert p.distance == pytest.approx(1.8)
    assert p.parcouru == pytest.approx(avant.parcouru + 6.0)


def test_une_distance_d_avant_la_ligne_ne_recale_pas_le_nouveau_tour():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=2990.0))
    suivi.avancer(Echantillon(0.2, 2, 0.17, 216.0, 0, 0, 0))
    p = suivi.avancer(
        Echantillon(0.22, 2, 0.17, 216.0, 0, 0, 0, distance=2999.0, temps_distance=0.16)
    )
    assert p.distance == pytest.approx(3.0)


def test_la_distance_peut_etre_negative_juste_apres_la_ligne():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=100.0))
    suivi.avancer(Echantillon(0.1, 2, 0.1, 216.0, 0, 0, 0))
    p = suivi.avancer(
        Echantillon(0.12, 2, 0.1, 216.0, 0, 0, 0, distance=-0.5, temps_distance=0.12)
    )
    assert p.distance == pytest.approx(-0.5)


def test_le_scoring_qui_franchit_la_ligne_avant_la_telemetrie_ne_casse_rien():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=2990.0))
    # La distance repart de zéro alors que le numéro de tour n'a pas encore changé.
    p = suivi.avancer(Echantillon(0.1, 1, 0.0, 216.0, 0, 0, 0, distance=2.0, temps_distance=0.1))
    assert p.distance == pytest.approx(2996.0)
    assert not p.rupture
    assert suivi.avancer(Echantillon(0.2, 2, 0.15, 216.0, 0, 0, 0)).ligne


def test_le_temps_qui_recule_est_une_nouvelle_session():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(500.0, 3, 450.0, 216.0, 0, 0, 0, distance=100.0))
    # Tant que la distance de la nouvelle session n'est pas connue, on ne dit rien.
    assert suivi.avancer(Echantillon(1.0, 0, 0.0, 0.0, 0, 0, 0)) is None
    p = suivi.avancer(Echantillon(1.1, 0, 0.0, 0.0, 0, 0, 0, distance=5.0, temps_distance=1.1))
    assert p.rupture
    assert p.distance == pytest.approx(5.0)
    assert not suivi.avancer(Echantillon(1.2, 0, 0.0, 0.0, 0, 0, 0)).rupture


def test_un_trou_dans_le_flux_est_une_rupture():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=100.0))
    p = suivi.avancer(Echantillon(2.0, 1, 0.0, 216.0, 0, 0, 0, distance=220.0, temps_distance=2.0))
    assert p.rupture


def test_une_voiture_replacee_est_une_rupture():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=1000.0))
    ruptures = []
    for i in range(1, 5):
        t = i * 0.2
        p = suivi.avancer(
            Echantillon(t, 1, 0.0, 216.0, 0, 0, 0, distance=200.0 + i, temps_distance=t)
        )
        ruptures.append(p.rupture)
    assert ruptures == [False, False, True, False]
    assert p.distance < 300


def test_une_coupe_de_chicane_ne_passe_pas_pour_une_rupture():
    suivi = SuiviTour()
    suivi.avancer(Echantillon(0.0, 1, 0.0, 216.0, 0, 0, 0, distance=2150.0))
    p = suivi.avancer(Echantillon(0.2, 1, 0.0, 216.0, 0, 0, 0, distance=2184.0, temps_distance=0.2))
    assert p.distance == pytest.approx(2184.0)
    assert not p.rupture


# ----------------------------------------------------------------------
# Zones
# ----------------------------------------------------------------------


def numeros(z: Zone) -> list[int]:
    return [v.numero for v in z.virages]


def test_deux_virages_proches_font_une_seule_zone():
    a = Virage(1, 500.0, 600.0, 20.0)
    b = Virage(2, 600.0, 700.0, 20.0)
    c = Virage(3, 760.0, 800.0, 20.0)
    d = Virage(4, 1500.0, 1600.0, 20.0)
    circuit = DefinitionCircuit("Essai", LONGUEUR, (a, b, c, d))
    assert [numeros(z) for z in zones(circuit)] == [[1, 2, 3], [4]]
    assert [numeros(z) for z in zones(circuit, SeuilsCoach(ecart_groupe=50.0))] == [[1, 2], [3], [4]]


def test_une_zone_va_du_freinage_a_la_sortie_sans_mordre_sur_ses_voisines():
    z1, z2 = zones(CIRCUIT, virages=SeuilsVirage(remontee_freinage=350, prolongement_sortie=100))
    assert (z1.debut, z1.fin) == (650.0, 1300.0)
    assert (z2.debut, z2.fin) == (1950.0, 2500.0)

    proche = DefinitionCircuit(
        "Essai", LONGUEUR, (Virage(1, 1000.0, 1200.0, 40.0), Virage(2, 1350.0, 1400.0, 40.0))
    )
    a, b = zones(proche)
    assert a.fin == 1300.0
    assert b.debut == 1200.0


def test_un_freinage_d_avant_la_ligne_appartient_a_la_zone():
    virage = Virage(1, 60.0, 150.0, 20.0)
    (zone,) = zones(DefinitionCircuit("Essai", LONGUEUR, (virage,)))
    assert zone.debut == pytest.approx(60.0 - 350.0)


def test_le_virage_d_avant_la_ligne_borne_le_freinage_du_premier():
    premier = Virage(1, 60.0, 150.0, 20.0)
    dernier = Virage(2, 2900.0, 2950.0, 20.0)
    a, b = zones(DefinitionCircuit("Essai", LONGUEUR, (premier, dernier)))
    assert a.debut == pytest.approx(-50.0)
    assert b.fin == pytest.approx(3050.0)


def test_le_nom_d_une_zone():
    nomme = Virage(1, 0.0, 10.0, 20.0, nom="Lesmo 2")
    assert Zone((nomme,), 0.0, 10.0).libelle == "Lesmo 2"
    sans_nom = Virage(6, 0.0, 10.0, 20.0)
    assert Zone((sans_nom,), 0.0, 10.0).libelle == "T6"
    a = Virage(1, 0.0, 10.0, 20.0, nom="Ascari")
    b = Virage(2, 10.0, 20.0, 20.0, nom="Ascari")
    c = Virage(3, 20.0, 30.0, 20.0, nom="Ascari")
    assert Zone((a, b, c), 0.0, 30.0).libelle == "Ascari"
    assert Zone((sans_nom, Virage(7, 10.0, 20.0, 20.0)), 0.0, 30.0).libelle == "T6-7"


# ----------------------------------------------------------------------
# Moteur
# ----------------------------------------------------------------------


def test_un_bilan_par_zone_et_par_tour():
    resultat = bilans(traiter(rouler(3)))
    assert [(b.passage.tour, b.passage.zone.libelle) for b in resultat] == [
        (0, "Première"), (0, "T2"),
        (1, "Première"), (1, "T2"),
        (2, "Première"), (2, "T2"),
    ]


def test_un_tour_propre_ne_donne_aucun_conseil():
    assert [b.conseil for b in bilans(traiter(rouler(3)))] == [None] * 6


def test_la_faute_est_vue_a_son_tour_et_a_son_virage():
    def faute(tour: int, d: float, e: Echantillon) -> None:
        # Lever de pied 0,5 s avant le frein du premier virage, au tour 1.
        if tour == 1 and 770.0 <= d < 800.0:
            e.gaz = 0.0

    avec_conseil = [b for b in bilans(traiter(rouler(3, faute=faute))) if b.conseil]
    assert [(b.passage.tour, b.passage.zone.libelle) for b in avec_conseil] == [(1, "Première")]
    assert avec_conseil[0].conseil.code == "roue_libre_avant"
    assert str(avec_conseil[0].conseil.message) == "Première : roue libre de 0,5 s avant de freiner"


def test_la_cadence_ne_change_pas_le_verdict():
    def faute(tour: int, d: float, e: Echantillon) -> None:
        if tour == 1 and 770.0 <= d < 800.0:
            e.gaz = 0.0

    a = [b.conseil.code for b in bilans(traiter(rouler(3, 50, faute))) if b.conseil]
    b = [b.conseil.code for b in bilans(traiter(rouler(3, 100, faute))) if b.conseil]
    assert a == b == ["roue_libre_avant"]


def test_le_passage_arrive_juste_apres_la_fin_de_la_zone():
    moteur = Moteur(CIRCUIT)
    zone = moteur.zones[0]
    for e in rouler(1):
        (bilan,) = bilans(moteur.traiter(e)) or (None,)
        if bilan is not None:
            assert bilan.passage.zone == zone
            assert bilan.passage.distance[-1] == pytest.approx(zone.fin, abs=2.0)
            assert bilan.passage.temps_sortie == pytest.approx(T1.fin / VITESSE, abs=0.1)
            return
    pytest.fail("aucun passage")


def test_le_tour_termine_donne_le_chrono_du_jeu():
    tours = [e for e in traiter(rouler(3)) if isinstance(e, TourTermine)]
    assert [(t.tour, t.chrono) for t in tours] == [(0, 50.0), (1, 50.0)]


def test_un_tour_non_chronometre_est_signale():
    flux = rouler(3, dernier_chrono=lambda tour: None if tour == 1 else 50.0)
    assert [t.chrono for t in traiter(flux) if isinstance(t, TourTermine)] == [50.0, None]


def test_un_passage_commence_en_route_n_est_pas_juge():
    # Le moteur démarre au milieu du premier virage : il ne l'a pas vu en entier.
    resultat = bilans(traiter(rouler(2, depart=1100.0)))
    assert (0, "Première") not in [(b.passage.tour, b.passage.zone.libelle) for b in resultat]
    assert (0, "T2") in [(b.passage.tour, b.passage.zone.libelle) for b in resultat]


def test_un_freinage_d_avant_la_ligne_reste_dans_le_passage():
    virage = Virage(1, 60.0, 150.0, 20.0, sens=-1)
    circuit = DefinitionCircuit("Essai", LONGUEUR, (virage,))

    def freinage(_tour: int, d: float, e: Echantillon) -> None:
        e.gaz, e.frein = (0.0, 100.0) if d >= 2900.0 or d < 60.0 else (100.0, 0.0)

    resultat = bilans(traiter(rouler(3, faute=freinage, circuit=circuit), circuit))
    passage = next(b.passage for b in resultat if b.passage.tour == 1)
    assert passage.distance[0] == pytest.approx(-290.0, abs=3.0)
    assert passage.frein[passage.distance < 0].max() == 100.0


@pytest.mark.parametrize(
    "faute, raison",
    [
        (lambda e: setattr(e, "hors_piste", True), "hors_piste"),
        (lambda e: setattr(e, "stands", True), "stands"),
        (lambda e: setattr(e, "vitesse", 20.0), "arret"),
    ],
)
def test_un_passage_anormal_n_est_pas_juge(faute, raison):
    def perturber(tour: int, d: float, e: Echantillon) -> None:
        if tour == 1 and 1100.0 <= d < 1150.0:
            faute(e)

    resultat = bilans(traiter(rouler(3, faute=perturber)))
    premier_virage = [b for b in resultat if b.passage.zone.virages == (T1,)]
    assert [(b.passage.tour, b.ecarte) for b in premier_virage] == [
        (0, None), (1, raison), (2, None),
    ]


def test_un_choc_ecarte_le_passage_ou_il_a_lieu():
    instant = []

    def heurter(tour: int, d: float, e: Echantillon) -> None:
        if tour == 1 and d >= 1100.0 and not instant:
            instant.append(e.temps)
        # Le jeu garde l'heure du dernier choc jusqu'au suivant.
        e.dernier_choc = instant[0] if instant else -1.0

    resultat = bilans(traiter(rouler(3, faute=heurter)))
    assert [(b.passage.tour, b.ecarte) for b in resultat] == [
        (0, None), (0, None), (1, "choc"), (1, None), (2, None), (2, None),
    ]


def test_un_choc_de_la_session_precedente_ne_compte_pas():
    def oublier(_tour: int, _d: float, e: Echantillon) -> None:
        e.dernier_choc = 9999.0

    assert [b.ecarte for b in bilans(traiter(rouler(2, faute=oublier)))] == [None] * 4


def test_un_bref_passage_sur_l_herbe_est_tolere():
    def effleurer(tour: int, d: float, e: Echantillon) -> None:
        e.hors_piste = tour == 1 and 1100.0 <= d < 1106.0

    assert [b.ecarte for b in bilans(traiter(rouler(2, faute=effleurer)))] == [None] * 4


def test_le_tour_de_sortie_des_stands_n_est_pas_juge():
    def sortir(tour: int, d: float, e: Echantillon) -> None:
        e.stands = tour == 0 and d < 300.0

    resultat = bilans(traiter(rouler(2, faute=sortir)))
    assert [(b.passage.tour, b.ecarte) for b in resultat] == [
        (0, "sortie_stands"), (0, "sortie_stands"), (1, None), (1, None),
    ]


def test_une_rupture_oublie_ce_qui_precede():
    moteur = Moteur(CIRCUIT)
    evenements = [x for e in rouler(1) for x in moteur.traiter(e)]
    assert not any(isinstance(x, Rupture) for x in evenements)

    # Nouvelle session : l'horloge repart de zéro.
    nouveaux = [x for e in rouler(2) for x in moteur.traiter(e)]
    assert sum(isinstance(x, Rupture) for x in nouveaux) == 1
    assert [(b.passage.tour, b.passage.zone.libelle) for b in bilans(nouveaux)] == [
        (0, "Première"), (0, "T2"), (1, "Première"), (1, "T2"),
    ]


def test_l_etalonnage_ecarte_une_roue_encore_bloquee():
    from lmu_telemetry.coach.roues import EtalonnageRoues

    etalonnage = EtalonnageRoues()
    for _ in range(50):
        etalonnage.observer(Echantillon(0, 0, 0, 200.0, 0, 0, 0, roues=(200, 200, 206, 206)))
    # Tête-à-queue : aucune pédale, volant droit, roues arrêtées.
    for _ in range(200):
        etalonnage.observer(Echantillon(0, 0, 0, 200.0, 0, 0, 0, roues=(0, 0, 0, 0)))
    assert etalonnage.echelle.tolist() == pytest.approx([1.0, 1.0, 1.03, 1.03])


def test_l_etalonnage_ne_retient_que_les_roues_libres():
    from lmu_telemetry.coach.roues import EtalonnageRoues

    etalonnage = EtalonnageRoues()
    etalonnage.observer(Echantillon(0, 0, 0, 200.0, 100.0, 0, 0, roues=(205,) * 4))
    etalonnage.observer(Echantillon(0, 0, 0, 200.0, 0, 50.0, 0, roues=(205,) * 4))
    etalonnage.observer(Echantillon(0, 0, 0, 200.0, 0, 0, 40.0, roues=(205,) * 4))
    etalonnage.observer(Echantillon(0, 0, 0, 30.0, 0, 0, 0, roues=(31,) * 4))
    assert etalonnage.echelle.tolist() == [1.0] * 4
