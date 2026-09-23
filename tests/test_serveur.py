"""Tests du serveur local : ce qui touche aux fichiers et aux caches.

Les routes elles-mêmes sont de simples mises en forme ; ce qui mérite d'être
testé, c'est ce qui peut désynchroniser la page de ce qu'il y a sur le disque.
"""

from __future__ import annotations

import json
from pathlib import Path

from lmu_telemetry.session import Session
from lmu_telemetry.virages import DefinitionCircuit, Virage, fichier_definition
from lmu_telemetry.web import serveur


def test_une_retouche_du_fichier_de_virages_est_prise_en_compte(
    session_test: Path, tmp_path: Path
) -> None:
    """Le README invite à corriger le découpage à la main, dans le fichier du
    circuit. La correction doit apparaître sans redémarrer le serveur.

    Le cache était indexé par le seul chemin du fichier : une retouche faite
    pendant que le serveur tournait était ignorée, sans aucun signe.
    """
    serveur._cache_virages.clear()
    contexte = serveur.Contexte(dossier_virages=tmp_path)
    session = Session.ouvrir(session_test)

    # Le circuit de test est un anneau trop large pour que la détection y
    # trouve un virage : on part donc d'un découpage écrit d'avance.
    chemin = fichier_definition(tmp_path, session.info.trace)
    DefinitionCircuit(
        circuit=session.info.trace,
        longueur=3725.0,
        virages=(Virage(1, 100.0, 200.0, 50.0),),
    ).enregistrer(chemin)

    avant, _ = serveur._definition(contexte, session)
    assert avant.virages[0].nom == ""

    brut = json.loads(chemin.read_text(encoding="utf-8"))
    brut["virages"][0]["nom"] = "Mon virage"
    brut["automatique"] = False
    chemin.write_text(json.dumps(brut, ensure_ascii=False), encoding="utf-8")

    apres, _ = serveur._definition(contexte, session)
    assert apres.virages[0].nom == "Mon virage"
    assert apres.automatique is False


def test_le_fichier_de_virages_est_ecrit_d_un_bloc(session_test: Path, tmp_path: Path) -> None:
    """Aucun fichier temporaire ne doit traîner après l'écriture, et le
    fichier final doit être lisible."""
    serveur._cache_virages.clear()
    contexte = serveur.Contexte(dossier_virages=tmp_path)
    _, chemin = serveur._definition(contexte, Session.ouvrir(session_test))
    assert [p.name for p in tmp_path.iterdir()] == [chemin.name]
    json.loads(chemin.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# Ce que la page a le droit de demander
# ----------------------------------------------------------------------


def test_session_du_dossier_acceptee(tmp_path: Path) -> None:
    session = tmp_path / "Circuit_P_2026-09-20T10_00_00Z.duckdb"
    session.write_bytes(b"")
    serveur._verifier_chemins(serveur.Contexte(dossier=tmp_path), {"chemin": [str(session)]})


def test_fichier_hors_du_dossier_refuse(tmp_path: Path) -> None:
    """La page transmet le chemin des fichiers à ouvrir ; le serveur ouvrait
    n'importe quel fichier du disque."""
    import pytest

    dossier = tmp_path / "Telemetry"
    dossier.mkdir()
    ailleurs = tmp_path / "ailleurs.duckdb"
    ailleurs.write_bytes(b"")
    contexte = serveur.Contexte(dossier=dossier)
    for cle in serveur.PARAMETRES_CHEMIN:
        with pytest.raises(serveur.CheminRefuse):
            serveur._verifier_chemins(contexte, {cle: [str(ailleurs)]})


def test_remontee_de_dossier_refusee(tmp_path: Path) -> None:
    """Un chemin qui commence dans le dossier mais en ressort par « .. »."""
    import pytest

    dossier = tmp_path / "Telemetry"
    dossier.mkdir()
    (tmp_path / "secret.duckdb").write_bytes(b"")
    detour = str(dossier / ".." / "secret.duckdb")
    with pytest.raises(serveur.CheminRefuse):
        serveur._verifier_chemins(serveur.Contexte(dossier=dossier), {"ref": [detour]})


def test_autre_extension_refusee(tmp_path: Path) -> None:
    import pytest

    autre = tmp_path / "notes.txt"
    autre.write_text("x", encoding="utf-8")
    with pytest.raises(serveur.CheminRefuse):
        serveur._verifier_chemins(serveur.Contexte(dossier=tmp_path), {"chemin": [str(autre)]})


def test_hotes_locaux_acceptes() -> None:
    for hote in ("127.0.0.1:8770", "localhost:8770", "127.0.0.1", "LOCALHOST:1"):
        assert serveur._hote_accepte(hote), hote


def test_autres_hotes_refuses() -> None:
    """Une page web qui fait résoudre son propre domaine vers 127.0.0.1 envoie
    SON nom dans l'en-tête Host : c'est ce qui permet de la reconnaître."""
    for hote in ("attaquant.example:8770", "127.0.0.1.attaquant.example", "", None):
        assert not serveur._hote_accepte(hote), hote
