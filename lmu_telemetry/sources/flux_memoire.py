"""Le flux d'échantillons de la mémoire partagée, en direct ou depuis une capture.

Une capture de la sonde contient les blocs bruts de la mémoire, tels quels. Les
relire passe donc par la même conversion que le direct, jusqu'au dernier octet :
c'est ce qui permet de tout vérifier sans le jeu, roues comprises.
"""

from __future__ import annotations

import math
import struct
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO

from .echantillon import FREQUENCE_LECTURE, Echantillon
from .memoire_lmu import (
    CHAMPS_ROUE,
    CHAMPS_SCORING,
    CHAMPS_TELEMETRIE,
    CHAMPS_VEHICULE,
    DEBUT_ROUES,
    TAILLE_ROUE,
    LecteurMemoire,
    Lecture,
    decoder,
)
from .reader import SURFACES_HORS_PISTE

ENTETE_CAPTURE = b"LMUCAP1\n"
ENREGISTREMENT = struct.Struct("<BdI")
TYPE_TELEMETRIE, TYPE_VEHICULE, TYPE_SCORING = 1, 2, 3

#: Ce que le flux lit de chaque bloc : décoder les noms de voiture et de circuit
#: à chaque échantillon ne servirait à rien.
_TELEMETRIE = {
    nom: CHAMPS_TELEMETRIE[nom]
    for nom in (
        "temps", "tour", "debut_tour", "vitesse_locale",
        "gaz_brut", "frein_brut", "volant", "choc_temps",
    )
}
_ROUE = {nom: CHAMPS_ROUE[nom] for nom in ("rotation", "surface", "rayon_cm")}
_VEHICULE = {
    nom: CHAMPS_VEHICULE[nom]
    for nom in ("distance_tour", "dernier_tour", "aux_stands")
}
_SCORING = {"temps": CHAMPS_SCORING["temps"]}


def ecrire_enregistrement(flux: BinaryIO, type_: int, instant: float, brut: bytes) -> None:
    flux.write(ENREGISTREMENT.pack(type_, instant, len(brut)))
    flux.write(brut)


def relire_capture(chemin: Path) -> Iterator[tuple[int, float, bytes]]:
    """Enregistrements d'une capture : (type, instant, bloc brut)."""
    with chemin.open("rb") as flux:
        if flux.read(len(ENTETE_CAPTURE)) != ENTETE_CAPTURE:
            raise ValueError(f"{chemin} n'est pas une capture de la sonde")
        while entete := flux.read(ENREGISTREMENT.size):
            if len(entete) < ENREGISTREMENT.size:
                return  # capture coupée en pleine écriture
            type_, instant, longueur = ENREGISTREMENT.unpack(entete)
            brut = flux.read(longueur)
            if len(brut) < longueur:
                return
            yield type_, instant, brut


class Convertisseur:
    """Transforme les lectures de la mémoire en échantillons.

    Il retient deux choses d'une lecture à l'autre : l'instant de la dernière
    télémétrie, parce que la mémoire peut être relue avant que le jeu l'ait
    changée, et la dernière distance, parce que `mLapDist` ne change qu'à 5 Hz.
    """

    def __init__(self) -> None:
        self._temps: float | None = None
        self._distance: float | None = None

    def convertir(self, lecture: Lecture) -> Echantillon | None:
        """L'échantillon d'une lecture, ou None si le jeu n'a rien publié de neuf."""
        telemetrie = decoder(lecture.telemetrie, _TELEMETRIE)
        if telemetrie["temps"] == self._temps:
            return None
        self._temps = telemetrie["temps"]

        roues = [
            decoder(lecture.telemetrie, _ROUE, DEBUT_ROUES + i * TAILLE_ROUE) for i in range(4)
        ]
        # La rotation est négative en marche avant, et le rayon est en centimètres.
        tours_roues = tuple(abs(r["rotation"]) * r["rayon_cm"] * 0.036 for r in roues)
        echantillon = Echantillon(
            temps=telemetrie["temps"],
            tour=telemetrie["tour"],
            debut_tour=telemetrie["debut_tour"],
            vitesse=math.hypot(*telemetrie["vitesse_locale"]) * 3.6,
            gaz=telemetrie["gaz_brut"] * 100.0,
            frein=telemetrie["frein_brut"] * 100.0,
            volant=telemetrie["volant"] * 100.0,
            hors_piste=any(r["surface"] in SURFACES_HORS_PISTE for r in roues),
            dernier_choc=telemetrie["choc_temps"] or -1.0,
            roues=tours_roues,
        )
        if lecture.vehicule is not None:
            vehicule = decoder(lecture.vehicule, _VEHICULE)
            echantillon.stands = vehicule["aux_stands"]
            chrono = vehicule["dernier_tour"]
            echantillon.dernier_chrono = chrono if chrono > 0 else None
            if vehicule["distance_tour"] != self._distance:
                self._distance = vehicule["distance_tour"]
                echantillon.distance = self._distance
                echantillon.temps_distance = decoder(lecture.scoring, _SCORING)["temps"]
        return echantillon


def flux_capture(chemin: Path) -> Iterator[Echantillon]:
    """Les échantillons d'une capture de la sonde, tels que le direct les aurait donnés."""
    convertisseur = Convertisseur()
    vehicule: bytes | None = None
    scoring: bytes | None = None
    for type_, _instant, brut in relire_capture(chemin):
        if type_ == TYPE_VEHICULE:
            vehicule = brut
        elif type_ == TYPE_SCORING:
            scoring = brut
        elif scoring is not None:
            echantillon = convertisseur.convertir(Lecture(brut, vehicule, scoring))
            if echantillon is not None:
                yield echantillon


def flux_direct(
    memoire: LecteurMemoire,
    continuer: Callable[[], bool] = lambda: True,
    frequence: int = FREQUENCE_LECTURE,
) -> Iterator[Echantillon]:
    """Les échantillons du jeu en marche, tant que `continuer` le dit."""
    convertisseur = Convertisseur()
    periode = 1.0 / frequence
    while continuer():
        debut = time.perf_counter()
        lecture = memoire.lire()
        if lecture is not None:
            echantillon = convertisseur.convertir(lecture)
            if echantillon is not None:
                yield echantillon
        time.sleep(max(0.0, periode - (time.perf_counter() - debut)))
