"""Les records partagés : un tour qui fait l'aller-retour par le groupe, ses garde-fous, le
choix des records de ce PC, leur synchronisation, et la comparaison avec le tour d'un ami
dans l'onglet Télémétrie.

Le tour vient de la session synthétique (`tests/fixtures/construire.py`) ; le service, de
`service/local.mjs` (voir `tests/test_groupe.py`).
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from lmu_telemetry.domaine.comparaison import comparer
from lmu_telemetry.domaine.donnees_tour import charger
from lmu_telemetry.domaine.virages import DefinitionCircuit, Virage
from lmu_telemetry.errors import ErreurTelemetrie
from lmu_telemetry.groupe import reglages, tours
from lmu_telemetry.groupe.service import ErreurGroupe, Service
from lmu_telemetry.groupe.synchro import (
    Copie,
    charger_partage,
    dossier_tours,
    synchroniser,
    tours_des_amis,
)
from lmu_telemetry.groupe.tours import Record, TourPartage, decoder, designer, encoder, identifiant_record
from lmu_telemetry.sources.reader import FichierSession
from lmu_telemetry.stockage.index import Index, resumer
from lmu_telemetry.web import reponses, serveur
from tests.test_classement import jeu, pilote, seance_xml, tour  # noqa: F401  (jeu : une fixture)
from tests.test_groupe import AMI, MOI, FauxService, service_local  # noqa: F401  (une fixture)

TRACE = "Circuit de test"


def record(chemin: Path, numero: int = 1, chrono: float = 90.0, voiture: str = "Voiture de test") -> Record:
    return Record(
        id=identifiant_record(TRACE, voiture), trace=TRACE, circuit=TRACE, voiture=voiture, marque=None,
        classe="GT3", pilote="Pilote de test", date="2026-11-09T17:00:00+00:00", type="Q",
        chemin=str(chemin), numero=numero, chrono=chrono,
    )


# ----------------------------------------------------------------------
# Un tour partagé
# ----------------------------------------------------------------------


def test_un_tour_fait_l_aller_retour(session_test: Path) -> None:
    original = charger(session_test, 1)
    texte = encoder(original)
    partage = decoder(texte, "groupe:AMI/abc", {"engagement": "Porsche", "modele": "Porsche"})
    assert isinstance(partage, TourPartage)
    assert (partage.identifiant, partage.voiture["modele"]) == ("groupe:AMI/abc", "Porsche")
    assert (partage.tour.numero, partage.tour.chrono, partage.tour.valide) == (1, 90.0, True)
    assert partage.tour.secteurs == original.tour.secteurs
    assert (partage.info.trace, partage.info.pilote, partage.info.setup_brut) == (TRACE, "Pilote de test", None)
    # Comparé à sa copie partagée, un tour ne s'en écarte que de la quantification.
    resultat = comparer(original, partage)
    assert abs(resultat.ecart_final) < 0.002
    assert np.abs(resultat.delta).max() < 0.002
    vitesse = resultat.traces["Ground Speed"]
    assert np.nanmax(np.abs(vitesse[0] - vitesse[1])) < 0.02
    # Ce qui part ne dit rien du réglage, ni du chemin du fichier.
    charge = json.loads(gzip.decompress(base64.b64decode(texte)))
    assert "setup_brut" not in charge["info"]
    assert str(session_test.name) not in json.dumps(charge)


def _abime(charge: dict) -> str:
    return base64.b64encode(gzip.compress(json.dumps(charge).encode())).decode()


@pytest.mark.parametrize(
    "modification",
    [
        lambda c: c.update(format=2),
        lambda c: c.update(nombre=tours.NOMBRE_MAX + 1),
        lambda c: c.update(pas=2.0),
        lambda c: c["temps"].update(d=[1, 2]),
        lambda c: c["temps"].update(d=[-1000] * len(c["temps"]["d"])),
        lambda c: c["tour"].update(chrono="vite"),
        lambda c: c["tour"].update(numero=-1),
        lambda c: c["info"].update(pilote="x" * 65),
        lambda c: c.update(canaux=[]),
        lambda c: c["canaux"]["Ground Speed"].update(d="beaucoup"),
    ],
)
def test_un_tour_qui_ne_se_lit_pas(session_test: Path, modification) -> None:
    charge = json.loads(gzip.decompress(base64.b64decode(encoder(charger(session_test, 1)))))
    modification(charge)
    with pytest.raises(ErreurGroupe) as erreur:
        decoder(_abime(charge), "groupe:AMI/abc")
    assert erreur.value.code == "tour_illisible"


def test_les_garde_fous_de_la_lecture(session_test: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for brut in ("pas du base64 !", "", base64.b64encode(b"pas du gzip").decode(), None):
        with pytest.raises(ErreurGroupe):
            decoder(brut, "groupe:AMI/abc")
    # Une bombe de compression s'arrête au plafond, sans tout décompresser.
    monkeypatch.setattr(tours, "TAILLE_MAX", 1000)
    with pytest.raises(ErreurGroupe):
        decoder(base64.b64encode(gzip.compress(b"0" * 100_000)).decode(), "groupe:AMI/abc")
    # Un canal inconnu est ignoré : il ne vient pas de l'outil.
    monkeypatch.setattr(tours, "TAILLE_MAX", 32 * 1024 * 1024)
    charge = json.loads(gzip.decompress(base64.b64decode(encoder(charger(session_test, 1)))))
    charge["canaux"]["Inconnu"] = charge["canaux"]["Ground Speed"]
    assert "Inconnu" not in decoder(_abime(charge), "groupe:AMI/abc").canaux


def test_la_designation_d_un_record() -> None:
    assert designer("AMI", "0123abcd") == "groupe:AMI/0123abcd"
    assert tours.analyser("groupe:AMI/0123abcd") == ("AMI", "0123abcd")
    assert tours.est_partage("groupe:AMI/0123abcd") and not tours.est_partage("C:/session.duckdb")
    for faux in ("groupe:AMI/../../x", "groupe:ami/0123", "groupe:AMI", "groupe:AMI/zz", "AMI/0123"):
        with pytest.raises(ErreurGroupe):
            tours.analyser(faux)
    # Le même tracé et la même voiture gardent le même numéro : le meilleur tour remplace l'ancien.
    assert identifiant_record(TRACE, "Porsche") == identifiant_record(TRACE, "Porsche")
    assert identifiant_record(TRACE, "Porsche") != identifiant_record(TRACE, "Ferrari")


# ----------------------------------------------------------------------
# Les records de ce PC
# ----------------------------------------------------------------------


def _seance_du_jeu(
    jeu_: Path, setting: str, decalage: int = 0, bloc: str = "Practice1", nom: str = "Moi"
) -> None:
    """Le fichier de résultats de la séance de la session de test, en ligne ou non, en
    essais ou en qualifs. `decalage` avance sa date : l'index des résultats ne se relit
    que si elle change."""
    with FichierSession(jeu_) as fichier:
        info = fichier.info
    fichier_xml = jeu_.parent.parent / "Log" / "Results" / "seance-01P1.xml"
    fichier_xml.write_text(
        seance_xml(bloc, info.enregistree_le - timedelta(minutes=5), [
            pilote(nom, info.voiture, "GT3", 1, 1, [tour(1, 1, "90.0000")], joueur=True),
        ], circuit=info.circuit, minutes=30, setting=setting),
        encoding="utf-8",
    )
    date = fichier_xml.stat().st_mtime + decalage
    os.utime(fichier_xml, (date, date))


def test_les_records_de_ce_pc(jeu: Path) -> None:  # noqa: F811
    # Le jeu nomme ses fichiers « <circuit>_<type>_<date> » : la date sert à retrouver
    # la séance dans les fichiers de résultats.
    with FichierSession(jeu) as fichier:
        date = fichier.info.enregistree_le.astimezone(timezone.utc)
    session = jeu.rename(jeu.with_name(f"{TRACE}_P_{date:%Y-%m-%dT%H_%M_%S}Z.duckdb"))
    contexte = reponses.Contexte(dossier=session.parent)
    Index().enregistrer([resumer(session)])
    # Une séance jouée seule ne partage rien ; des essais en ligne non plus.
    _seance_du_jeu(session, "Race Weekend")
    assert reponses.mes_records(contexte) == []
    _seance_du_jeu(session, "Multiplayer", decalage=10)
    assert reponses.mes_records(contexte) == []
    # Les mêmes tours, en qualifications en ligne : le record part.
    session = session.rename(session.with_name(session.name.replace("_P_", "_Q_")))
    Index().enregistrer([resumer(session)])
    _seance_du_jeu(session, "Multiplayer", decalage=20, bloc="Qualify")
    (record_,) = reponses.mes_records(contexte)
    assert (record_.trace, record_.numero, record_.chrono, record_.chemin, record_.type) == (
        TRACE, 1, 90.0, str(session), "Q",
    )
    assert record_.id == identifiant_record(TRACE, record_.voiture)
    assert reponses.sources_du_groupe(contexte)[2] == [record_]
    assert reponses.mes_records(contexte, trace="Autre tracé") == []


# ----------------------------------------------------------------------
# La synchronisation des records
# ----------------------------------------------------------------------


class FauxServiceTours(FauxService):
    def __init__(self) -> None:
        super().__init__()
        self.tours: dict[tuple[str, str], tuple[dict, int]] = {}
        self.envois_tours: list[str] = []

    def envoyer_tour(self, adhesion: Adhesion, tour: dict) -> dict:
        self.version += 1
        self.envois_tours.append(tour["id"])
        self.tours[(adhesion.membre, tour["id"])] = (tour, self.version)
        return {"version": self.version}

    def lire(self, adhesion: Adhesion, depuis: int = 0) -> dict:
        reponse = super().lire(adhesion, depuis)
        reponse["tours"] = [
            {"membre": membre, "id": ident, "maj": v, "meta": {k: x for k, x in t.items() if k != "donnees"}}
            for (membre, ident), (t, v) in self.tours.items()
            if v > depuis
        ]
        return reponse


from lmu_telemetry.groupe.reglages import Adhesion  # noqa: E402


def test_on_partage_ses_records_battus(tmp_path: Path) -> None:
    service = FauxServiceTours()
    copie = Copie.lire(MOI)
    exportes = []

    def exporteur(r: Record) -> str:
        exportes.append(r.id)
        return "QQ=="

    premier = record(tmp_path / "a.duckdb")
    bilan = synchroniser(service, MOI, copie, [], {}, [premier], exporteur)
    assert (bilan.tours_envoyes, service.envois_tours) == (1, [premier.id])
    # Rien de battu : rien ne repart.
    synchroniser(service, MOI, copie, [], {}, [premier], exporteur)
    assert service.envois_tours == [premier.id]
    # Un meilleur tour : il remplace l'ancien sous le même numéro.
    synchroniser(service, MOI, copie, [], {}, [replace(premier, numero=4, chrono=89.5)], exporteur)
    assert service.envois_tours == [premier.id, premier.id]


def test_un_tour_illisible_ne_se_retente_pas(tmp_path: Path) -> None:
    service = FauxServiceTours()
    copie = Copie.lire(MOI)
    essais = []

    def exporteur(r: Record) -> str:
        essais.append(r.id)
        raise ErreurTelemetrie("fichier abîmé")

    for _ in range(2):
        synchroniser(service, MOI, copie, [], {}, [record(tmp_path / "a.duckdb")], exporteur)
    assert (len(essais), service.envois_tours) == (1, [])


def test_on_recoit_la_liste_des_records_des_autres(tmp_path: Path) -> None:
    service = FauxServiceTours()
    # Un record d'essai, comme en partageait la première version de l'outil, ne compte pas.
    essai = replace(record(tmp_path / "c.duckdb", voiture="Essai"), type="P")
    synchroniser(service, AMI, Copie.lire(AMI), [], {}, [record(tmp_path / "a.duckdb"), essai], lambda r: "QQ==")
    copie = Copie.lire(MOI)
    bilan = synchroniser(service, MOI, copie, [], {}, [record(tmp_path / "b.duckdb", voiture="Autre")], lambda r: "QQ==")
    # La liste des siens ne revient pas ; celle de l'ami, sans la télémétrie ni son essai.
    assert bilan.tours_recus == 1
    (ident, meta), = copie.tours["AMI"].items()
    assert (meta["trace"], meta["chrono"], meta["pilote"], meta["maj"]) == (TRACE, 90.0, "Pilote de test", 1)
    assert "donnees" not in meta
    service.membres = [{"id": "MOI", "nom": "Moi"}]
    synchroniser(service, MOI, copie, [], {}, [], lambda r: "QQ==")
    assert copie.tours == {}


# ----------------------------------------------------------------------
# Comparer avec le tour d'un ami, contre le vrai service lancé sur ce PC
# ----------------------------------------------------------------------


@pytest.fixture
def groupe_avec_un_ami(
    service_local: str, session_test: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path  # noqa: F811
):
    """Ce PC et un ami dans un groupe ; l'ami a partagé son record (le tour 1 de la session
    de test) ; ce PC a synchronisé."""
    monkeypatch.setenv(reglages.VARIABLE_SERVICE, service_local)
    service = Service(service_local)
    moi = service.creer("Moi")
    ami = service.rejoindre(moi.code, "Ami")
    reglages.enregistrer(moi)
    # La copie de l'ami est sur son PC : ailleurs que celle de ce PC.
    synchroniser(service, ami, Copie.lire(ami, tmp_path / "copie-ami.json"), [], {},
                 [record(session_test)], lambda r: encoder(charger(r.chemin, r.numero)))
    synchroniser(service, moi, Copie.lire(moi), [], {})
    (partage,) = tours_des_amis()
    return partage


def test_comparer_avec_le_record_d_un_ami(groupe_avec_un_ami: dict, session_test: Path) -> None:
    partage = groupe_avec_un_ami
    assert (partage["trace"], partage["pilote"], partage["chrono"]) == (TRACE, "Pilote de test", 90.0)
    assert tours_des_amis("Autre tracé") == []
    tour_ami = charger_partage(partage["id"])
    # Téléchargé une fois, gardé sur le disque.
    assert len(list(dossier_tours().glob("*.txt"))) == 1
    resultat = comparer(charger(session_test, 3), tour_ami)
    assert resultat.ecart_final == pytest.approx(90.0 - 92.0, abs=0.05)
    with pytest.raises(ErreurGroupe):
        charger_partage(designer("INCONNU", "abcdef"))


def test_les_routes_avec_le_record_d_un_ami(groupe_avec_un_ami: dict, jeu: Path) -> None:  # noqa: F811
    partage = groupe_avec_un_ami
    instance = serveur.creer_serveur(0, jeu.parent)
    threading.Thread(target=instance.serve_forever, daemon=True).start()

    def demander(route: str, **params) -> dict:
        adresse = f"http://127.0.0.1:{instance.server_address[1]}{route}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(adresse) as reponse:
            return json.loads(reponse.read())

    try:
        liste = demander("/api/groupe/tours", trace=TRACE)
        session = demander("/api/session", chemin=partage["id"])
        comparaison = demander("/api/comparaison", ref=str(jeu), tour_ref=3, cmp=partage["id"], tour_cmp=1)
        virages = demander("/api/virages", ref=str(jeu), tour_ref=3, cmp=partage["id"], tour_cmp=1)
        # Un chemin hors du dossier reste refusé.
        with pytest.raises(urllib.error.HTTPError):
            demander("/api/session", chemin=str(Path(jeu).parent.parent / "ailleurs.duckdb"))
    finally:
        instance.shutdown()
        instance.server_close()
    assert [t["id"] for t in liste["tours"]] == [partage["id"]]
    assert (session["partage"], session["pilote"], [t["numero"] for t in session["tours"]]) == (
        True, "Pilote de test", [1],
    )
    assert (comparaison["compare"]["partage"], comparaison["compare"]["chemin"]) == (True, partage["id"])
    assert comparaison["reference"]["partage"] is False
    assert comparaison["ecart_final"] == pytest.approx(-2.0, abs=0.05)
    assert "virages" in virages


# ----------------------------------------------------------------------
# Choisir les deux tours depuis le leaderboard
# ----------------------------------------------------------------------


def _session_en_qualifs(jeu_: Path) -> Path:
    """La session de test renommée comme le jeu nomme une séance de qualifs, indexée, avec
    le fichier de résultats d'une séance en ligne où son pilote est le joueur."""
    with FichierSession(jeu_) as fichier:
        date = fichier.info.enregistree_le.astimezone(timezone.utc)
    session = jeu_.rename(jeu_.with_name(f"{TRACE}_Q_{date:%Y-%m-%dT%H_%M_%S}Z.duckdb"))
    Index().enregistrer([resumer(session)])
    _seance_du_jeu(session, "Multiplayer", decalage=10, bloc="Qualify", nom="Pilote de test")
    return session


