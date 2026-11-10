"""Le groupe : la relecture d'une performance reçue, les réglages, la synchronisation, et
les routes de l'écran Groupe.

La synchronisation se teste d'abord contre un faux service, puis contre le vrai
(`service/src/index.js`), lancé sur ce PC par Node avec sa base SQLite (`service/local.mjs`).
Sans Node, ces tests-là sont ignorés.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from lmu_telemetry import emplacements
from lmu_telemetry.domaine.performances import depuis_json
from lmu_telemetry.groupe import reglages
from lmu_telemetry.groupe.reglages import Adhesion
from lmu_telemetry.groupe.service import ErreurGroupe, Service, normaliser_code
from lmu_telemetry.groupe.synchro import Copie, Synchroniseur, copie_courante, fichier_copie, synchroniser
from lmu_telemetry.web import reponses
from tests.test_classement import T0, jeu, pilote, seance_xml, tour  # noqa: F401  (jeu : une fixture)
from tests.test_leaderboard import MONZA, SPA, course, perf

RACINE = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# Une performance reçue du groupe
# ----------------------------------------------------------------------


def test_une_performance_fait_l_aller_retour() -> None:
    for p in (perf(), course("Moi", 2, grille_classe=4, engages=20, engages_classe=12)):
        recue = depuis_json(json.loads(json.dumps(p.json())))
        assert recue == p


@pytest.mark.parametrize(
    "abime",
    [
        {"id": None},
        {"type": "X"},
        {"en_ligne": "oui"},
        {"meilleur_tour": "1:40.000"},
        {"meilleur_tour": float("nan")},
        {"secteurs_meilleur": [30.0, 30.0]},
        {"gommes": ["Medium"]},
        {"statut": "vainqueur"},
        {"pilote": "x" * 65},
        {"tours": True},
    ],
)
def test_une_performance_qui_ne_se_lit_pas(abime: dict) -> None:
    assert depuis_json({**perf().json(), **abime}) is None


def test_un_champ_inconnu_est_ignore() -> None:
    # Une version plus récente de l'outil, chez un ami, ajoute un champ.
    assert depuis_json({**perf().json(), "nouveau": 1}) == perf()
    assert depuis_json("pas un objet") is None


# ----------------------------------------------------------------------
# Le code d'un groupe, les réglages
# ----------------------------------------------------------------------


def test_le_code_d_un_groupe() -> None:
    assert normaliser_code("k7m2-qx9p") == "K7M2QX9P"
    assert normaliser_code(" K7M2 QX9P ") == "K7M2QX9P"
    for faux in ("K7M2QX9", "K7M2-QX0P", "", None):
        with pytest.raises(ErreurGroupe) as erreur:
            normaliser_code(faux)
        assert erreur.value.code == "code_invalide"


def test_les_reglages_du_groupe(monkeypatch: pytest.MonkeyPatch) -> None:
    # Les tests n'ont jamais d'adresse par défaut : ils ne parlent pas au service en ligne.
    assert (reglages.adresse_service(), reglages.adhesion()) == (None, None)
    monkeypatch.setattr(reglages, "SERVICE", "https://livre.exemple")
    assert reglages.adresse_service() == "https://livre.exemple"
    emplacements.enregistrer_reglages({"langue": "fr", "groupe": {"service": "https://groupe.exemple/"}})
    assert reglages.adresse_service() == "https://groupe.exemple"
    monkeypatch.setenv(reglages.VARIABLE_SERVICE, "http://127.0.0.1:8787")
    assert reglages.adresse_service() == "http://127.0.0.1:8787"

    adhesion = Adhesion("K7M2QX9P", "MEMBRE", "cle", "Moi")
    reglages.enregistrer(adhesion)
    assert (reglages.adhesion(), adhesion.code_affiche) == (adhesion, "K7M2-QX9P")
    # Les autres réglages et l'adresse choisie à la main restent.
    tout = emplacements.lire_reglages()
    assert (tout["langue"], tout["groupe"]["service"]) == ("fr", "https://groupe.exemple/")
    reglages.enregistrer(None)
    assert reglages.adhesion() is None
    assert emplacements.lire_reglages()["groupe"] == {"service": "https://groupe.exemple/"}


# ----------------------------------------------------------------------
# La synchronisation, contre un faux service
# ----------------------------------------------------------------------


class FauxService:
    """Ce que le vrai service fait, en mémoire : des écritures numérotées."""

    def __init__(self) -> None:
        self.version = 0
        self.lignes: dict[tuple[str, str], tuple[dict, int]] = {}
        self.contours: dict[str, tuple[list, int]] = {}
        self.envois: list[tuple[list[str], list[str]]] = []
        self.membres = [{"id": "MOI", "nom": "Moi"}, {"id": "AMI", "nom": "Ami"}]

    def envoyer(self, adhesion: Adhesion, performances: list[dict], contours: dict | None = None) -> dict:
        self.version += 1
        self.envois.append(([p["id"] for p in performances], sorted(contours or {})))
        for p in performances:
            # Comme sur le réseau : ce qui revient a fait le voyage en JSON.
            self.lignes[(adhesion.membre, p["id"])] = (json.loads(json.dumps(p)), self.version)
        for trace, points in (contours or {}).items():
            self.contours.setdefault(trace, (points, self.version))
        return {"version": self.version, "recues": len(performances)}

    def lire(self, adhesion: Adhesion, depuis: int = 0) -> dict:
        return {
            "version": self.version,
            "membres": self.membres,
            "performances": [
                {"membre": membre, "performance": p} for (membre, _), (p, v) in self.lignes.items() if v > depuis
            ],
            "contours": {trace: points for trace, (points, v) in self.contours.items() if v > depuis},
        }


MOI = Adhesion("K7M2QX9P", "MOI", "cle", "Moi")
AMI = Adhesion("K7M2QX9P", "AMI", "cle", "Ami")
CONTOUR = [[0.0, 0.0], [1.0, 0.0], [0.5, 1.0]]


def test_on_n_envoie_que_ce_qui_a_change() -> None:
    service = FauxService()
    copie = Copie.lire(MOI)
    miennes = [
        perf(),
        course("Moi", 1, id="1794243600-R"),
        perf(id="seul", en_ligne=False),
        perf(id="essais", type="P", trace=SPA, circuit=SPA),
    ]
    bilan = synchroniser(service, MOI, copie, miennes, {MONZA: CONTOUR, SPA: CONTOUR})
    # Contre l'IA ou en essais, rien ne part ; le contour d'un tracé qui compte, une seule fois.
    assert service.envois == [(["1794240000-P", "1794243600-R"], [MONZA])]
    assert (bilan.envoyees, bilan.recues, bilan.version) == (2, 0, 1)
    synchroniser(service, MOI, copie, miennes, {MONZA: CONTOUR})
    assert len(service.envois) == 1  # rien de neuf : rien ne part
    miennes[0] = replace(miennes[0], meilleur_tour=99.0)
    assert synchroniser(service, MOI, copie, miennes, {}).envoyees == 1


def test_on_recoit_les_autres_et_pas_soi() -> None:
    service = FauxService()
    synchroniser(service, AMI, Copie.lire(AMI), [perf(pilote="Ami", meilleur_tour=99.5)], {MONZA: CONTOUR})
    copie = Copie.lire(MOI)
    bilan = synchroniser(service, MOI, copie, [perf()], {})
    assert bilan.recues == 1  # la sienne, revenue du service, ne compte pas
    assert [(p.pilote, p.meilleur_tour) for p in copie.performances_des_autres()] == [("Ami", 99.5)]
    assert copie.contours == {MONZA: CONTOUR}
    assert [m["nom"] for m in copie.membres] == ["Moi", "Ami"]
    # La copie se relit telle quelle.
    relue = Copie.lire(MOI)
    assert (relue.version, relue.envoyees, relue.performances) == (copie.version, copie.envoyees, copie.performances)


def test_un_membre_parti_emporte_ses_performances() -> None:
    service = FauxService()
    synchroniser(service, AMI, Copie.lire(AMI), [perf(pilote="Ami")], {})
    copie = Copie.lire(MOI)
    synchroniser(service, MOI, copie, [], {})
    assert len(copie.performances_des_autres()) == 1
    service.membres = [{"id": "MOI", "nom": "Moi"}]
    synchroniser(service, MOI, copie, [], {})
    assert copie.performances_des_autres() == []


def test_un_service_qui_a_oublie_le_groupe() -> None:
    service = FauxService()
    copie = Copie.lire(MOI)
    synchroniser(service, MOI, copie, [perf()], {})
    service.__init__()  # une base refaite : tout est perdu là-bas
    synchroniser(service, MOI, copie, [perf()], {})
    # La version a reculé : la copie repart de zéro, et la performance repart.
    assert service.envois == [([perf().id], [])]
    assert copie.version == 1


def test_une_copie_d_un_autre_groupe_ne_se_lit_pas() -> None:
    copie = Copie.lire(MOI)
    copie.version = 7
    copie.enregistrer()
    assert Copie.lire(MOI).version == 7
    assert Copie.lire(replace(MOI, code="AAAABBBB")).version == 0
    fichier_copie().write_text("{abîmé", encoding="utf-8")
    assert Copie.lire(MOI).version == 0


# ----------------------------------------------------------------------
# Contre le vrai service, lancé sur ce PC
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def service_local():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node n'est pas installé")
    processus = subprocess.Popen(
        [node, str(RACINE / "service" / "local.mjs"), "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    try:
        ligne = processus.stdout.readline()
        while ligne and not ligne.startswith("pret "):
            ligne = processus.stdout.readline()
        if not ligne:
            pytest.fail("le service local n'a pas démarré")
        yield f"http://127.0.0.1:{ligne.split()[1]}"
    finally:
        processus.terminate()
        processus.wait(timeout=10)


def test_deux_pc_dans_un_groupe(service_local: str, tmp_path: Path) -> None:
    service = Service(service_local)
    moi = service.creer("Moi")
    ami = service.rejoindre(moi.code_affiche.lower(), "Ami")
    copie_moi = Copie.lire(moi, tmp_path / "moi.json")
    copie_ami = Copie.lire(ami, tmp_path / "ami.json")

    miennes = [perf(), course("Moi", 3, id="1794243600-R")]
    synchroniser(service, moi, copie_moi, miennes, {MONZA: CONTOUR})
    bilan = synchroniser(service, ami, copie_ami, [perf(pilote="Ami", meilleur_tour=99.5)], {})
    assert (bilan.envoyees, bilan.recues) == (1, 2)
    assert sorted(p.pilote for p in copie_ami.performances_des_autres()) == ["Moi", "Moi"]
    assert copie_ami.contours == {MONZA: CONTOUR}
    synchroniser(service, moi, copie_moi, miennes, {})
    assert [(p.pilote, p.meilleur_tour) for p in copie_moi.performances_des_autres()] == [("Ami", 99.5)]
    assert sorted(m["nom"] for m in copie_moi.membres) == ["Ami", "Moi"]

    # L'ami s'en va : ses performances partent du service, puis de la copie.
    service.quitter(ami)
    synchroniser(service, moi, copie_moi, [perf()], {})
    assert copie_moi.performances_des_autres() == []
    assert [m["nom"] for m in copie_moi.membres] == ["Moi"]
    with pytest.raises(ErreurGroupe) as erreur:
        service.lire(ami)
    assert erreur.value.code == "non_membre"


def test_les_erreurs_du_service(service_local: str) -> None:
    service = Service(service_local)
    with pytest.raises(ErreurGroupe) as erreur:
        service.rejoindre("AAAA-BBBB", "Moi")
    assert erreur.value.code == "groupe_introuvable"
    with pytest.raises(ErreurGroupe) as erreur:
        service.creer("x" * 41)
    assert erreur.value.code == "nom_invalide"
    # Un service qui ne répond pas.
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        port = libre.getsockname()[1]
    with pytest.raises(ErreurGroupe) as erreur:
        Service(f"http://127.0.0.1:{port}", delai=3).sante()
    assert erreur.value.code == "hors_ligne"


def test_la_synchronisation_de_l_outil(service_local: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(reglages.VARIABLE_SERVICE, service_local)
    synchro = Synchroniseur(lambda: ([perf()], {}))
    # Hors d'un groupe, elle ne fait rien.
    assert synchro.maintenant()["etat"] == "inactif"
    reglages.enregistrer(Service(service_local).creer("Moi"))
    etat = synchro.maintenant()
    assert (etat["etat"], etat["envoyees"]) == ("ok", 1)
    assert copie_courante().envoyees  # enregistrée là où l'outil la relit


# ----------------------------------------------------------------------
# Les routes de l'écran Groupe
# ----------------------------------------------------------------------


def test_sans_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(reglages.VARIABLE_SERVICE, raising=False)
    contexte = reponses.Contexte(dossier=tmp_path)
    synchro = Synchroniseur(lambda: ([], {}))
    etat = reponses.groupe(contexte, synchro)
    assert (etat["service"], etat["groupe"]) == (False, None)
    with pytest.raises(ErreurGroupe) as erreur:
        reponses.creer_groupe(contexte, synchro, {"nom": "Moi"})
    assert erreur.value.code == "sans_service"


def test_creer_un_groupe_et_y_voir_un_ami(jeu: Path, service_local: str, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setenv(reglages.VARIABLE_SERVICE, service_local)
    # Une course en ligne dans les fichiers du jeu : la performance du propriétaire.
    (jeu.parent.parent / "Log" / "Results" / "course-02R1.xml").write_text(
        seance_xml("Race", T0, [
            pilote("Inconnu", "B #2", "GT3", 1, 1, [tour(1, 1, "99.0000")] * 3, joueur=True),
            pilote("Moi", "A #1", "GT3", 2, 2, [tour(1, 2, "100.5000")] * 3, joueur=True),
        ], setting="Multiplayer"),
        encoding="utf-8",
    )
    contexte = reponses.Contexte(dossier=jeu.parent)
    synchro = Synchroniseur(lambda: reponses.sources_du_groupe(contexte))
    assert reponses.groupe(contexte, synchro)["nom_propose"] == "Moi"

    etat = reponses.creer_groupe(contexte, synchro, {"nom": " Moi "})
    code = etat["groupe"]["code"]
    assert (etat["synchro"]["etat"], etat["synchro"]["envoyees"]) == ("ok", 1)
    assert [(m["nom"], m["moi"]) for m in etat["groupe"]["membres"]] == [("Moi", True)]
    with pytest.raises(ErreurGroupe):
        reponses.rejoindre_groupe(contexte, synchro, {"code": code, "nom": "Moi"})  # déjà dans un groupe

    # Un ami rejoint depuis son PC, et envoie une course à Monza.
    service = Service(service_local)
    ami = service.rejoindre(code, "Ami")
    service.envoyer(ami, [course("Ami", 1, meilleur_tour=99.2).json()])
    etat = reponses.synchroniser_groupe(contexte, synchro)
    assert sorted(m["nom"] for m in etat["groupe"]["membres"]) == ["Ami", "Moi"]

    # Le leaderboard mêle ses performances et celles de l'ami.
    r = reponses.leaderboard(contexte, {"trace": [MONZA]})
    assert r["groupe"]["code"] == code
    (gt3,) = r["tours"]
    assert [(l["pilote"], l["moi"]) for l in gt3["lignes"]] == [("Ami", False), ("Moi", True)]
    assert [p["pilote"] for p in r["pilotes"]] == ["Ami", "Moi"]

    # Quitter : ses performances partent du service, la copie de ce PC aussi.
    etat = reponses.quitter_groupe(contexte, synchro)
    assert (etat["groupe"], reglages.adhesion()) == (None, None)
    assert not fichier_copie().exists()
    restant = service.lire(ami)
    assert [m["nom"] for m in restant["membres"]] == ["Ami"]
    assert [e["performance"]["pilote"] for e in restant["performances"]] == ["Ami"]
    assert reponses.leaderboard(contexte, {"trace": [MONZA]})["groupe"] is None


def test_la_route_du_groupe(jeu: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    import threading
    import urllib.request

    from lmu_telemetry.web import serveur

    monkeypatch.delenv(reglages.VARIABLE_SERVICE, raising=False)
    instance = serveur.creer_serveur(0, jeu.parent)
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    try:
        adresse = f"http://127.0.0.1:{instance.server_address[1]}/api/groupe"
        with urllib.request.urlopen(adresse) as reponse:
            charge = json.loads(reponse.read())
    finally:
        instance.shutdown()
        instance.server_close()
    assert (charge["service"], charge["groupe"], charge["synchro"]["etat"]) == (False, None, "inactif")
