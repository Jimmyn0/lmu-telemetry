"""Fabrique l'icône du .exe à partir de l'emblème de la page web.

    .venv\\Scripts\\python.exe tools\\icone.py

L'emblème est dessiné en SVG dans `index.html` : un carré arrondi sombre, deux
trajectoires — le tour comparé en orange, la référence en violet — et une voiture
blanche au bout de chacune. Windows veut un fichier .ico, qui n'est qu'une
collection d'images PNG de plusieurs tailles. On redessine donc l'emblème pixel
par pixel, avec numpy, plutôt que d'ajouter une bibliothèque d'images aux
dépendances pour un fichier produit une fois.

Chaque pixel est échantillonné 4 × 4 fois : sans ça, les bords et les courbes
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
FOND = (0x1B, 0x25, 0x33)
#: Les deux trajectoires, dans l'ordre du dessin : leur couleur, et les quatre points
#: de leur courbe de Bézier (le « C » du SVG).
TRAJECTOIRES = [
    ((0xEE, 0x8A, 0x35), [(5, 18), (11.5, 18), (11.5, 8), (20, 8)]),
    ((0xA2, 0x5E, 0xE8), [(5, 24), (13, 24), (13, 13), (24, 13)]),
]
EPAISSEUR = 2.6
#: Les deux voitures, au bout de leur trajectoire.
VOITURES = [(20, 8), (24, 13)]
RAYON_VOITURE = 2.3
SUREC = 4


def bezier(points: list[tuple[float, float]], pas: int = 32) -> np.ndarray:
    """La courbe de Bézier cubique de ces quatre points, en `pas` segments."""
    t = np.linspace(0.0, 1.0, pas + 1)[:, None]
    p0, p1, p2, p3 = (np.array(p, dtype=float) for p in points)
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t**2 * p2 + t**3 * p3


def distance_au_trace(x: np.ndarray, y: np.ndarray, trace: np.ndarray) -> np.ndarray:
    """Distance de chaque point au plus proche des segments du tracé."""
    distance = np.full(x.shape, np.inf)
    for (ax, ay), (bx, by) in zip(trace, trace[1:]):
        vx, vy = bx - ax, by - ay
        k = np.clip(((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        distance = np.minimum(distance, np.hypot(x - (ax + k * vx), y - (ay + k * vy)))
    return distance


def dessiner(taille: int) -> np.ndarray:
    """Image RGBA de `taille` pixels de côté."""
    n = taille * SUREC
    centres = (np.arange(n) + 0.5) / n * COTE
    x, y = np.meshgrid(centres, centres)

    # Carré aux coins arrondis : distance au rectangle intérieur réduit du rayon.
    dx = np.maximum(np.abs(x - COTE / 2) - (COTE / 2 - RAYON_COIN), 0)
    dy = np.maximum(np.abs(y - COTE / 2) - (COTE / 2 - RAYON_COIN), 0)
    dans_carre = np.hypot(dx, dy) <= RAYON_COIN

    couleur = np.empty(x.shape + (3,))
    couleur[:] = FOND
    # Les trajectoires, traits aux bouts ronds, puis les voitures par-dessus.
    for teinte, points in TRAJECTOIRES:
        couleur[(distance_au_trace(x, y, bezier(points)) <= EPAISSEUR / 2) & dans_carre] = teinte
    for cx, cy in VOITURES:
        couleur[(np.hypot(x - cx, y - cy) <= RAYON_VOITURE) & dans_carre] = 255.0

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
