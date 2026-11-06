"""Ce que le moteur dit de tes sessions, et ce que ça coûte vraiment.

Rejoue toutes les sessions d'un tracé et répond à deux questions :

* à quelle fréquence chaque conseil tombe-t-il ?
* un passage au-dessus du seuil est-il plus lent que les autres ?

La seconde question est celle qui valide un seuil. Chaque passage est comparé à la
médiane de la même zone dans la même session : même voiture, même piste, même pilote.

Usage, depuis la racine du projet :

    .venv\\Scripts\\python.exe -m tools.bilan_coach "Autodromo Nazionale Monza" --categorie GT3
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from lmu_telemetry import emplacements, parametres
from lmu_telemetry.coach.moteur import BilanPassage
from lmu_telemetry.coach.rejeu import ouvrir, rejouer
from lmu_telemetry.domaine.circuits import definition_circuit
from lmu_telemetry.domaine.session import Session
from lmu_telemetry.errors import ErreurTelemetrie
from lmu_telemetry.sources import catalogue
from lmu_telemetry.sources.reader import FichierSession
from lmu_telemetry.textes import console_utf8

#: Une zone n'est comparée à elle-même qu'à partir de ce nombre de passages.
PASSAGES_MINIMUM = 4

#: Au-delà de cet écart (s), le passage a croisé autre chose que le virage : un arrêt,
#: du trafic. La médiane n'en souffre pas, mais il n'a rien à dire sur le geste.
ECART_MAXIMAL = 3.0

#: (nom affiché, champ de `Mesures`, champ de `SeuilsCoach`).
MESURES = (
    ("Roue libre avant le frein", "roue_libre_avant", "roue_libre_avant"),
    ("Roue libre en virage", "roue_libre_virage", "roue_libre_virage"),
    ("Frein brutal", "chute_frein", "chute_frein"),
    ("Gaz hésitants", "creux_gaz", "creux_gaz"),
    ("Correction de volant", "correction", "correction"),
)


@dataclass
class Ligne:
    session: str
    zone: str
    tour: int
    duree: float
    vitesse_sortie: float
    bilan: BilanPassage
    ecart: float = 0.0
    ecart_vitesse: float = 0.0


def relever(trace: str, categorie: str, limite: int) -> list[Ligne]:
    """Rejoue les sessions d'un tracé, des plus récentes aux plus anciennes."""
    lignes: list[Ligne] = []
    reglages = parametres.lire()
    sessions = 0
    for fichier in catalogue.lister():
        if sessions >= limite:
            break
        try:
            with FichierSession(fichier.chemin) as ouvert:
                info = ouvert.info
            if info.trace != trace or not info.categorie.startswith(categorie):
                continue
            session = Session.ouvrir(fichier.chemin)
            definition, _ = definition_circuit(
                session, emplacements.virages_utilisateur(), emplacements.virages_fournis()
            )
            evenements = list(rejouer(ouvrir(fichier.chemin).flux(), definition, reglages))
        except ErreurTelemetrie:
            continue
        sessions += 1
        for bilan in evenements:
            if isinstance(bilan, BilanPassage) and bilan.ecarte is None:
                p = bilan.passage
                lignes.append(
                    Ligne(
                        fichier.chemin.name,
                        p.zone.libelle,
                        p.tour,
                        float(p.temps[-1] - p.temps[0]),
                        float(p.vitesse[-1]),
                        bilan,
                    )
                )
    print(f"{sessions} session(s), {len(lignes)} passage(s) jugé(s)\n")
    return lignes


def comparer(lignes: list[Ligne]) -> list[Ligne]:
    """Situe chaque passage par rapport à sa zone dans sa session."""
    groupes: dict[tuple[str, str], list[Ligne]] = defaultdict(list)
    for ligne in lignes:
        groupes[(ligne.session, ligne.zone)].append(ligne)
    retenues = []
    for groupe in groupes.values():
        if len(groupe) < PASSAGES_MINIMUM:
            continue
        duree = float(np.median([l.duree for l in groupe]))
        vitesse = float(np.median([l.vitesse_sortie for l in groupe]))
        for ligne in groupe:
            ligne.ecart = ligne.duree - duree
            ligne.ecart_vitesse = ligne.vitesse_sortie - vitesse
            if abs(ligne.ecart) <= ECART_MAXIMAL:
                retenues.append(ligne)
    return retenues


def _case(lignes: list[Ligne]) -> str:
    if not lignes:
        return f"{'—':>26}"
    ecart = np.median([l.ecart for l in lignes])
    vitesse = np.median([l.ecart_vitesse for l in lignes])
    return f"{ecart:+7.3f} s {vitesse:+6.1f} km/h {len(lignes):4}"


def afficher(lignes: list[Ligne]) -> None:
    seuils = parametres.lire().coach

    print("Conseils, en % des passages")
    zones = sorted({l.zone for l in lignes})
    print(f"  {'':16}{'Tout':>8}" + "".join(f"{z[:12]:>13}" for z in zones))

    def part(lignes_zone: list[Ligne], champ: str, limite: float) -> float:
        dessus = sum(getattr(l.bilan.mesures, champ) >= limite for l in lignes_zone)
        return 100 * dessus / len(lignes_zone)

    for nom, champ, seuil in MESURES:
        limite = getattr(seuils, seuil)
        cases = [f"{part([l for l in lignes if l.zone == z], champ, limite):13.1f}" for z in zones]
        print(f"  {nom[:16]:16}{part(lignes, champ, limite):8.1f}" + "".join(cases))

    tours = Counter((l.session, l.tour) for l in lignes)
    conseils = Counter((l.session, l.tour) for l in lignes if l.bilan.conseil)
    print(f"\nConseils par tour : {sum(conseils.values()) / len(tours):.2f} en moyenne\n")

    comparees = comparer(lignes)
    print("Écart à la médiane de la zone : temps, vitesse de sortie, nombre de passages")
    print(f"  {'':28}{'sous le seuil':>26}{'au-dessus':>26}")
    for nom, champ, seuil in MESURES:
        limite = getattr(seuils, seuil)
        sous = [l for l in comparees if getattr(l.bilan.mesures, champ) < limite]
        dessus = [l for l in comparees if getattr(l.bilan.mesures, champ) >= limite]
        print(f"  {nom:28}{_case(sous)}{_case(dessus)}")


def main(argv: list[str] | None = None) -> int:
    console_utf8()
    parseur = argparse.ArgumentParser(prog="python -m tools.bilan_coach", description=__doc__)
    parseur.add_argument("trace", help="nom exact du tracé")
    parseur.add_argument("--categorie", default="", help="début du nom de la catégorie")
    parseur.add_argument("--sessions", type=int, default=400, help="nombre de sessions maximal")
    args = parseur.parse_args(argv)
    lignes = relever(args.trace, args.categorie, args.sessions)
    if lignes:
        afficher(lignes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
