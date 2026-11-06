"""Ligne de commande.

    python -m lmu_telemetry sessions            liste les sessions du disque
    python -m lmu_telemetry tours <fichier>     détaille les tours d'une session
    python -m lmu_telemetry info <fichier>      structure brute d'un fichier
    python -m lmu_telemetry rejouer <fichier>   les conseils qu'une session aurait donnés
    python -m lmu_telemetry direct              les conseils en direct, jeu lancé

Un `<fichier>` peut être un chemin complet, ou simplement le numéro affiché
dans la première colonne de `sessions`. `rejouer` accepte aussi le dossier d'une
capture de la sonde, seule à voir le blocage et le patinage.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import emplacements, parametres
from .sources import catalogue
from .errors import DossierIntrouvable, ErreurTelemetrie, FichierIntrouvable
from .sources.reader import FichierSession
from .textes import console_utf8
from .domaine.circuits import definition_circuit, definition_connue
from .domaine.session import Session


# ----------------------------------------------------------------------
# Mise en forme
# ----------------------------------------------------------------------


def chrono(secondes: float | None, decimales: int = 3) -> str:
    """Formate un temps en m:ss.mmm, comme le jeu l'affiche.

    `decimales` permet de n'afficher que la précision réellement disponible :
    la durée mesurée entre deux événements `Lap` ne vaut qu'à ±0,02 s près,
    l'afficher au millième laisserait croire à une précision qu'on n'a pas.
    """
    if secondes is None:
        return "—"
    minutes, reste = divmod(secondes, 60)
    largeur = 3 + decimales
    return f"{int(minutes)}:{reste:0{largeur}.{decimales}f}"


def _resoudre(reference: str, dossier: str | None) -> Path:
    """Accepte un chemin, ou le numéro d'une ligne de `sessions`."""
    if reference.isdigit():
        sessions = catalogue.lister(dossier)
        rang = int(reference)
        if not 1 <= rang <= len(sessions):
            raise ErreurTelemetrie(
                f"Il n'y a pas de session numéro {rang}. "
                f"La liste en compte {len(sessions)} — voir `sessions`."
            )
        return sessions[rang - 1].chemin
    chemin = Path(reference)
    if not chemin.exists():
        raise FichierIntrouvable(chemin)
    return chemin


# ----------------------------------------------------------------------
# Commandes
# ----------------------------------------------------------------------


def cmd_sessions(args: argparse.Namespace) -> int:
    # Les numéros sont ceux de la liste COMPLÈTE : un filtre ne doit pas les
    # renuméroter, sinon `tours 3` ne désignerait pas la même session selon le
    # filtre utilisé juste avant.
    numerotes = list(enumerate(catalogue.lister(args.dossier), 1))
    if args.circuit:
        motif = args.circuit.lower()
        numerotes = [(n, f) for n, f in numerotes if motif in f.circuit.lower()]
    if args.type:
        numerotes = [(n, f) for n, f in numerotes if f.code_type == args.type.upper()]

    total = len(numerotes)
    numerotes = numerotes[: args.limite]

    print(f"{'n°':>4}  {'date':<17}{'circuit':<32}{'type':<6}{'taille':>8}")
    print("-" * 72)
    for rang, f in numerotes:
        # Le jeu horodate en UTC ; on affiche l'heure de la montre du pilote.
        date = (
            f.enregistre_le.astimezone().strftime("%Y-%m-%d %H:%M")
            if f.enregistre_le
            else "?"
        )
        marque = "  ⚠ journal .wal" if f.journal_present else ""
        print(
            f"{rang:>4}  {date:<17}{f.circuit[:30]:<32}{f.code_type:<6}"
            f"{f.taille / 1024 / 1024:>7.1f}M{marque}"
        )
    print("-" * 72)
    print(f"{len(numerotes)} affichée(s) sur {total}. "
          f"Détail d'une session : python -m lmu_telemetry tours <n°>")
    return 0


