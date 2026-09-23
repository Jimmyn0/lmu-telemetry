"""Tests de la deuxième source de données : les fichiers de résultats du jeu.

Aucun de ces tests n'a besoin que Le Mans Ultimate soit installé : les XML sont
fabriqués ici, à l'image de ceux du jeu. Les seuls tests qui touchent aux vrais
fichiers sont marqués et se sautent tout seuls ailleurs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lmu_telemetry import pays, resultats
from lmu_telemetry.errors import DossierIntrouvable

# Un fichier de résultats réduit à ce dont on se sert, mais avec la même
# structure que ceux du jeu : en-tête, bloc de session, blocs pilote.
MODELE_XML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE rF [
<!ENTITY rFEnt "rFactor Entity">
]>
<rFactorXML version="1.0">
<RaceResults>
<Setting>Multiplayer</Setting>
<DateTime>1788729028</DateTime>
<TimeString>2026/09/06 23:10:28</TimeString>
<TrackVenue>{circuit}</TrackVenue>
<TrackLength>5793.0</TrackLength>
<{bloc}>
<DateTime>1788729802</DateTime>
{pilotes}
</{bloc}>
</RaceResults>
</rFactorXML>
"""

PILOTE = """<Driver>
<Name>{nom}</Name>
<VehName>{engagement}</VehName>
<CarType>{modele}</CarType>
<CarClass>{classe}</CarClass>
</Driver>"""


def ecrire(dossier: Path, nom: str, pilotes: list[tuple], bloc: str = "Practice1",
           circuit: str = "Autodromo Nazionale Monza") -> Path:
    corps = "\n".join(
        PILOTE.format(nom=n, engagement=e, modele=m, classe=c) for n, e, m, c in pilotes
    )
    chemin = dossier / nom
    chemin.write_text(
        MODELE_XML.format(circuit=circuit, bloc=bloc, pilotes=corps), encoding="utf-8"
    )
    return chemin


@pytest.fixture
def resultats_test(tmp_path: Path) -> Path:
    dossier = tmp_path / "Results"
    dossier.mkdir()
    ecrire(
        dossier,
        "a-01P1.xml",
        [
            ("Jimmy Larbi#1", "Manthey DK Engineering 2026 #91:WEC",
             "Porsche 911 GT3 R LMGT3", "GT3"),
            ("Autre Pilote#2", "Team WRT 2026 #32:WEC", "BMW M4 LMGT3", "GT3"),
        ],
    )
    ecrire(
        dossier,
        "b-02R1.xml",
        [("Troisieme#3", "VDS Panis Racing #48:ELMS25", "Oreca 07", "LMP2_ELMS")],
        bloc="Race",
    )
    return dossier


# ----------------------------------------------------------------------
# Index des voitures
# ----------------------------------------------------------------------


def test_index_relie_engagement_et_modele(resultats_test: Path) -> None:
    """C'est tout l'objet du module : le fichier de télémétrie ne connaît que
    l'engagement, le modèle n'existe que dans les résultats."""
    index = resultats.index_voitures(resultats_test)
    assert len(index) == 3
    porsche = index["Manthey DK Engineering 2026 #91:WEC"]
    assert porsche.modele == "Porsche 911 GT3 R LMGT3"
    assert porsche.marque == "Porsche"
    assert porsche.classe == "GT3"


def test_index_couvre_tous_les_pilotes_pas_seulement_le_joueur(
    resultats_test: Path,
) -> None:
    """Une voiture qu'on n'a jamais pilotée doit quand même être indexée : elle
    peut apparaître comme adversaire ici et comme la nôtre dans une autre
    session."""
    index = resultats.index_voitures(resultats_test)
    assert "Team WRT 2026 #32:WEC" in index


def test_index_tolere_un_fichier_illisible(resultats_test: Path) -> None:
    """Un fichier sur 414 est tronqué chez l'utilisateur : il ne doit pas
    emporter les 413 autres."""
    (resultats_test / "casse.xml").write_text("<rFactorXML><RaceRes", encoding="utf-8")
    resultats._cache.clear()
    assert len(resultats.index_voitures(resultats_test)) == 3


def test_dossier_absent_donne_un_index_vide(tmp_path: Path) -> None:
    """Le modèle est un agrément : son absence ne doit pas empêcher d'ouvrir
    une session."""
    assert resultats.index_voitures(tmp_path / "nulle part") == {}


