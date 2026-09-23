"""Repérage des fichiers de session sur le disque.

Les fichiers restent là où le jeu les écrit : rien n'est copié ni déplacé.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import emplacements
from .errors import DossierIntrouvable

#: Chemin du dossier de télémétrie à l'intérieur d'une bibliothèque Steam.
SOUS_CHEMIN_JEU = ("steamapps", "common", "Le Mans Ultimate")
SOUS_CHEMIN_TELEMETRIE = ("UserData", "Telemetry")

#: Emplacements de Steam essayés quand le registre ne dit rien.
STEAM_HABITUELS = (
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
)

#: Variable d'environnement pour forcer l'emplacement.
VARIABLE_ENV = "LMU_TELEMETRIE"

#: Clé du fichier de réglages qui retient le dossier choisi dans l'interface.
REGLAGE_DOSSIER = "dossier_telemetrie"


@dataclass(frozen=True)
class FichierRepere:
    """Un fichier de session, identifié sans être ouvert."""

    chemin: Path
    circuit: str
    code_type: str
    enregistre_le: datetime | None
    taille: int

    @property
    def journal_present(self) -> bool:
        return self.chemin.with_suffix(self.chemin.suffix + ".wal").exists()


def dossier_telemetrie(force: Path | str | None = None) -> Path:
    """Trouve le dossier de télémétrie de LMU.

    Ordre : le chemin passé en argument, puis la variable d'environnement
    LMU_TELEMETRIE, puis le dossier choisi dans l'interface (réglages), puis
    les bibliothèques Steam de la machine.
    """
    if force is not None:
        chemin = Path(force)
        if not chemin.is_dir():
            raise DossierIntrouvable(chemin)
        return chemin

    if depuis_env := os.environ.get(VARIABLE_ENV):
        chemin = Path(depuis_env)
        if chemin.is_dir():
            return chemin
        raise DossierIntrouvable(chemin)

    # Un dossier choisi puis disparu (disque débranché, jeu déplacé) n'est pas
    # une impasse : on retente la détection avant d'abandonner.
    if choisi := emplacements.lire_reglages().get(REGLAGE_DOSSIER):
        if Path(choisi).is_dir():
            return Path(choisi)

    jeux = []
    for bibliotheque in bibliotheques_steam():
        jeu = bibliotheque.joinpath(*SOUS_CHEMIN_JEU)
        telemetrie = jeu.joinpath(*SOUS_CHEMIN_TELEMETRIE)
        if telemetrie.is_dir():
            return telemetrie
        if jeu.is_dir():
            jeux.append(jeu)

    # Le jeu est installé mais n'a encore rien enregistré : c'est un autre
    # problème que « jeu introuvable », et il mérite un autre message.
    if jeux:
        raise DossierIntrouvable(jeux[0].joinpath(*SOUS_CHEMIN_TELEMETRIE), jeu_trouve=True)
    raise DossierIntrouvable(None)


def bibliotheques_steam() -> list[Path]:
    """Toutes les bibliothèques Steam de la machine, sans doublon.

    Steam peut installer les jeux sur plusieurs disques ; il tient la liste de
    ces « bibliothèques » dans `steamapps/libraryfolders.vdf`. Sur la machine
    de développement, Steam est sur C: et Le Mans Ultimate sur D: : sans lire
    ce fichier, on ne le trouverait qu'en devinant les lettres de lecteur.
    """
    racines = []
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as cle:
            racines.append(Path(winreg.QueryValueEx(cle, "SteamPath")[0]))
    except (ImportError, OSError):
        pass
    racines += [Path(r) for r in STEAM_HABITUELS]

    trouvees: list[Path] = []
    for racine in racines:
        try:
            texte = (racine / "steamapps" / "libraryfolders.vdf").read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
        trouvees.append(racine)
        trouvees += bibliotheques_du_vdf(texte)

    uniques: dict[str, Path] = {}
    for chemin in trouvees:
        uniques.setdefault(os.path.normcase(os.path.normpath(chemin)), chemin)
    return list(uniques.values())


def bibliotheques_du_vdf(texte: str) -> list[Path]:
    """Les chemins listés dans un `libraryfolders.vdf`.

    Deux formats existent : le récent, `"path"  "D:\\\\SteamLibrary"` dans un
    bloc par bibliothèque, et l'ancien, `"1"  "D:\\\\SteamLibrary"` directement.
    Les barres obliques inverses y sont doublées.
    """
    chemins = []
    for cle, valeur in re.findall(r'"(path|\d+)"\s+"([^"]+)"', texte):
        # Dans l'ancien format, une clé numérique peut aussi être un numéro de
        # jeu suivi d'une taille : seule une valeur qui ressemble à un chemin
        # compte.
        if cle != "path" and ":" not in valeur:
            continue
        chemins.append(Path(valeur.replace("\\\\", "\\")))
    return chemins


def lister(dossier: Path | str | None = None) -> list[FichierRepere]:
    """Liste les sessions présentes, de la plus récente à la plus ancienne.

    Les informations viennent du NOM du fichier, sans l'ouvrir : c'est
    instantané même sur des centaines de sessions, et ça marche aussi sur un
    fichier verrouillé par le jeu.
    """
    racine = dossier_telemetrie(dossier)
    reperes = []
    for chemin in racine.glob("*.duckdb"):
        circuit, code, horodatage = _decouper_nom(chemin.stem)
        reperes.append(
            FichierRepere(
                chemin=chemin,
                circuit=circuit,
                code_type=code,
                enregistre_le=horodatage,
                taille=chemin.stat().st_size,
            )
        )
    return sorted(
        reperes,
        key=lambda f: (f.enregistre_le is not None, f.enregistre_le),
        reverse=True,
    )


def _decouper_nom(nom: str) -> tuple[str, str, datetime | None]:
    """Découpe `Autodromo Nazionale Monza_P_2026-09-08T12_12_19Z`.

    Format observé sur les 378 fichiers : `<circuit>_<P|Q|R>_<date ISO>`, la
    date ayant ses deux-points remplacés par des underscores (interdits dans un
    nom de fichier Windows). On reste tolérant : un nom inattendu ne doit pas
    faire échouer la liste entière.

    Le « Z » final signifie que l'heure est en UTC : il faut le dire
    explicitement, sinon la date passe pour une heure locale et la liste affiche
    une session de 14 h 12 comme datant de 12 h 12.
    """
    morceaux = nom.rsplit("_", 4)
    if len(morceaux) == 5 and len(morceaux[1]) == 1:
        circuit, code = morceaux[0], morceaux[1]
        brut = "_".join(morceaux[2:])
        try:
            date, _, heure = brut.partition("T")
            horodatage = datetime.fromisoformat(
                f"{date}T{heure.rstrip('Z').replace('_', ':')}"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            horodatage = None
        return circuit, code, horodatage
    return nom, "?", None
