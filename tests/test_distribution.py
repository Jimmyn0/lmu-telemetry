"""Tests de ce qui rend l'outil utilisable ailleurs que sur la machine de
développement : trouver le jeu, ranger ses fichiers, choisir le dossier depuis
l'interface, démarrer même quand le port est pris.

Un ami qui reçoit le .exe n'a ni le même disque, ni le même dossier Steam, ni
de terminal pour taper une option : chacun de ces cas doit se régler sans lui
demander autre chose qu'un chemin.
"""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from lmu_telemetry import catalogue, emplacements
from lmu_telemetry.errors import DossierIntrouvable
from lmu_telemetry.session import Session
from lmu_telemetry.virages import DefinitionCircuit, Virage, fichier_definition
from lmu_telemetry.web import serveur

VDF_RECENT = r'''"libraryfolders"
{
	"0"
	{
		"path"		"C:\\Program Files (x86)\\Steam"
		"apps"
		{
			"228980"		"215019902"
		}
	}
	"1"
	{
		"path"		"D:\\SteamLibrary"
		"apps"
		{
			"2399420"		"54015671544"
		}
	}
}
'''

VDF_ANCIEN = r'''"LibraryFolders"
{
	"TimeNextStatsReport"		"1234567890"
	"ContentStatsID"		"-123"
	"1"		"E:\\Jeux\\Steam"
}
'''


# ----------------------------------------------------------------------
# Trouver le jeu
# ----------------------------------------------------------------------


def test_bibliotheques_steam_format_recent() -> None:
    assert catalogue.bibliotheques_du_vdf(VDF_RECENT) == [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"D:\SteamLibrary"),
    ]


def test_bibliotheques_steam_format_ancien() -> None:
    """L'ancien format mélange des numéros de bibliothèque et des compteurs :
    seules les valeurs qui ressemblent à un chemin comptent."""
    assert catalogue.bibliotheques_du_vdf(VDF_ANCIEN) == [Path(r"E:\Jeux\Steam")]


def _faux_steam(monkeypatch, bibliotheques: list[Path]) -> None:
    monkeypatch.delenv(catalogue.VARIABLE_ENV, raising=False)
    monkeypatch.setattr(catalogue, "bibliotheques_steam", lambda: bibliotheques)


def test_le_jeu_est_trouve_dans_n_importe_quelle_bibliotheque(tmp_path, monkeypatch) -> None:
    vide = tmp_path / "C"
    vide.mkdir()
    telemetrie = tmp_path / "D" / "steamapps/common/Le Mans Ultimate/UserData/Telemetry"
    telemetrie.mkdir(parents=True)
    _faux_steam(monkeypatch, [vide, tmp_path / "D"])
    assert catalogue.dossier_telemetrie() == telemetrie


def test_jeu_installe_sans_aucune_session(tmp_path, monkeypatch) -> None:
    """Le jeu est là mais n'a encore rien enregistré : le message doit le dire,
    et non prétendre que le jeu est introuvable."""
    (tmp_path / "steamapps/common/Le Mans Ultimate").mkdir(parents=True)
    _faux_steam(monkeypatch, [tmp_path])
    with pytest.raises(DossierIntrouvable, match="aucune session"):
        catalogue.dossier_telemetrie()


def test_jeu_introuvable(tmp_path, monkeypatch) -> None:
    _faux_steam(monkeypatch, [tmp_path])
    with pytest.raises(DossierIntrouvable, match="Impossible de trouver"):
        catalogue.dossier_telemetrie()


def test_le_dossier_choisi_passe_avant_la_detection(tmp_path, monkeypatch) -> None:
    choisi = tmp_path / "ailleurs"
    choisi.mkdir()
    _faux_steam(monkeypatch, [])
    emplacements.enregistrer_reglages({catalogue.REGLAGE_DOSSIER: str(choisi)})
    assert catalogue.dossier_telemetrie() == choisi