def test_cache_invalide_par_un_nouveau_fichier(resultats_test: Path) -> None:
    resultats._cache.clear()
    assert len(resultats.index_voitures(resultats_test)) == 3
    ecrire(
        resultats_test,
        "c-03Q1.xml",
        [("Quatrieme#4", "Iron Lynx 2026 #61:LM", "Mercedes-AMG LMGT3", "GT3")],
        bloc="Qualify",
    )
    assert len(resultats.index_voitures(resultats_test)) == 4


# ----------------------------------------------------------------------
# Marques
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "modele, attendu",
    [
        ("Porsche 911 GT3 R LMGT3", "Porsche"),
        ("Ferrari 296 LMGT3 Evo", "Ferrari"),
        ("BMW M Hybrid V8", "BMW"),
        ("Oreca 07", "Oreca"),
        ("ADESS AD25 LMP3", "ADESS"),
        ("Toyota GR010", "Toyota"),
        # Les deux cas qui ne se devinent pas au premier mot.
        ("Corvette C8.R GTE", "Chevrolet"),
        ("Mercedes-AMG LMGT3", "Mercedes"),
        # Deux mots : le préfixe le plus long doit gagner.
        ("Aston Martin Vantage AMR LMGT3", "Aston Martin"),
        ("Isotta Fraschini TIPO6", "Isotta Fraschini"),
        # Marque inconnue : on rend le premier mot plutôt que rien, pour qu'une
        # voiture ajoutée par une mise à jour s'affiche sans toucher au code.
        ("Bugatti Type 57G", "Bugatti"),
        ("", ""),
    ],
)
def test_marque_deduite_du_modele(modele: str, attendu: str) -> None:
    assert resultats.marque(modele) == attendu


# ----------------------------------------------------------------------
# Emplacement
# ----------------------------------------------------------------------


def test_dossier_deduit_de_celui_de_la_telemetrie(tmp_path: Path) -> None:
    """Les deux dossiers sont frères sous UserData : inutile de demander le
    second à l'utilisateur."""
    telemetrie = tmp_path / "UserData" / "Telemetry"
    telemetrie.mkdir(parents=True)
    attendu = tmp_path / "UserData" / "Log" / "Results"
    assert resultats.dossier_resultats(telemetrie=telemetrie) == attendu


def test_dossier_force_inexistant_est_signale(tmp_path: Path) -> None:
    with pytest.raises(DossierIntrouvable):
        resultats.dossier_resultats(force=tmp_path / "absent")


# ----------------------------------------------------------------------
# Pays des circuits
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "circuit, code",
    [
        ("Autodromo Nazionale Monza", "IT"),
        ("Circuit de Spa-Francorchamps", "BE"),
        ("Circuit de la Sarthe", "FR"),
        ("Fuji Speedway", "JP"),
        ("Algarve International Circuit", "PT"),
        ("Bahrain International Circuit", "BH"),
        ("Autódromo José Carlos Pace", "BR"),
        ("Lusail International Circuit", "QA"),
        ("Sebring International Raceway", "US"),
        # Circuits installés avec le jeu mais jamais roulés ici.
        ("Circuit de Barcelona-Catalunya", "ES"),
        ("Silverstone Circuit", "GB"),
        ("Autodromo Enzo e Dino Ferrari", "IT"),
    ],
)
def test_pays_reconnu(circuit: str, code: str) -> None:
    trouve = pays.pays_du_circuit(circuit)
    assert trouve is not None and trouve.code == code


def test_circuit_inconnu_ne_donne_pas_de_pays() -> None:
    """Pas de drapeau vaut mieux qu'un mauvais drapeau."""
    assert pays.pays_du_circuit("Circuit Imaginaire de Nulle Part") is None


def test_supplement_ajoute_un_circuit(tmp_path: Path) -> None:
    (tmp_path / pays.FICHIER_SUPPLEMENT).write_text(
        '{"nordschleife": "DE"}', encoding="utf-8"
    )
    trouve = pays.pays_du_circuit("Nordschleife", tmp_path)
    assert trouve is not None and trouve.code == "DE"


def test_supplement_illisible_est_ignore(tmp_path: Path) -> None:
    (tmp_path / pays.FICHIER_SUPPLEMENT).write_text("{ pas du json", encoding="utf-8")
    trouve = pays.pays_du_circuit("Autodromo Nazionale Monza", tmp_path)
    assert trouve is not None and trouve.code == "IT"
