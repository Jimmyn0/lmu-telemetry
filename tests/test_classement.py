"""Le classement d'une séance : le fichier de résultats lu en entier, relié à la session
de télémétrie qui l'a enregistrée, et mis en forme pour l'écran Résultats.

Les fichiers sont fabriqués ici, à l'image de ceux du jeu (voir `sources/resultats.py`).
"""

from __future__ import annotations

import json
import shutil
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lmu_telemetry.domaine.classement import classement_json, ecart, incidents, statistiques
from lmu_telemetry.sources import resultats
from lmu_telemetry.sources.reader import FichierSession
from lmu_telemetry.web import reponses, serveur

T0 = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)


def seance_xml(bloc: str, debut: datetime, pilotes: list[str], circuit: str = "Autodromo Nazionale Monza",
               minutes: int = 10, tours: int = 2147483647, journal: str = "",
               setting: str = "Race Weekend") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rFactorXML version="1.0">
<RaceResults>
<Setting>{setting}</Setting>
<TrackVenue>{circuit}</TrackVenue>
<TrackCourse>{circuit}</TrackCourse>
<TrackLength>5780.6</TrackLength>
<{bloc}>
<DateTime>{int(debut.timestamp())}</DateTime>
<Laps>{tours}</Laps>
<Minutes>{minutes}</Minutes>
{"".join(pilotes)}
<Stream>
{journal}
</Stream>
</{bloc}>
</RaceResults>
</rFactorXML>
"""


def tour(num: int, p: int, chrono: str, secteurs=(None, None, None), *, pit: bool = False,
         gomme: str = "0,Medium", vmax: str = "250.0") -> str:
    attributs = f'num="{num}" p="{p}" et="{num * 100}.0" topspeed="{vmax}" fcompound="{gomme}"'
    for i, valeur in enumerate(secteurs, start=1):
        if valeur is not None:
            attributs += f' s{i}="{valeur}"'
    if pit:
        attributs += ' pit="1"'
    return f"<Lap {attributs}>{chrono}</Lap>\n"


def pilote(nom: str, engagement: str, classe: str, place: int, place_classe: int, tours: list[str], *,
           joueur: bool = False, meilleur: str = "", total: str = "", statut: str = "Finished Normally",
           numero: str = "1", modele: str = "Porsche 911 GT3 R LMGT3", arrets: int = 0,
           grille: int | None = None, grille_classe: int | None = None) -> str:
    return f"""<Driver>
