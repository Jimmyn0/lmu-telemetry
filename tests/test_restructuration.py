"""Tests de ce que la restructuration de la v2 a corrigé ou ajouté : fichiers
abîmés, mesures d'un virage, seuils réglables, caches.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from lmu_telemetry import emplacements, parametres
from lmu_telemetry.cache import CacheBorne
from lmu_telemetry.domaine import donnees_tour
from lmu_telemetry.domaine.donnees_tour import CANAL_GAZ_BRUT, charger, charger_tours
from lmu_telemetry.domaine.session import Session
from lmu_telemetry.domaine.virages import (
    SANS_FREINER,
    DefinitionCircuit,
    Virage,
    ecarts_par_virage,
    mesurer,
)
from lmu_telemetry.errors import ErreurTelemetrie, FichierIllisible
from lmu_telemetry.parametres import SeuilsVirage
from lmu_telemetry.sources.reader import FichierSession

# ----------------------------------------------------------------------
# Fichiers abîmés
# ----------------------------------------------------------------------


@pytest.mark.parametrize("contenu", [b"pas une base" * 100, b""])
def test_un_fichier_abime_donne_une_erreur_lisible(tmp_path: Path, contenu: bytes) -> None:
    chemin = tmp_path / "abime.duckdb"
    chemin.write_bytes(contenu)
    with pytest.raises(FichierIllisible, match="abime.duckdb"):
        FichierSession(chemin)


# ----------------------------------------------------------------------
# Mesures d'un virage
# ----------------------------------------------------------------------

DEBUT, FIN = 1000.0, 1100.0


@pytest.fixture
def definition(session_test: Path) -> DefinitionCircuit:
    return DefinitionCircuit(
        circuit="Circuit de test",
        longueur=charger(session_test, 1).longueur,
        virages=(Virage(1, DEBUT, FIN, 50.0),),
    )


def _tour(session_test: Path, gaz, frein, gaz_brut=None):
    """Un tour à 50 m/s, dont les pédales dépendent de la distance.

    La vitesse est à son plus bas à 1 050 m, au milieu du virage.
    """
    tour = charger(session_test, 1)
    d = tour.distance
    canaux = dict(tour.canaux)
    canaux["Ground Speed"] = 180.0 - 100.0 * np.exp(-(((d - 1050.0) / 40.0) ** 2))
    canaux["Throttle Pos"] = gaz(d)
    canaux["Brake Pos"] = frein(d)
    if gaz_brut is not None:
        canaux[CANAL_GAZ_BRUT] = gaz_brut(d)
    return replace(tour, canaux=canaux)


def _plage(debut: float, fin: float, valeur: float = 100.0):
    return lambda d: np.where((d >= debut) & (d < fin), valeur, 0.0)


def _remarques(mesure) -> set[str]:
    return {r.cle for r in mesure.remarques}


def test_un_coup_de_gaz_relache_n_est_pas_la_remise_des_gaz(session_test, definition) -> None:
    """La remise des gaz était le premier franchissement du seuil : elle masquait
    justement les hésitations en sortie de virage."""
    tour = _tour(
        session_test,
        gaz=lambda d: _plage(1060, 1062)(d) + _plage(1090, 9999)(d),
        frein=_plage(900, 1000),
    )
    assert mesurer(tour, definition)[0].remise_gaz == pytest.approx(1090, abs=2)


def test_la_remise_des_gaz_lit_le_geste_du_pilote(session_test, definition) -> None:
    """Les coupures automatiques de `Throttle Pos` ne sont pas un lever de pied."""
    tour = _tour(
        session_test,
        gaz=lambda d: _plage(1060, 1062)(d) + _plage(1090, 9999)(d),
        frein=_plage(900, 1000),
        gaz_brut=_plage(1060, 9999),
    )
    assert mesurer(tour, definition)[0].remise_gaz == pytest.approx(1060, abs=2)


def test_une_pedale_deja_enfoncee_n_est_pas_un_point_de_freinage(
    session_test, definition
) -> None:
    """Le début de zone passait pour le point de freinage du virage."""
    tour = _tour(session_test, gaz=_plage(1060, 9999), frein=_plage(0, 1010))
    mesure = mesurer(tour, definition)[0]
    assert mesure.debut_freinage is None
    assert _remarques(mesure) == {"serveur.virage.freinage_precedent"}


def test_un_freinage_apres_le_point_lent_prepare_le_virage_suivant(
    session_test, definition
) -> None:
    tour = _tour(session_test, gaz=_plage(1060, 1100), frein=_plage(1150, 1190))
    mesure = mesurer(tour, definition)[0]
    assert mesure.debut_freinage is None
    assert SANS_FREINER in _remarques(mesure)


def test_le_point_de_freinage_est_la_premiere_attaque(session_test, definition) -> None:
    tour = _tour(session_test, gaz=_plage(1060, 9999), frein=_plage(900, 1000))
    mesure = mesurer(tour, definition)[0]
    assert mesure.debut_freinage == pytest.approx(900, abs=2)
    assert mesure.distance_freinage == pytest.approx(100, abs=2)


def test_les_ecarts_par_virage_s_additionnent(session_test: Path) -> None:
    """Une colonne de temps qui ne totalise pas l'écart du tour serait trompeuse."""
    a, b = charger(session_test, 1), charger(session_test, 3)
    definition = DefinitionCircuit(
        circuit="Circuit de test",
        longueur=min(a.longueur, b.longueur),
        virages=(Virage(1, 500.0, 600.0, 50.0), Virage(2, 2000.0, 2100.0, 50.0)),
    )
    ecarts = ecarts_par_virage(a, b, definition)
    axe = np.arange(0.0, min(a.longueur, b.longueur), 1.0)
    final = float((b.temps_a_distance(axe) - a.temps_a_distance(axe))[-1])
    assert sum(e.delta_zone for e in ecarts) == pytest.approx(final, abs=1e-6)


