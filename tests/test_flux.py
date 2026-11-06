"""Les trois sources du moteur : fichier, capture et mémoire du jeu.

Une capture et le direct passent par la même conversion : la tester sur des blocs
bruts vaut pour les deux. La session de test sert au rejeu d'un fichier.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

from lmu_telemetry.cli import main
from lmu_telemetry.coach.moteur import BilanPassage, TourTermine
from lmu_telemetry.coach.rejeu import identite_capture, ouvrir, rejouer
from lmu_telemetry.domaine.session import Session
from lmu_telemetry.domaine.virages import DefinitionCircuit, Virage
from lmu_telemetry.sources import memoire_lmu as m
from lmu_telemetry.sources.echantillon import FREQUENCE_LECTURE
from lmu_telemetry.sources.flux_fichier import flux_fichier
from lmu_telemetry.sources.flux_memoire import (
    ENTETE_CAPTURE,
    TYPE_SCORING,
    TYPE_TELEMETRIE,
    TYPE_VEHICULE,
    Convertisseur,
    ecrire_enregistrement,
    flux_capture,
    flux_direct,
)
from tests.fixtures import construire as fixture
from tests.test_memoire_lmu import FausseMemoire

# ----------------------------------------------------------------------
# Fichier
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def echantillons(session_test: Path) -> list:
    return list(flux_fichier(session_test))


def a_l_instant(echantillons: list, temps: float):
    return echantillons[int((temps - fixture.T0) * FREQUENCE_LECTURE)]


def test_le_fichier_est_lu_a_la_cadence_du_direct(echantillons):
    assert len(echantillons) == int(fixture.DUREE * FREQUENCE_LECTURE)
    assert echantillons[1].temps - echantillons[0].temps == pytest.approx(1 / FREQUENCE_LECTURE)


def test_la_distance_n_arrive_qu_a_cinq_hertz(echantillons):
    mises_a_jour = [e for e in echantillons if e.distance is not None]
    assert len(mises_a_jour) == pytest.approx(fixture.DUREE * 5, abs=1)
    ecarts = {round(b.temps - a.temps, 2) for a, b in zip(mises_a_jour, mises_a_jour[1:])}
    assert ecarts == {0.2}


def test_les_tours_suivent_les_evenements_du_jeu(echantillons):
    e = a_l_instant(echantillons, 300.0)
    assert (e.tour, e.debut_tour) == (2, 250.0)
    assert a_l_instant(echantillons, 620.0).tour == 6


def test_le_fichier_donne_le_geste_et_les_unites_du_direct(echantillons):
    # 44 s après la ligne : le freinage du virage de test.
    e = a_l_instant(echantillons, 160.0 + 44.5)
    assert (e.gaz, e.frein) == (0.0, 100.0)
    assert a_l_instant(echantillons, 200.0).vitesse == pytest.approx(150.0)
    assert e.roues is None


def test_les_canaux_bruts_sont_preferes(tmp_path: Path, session_test: Path):
    import shutil

    import duckdb

    copie = tmp_path / "avec_brut.duckdb"
    shutil.copyfile(session_test, copie)
    con = duckdb.connect(str(copie))
    n = con.execute('SELECT count(*) FROM "Throttle Pos"').fetchone()[0]
    con.execute('CREATE TABLE "Throttle Pos Unfiltered" (value DOUBLE)')
    con.execute(f'INSERT INTO "Throttle Pos Unfiltered" SELECT 42.0 FROM range({n})')
    con.execute("INSERT INTO channelsList VALUES ('Throttle Pos Unfiltered', 50, '%')")
    con.close()
    assert next(flux_fichier(copie)).gaz == 42.0


def test_le_chrono_d_un_tour_invalide_ne_reprend_pas_le_precedent(echantillons):
    assert a_l_instant(echantillons, 300.0).dernier_chrono == 90.0
    assert a_l_instant(echantillons, 345.0).dernier_chrono is None
    assert a_l_instant(echantillons, 440.0).dernier_chrono == 92.0


def test_les_stands_le_hors_piste_et_les_chocs(echantillons):
    assert a_l_instant(echantillons, 110.0).stands
    assert not a_l_instant(echantillons, 140.0).stands
    assert a_l_instant(echantillons, 354.0).dernier_choc == -1.0
    assert a_l_instant(echantillons, 356.0).dernier_choc == 355.0
    assert a_l_instant(echantillons, 500.0).dernier_choc == 360.0
    assert any(e.hors_piste for e in echantillons)


def definition_de_test() -> DefinitionCircuit:
    debut = fixture.VITESSE_RAPIDE / 3.6 * fixture.VIRAGE_LENT_S[0]
    return DefinitionCircuit(
        "Circuit de test",
        fixture.LONGUEUR_TOUR,
        (Virage(1, debut, debut + 200.0, 50.0, sens=1),),
    )


def test_le_rejeu_retrouve_les_tours_de_la_session(session_test: Path):
    evenements = list(rejouer(flux_fichier(session_test), definition_de_test()))
    tours = [e for e in evenements if isinstance(e, TourTermine)]
    session = Session.ouvrir(session_test)
    assert [(t.tour, t.chrono) for t in tours] == [
        (t.numero, t.chrono) for t in session.tours if t.complet
    ]


def test_le_rejeu_juge_le_virage_de_chaque_tour(session_test: Path):
    bilans = [
        e for e in rejouer(flux_fichier(session_test), definition_de_test())
        if isinstance(e, BilanPassage)
    ]
    assert {b.passage.tour for b in bilans} >= {1, 2, 4, 5}


def test_la_commande_rejouer(session_test: Path, capsys: pytest.CaptureFixture, monkeypatch):
    from lmu_telemetry import emplacements

    definition_de_test().enregistrer(
        emplacements.virages_utilisateur() / "Circuit de test.json"
    )
    assert main(["rejouer", str(session_test)]) == 0
    sortie = capsys.readouterr().out
    assert "Tour 1 : 1:30.000" in sortie
    assert "Tour 2 : non chronométré" in sortie
    assert "ni blocage ni patinage" in sortie


# ----------------------------------------------------------------------
# Mémoire et capture
# ----------------------------------------------------------------------


def bloc(taille: int, champs: dict, base: int = 0, **valeurs) -> bytearray:
    brut = bytearray(taille)
    remplir(brut, champs, base, **valeurs)
    return brut


def remplir(brut: bytearray, champs: dict, base: int = 0, **valeurs) -> None:
    for nom, valeur in valeurs.items():
        decalage, format_ = champs[nom]
        arguments = valeur if isinstance(valeur, tuple) else (valeur,)
        struct.pack_into(format_, brut, base + decalage, *arguments)


def telemetrie(temps: float = 12.5, **valeurs) -> bytes:
    defauts = dict(
        temps=temps,
        tour=3,
        debut_tour=10.0,
        vitesse_locale=(30.0, 0.0, -40.0),
        gaz_brut=0.75,
        frein_brut=0.25,
        volant=-0.5,
        circuit=b"Monza",
        modele=b"BMW M4 GT3",
    )
    brut = bloc(m.TAILLE_TELEMETRIE, m.CHAMPS_TELEMETRIE, **{**defauts, **valeurs})
    for i, rotation in enumerate((-100.0, -100.0, -110.0, -110.0)):
        base = m.DEBUT_ROUES + i * m.TAILLE_ROUE
        remplir(brut, m.CHAMPS_ROUE, base, rotation=rotation, rayon_cm=35)
    return bytes(brut)


def vehicule(distance: float = 1500.0, **valeurs) -> bytes:
    defauts = dict(distance_tour=distance, dernier_tour=114.5, aux_stands=False)
    return bytes(bloc(m.TAILLE_VEHICULE, m.CHAMPS_VEHICULE, **{**defauts, **valeurs}))


def scoring(temps: float = 12.4) -> bytes:
    return bytes(bloc(m.TAILLE_SCORING, m.CHAMPS_SCORING, temps=temps, circuit=b"Monza"))


def lecture(t: bytes | None = None, v: bytes | None = None, s: bytes | None = None) -> m.Lecture:
    return m.Lecture(t or telemetrie(), v or vehicule(), s or scoring())


def test_la_conversion_rend_les_unites_du_fichier():
    e = Convertisseur().convertir(lecture())
    assert e.temps == 12.5
    assert (e.tour, e.debut_tour) == (3, 10.0)
    assert e.vitesse == pytest.approx(math.hypot(30, 40) * 3.6)
    assert (e.gaz, e.frein, e.volant) == (75.0, 25.0, -50.0)
    assert e.dernier_chrono == 114.5
    assert not e.stands


def test_la_vitesse_des_roues_vient_de_la_rotation():
    e = Convertisseur().convertir(lecture())
    assert e.roues == pytest.approx((126.0, 126.0, 138.6, 138.6))


def test_une_roue_dans_l_herbe_met_la_voiture_hors_piste():
    brut = bytearray(telemetrie())
    remplir(brut, m.CHAMPS_ROUE, m.DEBUT_ROUES + 2 * m.TAILLE_ROUE, surface=2)
    assert Convertisseur().convertir(lecture(bytes(brut))).hors_piste


def test_une_lecture_sans_rien_de_neuf_ne_donne_rien():
    convertisseur = Convertisseur()
    assert convertisseur.convertir(lecture()) is not None
    assert convertisseur.convertir(lecture()) is None


def test_la_distance_n_est_donnee_que_quand_elle_change():
    convertisseur = Convertisseur()
    a = convertisseur.convertir(lecture(telemetrie(1.0), vehicule(100.0), scoring(0.95)))
    b = convertisseur.convertir(lecture(telemetrie(1.01), vehicule(100.0), scoring(0.95)))
    c = convertisseur.convertir(lecture(telemetrie(1.02), vehicule(106.0), scoring(1.02)))
    assert (a.distance, a.temps_distance) == (100.0, 0.95)
    assert b.distance is None
    assert (c.distance, c.temps_distance) == (106.0, 1.02)


def test_un_tour_non_chronometre_vaut_moins_un_dans_la_memoire():
    e = Convertisseur().convertir(lecture(v=vehicule(dernier_tour=-1.0)))
    assert e.dernier_chrono is None


def test_sans_bloc_vehicule_l_echantillon_reste_utilisable():
    e = Convertisseur().convertir(m.Lecture(telemetrie(), None, scoring()))
    assert e.distance is None
    assert e.dernier_chrono is None


def ecrire_capture(chemin: Path) -> None:
    with chemin.open("wb") as flux:
        flux.write(ENTETE_CAPTURE)
        # L'ancienne voiture, encore en mémoire au chargement de la session.
        ecrire_enregistrement(flux, TYPE_TELEMETRIE, 0.0, telemetrie(90.0, modele=b"Ancienne"))
        ecrire_enregistrement(flux, TYPE_SCORING, 0.0, scoring())
        ecrire_enregistrement(flux, TYPE_VEHICULE, 0.0, vehicule())
        ecrire_enregistrement(flux, TYPE_TELEMETRIE, 0.01, telemetrie(12.5))
        ecrire_enregistrement(flux, TYPE_TELEMETRIE, 0.02, telemetrie(12.51))


def test_une_capture_passe_par_la_meme_conversion(tmp_path: Path):
    chemin = tmp_path / "capture.bin"
    ecrire_capture(chemin)
    flux = list(flux_capture(chemin))
    assert [e.temps for e in flux] == [12.5, 12.51]
    assert flux[0].roues is not None
    assert flux[0].distance == 1500.0
    assert flux[1].distance is None


def test_une_capture_s_ouvre_par_son_fichier_ou_son_dossier(tmp_path: Path):
    ecrire_capture(tmp_path / "capture.bin")
    for chemin in (tmp_path, tmp_path / "capture.bin"):
        source = ouvrir(chemin)
        assert source.roues
        assert len(list(source.flux())) == 2
    assert identite_capture(tmp_path) == ("Monza", "BMW M4 GT3")


def test_un_fichier_du_jeu_ne_voit_pas_les_roues(session_test: Path):
    assert not ouvrir(session_test).roues


class FauxLecteur:
    """Une mémoire déjà ouverte, sur le circuit de test."""

    def __enter__(self) -> "FauxLecteur":
        return self

    def __exit__(self, *_exc: object) -> None:
        pass

    def lire(self) -> m.Lecture:
        brut = bloc(m.TAILLE_SCORING, m.CHAMPS_SCORING, circuit=b"Circuit de test")
        return lecture(s=bytes(brut))


def test_la_commande_direct_change_de_moteur_avec_la_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    from lmu_telemetry import emplacements
    from lmu_telemetry.sources import flux_memoire
    from lmu_telemetry.sources.echantillon import Echantillon

    definition_de_test().enregistrer(emplacements.virages_utilisateur() / "Circuit de test.json")

    def faux_flux(_memoire):
        yield Echantillon(10.0, 1, 0.0, 200.0, 0, 0, 0, distance=100.0, temps_distance=10.0)
        # L'horloge repart de zéro : nouvelle session.
        yield Echantillon(1.0, 0, 0.0, 0.0, 0, 0, 0, distance=5.0, temps_distance=1.0)
        raise KeyboardInterrupt

    monkeypatch.setattr(m, "LecteurMemoire", FauxLecteur)
    monkeypatch.setattr(flux_memoire, "flux_direct", faux_flux)
    assert main(["direct"]) == 0
    assert capsys.readouterr().out.count("Circuit : Circuit de test") == 2


def test_la_commande_direct_sans_decoupage_le_dit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.setattr(m, "LecteurMemoire", FauxLecteur)
    assert main(["direct"]) == 1
    assert "Circuit de test" in capsys.readouterr().err


def test_le_direct_lit_le_jeu_sans_se_repeter():
    jeu = FausseMemoire()
    jeu.preparer()
    jeu.champ(jeu.base_telemetrie, m.CHAMPS_TELEMETRIE, "temps", 5.0)
    jeu.champ(jeu.base_telemetrie, m.CHAMPS_TELEMETRIE, "gaz_brut", 0.5)
    jeu.champ(jeu.base_vehicule, m.CHAMPS_VEHICULE, "distance_tour", 321.0)

    tours = iter(range(5))
    try:
        with m.LecteurMemoire(jeu.nom) as memoire:
            flux = list(
                flux_direct(memoire, lambda: next(tours, None) is not None, frequence=1000)
            )
    finally:
        jeu.fermer()
    assert len(flux) == 1
    assert flux[0].gaz == 50.0
    assert flux[0].distance == 321.0
