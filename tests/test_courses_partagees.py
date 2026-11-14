"""Les courses partagées avec le groupe (demandé le 2026-11-14) : le classement complet de
chaque course en ligne, pour l'ouvrir dans l'onglet Résultats d'un autre PC, et la télémétrie
de son meilleur tour, pour le comparer depuis l'onglet Courses du leaderboard.

Les fichiers de résultats sont fabriqués ici (voir `tests/test_classement.py`) ; le service,
c'est `service/local.mjs` (voir `tests/test_groupe.py`).
"""

from __future__ import annotations

import base64
import gzip
import json
import threading
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import timezone
from pathlib import Path

import pytest

from lmu_telemetry.domaine.donnees_tour import charger
from lmu_telemetry.groupe import reglages, seances
from lmu_telemetry.groupe.seances import LOCAL, decoder_seance, designer_seance, encoder_seance
from lmu_telemetry.groupe.service import ErreurGroupe, Service
from lmu_telemetry.groupe.synchro import (
    Copie,
    CourseAPartager,
    dossier_seances,
    synchroniser,
)
from lmu_telemetry.groupe.tours import designer, encoder, identifiant_course
from lmu_telemetry.sources import resultats
from lmu_telemetry.sources.reader import FichierSession
from lmu_telemetry.stockage.index import Index, resumer
from lmu_telemetry.web import reponses, serveur
from tests.test_classement import T0, course_xml, jeu, pilote, seance_xml, tour  # noqa: F401  (jeu : une fixture)
from tests.test_groupe import AMI, MOI, service_local  # noqa: F401  (une fixture)
from tests.test_leaderboard import course
from tests.test_tours_partages import TRACE, FauxServiceTours, _seance_du_jeu, record

# ----------------------------------------------------------------------
# Une course qui fait l'aller-retour
# ----------------------------------------------------------------------


def _course(tmp_path: Path, xml: str | None = None, nom: str = "course-01R1.xml") -> Path:
    fichier = tmp_path / nom
    fichier.write_text(xml or course_xml(), encoding="utf-8")
    return fichier


def test_une_course_fait_l_aller_retour(tmp_path: Path) -> None:
    seance = resultats.lire_session(_course(tmp_path))
    recue = decoder_seance(encoder_seance(seance), "seance:AMI/1-R")
    # Tout ce que l'écran Résultats montre revient à l'identique ; le fichier, non.
    assert replace(recue, fichier=seance.fichier) == seance
    assert recue.fichier == Path("groupe") / "AMI/1-R"


def _reencoder(donnees: str, modifier) -> str:
    charge = json.loads(gzip.decompress(base64.b64decode(donnees)))
    modifier(charge)
    return base64.b64encode(gzip.compress(json.dumps(charge).encode("utf-8"))).decode("ascii")


@pytest.mark.parametrize(
    "modification",
    [
        lambda c: c.update(format=99),
        lambda c: c["seance"].update(type="X"),
        lambda c: c["seance"]["engages"][0].update(joueur="oui"),
        lambda c: c["seance"]["engages"][0].update(nom="x" * 500),
        lambda c: c["seance"]["engages"][0]["tours_detail"][0].append(1),
        lambda c: c["seance"]["engages"][0]["tours_detail"][0].__setitem__(3, "rapide"),
        lambda c: c["seance"].update(engages=[c["seance"]["engages"][0]] * 500),
        lambda c: c["seance"].update(evenements=[{"genre": "inconnu", "instant": 1.0, "pilote": "A"}]),
        lambda c: c["seance"].pop("circuit"),
    ],
)
def test_une_course_qui_ne_se_lit_pas(tmp_path: Path, modification) -> None:
    donnees = encoder_seance(resultats.lire_session(_course(tmp_path)))
    with pytest.raises(ErreurGroupe) as erreur:
        decoder_seance(_reencoder(donnees, modification), "seance:AMI/1-R")
    assert erreur.value.code == "seance_illisible"


def test_les_garde_fous_de_la_lecture() -> None:
    for donnees in ("pas du base64 !", base64.b64encode(b"pas du gzip").decode(), 12):
        with pytest.raises(ErreurGroupe):
            decoder_seance(donnees, "seance:AMI/1-R")
    # Une bombe de compression : 20 Mo de zéros, qui tiennent en 20 Ko.
    bombe = base64.b64encode(gzip.compress(b"0" * (20 * 1024 * 1024))).decode("ascii")
    with pytest.raises(ErreurGroupe):
        decoder_seance(bombe, "seance:AMI/1-R")