def test_chaque_ligne_du_leaderboard_dit_son_tour_enregistre(
    jeu: Path, service_local: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path  # noqa: F811
) -> None:
    monkeypatch.setenv(reglages.VARIABLE_SERVICE, service_local)
    session = _session_en_qualifs(jeu)
    contexte = reponses.Contexte(dossier=session.parent)
    service = Service(service_local)
    moi = service.creer("Moi")
    ami = service.rejoindre(moi.code, "Ami")
    reglages.enregistrer(moi)
    # L'ami a couru en qualifs sur ce tracé, et partagé son record ; un autre ami n'a rien partagé.
    from tests.test_leaderboard import perf

    tour_ami = replace(record(session), pilote="Ami rapide")
    service.envoyer(ami, [perf(pilote="Ami rapide", trace=TRACE, circuit=TRACE, meilleur_tour=89.5).json()])
    synchroniser(service, ami, Copie.lire(ami, tmp_path / "ami.json"), [], {}, [tour_ami],
                 lambda r: encoder(charger(r.chemin, r.numero)))
    synchroniser(service, moi, Copie.lire(moi), [], {})

    r = reponses.leaderboard(contexte, {"trace": [TRACE]})
    lignes = {l["pilote"]: l for c in r["tours"] for l in c["lignes"]}
    assert set(lignes) == {"Ami rapide", "Pilote de test"}
    # Le sien : le record de ce PC, par son fichier ; celui de l'ami : sa désignation.
    assert lignes["Pilote de test"]["enregistre"] == {
        "chemin": str(session), "numero": 1, "chrono": 90.0, "voiture": lignes["Pilote de test"]["enregistre"]["voiture"],
    }
    assert lignes["Ami rapide"]["enregistre"]["chemin"] == designer(ami.membre, tour_ami.id)
    # Hors de la page d'un circuit, rien n'est cherché.
    assert "enregistre" not in str(reponses.leaderboard(contexte, {}).get("tours"))


