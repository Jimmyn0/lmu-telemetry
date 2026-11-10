# Recette de construction du .exe, lue par PyInstaller.
#
# Ne se lance pas directement : utilise `construire-exe.bat`, qui passe aussi
# les tests avant de construire et prépare l'archive à partager.
#
# Choix faits ici :
#
# * UN DOSSIER, `GhostLine`, plutôt qu'un seul fichier. Un .exe autonome se
#   décompresse dans un dossier temporaire à chaque lancement, puis y charge la
#   fenêtre (.NET, WebView2) depuis des fichiers tout neufs : 21 s avant qu'elle
#   s'ouvre, contre 3 à 4 s pour le dossier (mesuré le 2026-11-10). On envoie le
#   dossier, zippé.
# * PAS DE FENÊTRE DE CONSOLE : l'outil a sa propre fenêtre, et la fermer l'arrête.
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
                StringStruct("FileDescription", "GhostLine for LMU"),
                StringStruct("ProductName", "GhostLine for LMU"),
                StringStruct("FileVersion", __version__),
                StringStruct("ProductVersion", __version__),
                StringStruct("OriginalFilename", "GhostLine.exe"),
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
        # logos des constructeurs (voir ressources/logos/SOURCES.md). Pas les
        # logos qu'un utilisateur dépose dans son dossier de données.
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
    [],
    exclude_binaries=True,
    name="GhostLine",
    icon=str(RACINE / "lmu_telemetry" / "ressources" / "icone.ico"),
    version=version,
    console=False,
    upx=False,
)
# Le dossier : le .exe, et à côté de lui ses bibliothèques et ses fichiers (`_internal`).
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="GhostLine")
