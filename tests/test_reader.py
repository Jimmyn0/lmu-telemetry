"""Tests de la couche d'abstraction sur le format LMU."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pytest

from lmu_telemetry.errors import (
    DonneeManquante,
    FichierIntrouvable,
    SchemaInconnu,
    SessionEnCours,
)
from lmu_telemetry.reader import FichierSession
from tests.fixtures import construire as constructeur


# ----------------------------------------------------------------------
# Métadonnées
# ----------------------------------------------------------------------


def test_metadonnees_normalisees(session_test: Path) -> None:
    with FichierSession(session_test) as f:
        info = f.info
    assert info.circuit == "Circuit de test"
    assert info.voiture == "Voiture de test #1"
    assert info.categorie == "GT3"
    assert info.type_session == "Practice"
    assert info.code_type == "P"
    assert info.version_schema == "1"


def test_date_avec_underscores(session_test: Path) -> None:
    """Le jeu écrit `2026-01-02T03_04_05Z` : les « : » sont interdits sous Windows."""
    with FichierSession(session_test) as f:
        date = f.info.enregistree_le
    assert date is not None
    assert (date.year, date.month, date.day) == (2026, 1, 2)
    assert (date.hour, date.minute, date.second) == (3, 4, 5)
    # Le « Z » veut dire UTC : sans cette information, l'heure affichée serait
    # décalée du fuseau du pilote.
    assert date.tzinfo is not None
    assert date.utcoffset().total_seconds() == 0


# ----------------------------------------------------------------------
# Catalogue des canaux et des événements
# ----------------------------------------------------------------------


def test_catalogue_des_canaux(session_test: Path) -> None:
    with FichierSession(session_test) as f:
        canaux = f.canaux
        assert canaux["Ground Speed"].frequence == 100
        assert canaux["Ground Speed"].unite == "km/h"
        assert canaux["Ground Speed"].par_roue is False
        assert canaux["SurfaceTypes"].par_roue is True
        # Même durée de session quelle que soit la fréquence du canal.
        assert canaux["Ground Speed"].duree == pytest.approx(constructeur.DUREE)
        assert canaux["Lap Dist"].duree == pytest.approx(constructeur.DUREE)


def test_forme_des_tableaux(session_test: Path) -> None:
    with FichierSession(session_test) as f:
        assert f.canal("Ground Speed").shape == (int(constructeur.DUREE * 100),)
        # Un canal par roue rend quatre colonnes : AVG, AVD, ARG, ARD.
        assert f.canal("SurfaceTypes").shape == (int(constructeur.DUREE * 5), 4)


def test_canal_inconnu_dit_ou_chercher(session_test: Path) -> None:
    with FichierSession(session_test) as f:
        with pytest.raises(DonneeManquante) as erreur:
            f.canal("Speed")
    # Le message doit orienter, pas seulement constater l'échec.
    assert "Ground Speed" in str(erreur.value)


# ----------------------------------------------------------------------
# Recalage temporel : le cœur de la couche d'abstraction
# ----------------------------------------------------------------------


def test_t0_est_le_premier_evenement(session_test: Path) -> None:
    with FichierSession(session_test) as f:
        assert f.t0 == pytest.approx(100.0)


def test_temps_reconstruits_a_partir_de_la_frequence(session_test: Path) -> None:
    """Les canaux n'ont pas d'horodatage : t = t0 + indice / fréquence."""
    with FichierSession(session_test) as f:
        temps = f.temps_canal("Ground Speed")
        assert temps[0] == pytest.approx(constructeur.T0)
        assert temps[1] == pytest.approx(constructeur.T0 + 0.01)
        assert temps[-1] == pytest.approx(constructeur.FIN - 0.01)


def test_lap_dist_retombe_a_zero_aux_franchissements(session_test: Path) -> None:
    """Contrôle de cohérence du recalage, celui fait à la main sur les vraies
    sessions : à chaque événement `Lap`, la distance parcourue repart de zéro.
    """
    with FichierSession(session_test) as f:
        distances = f.canal("Lap Dist")
        instants, _ = f.evenement("Lap")
        for instant in instants:
            indice = f.indice("Lap Dist", float(instant))
            assert distances[indice] == pytest.approx(0.0, abs=5.0)
            if indice > 0:
                # Juste avant, on était en fin de tour, donc loin de zéro.
                assert distances[indice - 1] > 100.0


def test_indice_reste_dans_les_bornes(session_test: Path) -> None:
    with FichierSession(session_test) as f:
        assert f.indice("Ground Speed", -1e9) == 0
        assert f.indice("Ground Speed", 1e9) == int(constructeur.DUREE * 100) - 1


# ----------------------------------------------------------------------
# Événements
# ----------------------------------------------------------------------


def test_lecture_des_evenements(session_test: Path) -> None:
    with FichierSession(session_test) as f:
        instants, numeros = f.evenement("Lap")
    assert list(instants) == list(constructeur.FRONTIERES)
    assert list(numeros) == list(range(len(constructeur.FRONTIERES)))


def test_valeur_a_prend_la_derniere_connue(session_test: Path) -> None:
    """Un événement n'est écrit qu'au changement : l'état à l'instant t est la
    dernière valeur écrite avant t."""
    with FichierSession(session_test) as f:
        assert f.valeur_a("In Pits", 120.0) == 1  # encore aux stands
        assert f.valeur_a("In Pits", 130.0) == 0  # sortie
        assert f.valeur_a("In Pits", 400.0) == 0  # bien plus tard, toujours en piste
        assert f.valeur_a("In Pits", 50.0, defaut="rien") == "rien"  # avant t0


# ----------------------------------------------------------------------
# Erreurs : elles doivent expliquer quoi faire
# ----------------------------------------------------------------------


def test_fichier_absent(tmp_path: Path) -> None:
    with pytest.raises(FichierIntrouvable) as erreur:
        FichierSession(tmp_path / "rien.duckdb")
    assert "UserData" in str(erreur.value)


def test_version_de_schema_refusee(tmp_path: Path) -> None:
    """Une mise à jour de LMU doit produire un refus net, pas des données fausses."""
    chemin = tmp_path / "futur.duckdb"
    constructeur.construire(chemin)
    con = duckdb.connect(str(chemin))
    con.execute("UPDATE metadata SET value = '2' WHERE key = 'Version'")
    con.close()

    with pytest.raises(SchemaInconnu) as erreur:
        FichierSession(chemin)
    message = str(erreur.value)
    assert "reader.py" in message  # on dit quel fichier corriger
    assert "'2'" in message


def test_fichier_verrouille_par_le_jeu(tmp_path: Path) -> None:
    """Reproduit le cas réel : LMU garde la session en cours ouverte en écriture.

    Le verrou doit venir d'un AUTRE processus. Ouvrir le fichier deux fois dans
    le même processus produit une erreur DuckDB différente, qui ne correspond
    pas à la situation qu'on veut couvrir.
    """
    chemin = tmp_path / "en_cours.duckdb"
    constructeur.construire(chemin)
    pret = tmp_path / "pret"

    geolier = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import duckdb, pathlib, time, sys\n"
            "con = duckdb.connect(sys.argv[1])\n"
            "pathlib.Path(sys.argv[2]).write_text('ok')\n"
            "time.sleep(30)\n",
            str(chemin),
            str(pret),
        ]
    )
    try:
        debut = time.monotonic()
        while not pret.exists() and time.monotonic() - debut < 20:
            time.sleep(0.05)
        if not pret.exists():
            pytest.skip("le processus qui devait verrouiller le fichier n'a pas démarré")

        with pytest.raises(SessionEnCours) as erreur:
            FichierSession(chemin)
        message = str(erreur.value)
        assert "Quitte le jeu" in message
        assert chemin.name in message
    finally:
        geolier.kill()
        geolier.wait(timeout=10)


def test_journal_wal_signale(tmp_path: Path) -> None:
    chemin = tmp_path / "interrompue.duckdb"
    constructeur.construire(chemin)
    Path(str(chemin) + ".wal").write_bytes(b"")
    with FichierSession(chemin) as f:
        assert f.journal_present is True


def test_lecture_seule_ne_modifie_rien(session_test: Path) -> None:
    avant = session_test.stat().st_mtime_ns
    with FichierSession(session_test) as f:
        f.canal("Ground Speed")
        f.evenement("Lap")
    assert session_test.stat().st_mtime_ns == avant


# ----------------------------------------------------------------------
# Sur de vraies sessions, si le jeu est installé sur cette machine
# ----------------------------------------------------------------------


def test_vraies_sessions_lisibles(dossier_lmu: Path | None) -> None:
    if dossier_lmu is None:
        pytest.skip("Le Mans Ultimate n'est pas installé sur cette machine")

    fichiers = sorted(dossier_lmu.glob("*.duckdb"))[:20]
    if not fichiers:
        pytest.skip("aucune session enregistrée")

    for chemin in fichiers:
        try:
            with FichierSession(chemin) as f:
                assert f.info.version_schema == "1"
                assert f.t0 >= 0
                # Le recalage doit tenir sur toute la durée réelle.
                distances = f.canal("Lap Dist")
                instants, _ = f.evenement("Lap")
                for instant in instants[1:]:
                    indice = f.indice("Lap Dist", float(instant))
                    voisinage = distances[max(0, indice - 1) : indice + 2]
                    assert np.min(voisinage) < 50.0, (
                        f"{chemin.name} : pas de remise à zéro de Lap Dist "
                        f"au franchissement t={instant}"
                    )
        except SessionEnCours:
            pass  # le jeu tourne : ce cas est déjà couvert par un test dédié
