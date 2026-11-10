"""Photographie chaque écran de l'application, pour le comparer aux maquettes.

Ouvre la vraie fenêtre à la taille des maquettes, enchaîne les écrans, et enregistre
une image de chacun. Seule la fenêtre de l'outil est capturée, même si une autre
fenêtre passe devant : rien d'autre de l'écran ne se retrouve dans les images.

Usage, depuis la racine du projet :

    .venv\\Scripts\\python.exe -m tools.captures_ecrans <dossier> [écran ...]

Les écrans se choisissent par nom ; sans nom, tous sont capturés.
"""

from __future__ import annotations

import ctypes
import struct
import sys
import threading
import time
import zlib
from ctypes import wintypes
from pathlib import Path

import numpy as np

from lmu_telemetry import fenetre as module_fenetre
from lmu_telemetry.web.serveur import creer_serveur

PORT = 8797

#: Ce qui reste à faire après le chargement d'un écran : les tracés et les listes se
#: construisent en plusieurs requêtes.
ATTENTE = 3.5

ONGLET = 'document.querySelector(\'[data-onglet="{}"]\').click()'

#: (nom, script à exécuter dans la page). Les écrans s'enchaînent dans cet ordre.
ECRANS = [
    ("resultats", ONGLET.format("resultats")),
    # La première session de course : plusieurs tours valides à comparer.
    ("session", 'document.querySelector(".carte-session.type-R")?.click()'),
    ("regularite", 'document.querySelector(\'[data-vue="regularite"]\')?.click()'),
    ("tours", 'document.querySelector(\'[data-vue="tours"]\')?.click()'),
    ("telemetrie", 'document.querySelector("#comparer-tours")?.click() ?? document.querySelector(\'[data-onglet="telemetrie"]\').click()'),
    ("telemetrie-bas", 'document.querySelector("#ecran-telemetrie").scrollTo(0, 99999)'),
    ("temps", ONGLET.format("temps")),
    ("reglages", 'document.querySelector("#ouvrir-reglages").click()'),
]


def _ecrire_png(chemin: Path, image: np.ndarray) -> None:
    hauteur, largeur, _ = image.shape

    def bloc(nature: bytes, donnees: bytes) -> bytes:
        return (
            struct.pack(">I", len(donnees))
            + nature
            + donnees
            + struct.pack(">I", zlib.crc32(nature + donnees))
        )

    brut = b"".join(b"\0" + image[y].tobytes() for y in range(hauteur))
    chemin.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + bloc(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0))
        + bloc(b"IDAT", zlib.compress(brut, 6))
        + bloc(b"IEND", b"")
    )


class _EnteteImage(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def capturer(poignee: int, largeur: int, hauteur: int) -> np.ndarray:
    """Image de la seule fenêtre `poignee`, en RGB."""
    user32 = ctypes.WinDLL("user32")
    gdi32 = ctypes.WinDLL("gdi32")
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
    ]

    ecran = user32.GetWindowDC(poignee)
    memoire = gdi32.CreateCompatibleDC(ecran)
    image = gdi32.CreateCompatibleBitmap(ecran, largeur, hauteur)
    gdi32.SelectObject(memoire, image)
    user32.PrintWindow(poignee, memoire, 2)  # PW_RENDERFULLCONTENT

    entete = _EnteteImage()
    entete.biSize = ctypes.sizeof(entete)
    entete.biWidth = largeur
    entete.biHeight = -hauteur  # de haut en bas
    entete.biPlanes = 1
    entete.biBitCount = 32
    tampon = np.empty((hauteur, largeur, 4), dtype=np.uint8)
    gdi32.GetDIBits(memoire, image, 0, hauteur, tampon.ctypes.data, ctypes.byref(entete), 0)

    gdi32.DeleteObject(image)
    gdi32.DeleteDC(memoire)
    user32.ReleaseDC(poignee, ecran)
    return np.ascontiguousarray(tampon[:, :, 2::-1])


def main() -> int:
    dossier = Path(sys.argv[1])
    dossier.mkdir(parents=True, exist_ok=True)
    voulus = set(sys.argv[2:])

    serveur = creer_serveur(PORT)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()

    def scenario(f: module_fenetre.Fenetre) -> None:
        def derouler() -> None:
            try:
                time.sleep(ATTENTE)
                for nom, script in ECRANS:
                    f._vue.evaluate_js(script)
                    time.sleep(ATTENTE)
                    if voulus and nom not in voulus:
                        continue
                    r = f._rect()
                    _ecrire_png(dossier / f"{nom}.png", capturer(f._poignee, r.largeur, r.hauteur))
                    print(nom, r.largeur, r.hauteur, flush=True)
            finally:
                f.fermer()

        threading.Thread(target=derouler, daemon=True).start()

    module_fenetre.ouvrir(f"http://127.0.0.1:{PORT}/", scenario)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
