"""Où l'outil range ses fichiers, qu'il tourne depuis le code source ou en .exe.

Il y a deux sortes de fichiers, et elles ne peuvent pas vivre au même endroit :

* les RESSOURCES livrées avec l'outil — la page web, les découpages de circuit
  de référence, les logos libres de droits. En lecture seule. Dans le .exe,
  PyInstaller les extrait à chaque lancement dans un dossier temporaire, effacé
  à la fermeture : une retouche faite là serait perdue.

* les DONNÉES de l'utilisateur — découpages retouchés à la main, logos ajoutés,
  réglages. Elles vont dans `%LOCALAPPDATA%\\Telemetrie LMU`, qui ne dépend pas
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

#: Nom du dossier de données, et nom affiché de l'application.
NOM_APPLI = "Telemetrie LMU"

#: Variable d'environnement pour ranger les données ailleurs (tests, dépannage).
VARIABLE_DONNEES = "LMU_DONNEES"

#: Ressources livrées avec l'outil. `__file__` désigne le bon dossier dans les
#: deux cas : à côté du code source, ou dans le dossier d'extraction du .exe.
RESSOURCES = Path(__file__).parent / "ressources"


def donnees() -> Path:
    """Dossier des données de l'utilisateur. Il n'est pas créé ici."""
    if brut := os.environ.get(VARIABLE_DONNEES):
        return Path(brut)
    base = os.environ.get("LOCALAPPDATA")
    racine = Path(base) if base else Path.home() / "AppData" / "Local"
    return racine / NOM_APPLI


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
