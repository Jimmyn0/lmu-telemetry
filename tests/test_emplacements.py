"""Le dossier de données. L'outil s'appelait « Télémétrie LMU » : au lancement, le dossier
de l'ancien nom prend le nouveau, et rien ne repart de zéro.

Tout se passe dans un dossier temporaire : LOCALAPPDATA y est redirigé, et la variable
LMU_DONNEES, posée pour tous les tests par conftest.py, est retirée (sinon les données
iraient tout droit dans le dossier qu'elle désigne).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lmu_telemetry import emplacements, lanceur


@pytest.fixture
def locales(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv(emplacements.VARIABLE_DONNEES, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


def _ancien(locales: Path) -> Path:
    ancien = locales / "Telemetrie LMU"
    (ancien / "virages").mkdir(parents=True)
    (ancien / "reglages.json").write_text('{"langue": "fr"}', encoding="utf-8")
    return ancien


def test_sans_ancien_dossier_les_donnees_vont_sous_le_nouveau_nom(locales: Path) -> None:
    assert emplacements.donnees() == locales / "GhostLine"
    assert emplacements.migrer_ancien_dossier() is False
    assert not (locales / "GhostLine").exists()


def test_l_ancien_dossier_prend_le_nouveau_nom(locales: Path) -> None:
    ancien = _ancien(locales)
    # Avant le lancement, l'outil lit encore l'ancien dossier.
    assert emplacements.donnees() == ancien
    assert emplacements.migrer_ancien_dossier() is True
    nouveau = locales / "GhostLine"
    assert emplacements.donnees() == nouveau
    assert not ancien.exists()
    assert (nouveau / "reglages.json").read_text(encoding="utf-8") == '{"langue": "fr"}'
    assert (nouveau / "virages").is_dir()
    # Une seule fois.
    assert emplacements.migrer_ancien_dossier() is False


def test_un_renommage_refuse_garde_l_ancien_dossier(locales: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ancien = _ancien(locales)

    def refuse(self, cible):
        raise PermissionError(32, "Le fichier est utilisé par un autre processus")

    monkeypatch.setattr(Path, "rename", refuse)
    assert emplacements.migrer_ancien_dossier() is False
    # L'ancien dossier continue de servir ; on réessaiera au lancement suivant.
    assert emplacements.donnees() == ancien
    assert (ancien / "reglages.json").is_file()


def test_le_nouveau_dossier_l_emporte_et_l_ancien_reste_intact(locales: Path) -> None:
    ancien = _ancien(locales)
    (locales / "GhostLine").mkdir()
    assert emplacements.donnees() == locales / "GhostLine"
    assert emplacements.migrer_ancien_dossier() is False
    assert (ancien / "reglages.json").is_file()


def test_un_dossier_impose_n_est_jamais_deplace(
    locales: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    ancien = _ancien(locales)
    impose = tmp_path_factory.mktemp("ailleurs")
    monkeypatch.setenv(emplacements.VARIABLE_DONNEES, str(impose))
    assert emplacements.donnees() == impose
    assert emplacements.migrer_ancien_dossier() is False
    assert ancien.is_dir()


@pytest.mark.parametrize("deja_ouvert", [True, False])
def test_au_lancement_rien_ne_bouge_sous_une_fenetre_deja_ouverte(
    locales: Path, monkeypatch: pytest.MonkeyPatch, deja_ouvert: bool
) -> None:
    ancien = _ancien(locales)
    monkeypatch.setattr(lanceur, "outil_deja_ouvert", lambda port: deja_ouvert)
    lanceur.reprendre_ancien_dossier()
    # Une fenêtre de l'outil déjà ouverte se sert encore de l'ancien dossier.
    assert ancien.is_dir() is deja_ouvert
    assert (locales / "GhostLine").is_dir() is not deja_ouvert