<Name>{nom}</Name>
<VehName>{engagement}</VehName>
<CarType>{modele}</CarType>
<CarClass>{classe}</CarClass>
<CarNumber>{numero}</CarNumber>
<TeamName>Équipe {nom}</TeamName>
<isPlayer>{1 if joueur else 0}</isPlayer>
<GridPos>{grille or place}</GridPos>
<Position>{place}</Position>
<ClassGridPos>{grille_classe or place_classe}</ClassGridPos>
<ClassPosition>{place_classe}</ClassPosition>
<BestLapTime>{meilleur}</BestLapTime>
<FinishTime>{total}</FinishTime>
<Laps>{len(tours)}</Laps>
<Pitstops>{arrets}</Pitstops>
<FinishStatus>{statut}</FinishStatus>
{"".join(tours)}</Driver>
"""


def course_xml() -> str:
    """Un Hypercar en tête, le joueur premier des GT3, une GT3 qui abandonne au premier tour."""
    return seance_xml("Race", T0, [
        pilote("Alice", "Cadillac #12:WEC", "Hyper", 1, 1, [
            tour(1, 1, "100.0000", (33.0, 33.0, 34.0)),
            tour(2, 1, "98.0000", (32.5, 33.0, 32.5)),
        ], meilleur="98.0000", total="198.0000", numero="12", modele="Cadillac V-Series.R"),
        pilote("Bruno", "Mercedes #61:WEC", "GT3", 2, 1, [
            tour(1, 2, "115.0000", (38.0, 39.0, 38.0)),
            tour(2, 2, "--.----", (37.5, None, None), gomme="0,Soft"),
        ], joueur=True, meilleur="115.0000", total="230.0000", numero="61", modele="Mercedes-AMG LMGT3"),
        pilote("Chloé", "Corvette #82:WEC", "GT3", 3, 2, [
            tour(1, 3, "117.0000", (39.0, 39.0, 39.0), pit=True, gomme="15,N/A"),
        ], meilleur="117.0000", statut="DNF", numero="82", modele="Chevrolet Corvette Z06 GT3.R"),
    ])


# ----------------------------------------------------------------------
# Lire une séance
# ----------------------------------------------------------------------


def test_une_seance_se_lit_en_entier(tmp_path: Path) -> None:
    fichier = tmp_path / "course-02R1.xml"
    fichier.write_text(course_xml(), encoding="utf-8")
    seance = resultats.lire_session(fichier)
    assert (seance.type, seance.circuit, seance.minutes, seance.tours_prevus) == (
        "R", "Autodromo Nazionale Monza", 10, None,
    )
    assert seance.debut == T0
    assert [e.nom for e in seance.engages] == ["Alice", "Bruno", "Chloé"]
    bruno = seance.engages[1]
    assert (bruno.numero, bruno.marque, bruno.equipe, bruno.joueur) == ("61", "Mercedes", "Équipe Bruno", True)
    # Un tour sans temps garde ce que le jeu a écrit : le premier secteur, la gomme.
    assert bruno.tours_detail[1].chrono is None
    assert bruno.tours_detail[1].secteurs == (37.5, None, None)
    assert bruno.tours_detail[1].gomme == "Soft"
    chloe = seance.engages[2]
    assert (chloe.statut, chloe.temps_total) == ("DNF", None)
    assert chloe.tours_detail[0].stands
    assert chloe.tours_detail[0].gomme is None  # « 15,N/A »


def test_un_fichier_illisible_ne_donne_pas_de_seance(tmp_path: Path) -> None:
    fichier = tmp_path / "abime-01P1.xml"
    fichier.write_text("<rFactorXML><RaceResults>", encoding="utf-8")
    assert resultats.lire_session(fichier) is None
    assert resultats.lire_session(tmp_path / "absent.xml") is None


# ----------------------------------------------------------------------
# Relier une session de télémétrie à sa séance
# ----------------------------------------------------------------------


@pytest.fixture
def dossier_seances(tmp_path: Path) -> Path:
    dossier = tmp_path / "Results"
    dossier.mkdir()
    joueur = [pilote("Moi", "A #1", "GT3", 1, 1, [], joueur=True)]
    for nom, bloc, debut, minutes, circuit in (
        ("p1-01P1.xml", "Practice1", T0, 30, "Autodromo Nazionale Monza"),
        ("p2-02P1.xml", "Practice1", T0 + timedelta(hours=1), 30, "Autodromo Nazionale Monza"),
        ("r-03R1.xml", "Race", T0 + timedelta(hours=2), 10, "Autodromo Nazionale Monza"),
        ("spa-04P1.xml", "Practice1", T0 + timedelta(hours=1), 30, "Circuit de Spa-Francorchamps"),
    ):
        (dossier / nom).write_text(seance_xml(bloc, debut, joueur, circuit, minutes), encoding="utf-8")
    return dossier


def trouver(dossier: Path, type_: str, apres: timedelta, voiture: str = "A #1",
            circuit: str = "Autodromo Nazionale Monza") -> str | None:
    fichier = resultats.trouver_session(circuit, type_, T0 + apres, voiture, dossier)
    return fichier.name if fichier else None


def test_la_seance_est_la_derniere_commencee_avant_la_sortie(dossier_seances: Path) -> None:
    assert trouver(dossier_seances, "P", timedelta(minutes=10)) == "p1-01P1.xml"
    # Sorti du garage un quart d'heure après le début de la deuxième séance.
    assert trouver(dossier_seances, "P", timedelta(hours=1, minutes=15)) == "p2-02P1.xml"
    assert trouver(dossier_seances, "P", timedelta(hours=1), circuit="Circuit de Spa-Francorchamps") == (
        "spa-04P1.xml"
    )


def test_la_telemetrie_peut_commencer_juste_avant_le_depart(dossier_seances: Path) -> None:
    assert trouver(dossier_seances, "R", timedelta(hours=2, seconds=-90)) == "r-03R1.xml"
    assert trouver(dossier_seances, "R", timedelta(hours=2, seconds=30)) == "r-03R1.xml"


def test_pas_de_seance_d_un_autre_type_ni_d_avant(dossier_seances: Path) -> None:
    assert trouver(dossier_seances, "Q", timedelta(hours=1)) is None
    assert trouver(dossier_seances, "P", timedelta(minutes=-30)) is None


def test_bien_apres_la_seance_il_faut_y_retrouver_sa_voiture(dossier_seances: Path) -> None:
    apres = timedelta(hours=1, minutes=55)  # la deuxième séance a fini depuis 25 min
    assert trouver(dossier_seances, "P", apres, voiture="A #1") == "p2-02P1.xml"
    assert trouver(dossier_seances, "P", apres, voiture="B #2") is None


# ----------------------------------------------------------------------
# Le classement pour l'écran
# ----------------------------------------------------------------------


def classement(tmp_path: Path, xml: str) -> dict:
    fichier = tmp_path / "seance.xml"
    fichier.write_text(xml, encoding="utf-8")
    return classement_json(resultats.lire_session(fichier))


def test_les_ecarts_au_general_et_dans_la_categorie(tmp_path: Path) -> None:
    r = classement(tmp_path, course_xml())
    alice, bruno, chloe = r["engages"]
    assert r["categories"] == ["Hyper", "GT3"]
    assert alice["ecart"] is None
    assert bruno["ecart"] == {"temps": 32.0}
    assert bruno["ecart_categorie"] is None  # premier des GT3
    assert chloe["ecart"] == {"tours": 1}
    assert chloe["ecart_categorie"] == {"tours": 1}


def test_ce_que_l_ecran_montre_de_chaque_voiture(tmp_path: Path) -> None:
    _alice, bruno, chloe = classement(tmp_path, course_xml())["engages"]
    assert (bruno["tour_meilleur"], bruno["secteurs_meilleur"]) == (1, [38.0, 39.0, 38.0])
    assert bruno["gomme"] == "Soft"  # en course, celle de l'arrivée
    assert (bruno["statut"], chloe["statut"]) == ("arrivee", "abandon")
    assert bruno["vitesse_max"] == 250.0
    # Au premier tour, les deux GT3 se classent entre elles ; au deuxième, Bruno est seul.
    assert [x["place_categorie"] for x in bruno["tours_detail"]] == [1, 1]
    assert [x["place_categorie"] for x in chloe["tours_detail"]] == [2]
    assert chloe["tours_detail"][0]["stands"] is True


def test_en_qualifications_l_ecart_est_celui_du_meilleur_tour(tmp_path: Path) -> None:
    xml = seance_xml("Qualify", T0, [
        pilote("Alice", "A #1", "GT3", 1, 1, [
            tour(1, 1, "116.5000", gomme="0,Medium"),
            tour(2, 1, "115.2000", (38.1, 39.0, 38.1), gomme="0,Soft"),
            tour(3, 1, "117.0000", gomme="0,Medium"),
        ], meilleur="115.2000", statut="None"),
        pilote("Bruno", "B #2", "GT3", 2, 2, [tour(1, 2, "115.6000")], meilleur="115.6000", statut="None"),
        pilote("Chloé", "C #3", "GT3", 3, 3, [tour(1, 3, "--.----")], statut="None"),
    ])
    alice, bruno, chloe = classement(tmp_path, xml)["engages"]
    assert bruno["ecart"]["temps"] == pytest.approx(0.4)
    assert chloe["ecart"] is None  # pas de temps
    assert alice["gomme"] == "Soft"  # celle du meilleur tour
    assert alice["statut"] is None


def test_toi_c_est_le_pilote_de_la_telemetrie(tmp_path: Path) -> None:
    # En multijoueur, le jeu marque tous les humains comme joueurs.
    xml = seance_xml("Race", T0, [
        pilote(nom, "Iron Lynx #61:LM", "GT3", place, place, [tour(1, place, "115.0000")], joueur=True)
        for place, nom in enumerate(("Alice", "Bruno", "Chloé"), start=1)
    ])
    fichier = tmp_path / "en-ligne.xml"
    fichier.write_text(xml, encoding="utf-8")
    seance = resultats.lire_session(fichier)
    assert [e["joueur"] for e in classement_json(seance, "Bruno")["engages"]] == [False, True, False]
    # Sans le nom, personne : mieux vaut ne désigner personne que le mauvais.
    assert not any(e["joueur"] for e in classement_json(seance, None)["engages"])


def test_hors_ligne_le_marquage_du_jeu_suffit(tmp_path: Path) -> None:
    joueurs = [e["joueur"] for e in classement(tmp_path, course_xml())["engages"]]
    assert joueurs == [False, True, False]


def test_l_ecart_d_une_voiture_sur_elle_meme_est_nul(tmp_path: Path) -> None:
    fichier = tmp_path / "seance.xml"
    fichier.write_text(course_xml(), encoding="utf-8")
    alice = resultats.lire_session(fichier).engages[0]
    assert ecart(alice, alice, course=True) is None
    assert ecart(alice, None, course=True) is None


# ----------------------------------------------------------------------
# Les statistiques de chaque catégorie
# ----------------------------------------------------------------------


def stats(tmp_path: Path, xml: str) -> list[dict]:
    fichier = tmp_path / "stats.xml"
    fichier.write_text(xml, encoding="utf-8")
    return statistiques(resultats.lire_session(fichier))


def test_les_records_de_chaque_categorie(tmp_path: Path) -> None:
    hyper, gt3 = stats(tmp_path, course_xml())
    assert (hyper["categorie"], hyper["voitures"], gt3["voitures"]) == ("Hyper", 1, 2)
    assert hyper["meilleur_tour"] == {"temps": 98.0, "rang": 0, "tour": 2}
    assert hyper["secteurs"][0] == {"temps": 32.5, "rang": 0, "tour": 2}
    assert gt3["meilleur_tour"] == {"temps": 115.0, "rang": 1, "tour": 1}
    # Le premier secteur en 37.5 vient d'un tour sans temps : il ne compte pas.
    assert gt3["secteurs"][0] == {"temps": 38.0, "rang": 1, "tour": 1}


def test_la_regularite_ecarte_le_depart_les_stands_et_les_incidents(tmp_path: Path) -> None:
    regulier = [
        tour(1, 1, "130.0000"),  # le départ
        tour(2, 1, "100.0000"),
        tour(3, 1, "100.4000"),
        tour(4, 1, "160.0000", pit=True),  # entrée aux stands
        tour(5, 1, "125.0000"),  # sortie des stands
        tour(6, 1, "99.8000"),
        tour(7, 1, "120.0000"),  # une sortie de piste : à plus de 7 %
        tour(8, 1, "100.2000"),
    ]
    trop_court = [tour(1, 2, "131.0000"), tour(2, 2, "100.0000"), tour(3, 2, "100.0000")]
    (gt3,) = stats(tmp_path, seance_xml("Race", T0, [
        pilote("Alice", "A #1", "GT3", 1, 1, regulier, meilleur="99.8000"),
        pilote("Bruno", "B #2", "GT3", 2, 2, trop_court, meilleur="100.0000"),
    ]))
    assert gt3["regularite"]["rang"] == 0
    assert gt3["regularite"]["tours"] == 4
    assert gt3["regularite"]["ecart_type"] == pytest.approx(0.2236, abs=1e-4)


def test_les_places_gagnees_et_perdues_dans_la_categorie(tmp_path: Path) -> None:
    (gt3,) = stats(tmp_path, seance_xml("Race", T0, [
        pilote("Alice", "A #1", "GT3", 1, 1, [], grille=3, grille_classe=3),
        pilote("Bruno", "B #2", "GT3", 2, 2, [], grille=2, grille_classe=2),
        pilote("Chloé", "C #3", "GT3", 3, 3, [], grille=1, grille_classe=1),
    ]))
    assert gt3["gagnees"] == {"rang": 0, "places": 2}
    assert gt3["perdues"] == {"rang": 2, "places": 2}
    # Personne n'a bougé : rien à dire.
    hyper, _gt3 = stats(tmp_path, course_xml())
    assert hyper["gagnees"] is None and hyper["perdues"] is None


def test_la_gomme_la_plus_utilisee(tmp_path: Path) -> None:
    (gt3,) = stats(tmp_path, seance_xml("Race", T0, [
        pilote("Alice", "A #1", "GT3", 1, 1, [
            tour(1, 1, "100.0000", gomme="0,Soft"), tour(2, 1, "100.0000", gomme="0,Medium"),
        ]),
        pilote("Bruno", "B #2", "GT3", 2, 2, [
            tour(1, 2, "100.0000", gomme="0,Medium"), tour(2, 2, "100.0000", gomme="15,N/A"),
        ]),
    ]))
    assert gt3["gomme"] == {"nom": "Medium", "tours": 2}


# ----------------------------------------------------------------------
# Les incidents
# ----------------------------------------------------------------------

JOURNAL = """<Score et="70.0">Alice(1) lap=0 point=1 t=33.0 et=70.0</Score>
<Incident et="74.4">Alice(1) reported contact (115.48) with another vehicle Bruno(2)</Incident>
<Incident et="74.4">Bruno(2) reported contact (115.48) with another vehicle Alice(1)</Incident>
<Incident et="190.0">Bruno(2) reported contact (2500.00) with Immovable</Incident>
<Incident et="191.0">(3) reported contact (12.00) with Immovable</Incident>
<Sector Driver="Alice" ID="1" Sector="1" Class="Hyper" et="105.6">Alice(1) set new best for sector 1</Sector>
<TrackLimits Driver="Bruno" ID="2" Lap="1" WarningPoints="0" CurrentPoints="0" Resolution="4" et="200.0">Warning</TrackLimits>
<Penalty Driver="Chloé" ID="3" Penalty="Stop/Go" Time="10" Laps="0" Reason="Speeding In Pitlane" et="150.0">Chloé received Stop/Go penalty, 10s, 0laps for Speeding In Pitlane. Result: penalties=1, 1st=S</Penalty>
<Penalty et="210.0">Chloé served 1st Stop/Go penalty, result: penalties=0, 1st=Stop/Go,10s</Penalty>"""


def journal_xml() -> str:
    """La course de `course_xml`, et son journal. Le départ des premiers tours est à 100 s."""
    return course_xml().replace("<Stream>\n\n</Stream>", f"<Stream>\n{JOURNAL}\n</Stream>")


def test_le_journal_se_lit_en_incidents(tmp_path: Path) -> None:
    fichier = tmp_path / "journal.xml"
    fichier.write_text(journal_xml(), encoding="utf-8")
    evenements = resultats.lire_session(fichier).evenements
    # Ni les scores ni les meilleurs secteurs ; ni un contact sans pilote.
    assert [e.genre for e in evenements] == ["contact", "contact", "contact", "limites", "penalite", "purge"]
    alice, _bruno, decor, limites, penalite, purge = evenements
    assert (alice.pilote, alice.autre, alice.intensite) == ("Alice", "Bruno", 115.48)
    assert (decor.pilote, decor.objet, decor.autre) == ("Bruno", "Immovable", None)
    assert (limites.pilote, limites.suite) == ("Bruno", "Warning")
    assert (penalite.pilote, penalite.penalite, penalite.motif, penalite.secondes) == (
        "Chloé", "Stop/Go", "Speeding In Pitlane", 10.0,
    )
    assert (purge.pilote, purge.penalite) == ("Chloé", "Stop/Go")


def test_chaque_incident_a_son_heure_son_tour_et_sa_gravite(tmp_path: Path) -> None:
    fichier = tmp_path / "journal.xml"
    fichier.write_text(journal_xml(), encoding="utf-8")
    liste = incidents(resultats.lire_session(fichier))
    contact, _symetrique, decor, limites, *_ = liste
    # Les premiers tours partent à 100 s (drapeau vert) ; la course dure 10 min. Un contact
    # avant le départ n'a pas encore de tour, et plus de 10 min devant lui.
    assert (contact["ecoule"], contact["restant"], contact["tour"]) == (0.0, 625.6, None)
    assert (contact["rang"], contact["autre"], contact["gravite"]) == (0, "Bruno", "moyen")
    assert (decor["tour"], decor["gravite"], decor["objet"]) == (1, "violent", "Immovable")
    assert (limites["ecoule"], limites["restant"], limites["tour"]) == (100.0, 500.0, 2)


# ----------------------------------------------------------------------
# Les étiquettes de la colonne des sessions, et le chat
# ----------------------------------------------------------------------


def test_en_ligne_la_victoire_se_lit_au_nom_du_pilote(tmp_path: Path) -> None:
    dossier = tmp_path / "Results"
    dossier.mkdir()
    # En ligne, le jeu marque tous les humains comme joueurs.
    (dossier / "course-01R1.xml").write_text(seance_xml("Race", T0, [
        pilote("Alice", "A #1", "GT3", 1, 1, [], joueur=True),
        pilote("Bruno", "B #2", "GT3", 2, 2, [], joueur=True),
    ], setting="Multiplayer"), encoding="utf-8")
    seances = resultats.Seances(dossier)
    sortie = T0 + timedelta(seconds=30)
    monza = "Autodromo Nazionale Monza"
    assert seances.etiquettes(monza, "R", sortie, "A #1", "Alice") == {"en_ligne": True, "victoire": True}
    assert seances.etiquettes(monza, "R", sortie, "B #2", "Bruno") == {"en_ligne": True, "victoire": False}
    # Sans le nom, deux joueurs : une victoire qu'on ne peut attribuer ne s'affiche pas.
    assert seances.etiquettes(monza, "R", sortie, "A #1")["victoire"] is False
    assert seances.etiquettes(monza, "Q", sortie) is None


def test_seul_contre_l_ia_le_seul_joueur_suffit(tmp_path: Path) -> None:
    dossier = tmp_path / "Results"
    dossier.mkdir()
    (dossier / "course-01R1.xml").write_text(seance_xml("Race", T0, [
        pilote("Alice", "A #1", "GT3", 1, 1, [], joueur=True),
        pilote("IA", "B #2", "GT3", 2, 2, []),
    ]), encoding="utf-8")
    (dossier / "abandon-02R1.xml").write_text(seance_xml("Race", T0 + timedelta(hours=1), [
        pilote("Alice", "A #1", "GT3", 1, 1, [], joueur=True, statut="DNF"),
    ]), encoding="utf-8")
    seances = resultats.Seances(dossier)
    monza = "Autodromo Nazionale Monza"
    assert seances.etiquettes(monza, "R", T0) == {"en_ligne": False, "victoire": True}
    # Premier sur le papier, mais sans avoir vu l'arrivée : pas une victoire.
    assert seances.etiquettes(monza, "R", T0 + timedelta(hours=1))["victoire"] is False


@pytest.mark.parametrize(
    "heure, nuit",
    [
        ("21:00:00", True), ("01:30:00", True), ("05:59:59", True), ("06:00:00", False),
        ("12:30:00", False), ("19:59:00", False), (None, False), ("?", False),
    ],
)
def test_un_depart_de_nuit(heure: str | None, nuit: bool) -> None:
    assert reponses.de_nuit(heure) is nuit


def test_le_chat_d_une_seance_en_ligne(tmp_path: Path) -> None:
    journal = (
        '<ChatMessage et="160.0">Alice: bonne course: à tout de suite</ChatMessage>\n'
        '<ChatMessage et="170.0">sans auteur</ChatMessage>\n'
        '<ChatMessage et="760.0">Alice: gg</ChatMessage>'
    )
    fichier = tmp_path / "chat.xml"
    fichier.write_text(seance_xml("Race", T0, [
        pilote("Alice", "A #1", "GT3", 1, 1, [tour(1, 1, "100.0000")]),
    ], journal=journal, setting="Multiplayer"), encoding="utf-8")
    r = classement_json(resultats.lire_session(fichier))
    assert r["en_ligne"] is True
    # Le premier tour part à 100 s : le message de 160 s vient une minute après, à 9 min de la fin.
    # Le dernier arrive une minute après la fin du temps : son temps restant est négatif.
    assert r["chat"] == [
        {"ecoule": 60.0, "restant": 540.0, "auteur": "Alice", "texte": "bonne course: à tout de suite"},
        {"ecoule": 70.0, "restant": 530.0, "auteur": "", "texte": "sans auteur"},
        {"ecoule": 660.0, "restant": -60.0, "auteur": "Alice", "texte": "gg"},
    ]


# ----------------------------------------------------------------------
# La route : la session de télémétrie retrouve son classement
# ----------------------------------------------------------------------


@pytest.fixture
def jeu(tmp_path: Path, session_test: Path) -> Path:
    """Un dossier `UserData` : la session synthétique, et le fichier de sa séance."""
    telemetrie = tmp_path / "UserData" / "Telemetry"
    telemetrie.mkdir(parents=True)
    copie = Path(shutil.copy(session_test, telemetrie / session_test.name))
    with FichierSession(copie) as fichier:
        info = fichier.info
    resultats_jeu = tmp_path / "UserData" / "Log" / "Results"
    resultats_jeu.mkdir(parents=True)
    (resultats_jeu / "seance-01P1.xml").write_text(
        seance_xml(
            "Practice1",
            info.enregistree_le - timedelta(minutes=5),
            [
                pilote("Rapide", "Autre #7", "GT3", 1, 1, [tour(1, 1, "100.0000")], meilleur="100.0000"),
                pilote("Moi", info.voiture, "GT3", 2, 2, [tour(1, 2, "101.5000")], meilleur="101.5000",
                       joueur=True),
            ],
            circuit=info.circuit,
            minutes=30,
        ),
        encoding="utf-8",
    )
    return copie


def test_une_session_retrouve_le_classement_de_sa_seance(jeu: Path) -> None:
    r = reponses.classement(reponses.Contexte(dossier=jeu.parent), str(jeu))
    assert r["trouve"] is True
    assert [e["nom"] for e in r["engages"]] == ["Rapide", "Moi"]
    assert r["engages"][1]["ecart"]["temps"] == pytest.approx(1.5)


def test_sans_fichier_de_resultats_pas_de_classement(jeu: Path) -> None:
    for fichier in (jeu.parent.parent / "Log" / "Results").glob("*.xml"):
        fichier.unlink()
    assert reponses.classement(reponses.Contexte(dossier=jeu.parent), str(jeu)) == {"trouve": False}


def test_la_route_du_classement(jeu: Path) -> None:
    instance = serveur.creer_serveur(0, jeu.parent)
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    try:
        adresse = f"http://127.0.0.1:{instance.server_address[1]}"
        requete = adresse + "/api/classement?" + urllib.parse.urlencode({"chemin": str(jeu)})
        with urllib.request.urlopen(requete) as reponse:
            charge = json.loads(reponse.read())
    finally:
        instance.shutdown()
        instance.server_close()
    assert charge["trouve"] is True
    assert charge["type"] == "P"
