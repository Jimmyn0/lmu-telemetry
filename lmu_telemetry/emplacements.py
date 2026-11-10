"""Où l'outil range ses fichiers, qu'il tourne depuis le code source ou en .exe.

Il y a deux sortes de fichiers, et elles ne peuvent pas vivre au même endroit :

* les RESSOURCES livrées avec l'outil — la page web, les découpages de circuit
  de référence, les logos libres de droits. En lecture seule. Dans le .exe,
  PyInstaller les extrait à chaque lancement dans un dossier temporaire, effacé
  à la fermeture : une retouche faite là serait perdue.

* les DONNÉES de l'utilisateur — découpages retouchés à la main, logos ajoutés,
  réglages. Elles vont dans `%LOCALAPPDATA%\\GhostLine`, qui ne dépend pas
  de l'endroit où se trouve le .exe et survit donc à son remplacement par une
  nouvelle version.

Un découpage de circuit livré avec l'outil est recopié dans les données de
l'utilisateur la première fois qu'il sert (voir `web/serveur.py`) : c'est cette
copie qu'on retouche, et c'est elle qui fait foi ensuite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: Nom du dossier de données. L'outil s'appelait « Télémétrie LMU » jusqu'au 2026-11-10 :
#: le dossier de son ancien nom est repris au lancement (`migrer_ancien_dossier`).
NOM_APPLI = "GhostLine"
ANCIEN_NOM_APPLI = "Telemetrie LMU"

#: Variable d'environnement pour ranger les données ailleurs (tests, dépannage).
VARIABLE_DONNEES = "LMU_DONNEES"

#: Ressources livrées avec l'outil. `__file__` désigne le bon dossier dans les
#: deux cas : à côté du code source, ou dans le dossier d'extraction du .exe.
RESSOURCES = Path(__file__).parent / "ressources"


def _racine() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) if base else Path.home() / "AppData" / "Local"


def donnees() -> Path:
    """Dossier des données de l'utilisateur. Il n'est pas créé ici.

    Tant que le dossier de l'ancien nom de l'outil n'a pas pu prendre le nouveau (voir
    `migrer_ancien_dossier`), c'est lui qui sert : on ne repart pas de zéro.
    """
    if brut := os.environ.get(VARIABLE_DONNEES):
        return Path(brut)
    nouveau, ancien = _racine() / NOM_APPLI, _racine() / ANCIEN_NOM_APPLI
    return ancien if not nouveau.exists() and ancien.is_dir() else nouveau


def migrer_ancien_dossier() -> bool:
    """Donne au dossier de données le nouveau nom de l'outil, s'il porte encore l'ancien.

    À appeler une fois, au lancement, avant que rien n'y soit ouvert. Si le renommage
    échoue (un fichier encore ouvert ailleurs), l'ancien dossier continue de servir, et
    on réessaiera au lancement suivant. Vrai si le dossier vient d'être renommé.
    """
    if os.environ.get(VARIABLE_DONNEES):
        return False
    nouveau, ancien = _racine() / NOM_APPLI, _racine() / ANCIEN_NOM_APPLI
    if nouveau.exists() or not ancien.is_dir():
        return False
    try:
        ancien.rename(nouveau)
    except OSError:
        return False
    return True


def virages_utilisateur() -> Path:
    return donnees() / "virages"


def logos_utilisateur() -> Path:
    return donnees() / "logos"


def virages_fournis() -> Path:
    return RESSOURCES / "virages"


def logos_fournis() -> Path:
    return RESSOURCES / "logos"


def fichier_reglages() -> Path:
    return donnees() / "reglages.json"


def fichier_index() -> Path:
    return donnees() / "index.sqlite"


def fichier_parametres() -> Path:
    return donnees() / "parametres.json"


def lire_reglages() -> dict:
    """Réglages enregistrés. Un fichier absent ou abîmé vaut « aucun réglage »."""
    try:
        brut = json.loads(fichier_reglages().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return brut if isinstance(brut, dict) else {}


def enregistrer_reglages(reglages: dict) -> None:
    """Écrit les réglages d'un coup : jamais de fichier à moitié écrit."""
    chemin = fichier_reglages()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    provisoire = chemin.with_suffix(".tmp")
    provisoire.write_text(json.dumps(reglages, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(provisoire, chemin)
