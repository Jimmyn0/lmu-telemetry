"""Le découpage d'un circuit : lu sur disque, ou détecté puis enregistré.

Le fichier est fait pour être retouché à la main : une fois écrit, on ne le
régénère jamais, même si la détection donnerait autre chose.

Ce module sert à l'interface et servira au direct : tous deux doivent voir le
même découpage.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from ..cache import CacheBorne
from ..errors import ErreurTelemetrie
from ..sources.reader import cle_fichier
from .donnees_tour import charger_tours
from .session import Session
from .virages import DefinitionCircuit, detecter, fichier_definition

#: Nombre de tours utilisés pour détecter les virages. Plusieurs tours valent
#: mieux qu'un : la géométrie de la piste s'en trouve mieux contrainte, et les
#: deux bords sont connus sur une plus grande part du tour.
TOURS_DETECTION = 5

#: Découpages déjà lus, indexés par la date de modification ET la taille du
#: fichier, pas par son seul chemin : le README invite à retoucher ce fichier à
#: la main, et une retouche faite pendant que le serveur tournait était ignorée
#: jusqu'au redémarrage, sans aucun signe.
_lus: CacheBorne[tuple[str, int, int], DefinitionCircuit] = CacheBorne(32)

#: Deux requêtes simultanées sur un circuit pas encore découpé détecteraient
#: chacune les virages et écriraient le même fichier en même temps.
_verrou = threading.Lock()


def definition_circuit(
    session: Session, dossier_utilisateur: Path, dossier_fournis: Path
) -> tuple[DefinitionCircuit, Path]:
    """Découpage du circuit d'une session, et le fichier qui le contient."""
    chemin = fichier_definition(dossier_utilisateur, session.info.trace)
    with _verrou:
        # Un découpage livré avec l'outil est recopié chez l'utilisateur la
        # première fois : c'est la copie qu'il retouchera, et elle survivra au
        # remplacement de l'outil par une nouvelle version.
        fourni = fichier_definition(dossier_fournis, session.info.trace)
        if not chemin.exists() and fourni.is_file():
            chemin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fourni, chemin)
        cle = cle_fichier(chemin)
        if cle is not None:
            return _lus.obtenir(cle, lambda: DefinitionCircuit.lire(chemin)), chemin

        numeros = [t.numero for t in session.tours_valides if t.chrono][:TOURS_DETECTION]
        if not numeros:
            raise ErreurTelemetrie.de("serveur.erreur.decoupage_aucun_tour_valide")
        detecter(charger_tours(session.chemin, numeros)).enregistrer(chemin)
        # Relu plutôt que gardé tel quel : le fichier arrondit au décimètre, et
        # le découpage ne doit pas changer au redémarrage de l'outil.
        return _lus.obtenir(cle_fichier(chemin), lambda: DefinitionCircuit.lire(chemin)), chemin
