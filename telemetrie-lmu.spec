# Recette de construction du .exe, lue par PyInstaller.
#
# Ne se lance pas directement : utilise `construire-exe.bat`, qui passe aussi
# les tests avant de construire et prépare l'archive à partager.
#
# Choix faits ici :
#
# * UN SEUL FICHIER (.exe autonome) : c'est ce qu'on envoie à un ami. Il
#   s'extrait dans un dossier temporaire à chaque lancement, d'où quelques
#   secondes de démarrage.
# * FENÊTRE DE CONSOLE conservée : c'est elle qui dit que l'outil tourne, où
#   le trouver, et qui l'arrête quand on la ferme. Sans elle, l'outil
#   tournerait en arrière-plan sans moyen évident de l'arrêter.
# * PAS DE COMPRESSION UPX : elle rend le .exe plus petit mais le fait
#   beaucoup plus souvent prendre pour un virus par les antivirus.

import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

RACINE = Path(SPECPATH)
sys.path.insert(0, str(RACINE))
from lmu_telemetry import __version__  # noqa: E402

# Le numéro de version apparaît dans les propriétés du fichier (clic droit ›
# Propriétés › Détails) : utile pour savoir quelle version un ami a entre les
# mains.
chiffres = tuple(int(c) for c in __version__.split(".")) + (0,)
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=chiffres, prodvers=chiffres),
    kids=[
        StringFileInfo([
            StringTable("040C04B0", [
                StringStruct("FileDescription", "Télémétrie LMU"),
                StringStruct("ProductName", "Télémétrie LMU"),
                StringStruct("FileVersion", __version__),
                StringStruct("ProductVersion", __version__),
                StringStruct("OriginalFilename", "Telemetrie-LMU.exe"),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)

a = Analysis(
    [str(RACINE / "tools" / "point_entree_exe.py")],
    pathex=[str(RACINE)],
    datas=[
        # La page web, et les ressources livrées : découpages de référence et
        # logos libres de droits. Pas les logos personnels, qui vivent dans
        # le dossier de données de chacun.
        (str(RACINE / "lmu_telemetry" / "web" / "statique"), "lmu_telemetry/web/statique"),
        (str(RACINE / "lmu_telemetry" / "ressources"), "lmu_telemetry/ressources"),
    ],
    # Rien de tout ça n'est utilisé par l'outil : autant ne pas l'embarquer.
    excludes=["tkinter", "pytest", "_pytest", "IPython", "matplotlib", "pandas"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Telemetrie-LMU",
    icon=str(RACINE / "lmu_telemetry" / "ressources" / "icone.ico"),
    version=version,
    console=True,
    upx=False,
)