def test_la_designation_d_une_course() -> None:
    assert seances.analyser_seance(designer_seance("AMI", "1794245179-R")) == ("AMI", "1794245179-R")
    assert seances.analyser_seance("seance:local/12-Q") == (LOCAL, "12-Q")
    for faux in ("seance:AMI/1-P", "seance:../x/1-R", "seance:ami/1-R", "seance:AMI/1-R/", "groupe:AMI/1-R"):
        with pytest.raises(ErreurGroupe):
            seances.analyser_seance(faux)


# ----------------------------------------------------------------------
# Les courses de ce PC
# ----------------------------------------------------------------------


def _session_en_course(jeu_: Path) -> Path:
    """La session de test renommée comme le jeu nomme une course, indexée, avec le fichier de
    résultats d'une course en ligne où son pilote est le joueur."""
    with FichierSession(jeu_) as fichier:
        date = fichier.info.enregistree_le.astimezone(timezone.utc)
    session = jeu_.rename(jeu_.with_name(f"{TRACE}_R_{date:%Y-%m-%dT%H_%M_%S}Z.duckdb"))
    Index().enregistrer([resumer(session)])
    _seance_du_jeu(session, "Multiplayer", decalage=10, bloc="Race", nom="Pilote de test")
    return session


def _course_sans_telemetrie(jeu_: Path) -> str:
    """Une autre course en ligne du même pilote, roulée sans enregistrer : son numéro."""
    (jeu_.parent.parent / "Log" / "Results" / "course-02R1.xml").write_text(
        seance_xml("Race", T0, [
            pilote("Pilote de test", "A #1", "GT3", 1, 1, [tour(1, 1, "95.0000")] * 3, joueur=True),
            pilote("Inconnu", "B #2", "GT3", 2, 2, [tour(1, 2, "96.0000")] * 3, joueur=True),
        ], circuit=TRACE, setting="Multiplayer"),
        encoding="utf-8",
    )
    return f"{int(T0.timestamp())}-R"


def test_les_courses_de_ce_pc_et_ce_qui_part_au_groupe(jeu: Path) -> None:  # noqa: F811
    session = _session_en_course(jeu)
    sans = _course_sans_telemetrie(session)
    contexte = reponses.Contexte(dossier=session.parent)
    courses = reponses.mes_courses(contexte)
    avec = next(i for i in courses if i != sans)
    # Les plus récentes d'abord (celle sans télémétrie date de novembre, la session de test de
    # janvier) ; le meilleur tour enregistré, seulement là où il y en a un.
    assert list(courses) == [sans, avec]
    tour_ = courses[avec].tour
    assert (tour_.id, tour_.type, tour_.chemin, tour_.trace) == (identifiant_course(avec), "R", str(session), TRACE)
    assert courses[sans].tour is None
    _, _, tours, a_partager = reponses.sources_du_groupe(contexte)
    assert tour_ in tours
    assert [c.id for c in a_partager] == [sans, avec]
    assert all(Path(c.fichier).is_file() and c.signature for c in a_partager)


# ----------------------------------------------------------------------
# La synchronisation des courses
# ----------------------------------------------------------------------


class FauxServiceCourses(FauxServiceTours):
    def __init__(self, refuser: str | None = None) -> None:
        super().__init__()
        self.seances: dict[tuple[str, str], tuple[str, int]] = {}
        self.envois_seances: list[str] = []
        self.refuser = refuser

    def envoyer_seance(self, adhesion, seance: dict) -> dict:
        if self.refuser:
            raise ErreurGroupe(None, self.refuser)
        self.version += 1
        self.envois_seances.append(seance["id"])
        self.seances[(adhesion.membre, seance["id"])] = (seance["donnees"], self.version)
        return {"version": self.version}

    def lire(self, adhesion, depuis: int = 0) -> dict:
        reponse = super().lire(adhesion, depuis)
        reponse["seances"] = [
            {"membre": membre, "id": ident, "maj": v} for (membre, ident), (_, v) in self.seances.items() if v > depuis
        ]
        return reponse


