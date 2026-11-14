"""Le leaderboard : les dernières courses, le menu des circuits, les meilleurs tours par
tracé et par catégorie, le bilan des courses, les filtres de l'écran, et la route.

Les performances sont fabriquées ici ; celles d'un vrai fichier de résultats sont
vérifiées dans `tests/test_performances.py`.
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

from lmu_telemetry.domaine import leaderboard as lb
from lmu_telemetry.domaine.performances import Performance
from lmu_telemetry.web import reponses, serveur
from tests.test_classement import T0, jeu, pilote, seance_xml, tour  # noqa: F401  (jeu : une fixture)

MONZA = "Autodromo Nazionale Monza"
CURVA_GRANDE = "Monza Curva Grande Circuit"
SPA = "Circuit de Spa-Francorchamps"
PORSCHE = "Porsche 911 GT3 R LMGT3"
FERRARI = "Ferrari 296 LMGT3"

BASE = Performance(
    id="1794240000-P",
    date="2026-11-01T10:00:00+00:00",
    circuit=MONZA,
    trace=MONZA,
    type="Q",
    en_ligne=True,
    pilote="Moi",
    voiture=PORSCHE,
    marque="Porsche",
    classe="GT3",
    tours=10,
    tours_chronometres=8,
    meilleur_tour=100.0,
    tour_meilleur=4,
    secteurs_meilleur=(33.0, 34.0, 33.0),
    meilleurs_secteurs=(32.9, 33.8, 33.0),
    temps_moyen=101.0,
    tours_moyenne=5,
    vitesse_max=260.0,
    gommes={"Medium": 10},
    gomme_meilleur="Medium",
)


def perf(**champs) -> Performance:
    return replace(BASE, **champs)


def course(pilote: str, place: int, *, statut: str = "arrivee", heure: int = 12, **champs) -> Performance:
    return perf(pilote=pilote, type="R", place=place, place_classe=place, statut=statut,
                date=f"2026-11-02T{heure:02d}:00:00+00:00", **champs)


# ----------------------------------------------------------------------
# Les meilleurs tours d'un tracé
# ----------------------------------------------------------------------


def test_une_ligne_par_pilote_et_par_categorie() -> None:
    perfs = [
        perf(),
        perf(classe="LMP3", voiture="Ligier JS P325", marque="Ligier", meilleur_tour=95.0),
        perf(pilote="Ami", meilleur_tour=99.5),
        perf(pilote="Ami", trace=SPA, circuit=SPA, meilleur_tour=130.0),  # un autre tracé
    ]
    categories = lb.classement_tours(perfs, lb.Filtres(trace=MONZA), {"Moi"})
    # La catégorie la plus rapide d'abord : un tour en LMP3 ne cache pas les chronos en GT3.
    assert [(c["classe"], c["reference"]) for c in categories] == [("LMP3", 95.0), ("GT3", 99.5)]
    gt3 = categories[1]["lignes"]
    assert [(l["place"], l["pilote"], l["moi"], l["ecart"]) for l in gt3] == [
        (1, "Ami", False, 0.0),
        (2, "Moi", True, 0.5),
    ]


def test_le_meilleur_tour_et_ce_qui_l_entoure() -> None:
    perfs = [
        perf(),
        perf(
            id="1794250000-Q", date="2026-11-03T10:00:00+00:00", type="Q", voiture=FERRARI,
            marque="Ferrari", meilleur_tour=99.8, secteurs_meilleur=(33.1, 33.7, 33.0),
            meilleurs_secteurs=(33.1, 33.7, 33.2), temps_moyen=100.0, tours_moyenne=15, vitesse_max=262.0,
            gommes={"Soft": 3, "Medium": 2}, gomme_meilleur="Soft", tours=5,
        ),
        perf(meilleur_tour=None, temps_moyen=None, tours_moyenne=0, meilleurs_secteurs=(None, None, None),
             vitesse_max=None, gommes={}, gomme_meilleur=None, tours=0),  # une sortie sans tour bouclé
    ]
    (ligne,) = lb.classement_tours(perfs, lb.Filtres(trace=MONZA))[0]["lignes"]
    # Le meilleur tour, avec sa voiture, sa séance et sa gomme.
    assert (ligne["meilleur_tour"], ligne["voiture"], ligne["marque"]) == (99.8, FERRARI, "Ferrari")
    assert (ligne["date"], ligne["type"], ligne["gomme_meilleur"]) == ("2026-11-03T10:00:00+00:00", "Q", "Soft")
    assert ligne["secteurs_meilleur"] == [33.1, 33.7, 33.0]
    # Les meilleurs secteurs de toutes les séances, et le tour idéal qu'ils font.
    assert ligne["meilleurs_secteurs"] == [32.9, 33.7, 33.0]
    assert ligne["tour_ideal"] == pytest.approx(99.6)
    # Le temps moyen de chaque séance pèse ses tours : (101 × 5 + 100 × 15) / 20.
    assert ligne["temps_moyen"] == pytest.approx(100.25)
    assert ligne["vitesse_max"] == 262.0
    assert ligne["gommes"] == {"Medium": 12, "Soft": 3}
    assert (ligne["seances"], ligne["tours"]) == (3, 15)
    json.dumps(ligne)


def test_l_ecart_se_prend_sur_la_reference_de_la_categorie() -> None:
    perfs = [perf(meilleur_tour=100.3, voiture=FERRARI), perf(pilote="Ami", meilleur_tour=99.5)]
    # Filtrée sur la Ferrari, la ligne garde son écart avec le meilleur GT3 du tracé.
    (gt3,) = lb.classement_tours(perfs, lb.Filtres(trace=MONZA, voiture=FERRARI))
    assert gt3["reference"] == 99.5
    assert [(l["pilote"], l["ecart"]) for l in gt3["lignes"]] == [("Moi", 0.8)]
    # De même filtrée sur un pilote.
    (gt3,) = lb.classement_tours(perfs, lb.Filtres(trace=MONZA, pilote="Moi"))
    assert [(l["pilote"], l["ecart"]) for l in gt3["lignes"]] == [("Moi", 0.8)]


def test_sans_trace_pas_de_meilleurs_tours() -> None:
    assert lb.classement_tours([perf()], lb.Filtres()) == []


@pytest.mark.parametrize(
    ("classe", "famille"),
    [("GT3", "GT3"), ("LMP2_ELMS", "LMP2"), ("LMP2", "LMP2"), ("Hyper", "HYPER"), ("Formule", "Formule")],
)
def test_les_familles_de_categories(classe: str, famille: str) -> None:
    assert lb.famille(classe) == famille


def test_les_variantes_d_une_categorie_se_comparent_ensemble() -> None:
    perfs = [perf(classe="LMP2_ELMS", meilleur_tour=97.0), perf(pilote="Ami", classe="LMP2", meilleur_tour=98.0)]
    (lmp2,) = lb.classement_tours(perfs, lb.Filtres(trace=MONZA, classe="LMP2"))
    assert lmp2["classe"] == "LMP2"
    assert [l["pilote"] for l in lmp2["lignes"]] == ["Moi", "Ami"]


# ----------------------------------------------------------------------
# Les courses : le bilan, et les dernières
# ----------------------------------------------------------------------


def test_le_bilan_des_courses() -> None:
    perfs = [
        course("Moi", 4), course("Moi", 1, statut="abandon", heure=14),
        course("Ami", 2), course("Ami", 3, heure=13),
        course("Rival", 1), course("Rival", 9, heure=13),
        perf(pilote="Ami"),  # des essais : ni course, ni place
    ]
    lignes = lb.classement_courses(perfs, lb.Filtres(), {"Moi"})
    # Les plus victorieux d'abord, puis les podiums, puis la place moyenne.
    assert [(l["pilote"], l["victoires"], l["podiums"], l["place_moyenne"]) for l in lignes] == [
        ("Rival", 1, 1, 5.0),
        ("Ami", 0, 2, 2.5),
        ("Moi", 0, 0, 4.0),
    ]
    assert (lignes[2]["moi"], lignes[2]["abandons"]) == (True, 1)
    assert lignes[1]["tours"] == 30  # les essais comptent dans les tours au total


def test_les_dernieres_courses() -> None:
    perfs = [
        course("Moi", 3, heure=10, grille_classe=5, engages_classe=12),
        course("Ami", 1, heure=11, trace=SPA, circuit=SPA, classe="LMP2_ELMS", voiture="Oreca 07"),
        course("Moi", 2, heure=12, statut="abandon"),
        perf(date="2026-11-02T13:00:00+00:00"),  # des essais : pas une course
    ]
    h = lb.historique(perfs, lb.Filtres(), {"Moi"})
    assert h["total"] == 3
    # La plus récente d'abord, tous circuits et catégories mêlés : chacune dit les siens.
    assert [(l["pilote"], l["trace"], l["classe"], l["statut"]) for l in h["lignes"]] == [
        ("Moi", MONZA, "GT3", "abandon"),
        ("Ami", SPA, "LMP2", "arrivee"),
        ("Moi", MONZA, "GT3", "arrivee"),
    ]
    derniere = h["lignes"][2]
    assert (derniere["moi"], derniere["grille"], derniere["place"], derniere["engages"]) == (True, 5, 3, 12)
    assert (derniere["voiture"], derniere["meilleur_tour"], derniere["tours"]) == (PORSCHE, 100.0, 10)
    # Une page à la fois, et les filtres s'appliquent.
    assert [l["pilote"] for l in lb.historique(perfs, lb.Filtres(), limite=1)["lignes"]] == ["Moi"]
    assert lb.historique(perfs, lb.Filtres(classe="LMP2"))["total"] == 1
    assert lb.historique(perfs, lb.Filtres(trace=MONZA, pilote="Moi"))["total"] == 2


# ----------------------------------------------------------------------
# Le menu des circuits, les filtres, la réponse entière
# ----------------------------------------------------------------------


def test_le_menu_des_circuits() -> None:
    perfs = [
        perf(),
        perf(date="2026-11-03T10:00:00+00:00", classe="Hyper", voiture="Ferrari 499P", meilleur_tour=90.0),
        course("Ami", 1, meilleur_tour=99.0),
        perf(trace=CURVA_GRANDE, meilleur_tour=95.0, date="2026-11-04T10:00:00+00:00"),
        perf(trace=SPA, circuit=SPA, meilleur_tour=None),
    ]
    monza, spa = lb.menu_circuits(perfs)
    assert (monza["circuit"], monza["seances"], monza["courses"], monza["derniere"]) == (
        MONZA, 4, 1, "2026-11-04T10:00:00+00:00",
    )
    # Les tracés d'un circuit, le plus roulé d'abord, avec leurs pilotes, leurs voitures, leurs
    # tours et le meilleur tour de chaque catégorie.
    assert [(x["nom"], x["seances"], x["courses"]) for x in monza["traces"]] == [(MONZA, 3, 1), (CURVA_GRANDE, 1, 0)]
    principal = monza["traces"][0]
    assert (principal["pilotes"], principal["voitures"], principal["tours"]) == (2, 2, 30)
    assert principal["meilleurs"] == [
        {"classe": "HYPER", "chrono": 90.0},
        {"classe": "GT3", "chrono": 99.0},
    ]
    assert (spa["circuit"], spa["traces"][0]["meilleurs"]) == (SPA, [])


def test_le_menu_des_pilotes() -> None:
    perfs = [
        course("Moi", 1), course("Moi", 3, heure=13), perf(classe="LMP3", voiture="Ligier JS P325"),
        perf(pilote="Ami", classe="LMP3", voiture="Ligier JS P325", date="2026-11-05T10:00:00+00:00"),
        perf(pilote="Ami", classe="LMP3", voiture="Ligier JS P325"),
        perf(pilote="Ami", classe="Hyper", voiture="Ferrari 499P"),
    ]
    ami, moi = lb.menu_pilotes(perfs, {"Moi"})
    assert (moi["pilote"], moi["moi"], moi["seances"], moi["courses"], moi["victoires"], moi["podiums"]) == (
        "Moi", True, 3, 2, 1, 2,
    )
    # Les catégories roulées, la plus roulée d'abord.
    assert (moi["classes"], ami["classes"]) == (["GT3", "LMP3"], ["LMP3", "HYPER"])
    assert (ami["moi"], ami["courses"], ami["derniere"]) == (False, 0, "2026-11-05T10:00:00+00:00")


# ----------------------------------------------------------------------
# Les voitures d'un circuit, la fiche d'un pilote
# ----------------------------------------------------------------------


def test_les_voitures_d_un_circuit() -> None:
    perfs = [
        perf(meilleur_tour=100.2, temps_moyen=101.0, tours_moyenne=5, tours=10),
        perf(pilote="Ami", meilleur_tour=100.1, temps_moyen=102.0, tours_moyenne=15, tours=20, gomme_meilleur="Soft"),
        perf(voiture=FERRARI, marque="Ferrari", meilleur_tour=99.9),
        perf(classe="LMP3", voiture="Ligier JS P325", marque="Ligier", meilleur_tour=95.0),
        perf(voiture="BMW M4 LMGT3", meilleur_tour=None),  # pas de tour chronométré
    ]
    lmp3, gt3 = lb.classement_voitures(perfs, lb.Filtres(trace=MONZA), {"Moi"})
    assert (lmp3["classe"], gt3["classe"], gt3["reference"]) == ("LMP3", "GT3", 99.9)
    # Une ligne par voiture, la plus rapide d'abord, avec le meilleur tour et son auteur.
    assert [(l["place"], l["voiture"], l["meilleur_tour"], l["ecart"], l["pilote"], l["moi"]) for l in gt3["lignes"]] == [
        (1, FERRARI, 99.9, 0.0, "Moi", True),
        (2, PORSCHE, 100.1, 0.2, "Ami", False),
    ]
    porsche = gt3["lignes"][1]
    assert (porsche["pilotes"], porsche["seances"], porsche["tours"], porsche["gomme_meilleur"]) == (2, 2, 30, "Soft")
    # Le temps moyen de tous les pilotes à son volant : (101 × 5 + 102 × 15) / 20.
    assert porsche["temps_moyen"] == pytest.approx(101.75)
    # Filtrée sur un pilote, chaque voiture garde son écart avec la référence de la catégorie.
    (gt3,) = lb.classement_voitures(perfs, lb.Filtres(trace=MONZA, pilote="Ami"))
    assert [(l["voiture"], l["ecart"]) for l in gt3["lignes"]] == [(PORSCHE, 0.2)]
    assert lb.classement_voitures(perfs, lb.Filtres()) == []


def test_la_fiche_d_un_pilote() -> None:
    perfs = [
        perf(date="2026-10-01T10:00:00+00:00"),
        perf(voiture=FERRARI, marque="Ferrari", meilleur_tour=100.4),
        course("Moi", 1, heure=12, meilleur_tour=99.8),
        course("Moi", 3, heure=13, trace=SPA, circuit=SPA, meilleur_tour=130.0),
        perf(classe="LMP3", voiture="Ligier JS P325", marque="Ligier", meilleur_tour=95.0),
        perf(pilote="Ami", meilleur_tour=99.5),
        perf(pilote="Rival", meilleur_tour=99.9, voiture=FERRARI),
    ]
    fiche = lb.fiche_pilote(perfs, lb.Filtres(pilote="Moi"), {"Moi"})
    assert (fiche["pilote"], fiche["moi"], fiche["seances"]) == ("Moi", True, 5)
    assert (fiche["depuis"], fiche["derniere"]) == ("2026-10-01T10:00:00+00:00", "2026-11-02T13:00:00+00:00")
    assert (fiche["bilan"]["courses"], fiche["bilan"]["victoires"], fiche["bilan"]["podiums"]) == (2, 1, 2)
    assert fiche["circuit_favori"] == {"circuit": MONZA, "seances": 4}
    assert fiche["voiture_favorite"] == {"voiture": PORSCHE, "marque": "Porsche", "seances": 3}
    assert [(c["classe"], c["seances"], c["courses"]) for c in fiche["categories"]] == [("LMP3", 1, 0), ("GT3", 4, 2)]
    # Un record par tracé et par catégorie, avec sa place parmi les meilleurs tours du groupe.
    assert [(r["trace"], r["classe"], r["meilleur_tour"], r["rang"], r["pilotes"], r["ecart"]) for r in fiche["records"]] == [
        (MONZA, "LMP3", 95.0, 1, 1, 0.0),
        (MONZA, "GT3", 99.8, 2, 3, pytest.approx(0.3)),
        (SPA, "GT3", 130.0, 1, 1, 0.0),
    ]
    gt3 = fiche["records"][1]
    assert (gt3["voiture"], gt3["type"], gt3["seances"], gt3["reference"]) == (PORSCHE, "R", 3, 99.5)


def test_un_record_dans_une_voiture_se_compare_a_toutes() -> None:
    perfs = [
        perf(meilleur_tour=99.8),
        perf(voiture=FERRARI, marque="Ferrari", meilleur_tour=100.4),
        perf(pilote="Ami", meilleur_tour=100.0),
    ]
    (record,) = lb.records_personnels(perfs, lb.Filtres(pilote="Moi", voiture=FERRARI))
    # Dans la Ferrari, il est derrière l'ami ; la référence reste son propre tour en Porsche.
    assert (record["voiture"], record["meilleur_tour"], record["rang"], record["pilotes"]) == (FERRARI, 100.4, 2, 2)
    assert (record["reference"], record["ecart"]) == (99.8, pytest.approx(0.6))


def test_ce_que_proposent_les_filtres() -> None:
    perfs = [
        perf(trace=SPA, circuit=SPA, classe="LMP3", voiture="Ligier JS P325"),
        perf(),
        perf(classe="Hyper", voiture="Ferrari 499P", marque="Ferrari"),
        perf(pilote="Ami", voiture=FERRARI, marque="Ferrari"),
    ]
    o = lb.options(perfs, lb.Filtres(trace=MONZA, classe="GT3"))
    assert o["classes"] == ["HYPER", "GT3"]  # celles du tracé, de la plus rapide à la plus lente
    assert o["voitures"] == [FERRARI, PORSCHE]  # celles de la catégorie choisie
    assert o["pilotes"] == ["Ami", "Moi"]
    # Sans tracé : celles de tous les circuits.
    assert lb.options(perfs, lb.Filtres())["classes"] == ["HYPER", "LMP3", "GT3"]


def test_les_filtres_d_une_demande() -> None:
    perfs = [perf(), perf(classe="LMP3", voiture="Ligier JS P325", trace=SPA, circuit=SPA)]
    # Sans tracé, ou un tracé inconnu : les dernières courses de tous les circuits.
    assert lb.filtres_demandes(perfs, {}) == lb.Filtres()
    assert lb.filtres_demandes(perfs, {"trace": "Inconnu"}).trace is None
    assert lb.filtres_demandes(perfs, {"trace": SPA}).trace == SPA
    # Une catégorie absente du tracé, une voiture absente de la catégorie : sans objet.
    assert lb.filtres_demandes(perfs, {"trace": MONZA, "classe": "LMP3"}).classe is None
    f = lb.filtres_demandes(perfs, {"trace": SPA, "classe": "LMP3", "voiture": PORSCHE, "pilote": "Moi"})
    assert (f.classe, f.voiture, f.pilote) == ("LMP3", None, "Moi")
    assert lb.filtres_demandes(perfs, {"pilote": "Inconnu"}).pilote is None


def test_seules_les_seances_en_ligne_comptent() -> None:
    perfs = [
        course("Moi", 1, en_ligne=False),  # contre l'IA
        perf(trace=SPA, circuit=SPA, en_ligne=False, meilleur_tour=90.0),
        course("Moi", 4, heure=13),
        perf(meilleur_tour=101.0),
    ]
    r = lb.leaderboard_json(perfs, {"trace": MONZA}, {"Moi"})
    assert [c["circuit"] for c in r["circuits"]] == [MONZA]  # Spa n'a été roulé que contre l'IA
    assert r["historique"]["total"] == 1
    assert [(l["courses"], l["victoires"]) for l in r["courses"]] == [(1, 0)]
    assert r["tours"][0]["reference"] == 100.0
    assert lb.leaderboard_json(perfs, {"trace": SPA})["filtres"]["trace"] is None


def test_les_essais_ne_comptent_pas() -> None:
    perfs = [
        perf(type="P", meilleur_tour=98.0, id="essais"),  # plus rapide, mais en essais
        perf(meilleur_tour=100.0),  # en qualifs
        course("Moi", 2, meilleur_tour=101.0),
        perf(type="P", trace=SPA, circuit=SPA, id="essais-spa"),  # Spa n'a vu que des essais
    ]
    r = lb.leaderboard_json(perfs, {"trace": MONZA}, {"Moi"})
    assert r["tours"][0]["reference"] == 100.0
    assert [c["circuit"] for c in r["circuits"]] == [MONZA]
    assert (r["circuits"][0]["seances"], r["pilotes"][0]["seances"]) == (2, 2)
    assert lb.comptee(perf()) and not lb.comptee(perf(type="P")) and not lb.comptee(perf(en_ligne=False))


def test_une_seance_sans_aucun_tour_ne_compte_pas() -> None:
    """Vu le 2026-11-14 : une qualif en Hypercar où l'on n'avait bouclé aucun tour faisait
    apparaître la catégorie sur la fiche. Une course quittée avant la fin du premier tour compte
    encore, comme un abandon (choisi le même jour)."""
    sans_tour = {"tours": 0, "tours_chronometres": 0, "meilleur_tour": None, "tour_meilleur": None}
    perfs = [
        perf(),
        perf(id="1-Q", classe="Hyper", voiture="Peugeot 9x8", marque="Peugeot", **sans_tour),
        course("Moi", None, statut="abandon", id="2-R", heure=13, **sans_tour),
        course("Moi", None, statut=None, id="3-R", heure=14, **sans_tour),  # ni arrivée, ni abandon
    ]
    r = lb.leaderboard_json(perfs, {}, {"Moi"})
    assert r["pilotes"][0]["classes"] == ["GT3"]
    assert [c["id"] for c in r["historique"]["lignes"]] == ["2-R"]
    assert (r["courses"][0]["courses"], r["courses"][0]["abandons"]) == (1, 1)
    assert r["pilotes"][0]["seances"] == 2


def test_la_page_des_dernieres_courses_s_allonge() -> None:
    perfs = [course("Moi", 1, heure=h) for h in range(10, 15)]
    assert len(lb.leaderboard_json(perfs, {})["historique"]["lignes"]) == 5
    assert len(lb.leaderboard_json(perfs, {"historique": "2"})["historique"]["lignes"]) == 2
    assert len(lb.leaderboard_json(perfs, {"historique": "0"})["historique"]["lignes"]) == 1
    assert len(lb.leaderboard_json(perfs, {"historique": "beaucoup"})["historique"]["lignes"]) == 5


def test_la_page_demandee() -> None:
    perfs = [
        perf(),
        perf(pilote="Ami", classe="LMP3", voiture="Ligier JS P325", trace=SPA, circuit=SPA),
        course("Ami", 2, trace=SPA, circuit=SPA, classe="LMP3", voiture="Ligier JS P325"),
    ]
    assert lb.leaderboard_json(perfs, {})["vue"] == "historique"
    assert lb.leaderboard_json(perfs, {"trace": MONZA})["vue"] == "circuit"
    # La fiche d'un pilote : le filtre de pilote est le sien, les listes proposent ses catégories.
    r = lb.leaderboard_json(perfs, {"profil": "Ami", "pilote": "Moi", "classe": "GT3"})
    assert (r["vue"], r["filtres"]["pilote"], r["filtres"]["classe"]) == ("pilote", "Ami", None)
    assert (r["options"]["classes"], r["options"]["pilotes"]) == (["LMP3"], ["Ami"])
    assert (r["profil"]["pilote"], r["historique"]["total"], r["tours"]) == ("Ami", 1, [])
    # Un pilote inconnu ramène aux dernières courses ; un tracé l'emporte sur un pilote.
    assert lb.leaderboard_json(perfs, {"profil": "Inconnu"})["vue"] == "historique"
    r = lb.leaderboard_json(perfs, {"profil": "Ami", "trace": MONZA})
    assert (r["vue"], r["profil"]) == ("circuit", None)


def test_le_leaderboard_passe_en_json() -> None:
    r = lb.leaderboard_json([perf(), course("Moi", 1)], {"trace": MONZA}, {"Moi"})
    assert set(r) == {
        "vue", "filtres", "options", "circuits", "pilotes", "historique", "tours", "voitures", "courses", "profil",
    }
    assert r["filtres"] == {"trace": MONZA, "classe": None, "voiture": None, "pilote": None}
    json.dumps(r)
    json.dumps(lb.leaderboard_json([perf(), course("Moi", 1)], {"profil": "Moi"}, {"Moi"}))


def test_sans_performance_un_leaderboard_vide() -> None:
    r = lb.leaderboard_json([], {})
    assert (r["vue"], r["filtres"]["trace"], r["profil"]) == ("historique", None, None)
    assert (r["circuits"], r["pilotes"], r["tours"], r["voitures"], r["courses"]) == ([], [], [], [], [])
    assert r["historique"] == {"total": 0, "lignes": []}


# ----------------------------------------------------------------------
# La route
# ----------------------------------------------------------------------


def test_la_route_du_leaderboard(jeu: Path) -> None:  # noqa: F811
    # La séance d'essais du dossier est jouée seule : elle dit le nom du propriétaire, mais
    # ne compte pas. On ajoute une course en ligne, où il n'est pas le seul joueur.
    (jeu.parent.parent / "Log" / "Results" / "course-02R1.xml").write_text(
        seance_xml("Race", T0, [
            pilote("Ami", "B #2", "GT3", 1, 1, [tour(1, 1, "99.0000")] * 3, joueur=True),
            pilote("Moi", "A #1", "GT3", 2, 2, [tour(1, 2, "100.5000")] * 3, joueur=True, grille_classe=1),
        ], setting="Multiplayer"),
        encoding="utf-8",
    )
    instance = serveur.creer_serveur(0, jeu.parent)
    threading.Thread(target=instance.serve_forever, daemon=True).start()

    def demander(**params) -> dict:
        adresse = f"http://127.0.0.1:{instance.server_address[1]}/api/leaderboard"
        with urllib.request.urlopen(adresse + "?" + urllib.parse.urlencode(params)) as reponse:
            return json.loads(reponse.read())

    try:
        r = demander()
        monza = demander(trace=MONZA)
        fiche = demander(profil="Moi")
    finally:
        instance.shutdown()
        instance.server_close()
    assert r["resultats"] is True
    # Le menu : le circuit de la course, avec son drapeau.
    (circuit,) = r["circuits"]
    assert (circuit["circuit"], circuit["courses"], circuit["pays"]["code"]) == (MONZA, 1, "IT")
    # Les dernières courses : seulement celles du propriétaire, jamais celles des autres joueurs.
    assert [(l["pilote"], l["place"], l["grille"]) for l in r["historique"]["lignes"]] == [("Moi", 2, 1)]
    (gt3,) = monza["tours"]
    assert [(l["pilote"], l["moi"]) for l in gt3["lignes"]] == [("Moi", True)]
    assert [l["voiture"] for l in monza["voitures"][0]["lignes"]] == ["Porsche 911 GT3 R LMGT3"]
    # La fiche du propriétaire : le seul pilote de ses fichiers.
    assert [p["pilote"] for p in r["pilotes"]] == ["Moi"]
    assert (fiche["vue"], fiche["profil"]["bilan"]["courses"], len(fiche["profil"]["records"])) == ("pilote", 1, 1)


def test_sans_dossier_de_resultats(tmp_path: Path) -> None:
    telemetrie = tmp_path / "Telemetry"
    telemetrie.mkdir()
    r = reponses.leaderboard(reponses.Contexte(dossier=telemetrie), {})
    assert r["resultats"] is False
    assert (r["circuits"], r["tours"]) == ([], [])
