"""Construit le .exe à partager, et l'archive qui l'accompagne.

    construire-exe.bat          (double-clic : c'est la façon normale)
    tools\\construire_exe.py     (double-clic : marche aussi)

Étapes, dans l'ordre, chacune arrêtant tout si elle échoue :

1. les outils de construction (PyInstaller), installés s'ils manquent ;
2. les tests — on ne distribue pas une version qui ne les passe pas ;
3. PyInstaller, selon la recette `telemetrie-lmu.spec` ;
4. l'archive `dist/Telemetrie-LMU-<version>.zip`, qui contient le .exe et le
   mode d'emploi `LISEZ-MOI.txt` : c'est elle qu'on envoie.

Un double-clic sur ce fichier le lance avec le Python de Windows, qui n'a pas
les bibliothèques du projet : il plantait à la première ligne, et la fenêtre
se refermait avant qu'on ait pu lire quoi que ce soit. Le script se relance
donc lui-même avec le Python du projet (`.venv`), et attend qu'on appuie sur
Entrée avant de fermer sa fenêtre, que la construction ait réussi ou non.

`--automatique` : ni pause à la fin, ni ouverture du dossier (pour les tests).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PYTHON_PROJET = RACINE / ".venv" / "Scripts" / "python.exe"
DIST = RACINE / "dist"
TRAVAIL = RACINE / "build"
NOM = "Telemetrie-LMU"
AUTOMATIQUE = "--automatique" in sys.argv


class Echec(Exception):
    """Une étape a échoué : le message dit laquelle."""


def etape(titre: str) -> None:
    print(f"\n=== {titre} ===\n", flush=True)


def lancer(commande: list[str | Path]) -> None:
    if subprocess.run([str(c) for c in commande], cwd=RACINE).returncode != 0:
        raise Echec(f"Échec de : {' '.join(str(c) for c in commande)}")


def dans_le_projet() -> bool:
    """Tourne-t-on avec le Python du projet, qui a toutes ses bibliothèques ?"""
    return Path(sys.prefix).resolve() == (RACINE / ".venv").resolve()


def construire() -> None:
    sys.path.insert(0, str(RACINE))
    from lmu_telemetry import __version__

    print(f"Construction de Télémétrie LMU {__version__}")

    # Windows interdit de remplacer un .exe en cours d'exécution : PyInstaller
    # échouait alors tout au bout, sur un « Accès refusé » incompréhensible.
    exe = DIST / f"{NOM}.exe"
    if exe.exists():
        try:
            # Ouvrir en écriture sans rien écrire : refusé si le .exe tourne.
            with exe.open("r+b"):
                pass
        except PermissionError:
            raise Echec(
                "Le .exe est en cours d'utilisation : ferme la fenêtre de l'outil\n"
                "(Télémétrie LMU), puis relance la construction."
            ) from None

    etape("1/4  Outils de construction")
    lancer([
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q",
        "-r", RACINE / "requirements-build.txt",
    ])

    etape("2/4  Tests")
    lancer([sys.executable, "-m", "pytest", "-q"])

    etape("3/4  Fabrication du .exe (environ une minute)")
    if not (RACINE / "lmu_telemetry" / "ressources" / "icone.ico").exists():
        lancer([sys.executable, RACINE / "tools" / "icone.py"])
    lancer([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--distpath", DIST,
        "--workpath", TRAVAIL,
        RACINE / "telemetrie-lmu.spec",
    ])
    exe = DIST / f"{NOM}.exe"
    if not exe.is_file():
        raise Echec(f"PyInstaller n'a pas produit {exe}")

    etape("4/4  Archive à partager")
    lisez_moi = RACINE / "LISEZ-MOI.txt"
    archive = DIST / f"{NOM}-{__version__}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_:
        zip_.write(exe, exe.name)
        zip_.write(lisez_moi, lisez_moi.name)
    shutil.copyfile(lisez_moi, DIST / lisez_moi.name)

    mo = 1024 * 1024
    print(f"Le .exe      : {exe}  ({exe.stat().st_size / mo:.0f} Mo)")
    print(f"À partager   : {archive}  ({archive.stat().st_size / mo:.0f} Mo)")
    print("\nTerminé.")
    if not AUTOMATIQUE and sys.platform == "win32":
        print("Le dossier dist va s'ouvrir.")
        os.startfile(DIST)  # noqa: S606


def main() -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    if not dans_le_projet():
        if not PYTHON_PROJET.exists():
            print("L'environnement Python du projet (.venv) est absent.")
            print("Fais d'abord l'installation décrite dans le README, section Installation.")
            return 1
        # Le Python du projet reprend la main ; c'est lui qui fera la pause.
        return subprocess.run([str(PYTHON_PROJET), __file__, *sys.argv[1:]]).returncode

    try:
        construire()
        return 0
    except Echec as echec:
        print(f"\n{echec}")
        print("La construction a échoué : lis les messages ci-dessus.")
        return 1


if __name__ == "__main__":
    code = main()
    # La pause n'est faite qu'une fois : par le Python du projet, ou par celui
    # de Windows si le projet n'a pas d'environnement.
    if not AUTOMATIQUE and (dans_le_projet() or not PYTHON_PROJET.exists()):
        try:
            input("\nAppuie sur Entrée pour fermer cette fenêtre.")
        except (EOFError, KeyboardInterrupt):
            pass
    raise SystemExit(code)