def cmd_tours(args: argparse.Namespace) -> int:
    chemin = _resoudre(args.fichier, args.dossier)
    session = Session.ouvrir(chemin)
    info = session.info

    print(f"Fichier   : {chemin.name}")
    print(f"Circuit   : {info.circuit}")
    locale = info.enregistree_le.astimezone() if info.enregistree_le else None
    print(f"Session   : {info.type_session}"
          + (f"   ({locale:%Y-%m-%d %H:%M})" if locale else ""))
    print(f"Voiture   : {info.voiture}   [{info.categorie}]")
    print(f"Pilote    : {info.pilote}")
    print(f"Météo     : {info.meteo}")
    if session.journal_present:
        print("⚠ Un journal .wal traîne à côté : la fin de cette session peut manquer.")
    print()

    entete = (f"{'tour':>5}  {'chrono':>10}{'mesuré ±0,02':>14}{'S1':>9}{'S2':>9}{'S3':>9}"
              f"{'v.min':>8}  {'':<3}remarques")
    print(entete)
    print("-" * max(len(entete), 88))

    meilleur = session.meilleur_tour
    for tour in session.tours:
        s1, s2, s3 = tour.secteurs
        marque = "★" if meilleur and tour is meilleur else ("✓" if tour.valide else "✗")
        print(
            f"{tour.numero:>5}  {chrono(tour.chrono):>10}"
            f"{chrono(tour.duree_mesuree, decimales=2):>14}"
            f"{(f'{s1:.3f}' if s1 else '—'):>9}"
            f"{(f'{s2:.3f}' if s2 else '—'):>9}"
            f"{(f'{s3:.3f}' if s3 else '—'):>9}"
            f"{tour.vitesse_min:>7.0f}  {marque:<3}"
            + " ; ".join(map(str, tour.remarques))
        )

    print("-" * max(len(entete), 88))
    valides = session.tours_valides
    print(f"{len(session.tours)} tour(s), dont {len(valides)} valide(s).  "
          "★ meilleur   ✓ valide   ✗ écarté")
    if meilleur:
        print(f"Meilleur tour : {chrono(meilleur.chrono)} (tour {meilleur.numero})")
    print()
    print("« chrono » est le temps officiel du jeu, exact. « mesuré » est recalculé entre")
    print("deux événements de franchissement de ligne, qui ne sont inscrits qu'à ±0,02 s")
    print("près : un écart de quelques centièmes est normal, au-delà il y a un problème.")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    chemin = _resoudre(args.fichier, args.dossier)
    with FichierSession(chemin) as fichier:
        info = fichier.info
        print(f"Fichier  : {chemin.name}")
        print(f"Schéma   : version {info.version_schema}")
        print(f"Circuit  : {info.circuit}    Session : {info.type_session}")
        print(f"Voiture  : {info.voiture}  [{info.categorie}]")
        print(f"t0       : {fichier.t0:.3f} s      durée : {fichier.duree:.1f} s")
        print()
        print(f"{len(fichier.canaux)} canaux (échantillonnage régulier, sans horodatage) :")
        print(f"  {'nom':<26}{'Hz':>5}{'unité':>8}{'échant.':>10}{'roues':>7}")
        for canal in sorted(fichier.canaux.values(), key=lambda c: c.nom):
            print(f"  {canal.nom:<26}{canal.frequence:>5}{canal.unite:>8}"
                  f"{canal.echantillons:>10}{'×4' if canal.par_roue else '':>7}")
        print()
        print(f"{len(fichier.evenements)} événements (horodatés, écrits au changement) :")
        print(f"  {'nom':<26}{'unité':>8}{'lignes':>9}{'roues':>7}")
        for ev in sorted(fichier.evenements.values(), key=lambda e: e.nom):
            print(f"  {ev.nom:<26}{ev.unite:>8}{ev.lignes:>9}"
                  f"{'×4' if ev.par_roue else '':>7}")
    return 0


def _afficher_evenement(evenement: object) -> None:
    """Une ligne par conseil et par tour, au fil de la session."""
    from .coach.moteur import BilanPassage, TourTermine

    if isinstance(evenement, BilanPassage) and evenement.conseil is not None:
        minutes, secondes = divmod(evenement.passage.temps_sortie, 60)
        print(f"  {int(minutes):3}:{secondes:04.1f}  {evenement.conseil.message}", flush=True)
    elif isinstance(evenement, TourTermine):
        temps = chrono(evenement.chrono) if evenement.chrono else "non chronométré"
        print(f"Tour {evenement.tour} : {temps}", flush=True)


def cmd_rejouer(args: argparse.Namespace) -> int:
    from .coach.moteur import BilanPassage
    from .coach.rejeu import identite_capture, ouvrir, rejouer

    chemin = Path(args.fichier) if Path(args.fichier).exists() else _resoudre(args.fichier, args.dossier)
    source = ouvrir(chemin)
    virages, fournis = emplacements.virages_utilisateur(), emplacements.virages_fournis()
    if source.roues:
        trace, modele = identite_capture(chemin)
        definition = definition_connue(trace, virages, fournis)
        if definition is None:
            raise ErreurTelemetrie(f"Aucun découpage en virages pour « {trace} ».")
    else:
        session = Session.ouvrir(chemin)
        trace, modele = session.info.trace, session.info.voiture
        definition, _ = definition_circuit(session, virages, fournis)

    print(f"Session : {trace}, {modele}")
    if not source.roues:
        print("Ce fichier ne voit pas les roues : ni blocage ni patinage.")
    print()
    passages = conseils = ecartes = 0
    for evenement in rejouer(source.flux(), definition, parametres.lire(), args.vitesse):
        _afficher_evenement(evenement)
        if isinstance(evenement, BilanPassage):
            passages += 1
            conseils += evenement.conseil is not None
            ecartes += evenement.ecarte is not None
    print(f"\n{passages} passage(s), {conseils} conseil(s), {ecartes} écarté(s) : "
          "stands, sortie de piste, choc ou arrêt.")
    return 0