def test_le_record_d_un_ami_sert_aussi_de_reference(groupe_avec_un_ami: dict, session_test: Path) -> None:
    partage = groupe_avec_un_ami
    contexte = reponses.Contexte(dossier=session_test.parent)
    params = {"ref": [partage["id"]], "tour_ref": ["1"], "cmp": [partage["id"]], "tour_cmp": ["1"]}
    # Pas de session de ce PC d'où tirer le découpage : il se détecte sur les tours eux-mêmes,
    # et s'enregistre comme celui d'une session. Le circuit de test n'a aucun virage assez
    # serré pour en compter un.
    r = reponses.virages(contexte, params)
    assert (r["circuit"], r["automatique"], r["virages"]) == (TRACE, True, [])
    assert Path(r["fichier"]).is_file()
    # Un découpage connu sert tel quel : deux records d'amis se comparent virage par virage.
    DefinitionCircuit(circuit=TRACE, longueur=3724.0, virages=(
        Virage(1, 400.0, 600.0, 80.0, sens=1), Virage(2, 2000.0, 2300.0, 120.0, sens=-1),
    )).enregistrer(Path(r["fichier"]))
    r = reponses.virages(contexte, params)
    assert [v["numero"] for v in r["virages"]] == [1, 2]
    assert all(v["delta_zone"] == pytest.approx(0, abs=0.01) for v in r["virages"])


def test_un_record_demande_par_plusieurs_routes_a_la_fois(
    groupe_avec_un_ami: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ouverte depuis le leaderboard, la page Télémétrie demande le même record par plusieurs
    # routes en même temps (la comparaison, la session, les virages). Un seul téléchargement,
    # et aucune demande n'efface le fichier qu'une autre est en train d'écrire.
    partage = groupe_avec_un_ami
    telecharger = Service.tour
    appels = []

    def lentement(self, *args):
        appels.append(args)
        time.sleep(0.1)
        return telecharger(self, *args)

    monkeypatch.setattr(Service, "tour", lentement)
    depart = threading.Barrier(6)
    tours_lus, erreurs = [], []

    def demander() -> None:
        depart.wait()
        try:
            tours_lus.append(charger_partage(partage["id"]))
        except Exception as erreur:  # noqa: BLE001
            erreurs.append(erreur)

    fils = [threading.Thread(target=demander) for _ in range(6)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()
    assert erreurs == []
    assert len(appels) == 1 and len(tours_lus) == 6
    assert len({id(tour) for tour in tours_lus}) == 1
    assert len(list(dossier_tours().iterdir())) == 1