# ----------------------------------------------------------------------
# Seuils réglables
# ----------------------------------------------------------------------


def _ecrire(contenu: object) -> None:
    chemin = emplacements.fichier_parametres()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu), encoding="utf-8")


def test_sans_fichier_les_valeurs_par_defaut_s_appliquent() -> None:
    assert parametres.lire().virages == SeuilsVirage()


def test_le_modele_contient_tous_les_reglages_et_se_relit() -> None:
    parametres.creer_modele()
    brut = json.loads(emplacements.fichier_parametres().read_text(encoding="utf-8"))
    assert brut["virages"]["frein"] == SeuilsVirage().frein
    assert parametres.lire().virages == SeuilsVirage()


def test_le_modele_n_ecrase_pas_les_reglages() -> None:
    _ecrire({"virages": {"frein": 7.5}})
    parametres.creer_modele()
    assert parametres.lire().virages.frein == 7.5


def test_une_valeur_partielle_garde_les_autres() -> None:
    _ecrire({"virages": {"frein": 7}})
    lus = parametres.lire().virages
    assert lus.frein == 7.0
    assert lus.gaz == SeuilsVirage().gaz


def test_une_retouche_est_prise_en_compte_sans_redemarrer() -> None:
    _ecrire({"virages": {"frein": 7}})
    assert parametres.lire().virages.frein == 7.0
    _ecrire({"virages": {"frein": 8, "gaz": 20}})
    assert parametres.lire().virages.frein == 8.0


@pytest.mark.parametrize(
    "contenu, attendu",
    [
        ({"virages": {"frien": 3}}, "virages.frien"),
        ({"virage": {}}, "virage"),
        ({"virages": {"frein": "3 %"}}, "virages.frein"),
        ({"virages": {"frein": -1}}, "virages.frein"),
        ({"virages": {"frein": True}}, "virages.frein"),
        ({"virages": 3}, "virages"),
        ([1, 2], "réglages"),
    ],
)
def test_une_erreur_de_saisie_designe_le_fichier(contenu, attendu) -> None:
    """Ignorer une faute de frappe laisserait croire qu'un réglage est pris en compte."""
    _ecrire(contenu)
    with pytest.raises(ErreurTelemetrie) as erreur:
        parametres.lire()
    assert "parametres.json" in str(erreur.value)
    assert attendu in str(erreur.value)