def test_on_partage_le_classement_de_ses_courses(tmp_path: Path) -> None:
    service = FauxServiceCourses()
    copie = Copie.lire(MOI)
    lues = []

    def lecteur(c: CourseAPartager) -> str:
        lues.append(c.id)
        if c.id == "3-R":
            raise ValueError("fichier abîmé")
        return "QQ=="

    courses = [CourseAPartager("1-R", "a.xml", "v1"), CourseAPartager("2-R", "b.xml", "v1"), CourseAPartager("3-R", "c.xml", "v1")]
    bilan = synchroniser(service, MOI, copie, [], {}, courses=courses, lecteur=lecteur)
    assert (bilan.seances_envoyees, service.envois_seances) == (2, ["1-R", "2-R"])
    # Rien de changé : rien ne repart, pas même la course illisible ; un fichier réécrit, si.
    synchroniser(service, MOI, copie, [], {}, courses=courses, lecteur=lecteur)
    synchroniser(service, MOI, copie, [], {}, courses=[replace(courses[0], signature="v2")], lecteur=lecteur)
    assert service.envois_seances == ["1-R", "2-R", "1-R"]
    assert lues == ["1-R", "2-R", "3-R", "1-R"]
    # L'ami reçoit la liste, pas le classement ; un membre parti emporte les siennes.
    copie_ami = Copie.lire(AMI, tmp_path / "ami.json")
    synchroniser(service, AMI, copie_ami, [], {})
    assert copie_ami.seances == {"MOI": {"1-R": 3, "2-R": 2}}
    service.membres = [{"id": "AMI", "nom": "Ami"}]
    synchroniser(service, AMI, copie_ami, [], {})
    assert copie_ami.seances == {}


def test_un_service_d_avant_les_courses(tmp_path: Path) -> None:
    """Le service en ligne pas encore mis à jour : rien ne part, rien n'est marqué, et la
    synchronisation reçoit quand même."""
    service = FauxServiceCourses(refuser="route_inconnue")
    copie = Copie.lire(MOI)
    bilan = synchroniser(service, MOI, copie, [], {}, courses=[CourseAPartager("1-R", "a.xml", "v1")],
                         lecteur=lambda c: "QQ==")
    assert (bilan.sans_seances, bilan.seances_envoyees, copie.seances_envoyees) == (True, 0, {})
    assert copie.version == service.version


def test_la_limite_de_tours_n_empeche_pas_de_recevoir(tmp_path: Path) -> None:
    class Plein(FauxServiceCourses):
        def envoyer_tour(self, adhesion, tour: dict) -> dict:
            raise ErreurGroupe(None, "trop_gros")

    service = Plein()
    service.envoyer(AMI, [course("Ami", 1).json()])
    copie = Copie.lire(MOI)
    bilan = synchroniser(service, MOI, copie, [], {}, [record(tmp_path / "a.duckdb")], lambda r: "QQ==")
    assert (bilan.tours_envoyes, bilan.recues, copie.tours_envoyes) == (0, 1, {})


# ----------------------------------------------------------------------
# Ouvrir une course depuis le leaderboard, contre le vrai service lancé sur ce PC
# ----------------------------------------------------------------------


@pytest.fixture
def course_d_un_ami(
    jeu: Path, service_local: str, session_test: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path  # noqa: F811
) -> dict:
    """Ce PC et un ami dans un groupe. L'ami a couru à Monza, seul humain de sa course, et a
    partagé sa performance, le classement de la course et son meilleur tour ; ce PC a
    synchronisé."""
    monkeypatch.setenv(reglages.VARIABLE_SERVICE, service_local)
    service = Service(service_local)
    moi = service.creer("Moi")
    ami = service.rejoindre(moi.code, "Ami")
    reglages.enregistrer(moi)
    identifiant = f"{int(T0.timestamp())}-R"
    fichier = _course(tmp_path, seance_xml("Race", T0, [
        pilote("Ami", "B #2", "GT3", 1, 1, [tour(1, 1, "99.0000")] * 3, joueur=True, meilleur="99.0000"),
        pilote("IA", "C #3", "GT3", 2, 2, [tour(1, 2, "100.0000")] * 3),
    ], circuit=TRACE, setting="Multiplayer"))
    service.envoyer(ami, [course("Ami", 1, id=identifiant, trace=TRACE, circuit=TRACE).json()])
    tour_ami = replace(record(session_test), id=identifiant_course(identifiant), pilote="Ami", type="R")
    synchroniser(service, ami, Copie.lire(ami, tmp_path / "copie-ami.json"), [], {}, [tour_ami],
                 lambda r: encoder(charger(r.chemin, r.numero)), [CourseAPartager(identifiant, str(fichier), "v1")])
    synchroniser(service, moi, Copie.lire(moi), [], {})
    return {"contexte": reponses.Contexte(dossier=jeu.parent), "membre": ami.membre, "id": identifiant, "jeu": jeu}


