"""Fabrique l'icône du .exe à partir de l'emblème de la page web.

    .venv\\Scripts\\python.exe tools\\icone.py

L'emblème est dessiné en SVG dans `index.html` : un carré arrondi dégradé
indigo → rose, barré d'une courbe blanche. Windows veut un fichier .ico, qui
n'est qu'une collection d'images PNG de plusieurs tailles. On redessine donc
l'emblème pixel par pixel, avec numpy, plutôt que d'ajouter une bibliothèque
d'images aux dépendances pour un fichier produit une fois.

Chaque pixel est échantillonné 4 × 4 fois : sans ça, les bords et la courbe
seraient en escalier.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import numpy as np

SORTIE = Path(__file__).resolve().parent.parent / "lmu_telemetry" / "ressources" / "icone.ico"
TAILLES = (16, 24, 32, 48, 64, 128, 256)

# Mêmes valeurs que le SVG d'index.html, dans son repère de 30 × 30.
COTE = 30.0
RAYON_COIN = 8.0
DEBUT = np.array([0x7C, 0x6C, 0xFF], dtype=float)
FIN = np.array([0xE0, 0x52, 0xA0], dtype=float)
COURBE = [(5, 20), (10, 20), (13, 11), (17, 23), (20, 15), (25, 15)]
EPAISSEUR = 2.2
SUREC = 4


def dessiner(taille: int) -> np.ndarray:
    """Image RGBA de `taille` pixels de côté."""
    n = taille * SUREC
    centres = (np.arange(n) + 0.5) / n * COTE
    x, y = np.meshgrid(centres, centres)

    # Carré aux coins arrondis : distance au rectangle intérieur réduit du rayon.
    dx = np.maximum(np.abs(x - COTE / 2) - (COTE / 2 - RAYON_COIN), 0)
    dy = np.maximum(np.abs(y - COTE / 2) - (COTE / 2 - RAYON_COIN), 0)
    dans_carre = np.hypot(dx, dy) <= RAYON_COIN

    # Dégradé en diagonale, comme x1=0 y1=0 x2=1 y2=1 dans le SVG.
    t = ((x + y) / (2 * COTE))[..., None]
    couleur = DEBUT * (1 - t) + FIN * t

    # Courbe : distance au plus proche des segments, traits et jonctions ronds.
    distance = np.full(x.shape, np.inf)
    for (ax, ay), (bx, by) in zip(COURBE, COURBE[1:]):
        vx, vy = bx - ax, by - ay
        k = np.clip(((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        distance = np.minimum(distance, np.hypot(x - (ax + k * vx), y - (ay + k * vy)))
    sur_courbe = (distance <= EPAISSEUR / 2) & dans_carre
    couleur[sur_courbe] = 255.0

    rgba = np.zeros((n, n, 4))
    rgba[..., :3] = couleur
    rgba[..., 3] = dans_carre * 255.0
    # Moyenne des sous-échantillons, en prémultipliant par l'opacité pour que
    # les bords ne virent pas au noir.
    blocs = rgba.reshape(taille, SUREC, taille, SUREC, 4).transpose(0, 2, 1, 3, 4)
    opacite = blocs[..., 3:4] / 255.0
    somme_opacite = opacite.sum(axis=(2, 3))
    rgb = (blocs[..., :3] * opacite).sum(axis=(2, 3)) / np.maximum(somme_opacite, 1e-9)
    alpha = somme_opacite / (SUREC * SUREC) * 255.0
    return np.round(np.concatenate([rgb, alpha], axis=-1)).clip(0, 255).astype(np.uint8)


def png(image: np.ndarray) -> bytes:
    """Encode une image RGBA en PNG, sans bibliothèque d'images."""
    hauteur, largeur, _ = image.shape
    brut = b"".join(b"\x00" + image[i].tobytes() for i in range(hauteur))

    def bloc(nature: bytes, donnees: bytes) -> bytes:
        return (
            struct.pack(">I", len(donnees))
            + nature
            + donnees
            + struct.pack(">I", zlib.crc32(nature + donnees) & 0xFFFFFFFF)
        )

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloc(b"IHDR", entete)
        + bloc(b"IDAT", zlib.compress(brut, 9))
        + bloc(b"IEND", b"")
    )


def ico(images: list[bytes], tailles: tuple[int, ...]) -> bytes:
    """Assemble des PNG en un .ico (format accepté depuis Windows Vista)."""
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    repertoire = b""
    for donnees, taille in zip(images, tailles):
        cote = 0 if taille >= 256 else taille  # 0 veut dire 256 dans ce format
        repertoire += struct.pack("<BBBBHHII", cote, cote, 0, 0, 1, 32, len(donnees), decalage)
        decalage += len(donnees)
    return entete + repertoire + b"".join(images)


def main() -> int:
    images = [png(dessiner(t)) for t in TAILLES]
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_bytes(ico(images, TAILLES))
    print(f"{SORTIE} : {len(TAILLES)} tailles, {SORTIE.stat().st_size // 1024} Ko")
    if "--apercu" in sys.argv:
        apercu = SORTIE.with_name("icone-apercu.png")
        apercu.write_bytes(images[-1])
        print(f"Aperçu : {apercu}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