def test_un_fichier_mal_forme_designe_le_fichier() -> None:
    chemin = emplacements.fichier_parametres()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("{ pas du json", encoding="utf-8")
    with pytest.raises(ErreurTelemetrie, match="parametres.json"):
        parametres.lire()


def test_les_seuils_changent_les_mesures(session_test, definition) -> None:
    tour = _tour(session_test, gaz=_plage(1060, 9999), frein=_plage(900, 1000, valeur=5.0))
    assert mesurer(tour, definition)[0].debut_freinage is not None
    sensible = mesurer(tour, definition, seuils=SeuilsVirage(frein=10.0))[0]
    assert sensible.debut_freinage is None


# ----------------------------------------------------------------------
# Caches
# ----------------------------------------------------------------------


def test_le_cache_oublie_ce_qui_a_servi_le_moins_recemment() -> None:
    cache: CacheBorne[str, int] = CacheBorne(2)
    cache["a"], cache["b"] = 1, 2
    assert cache.get("a") == 1
    cache["c"] = 3
    assert "b" not in cache
    assert "a" in cache
    assert len(cache) == 2


def test_le_cache_ne_recalcule_pas() -> None:
    cache: CacheBorne[str, int] = CacheBorne(2)
    appels = []
    for _ in range(3):
        assert cache.obtenir("a", lambda: appels.append(1) or 7) == 7
    assert len(appels) == 1


def _compter_ouvertures(monkeypatch) -> list:
    ouvertures = []
    vraie = donnees_tour.FichierSession

    class Compteur(vraie):
        def __init__(self, chemin):
            ouvertures.append(chemin)
            super().__init__(chemin)

    monkeypatch.setattr(donnees_tour, "FichierSession", Compteur)
    return ouvertures


def test_plusieurs_tours_n_ouvrent_le_fichier_qu_une_fois(
    session_test: Path, tmp_path: Path, monkeypatch
) -> None:
    copie = tmp_path / "copie.duckdb"
    copie.write_bytes(session_test.read_bytes())
    ouvertures = _compter_ouvertures(monkeypatch)
    numeros = [t.numero for t in Session.ouvrir(copie).tours_valides]
    assert len(numeros) >= 2
    charger_tours(copie, numeros)
    assert len(ouvertures) == 1
    charger_tours(copie, numeros)
    assert len(ouvertures) == 1  # tout vient du cache


def test_un_fichier_reecrit_est_relu(session_test: Path, tmp_path: Path, monkeypatch) -> None:
    copie = tmp_path / "copie.duckdb"
    copie.write_bytes(session_test.read_bytes())
    ouvertures = _compter_ouvertures(monkeypatch)
    charger(copie, 1)
    copie.write_bytes(session_test.read_bytes() + b"\0" * 4096)
    try:
        charger(copie, 1)
    except ErreurTelemetrie:
        pass  # peu importe que le fichier retouché soit lisible : il a été rouvert
    assert len(ouvertures) == 2


def test_modifier_un_tour_ne_touche_pas_le_cache(session_test: Path) -> None:
    """Le cache partage les tours entre les requêtes."""
    tour = charger(session_test, 1)
    tour.canaux["Ground Speed"] = np.zeros_like(tour.temps)
    assert charger(session_test, 1).canaux["Ground Speed"].max() > 0


def test_les_tableaux_partages_refusent_l_ecriture(session_test: Path) -> None:
    tour = charger(session_test, 1)
    with pytest.raises(ValueError):
        tour.canaux["Ground Speed"][0] = 0.0
    with pytest.raises(ValueError):
        tour.distance[0] = 0.0


def test_sur_distance_peut_se_limiter_a_quelques_canaux(session_test: Path) -> None:
    tour = charger(session_test, 1)
    axe = np.arange(0.0, 100.0, 1.0)
    assert set(tour.sur_distance(axe, ("Ground Speed", "Canal absent"))) == {"Ground Speed"}
    assert len(tour.sur_distance(axe)) == len(tour.canaux)
