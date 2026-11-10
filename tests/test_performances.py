"""Les performances d'un pilote, séance par séance, et le bilan de ses courses.

Les fichiers de résultats sont fabriqués ici (voir `tests/test_classement.py`).
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from lmu_telemetry.domaine import performances as perf
from lmu_telemetry.sources import resultats
from tests.test_classement import T0, pilote, seance_xml, tour


def seances(tmp_path: Path, *fichiers: tuple[str, str]) -> list:
    dossier = tmp_path / "Results"
    dossier.mkdir(exist_ok=True)
    for nom, xml in fichiers:
        (dossier / nom).write_text(xml, encoding="utf-8")
    return resultats.Seances(dossier).toutes()


def course_seul() -> str:
    """Une course contre l'IA : le joueur part 3e de sa catégorie et finit 2e."""
    tours = [
        tour(1, 3, "130.0000", (40.0, 45.0, 45.0)),  # le départ
        tour(2, 3, "100.0000", (33.0, 34.0, 33.0)),
        tour(3, 2, "--.----", (32.5, None, None), gomme="0,Soft"),  # invalidé : sans temps
        tour(4, 2, "100.4000", (33.2, 34.1, 33.1), vmax="262.5"),
        tour(5, 2, "99.6000", (32.9, 33.6, 33.1)),
    ]
    return seance_xml("Race", T0, [
        pilote("IA 1", "X #9", "Hyper", 1, 1, [], modele="Cadillac V-Series.R"),
        pilote("Moi", "A #1", "GT3", 2, 2, tours, joueur=True, meilleur="99.6000",
               total="530.0000", grille=4, grille_classe=3),
        pilote("IA 2", "Y #8", "GT3", 3, 1, []),
    ])


def test_une_seance_se_resume_en_une_performance(tmp_path: Path) -> None:
    (seance,) = seances(tmp_path, ("course-01R1.xml", course_seul()))
    p = perf.performance(seance, seance.joueurs[0])
    assert (p.id, p.type, p.en_ligne, p.pilote, p.classe) == (f"{int(T0.timestamp())}-R", "R", False, "Moi", "GT3")
    assert (p.trace, p.voiture, p.marque) == ("Autodromo Nazionale Monza", "Porsche 911 GT3 R LMGT3", "Porsche")
    assert (p.tours, p.tours_chronometres) == (5, 4)
    assert (p.meilleur_tour, p.tour_meilleur, p.secteurs_meilleur) == (99.6, 5, (32.9, 33.6, 33.1))
    # Le 32.5 du tour invalidé ne compte pas ; le meilleur S3 vient du tour 2, pas du meilleur tour.
    assert p.meilleurs_secteurs == (32.9, 33.6, 33.0)
    # Sans le départ : 100.0, 100.4 et 99.6.
    assert p.temps_moyen == pytest.approx(100.0)
    assert p.tours_moyenne == 3
    assert p.vitesse_max == 262.5
    assert p.gommes == {"Medium": 4, "Soft": 1}
    assert (p.grille_classe, p.place, p.place_classe, p.engages, p.engages_classe, p.statut) == (
        3, 2, 2, 3, 2, "arrivee",
    )
    json.dumps(p.json())  # ce qui sera partagé passe en JSON


def test_hors_course_ni_grille_ni_place(tmp_path: Path) -> None:
    (seance,) = seances(tmp_path, ("essais-01P1.xml", seance_xml("Practice1", T0, [
        pilote("Moi", "A #1", "GT3", 1, 1, [tour(1, 1, "101.0000")], joueur=True, statut="None"),
    ])))
    p = perf.performance(seance, seance.joueurs[0])
    assert (p.type, p.place, p.statut, p.meilleur_tour) == ("P", None, None, 101.0)
    assert p.temps_moyen is None  # le seul tour est le premier


def test_les_noms_du_proprietaire(tmp_path: Path) -> None:
    liste = seances(
        tmp_path,
        ("seul-01R1.xml", course_seul()),
        ("en-ligne-02R1.xml", seance_xml("Race", T0 + timedelta(hours=1), [
            pilote("Ami", "B #2", "GT3", 1, 1, [], joueur=True),
            pilote("Moi", "A #1", "GT3", 2, 2, [], joueur=True),
        ], setting="Multiplayer")),
    )
    # Seul contre l'IA, le jeu ne marque que lui ; en ligne, tout le monde.
    assert perf.noms_du_proprietaire(liste) == {"Moi"}
    assert perf.noms_du_proprietaire(liste, {"Pseudo", "?"}) == {"Moi", "Pseudo"}


def test_en_ligne_on_ne_garde_que_le_proprietaire(tmp_path: Path) -> None:
    liste = seances(
        tmp_path,
        ("seul-01R1.xml", course_seul()),
        ("en-ligne-02R1.xml", seance_xml("Race", T0 + timedelta(hours=1), [
            pilote("Ami", "B #2", "GT3", 1, 1, [tour(1, 1, "99.0000")], joueur=True),
            pilote("Moi", "A #1", "GT3", 2, 2, [tour(1, 2, "100.0000")], joueur=True),
        ], setting="Multiplayer")),
    )
    resultat = perf.performances(liste, {"Moi"})
    assert [(p.pilote, p.en_ligne) for p in resultat] == [("Moi", False), ("Moi", True)]


def test_le_bilan_des_courses(tmp_path: Path) -> None:
    def course(heure: int, place: int, statut: str = "Finished Normally") -> tuple[str, str]:
        return (f"c{heure}-0{heure}R1.xml", seance_xml("Race", T0 + timedelta(hours=heure), [
            pilote("Moi", "A #1", "GT3", place, place, [tour(1, place, "100.0000")] * 3,
                   joueur=True, statut=statut),
        ]))

    liste = seances(tmp_path, course(1, 1), course(2, 3), course(3, 12), course(4, 2, "DNF"),
                    ("essais-05P1.xml", seance_xml("Practice1", T0 + timedelta(hours=5), [
                        pilote("Moi", "A #1", "GT3", 1, 1, [tour(1, 1, "100.0000")] * 4, joueur=True),
                    ])))
    bilan = perf.bilan_courses(perf.performances(liste, {"Moi"}))
    assert bilan == {
        "courses": 4, "victoires": 1, "podiums": 2, "top10": 2, "abandons": 1,
        # Les arrivées seulement : 1, 3 et 12.
        "place_moyenne": pytest.approx(16 / 3, abs=0.01),
        "tours_en_course": 12, "tours": 16,
    }