def test_un_dossier_choisi_disparu_n_empeche_pas_la_detection(tmp_path, monkeypatch) -> None:
    """Disque débranché, jeu déplacé : on retombe sur la détection au lieu de
    rester bloqué sur un chemin mort."""
    telemetrie = tmp_path / "steamapps/common/Le Mans Ultimate/UserData/Telemetry"
    telemetrie.mkdir(parents=True)
    _faux_steam(monkeypatch, [tmp_path])
    emplacements.enregistrer_reglages({catalogue.REGLAGE_DOSSIER: str(tmp_path / "parti")})
    assert catalogue.dossier_telemetrie() == telemetrie


def test_reglages_abimes_ignores() -> None:
    emplacements.fichier_reglages().parent.mkdir(parents=True, exist_ok=True)
    emplacements.fichier_reglages().write_text("{pas du json", encoding="utf-8")
    assert emplacements.lire_reglages() == {}


# ----------------------------------------------------------------------
# Choisir le dossier depuis l'interface
# ----------------------------------------------------------------------


def test_choisir_un_dossier_inexistant(tmp_path) -> None:
    with pytest.raises(DossierIntrouvable):
        serveur._choisir_dossier(serveur.Contexte(), {"dossier": str(tmp_path / "rien")})


def test_choisir_le_dossier_du_jeu_au_lieu_de_telemetry(tmp_path) -> None:
    """L'erreur la plus probable : choisir le dossier du jeu. Le message doit
    dire quel sous-dossier prendre."""
    (tmp_path / "UserData" / "Telemetry").mkdir(parents=True)
    with pytest.raises(Exception, match=r"UserData\\Telemetry"):
        serveur._choisir_dossier(serveur.Contexte(), {"dossier": str(tmp_path)})


def test_choisir_un_dossier_valide_est_retenu(tmp_path) -> None:
    (tmp_path / "Monza_P_2026-09-08T12_12_19Z.duckdb").write_bytes(b"")
    etat = serveur._choisir_dossier(serveur.Contexte(), {"dossier": f'"{tmp_path}"'})
    assert etat["dossier"] == str(tmp_path)
    assert emplacements.lire_reglages()[catalogue.REGLAGE_DOSSIER] == str(tmp_path)


def test_un_dossier_impose_ne_se_change_pas(tmp_path) -> None:
    with pytest.raises(Exception, match="--dossier"):
        serveur._choisir_dossier(serveur.Contexte(dossier=tmp_path), {"dossier": str(tmp_path)})


@pytest.mark.parametrize(
    ("origine", "hote", "attendu"),
    [
        ("http://127.0.0.1:8770", "127.0.0.1:8770", True),
        ("http://localhost:8770", "localhost:8770", True),
        (None, "127.0.0.1:8770", False),
        ("https://site-malveillant.example", "127.0.0.1:8770", False),
        ("http://127.0.0.1:9999", "127.0.0.1:8770", False),
        ("http://site-malveillant.example", "site-malveillant.example", False),
    ],
)
def test_origine_acceptee(origine, hote, attendu) -> None:
    assert serveur._origine_acceptee(origine, hote) is attendu


def test_post_refuse_sans_origine_et_accepte_depuis_la_page(tmp_path) -> None:
    """Bout en bout, sur un vrai serveur : la route qui modifie les réglages
    n'obéit qu'à la page de l'outil."""
    (tmp_path / "Spa_R_2026-09-08T12_12_19Z.duckdb").write_bytes(b"")
    http_serveur = serveur.creer_serveur(0)
    port = http_serveur.server_address[1]
    fil = threading.Thread(target=http_serveur.serve_forever, daemon=True)
    fil.start()
    try:
        corps = json.dumps({"dossier": str(tmp_path)})

        def poster(entetes: dict) -> tuple[int, bytes]:
            connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connexion.request("POST", "/api/dossier", body=corps, headers=entetes)
            reponse = connexion.getresponse()
            return reponse.status, reponse.read()

        json_type = {"Content-Type": "application/json"}
        assert poster(json_type)[0] == 403
        origine = {"Origin": f"http://127.0.0.1:{port}"}
        assert poster({**origine, "Content-Type": "text/plain"})[0] == 415
        statut, reponse = poster({**origine, **json_type})
        assert statut == 200
        assert json.loads(reponse)["dossier"] == str(tmp_path)
    finally:
        http_serveur.shutdown()
        http_serveur.server_close()


