"""Rejouer une session : le moteur reçoit ce qu'il aurait reçu en piste.

Sert à vérifier les conseils sans lancer le jeu, à la vitesse qu'on veut. Le moteur
ne sait pas qu'il est rejoué : ce qu'il dit ici, il le dira en piste.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ..domaine.virages import DefinitionCircuit
from ..parametres import Parametres
from ..sources.echantillon import Echantillon
from ..sources.flux_fichier import flux_fichier
from ..sources.flux_memoire import TYPE_TELEMETRIE, flux_capture, relire_capture
from ..sources.memoire_lmu import CHAMPS_TELEMETRIE, decoder
from .moteur import Moteur

#: Nom du fichier que la sonde dépose dans son dossier.
NOM_CAPTURE = "capture.bin"


@dataclass(frozen=True)
class Enregistrement:
    """Une session à rejouer, d'où qu'elle vienne."""

    flux: Callable[[], Iterator[Echantillon]]

    roues: bool
    """La source voit-elle les roues ? Sinon, ni blocage ni patinage."""


def _capture(chemin: Path) -> Path | None:
    """Le fichier de capture désigné par un chemin, s'il y en a un."""
    if chemin.is_dir():
        chemin = chemin / NOM_CAPTURE
    return chemin if chemin.name == NOM_CAPTURE and chemin.is_file() else None


def identite_capture(chemin: Path) -> tuple[str, str]:
    """Le tracé et le modèle de voiture d'une capture."""
    champs = {"circuit": CHAMPS_TELEMETRIE["circuit"], "modele": CHAMPS_TELEMETRIE["modele"]}
    circuit = modele = ""
    fichier = _capture(chemin) or chemin
    for type_, _instant, brut in relire_capture(fichier):
        # La mémoire garde l'ancienne voiture jusqu'au chargement : seule la dernière
        # télémétrie d'une capture parle à coup sûr de la session capturée.
        if type_ == TYPE_TELEMETRIE:
            lu = decoder(brut, champs)
            circuit, modele = lu["circuit"], lu["modele"]
    return circuit, modele


def ouvrir(chemin: Path | str) -> Enregistrement:
    """Une session à rejouer : un `.duckdb`, une capture, ou le dossier d'une capture."""
    chemin = Path(chemin)
    if (capture := _capture(chemin)) is not None:
        return Enregistrement(lambda: flux_capture(capture), roues=True)
    return Enregistrement(lambda: flux_fichier(chemin), roues=False)


def rejouer(
    flux: Iterable[Echantillon],
    definition: DefinitionCircuit,
    parametres: Parametres = Parametres(),
    vitesse: float | None = None,
) -> Iterator:
    """Les événements d'une session, dans l'ordre.

    Sans `vitesse`, le plus vite possible. À 1, au rythme de la session : c'est ce qui
    permettra de tester l'affichage sans le jeu.
    """
    moteur = Moteur(definition, parametres.coach, parametres.virages)
    debut: float | None = None
    origine = 0.0
    for echantillon in flux:
        if vitesse:
            if debut is None:
                debut, origine = time.perf_counter(), echantillon.temps
            prevu = debut + (echantillon.temps - origine) / vitesse
            attente = prevu - time.perf_counter()
            if attente > 0:
                time.sleep(attente)
        yield from moteur.traiter(echantillon)