def test_la_course_d_un_ami_s_ouvre_dans_resultats(course_d_un_ami: dict) -> None:
    contexte, membre, identifiant = course_d_un_ami["contexte"], course_d_un_ami["membre"], course_d_un_ami["id"]
    designation = designer_seance(membre, identifiant)
    (ligne,) = reponses.leaderboard(contexte, {})["historique"]["lignes"]
    assert (ligne["pilote"], ligne["seance"], ligne["enregistre"]) == ("Ami", designation, None)
    # Sur la page du circuit, son meilleur tour se choisit aussi, pour le comparer.
    (ligne,) = reponses.leaderboard(contexte, {"trace": [TRACE]})["historique"]["lignes"]
    assert ligne["enregistre"]["chemin"] == designer(membre, identifiant_course(identifiant))

    session = reponses.session(contexte, designation)
    assert (session["seance"], session["proprietaire"], session["type"], session["tours"]) == (True, "Ami", "R", [])
    assert (session["circuit"], session["tours_seance"], session["en_ligne"]) == (TRACE, 3, True)
    r = reponses.classement(contexte, designation)
    assert [e["nom"] for e in r["engages"]] == ["Ami", "IA"]
    # Le jeu marque l'ami comme joueur, seul humain de sa course : il n'est pas « toi » pour autant.
    assert not any(e["joueur"] for e in r["engages"])
    # Téléchargée une fois, gardée sur le disque.
    assert len(list(dossier_seances().glob("*.txt"))) == 1


def test_la_route_d_une_course(course_d_un_ami: dict) -> None:
    designation = designer_seance(course_d_un_ami["membre"], course_d_un_ami["id"])
    instance = serveur.creer_serveur(0, course_d_un_ami["jeu"].parent)
    threading.Thread(target=instance.serve_forever, daemon=True).start()

    def demander(route: str, **params) -> dict:
        adresse = f"http://127.0.0.1:{instance.server_address[1]}{route}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(adresse) as reponse:
            return json.loads(reponse.read())

    try:
        session = demander("/api/session", chemin=designation)
        classement = demander("/api/classement", chemin=designation)
        with pytest.raises(urllib.error.HTTPError):
            demander("/api/classement", chemin="seance:../../ailleurs/1-R")
    finally:
        instance.shutdown()
        instance.server_close()
    assert (session["id"], classement["trouve"]) == (designation, True)


def test_quitter_le_groupe_oublie_ses_courses(course_d_un_ami: dict) -> None:
    contexte = course_d_un_ami["contexte"]
    reponses.session(contexte, designer_seance(course_d_un_ami["membre"], course_d_un_ami["id"]))
    reponses.quitter_groupe(contexte, reponses.Synchroniseur(lambda: reponses.sources_du_groupe(contexte)))
    assert not dossier_seances().exists()


def test_ma_course_sans_telemetrie_s_ouvre_par_son_classement(jeu: Path) -> None:  # noqa: F811
    session = _session_en_course(jeu)
    sans = _course_sans_telemetrie(session)
    contexte = reponses.Contexte(dossier=session.parent)
    lignes = {l["id"]: l for l in reponses.leaderboard(contexte, {})["historique"]["lignes"]}
    # Celle qui a été enregistrée s'ouvre par sa session ; l'autre, par son fichier de résultats.
    avec = next(i for i in lignes if i != sans)
    assert lignes[avec]["seance"] == str(session)
    assert lignes[sans]["seance"] == designer_seance(LOCAL, sans)
    r = reponses.classement(contexte, lignes[sans]["seance"])
    assert [(e["nom"], e["joueur"]) for e in r["engages"]] == [("Pilote de test", True), ("Inconnu", False)]
    assert reponses.session(contexte, lignes[sans]["seance"])["proprietaire"] is None


def test_une_course_sans_aucun_tour_ne_part_que_si_c_est_un_abandon(jeu: Path) -> None:  # noqa: F811
    """Comme au leaderboard (`leaderboard.a_roule`) : sans tour bouclé, seule une course
    abandonnée compte encore."""
    from datetime import timedelta

    session = _session_en_course(jeu)
    resultats_jeu = session.parent.parent / "Log" / "Results"
    for heure, statut in ((1, "DNF"), (2, "None")):
        (resultats_jeu / f"course-0{heure}R1.xml").write_text(
            seance_xml("Race", T0 + timedelta(hours=heure), [
                pilote("Pilote de test", "A #1", "GT3", 2, 2, [], joueur=True, statut=statut),
                pilote("Inconnu", "B #2", "GT3", 1, 1, [tour(1, 1, "96.0000")] * 3, joueur=True),
            ], circuit=TRACE, setting="Multiplayer"),
            encoding="utf-8",
        )
    courses = reponses.mes_courses(reponses.Contexte(dossier=session.parent))
    assert f"{int((T0 + timedelta(hours=1)).timestamp())}-R" in courses
    assert f"{int((T0 + timedelta(hours=2)).timestamp())}-R" not in courses