def test_port_occupe_explique() -> None:
    premier = serveur.creer_serveur(0)
    try:
        with pytest.raises(serveur.PortOccupe, match="déjà utilisé"):
            serveur.creer_serveur(premier.server_address[1])
    finally:
        premier.server_close()


# ----------------------------------------------------------------------
# Ressources livrées et données de l'utilisateur
# ----------------------------------------------------------------------


def test_les_ressources_livrees_existent() -> None:
    """Le .exe embarque ce dossier : s'il manquait, les amis n'auraient ni
    découpages de référence ni logos."""
    assert any(emplacements.virages_fournis().glob("*.json"))
    assert any(emplacements.logos_fournis().glob("*.png"))


def test_logos_de_l_utilisateur_prioritaires(tmp_path) -> None:
    fournis = tmp_path / "fournis"
    perso = tmp_path / "perso"
    fournis.mkdir()
    perso.mkdir()
    (fournis / "BMW.png").write_bytes(b"livre")
    (fournis / "Ford.png").write_bytes(b"livre")
    (perso / "BMW.svg").write_bytes(b"perso")
    (perso / "notes.txt").write_text("pas un logo")
    contexte = serveur.Contexte(logos_fournis=fournis, dossier_logos=perso)
    logos = serveur._logos(contexte)
    assert logos == {"BMW": perso / "BMW.svg", "Ford": fournis / "Ford.png"}


def test_decoupage_livre_recopie_chez_l_utilisateur(session_test: Path, tmp_path) -> None:
    """Le découpage de référence est recopié dans les données de l'utilisateur
    la première fois : c'est cette copie qu'il retouchera, et elle survit au
    remplacement du .exe."""
    serveur._cache_virages.clear()
    session = Session.ouvrir(session_test)
    fournis = tmp_path / "fournis"
    perso = tmp_path / "perso"
    DefinitionCircuit(
        circuit=session.info.trace,
        longueur=3725.0,
        virages=(Virage(1, 100.0, 200.0, 50.0, nom="Livré"),),
    ).enregistrer(fichier_definition(fournis, session.info.trace))

    contexte = serveur.Contexte(dossier_virages=perso, virages_fournis=fournis)
    definition, chemin = serveur._definition(contexte, session)
    assert chemin.parent == perso and chemin.is_file()
    assert definition.virages[0].nom == "Livré"


def test_la_page_s_affiche_meme_sans_dossier_de_telemetrie(tmp_path, monkeypatch) -> None:
    """Sans dossier trouvé, la page doit quand même s'afficher : c'est elle qui
    permet de l'indiquer. Constaté : chaque requête, fichiers de la page
    compris, cherchait d'abord le dossier et échouait."""
    _faux_steam(monkeypatch, [])
    http_serveur = serveur.creer_serveur(0)
    port = http_serveur.server_address[1]
    threading.Thread(target=http_serveur.serve_forever, daemon=True).start()
    try:
        def obtenir(chemin: str) -> tuple[int, bytes]:
            connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connexion.request("GET", chemin)
            reponse = connexion.getresponse()
            return reponse.status, reponse.read()

        statut, page = obtenir("/")
        assert statut == 200 and b"<html" in page
        statut, corps = obtenir("/api/sessions")
        assert statut == 400
        assert json.loads(corps)["code"] == "dossier_introuvable"
    finally:
        http_serveur.shutdown()
        http_serveur.server_close()


def test_le_lanceur_reconnait_un_outil_deja_ouvert() -> None:
    """Un double-clic de trop ne doit pas échouer sur un port occupé : le
    lanceur reconnaît l'outil déjà ouvert et se contente d'afficher sa page."""
    from lmu_telemetry import lanceur

    http_serveur = serveur.creer_serveur(0)
    port = http_serveur.server_address[1]
    threading.Thread(target=http_serveur.serve_forever, daemon=True).start()
    try:
        assert lanceur.outil_deja_ouvert(port)
    finally:
        http_serveur.shutdown()
        http_serveur.server_close()
    assert not lanceur.outil_deja_ouvert(port)