def cmd_direct(args: argparse.Namespace) -> int:
    from .coach.moteur import Moteur, Rupture
    from .sources.flux_memoire import flux_direct
    from .sources.memoire_lmu import CHAMPS_SCORING, LecteurMemoire, MemoireAbsente, decoder

    def attendre_memoire() -> LecteurMemoire:
        print("En attente de Le Mans Ultimate…", flush=True)
        while True:
            try:
                return LecteurMemoire()
            except MemoireAbsente:
                time.sleep(1.0)

    def moteur_du_circuit(memoire: LecteurMemoire) -> Moteur:
        """Le moteur du circuit en cours : attend qu'une voiture soit en piste."""
        while (lecture := memoire.lire()) is None:
            time.sleep(0.5)
        trace = decoder(lecture.scoring, {"circuit": CHAMPS_SCORING["circuit"]})["circuit"]
        definition = definition_connue(
            trace, emplacements.virages_utilisateur(), emplacements.virages_fournis()
        )
        if definition is None:
            raise ErreurTelemetrie(
                f"Aucun découpage en virages pour « {trace} » : "
                "ouvre une session de ce circuit dans l'outil pour le créer."
            )
        print(f"Circuit : {trace}. Ctrl+C pour arrêter.", flush=True)
        reglages = parametres.lire()
        return Moteur(definition, reglages.coach, reglages.virages)

    try:
        with attendre_memoire() as memoire:
            moteur = moteur_du_circuit(memoire)
            for echantillon in flux_direct(memoire):
                for evenement in moteur.traiter(echantillon):
                    _afficher_evenement(evenement)
                    # Une nouvelle session peut se dérouler sur un autre circuit.
                    if isinstance(evenement, Rupture):
                        moteur = moteur_du_circuit(memoire)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    from .web.serveur import demarrer

    dossier = Path(args.dossier) if args.dossier else None
    demarrer(port=args.port, dossier=dossier, ouvrir=not args.sans_navigateur)
    return 0


# ----------------------------------------------------------------------


def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="python -m lmu_telemetry",
        description="Analyse de télémétrie pour Le Mans Ultimate.",
    )
    parseur.add_argument(
        "--dossier",
        help="Dossier de télémétrie de LMU, si la détection automatique échoue.",
    )
    sous = parseur.add_subparsers(dest="commande", required=True)

    p = sous.add_parser("sessions", help="lister les sessions enregistrées")
    p.add_argument("--circuit", help="ne garder que les circuits dont le nom contient ceci")
    p.add_argument("--type", help="filtrer par type de session : P, Q ou R")
    p.add_argument("--limite", type=int, default=25, help="nombre de lignes (défaut : 25)")
    p.set_defaults(fonction=cmd_sessions)

    p = sous.add_parser("tours", help="détailler les tours d'une session")
    p.add_argument("fichier", help="chemin du fichier, ou numéro affiché par `sessions`")
    p.set_defaults(fonction=cmd_tours)

    p = sous.add_parser("info", help="structure brute d'un fichier")
    p.add_argument("fichier", help="chemin du fichier, ou numéro affiché par `sessions`")
    p.set_defaults(fonction=cmd_info)

    p = sous.add_parser("rejouer", help="les conseils qu'une session aurait donnés")
    p.add_argument(
        "fichier",
        help="chemin du fichier, numéro affiché par `sessions`, ou dossier d'une capture",
    )
    p.add_argument(
        "--vitesse",
        type=float,
        help="vitesse de lecture, 1 pour le temps réel (défaut : le plus vite possible)",
    )
    p.set_defaults(fonction=cmd_rejouer)

    p = sous.add_parser("direct", help="les conseils en direct, pendant que tu roules")
    p.set_defaults(fonction=cmd_direct)

    p = sous.add_parser("web", help="ouvrir l'interface graphique dans le navigateur")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument(
        "--sans-navigateur",
        action="store_true",
        help="ne pas ouvrir le navigateur automatiquement",
    )
    p.set_defaults(fonction=cmd_web)

    return parseur


def main(argv: list[str] | None = None) -> int:
    console_utf8()
    args = construire_parseur().parse_args(argv)
    try:
        return args.fonction(args)
    except ErreurTelemetrie as erreur:
        # Message destiné à être lu, pas une stacktrace : c'est une exigence du brief.
        print(f"\n{erreur}\n", file=sys.stderr)
        if isinstance(erreur, DossierIntrouvable):
            print(
                "En ligne de commande, indique-le avec l'option --dossier, par exemple :\n"
                r'  --dossier "D:\SteamLibrary\steamapps\common\Le Mans Ultimate\UserData\Telemetry"'
                "\n",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
