"""Ce que le serveur répond : la mise en forme JSON des analyses.

Aucun calcul de pilotage ici, et rien sur HTTP : ce module traduit les objets du
domaine en ce que la page attend.
"""

from __future__ import annotations

import math
import shutil
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .. import emplacements, parametres
from ..domaine import pays
from ..domaine.circuits import definition_circuit, definition_depuis_tours
from ..domaine.classement import classement_json
from ..domaine.comparaison import comparer
from ..domaine.donnees_tour import CANAL_GAZ_BRUT, bilan, charger
from ..domaine.leaderboard import TYPES_COMPTES, comptee, famille, leaderboard_json
from ..domaine.performances import Performance, noms_du_proprietaire, performance, performances
from ..domaine.piste import construire as construire_piste
from ..domaine.piste import trajectoires
from ..domaine.regularite import analyser
from ..domaine.session import Session
from ..domaine.virages import DefinitionCircuit, ecarts_par_virage
from ..errors import ErreurTelemetrie
from ..groupe import reglages as reglages_groupe
from ..groupe.seances import LOCAL, analyser_seance, designer_seance, est_seance
from ..groupe.service import ErreurGroupe, Service
from ..groupe.synchro import (
    CourseAPartager,
    Synchroniseur,
    charger_partage,
    charger_seance,
    copie_courante,
    dossier_seances,
    dossier_tours,
    fichier_copie,
    tours_des_amis,
)
from ..groupe.tours import Record, TourPartage, designer, est_partage, identifiant_course, identifiant_record
from ..sources import catalogue, resultats
from ..textes import Message
from ..stockage.index import Index, ResumeSession, balayage

#: Extensions acceptées pour un logo de marque déposé par l'utilisateur.
EXTENSIONS_LOGO = (".svg", ".png", ".webp", ".jpg", ".jpeg", ".gif")

#: Mesures d'un virage envoyées à la page.
MESURES_VIRAGE = (
    "distance_freinage",
    "vitesse_entree",
    "duree_freinage",
    "frein_max",
    "vitesse_min",
    "position_vitesse_min",
    "remise_gaz",
    "vitesse_remise_gaz",
    "vitesse_sortie",
    "temps_coasting",
)


@dataclass
class Contexte:
    """Ce que le serveur a besoin de savoir, passé aux gestionnaires de routes."""

    #: Dossier de télémétrie imposé (option --dossier) ; sinon, détection.
    dossier: Path | None = None
    #: Découpages et logos de l'utilisateur, qui priment sur ceux livrés avec
    #: l'outil (voir `emplacements.py`).
    dossier_virages: Path = field(default_factory=emplacements.virages_utilisateur)
    dossier_logos: Path = field(default_factory=emplacements.logos_utilisateur)
    virages_fournis: Path = field(default_factory=emplacements.virages_fournis)
    logos_fournis: Path = field(default_factory=emplacements.logos_fournis)

    @property
    def dossier_resultats(self) -> Path | None:
        """Dossier des résultats du jeu, d'où vient le modèle des voitures.

        Déduit de celui de la télémétrie. Renvoie None s'il est introuvable :
        l'outil marche sans, on perd seulement le modèle et la marque.
        """
        try:
            return resultats.dossier_resultats(telemetrie=self.dossier)
        except ErreurTelemetrie:
            return None


# ----------------------------------------------------------------------
# Mise en forme
# ----------------------------------------------------------------------


def _arrondir(valeurs: np.ndarray, decimales: int) -> list[float | None]:
    """Arrondit un tableau pour le JSON, en remplaçant les NaN par null.

    Sans arrondi, une comparaison de deux tours pèse plusieurs mégaoctets de
    chiffres dont les douze décimales ne veulent rien dire.
    """
    arrondi = np.round(np.asarray(valeurs, dtype=float), decimales)
    return [None if math.isnan(v) else float(v) for v in arrondi]


#: Canaux envoyés à la page, et décimales conservées selon ce que la donnée vaut
#: vraiment. Les autres canaux chargés ne servent qu'aux calculs.
DECIMALES = {
    "Ground Speed": 1,
    "Throttle Pos": 1,
    CANAL_GAZ_BRUT: 1,
    "Brake Pos": 1,
    "Steering Pos": 2,
    "Angle Volant": 1,
    "Engine RPM": 0,
    "Gear": 0,
    "Virtual Energy": 2,
    "GPS Latitude": 7,
    "GPS Longitude": 7,
}


# ----------------------------------------------------------------------
# Liste des sessions
# ----------------------------------------------------------------------


def _voiture(voitures: Mapping[str, resultats.Voiture], engagement: str | None) -> dict:
    """Ce qu'on affiche d'une voiture : l'engagement, et si on le sait le modèle.

    Le fichier de télémétrie ne connaît que l'engagement — « Manthey DK
    Engineering 2026 #91:WEC » — qui est l'écurie et le numéro, pas la voiture.
    Le modèle vient des fichiers de résultats du jeu (voir `resultats.py`).
    S'ils manquent, `modele` et `marque` sont nuls et la page se rabat sur
    l'engagement seul.
    """
    trouvee = voitures.get(engagement or "")
    return {
        "engagement": engagement,
        "modele": trouvee.modele if trouvee else None,
        "marque": trouvee.marque if trouvee else None,
        "classe": trouvee.classe if trouvee else None,
    }


def _voitures(contexte: Contexte) -> Mapping[str, resultats.Voiture]:
    """L'index des voitures, à ne demander qu'une fois par requête : même en cache,
    il parcourt le dossier des résultats pour vérifier qu'il est à jour."""
    return resultats.index_voitures(contexte.dossier_resultats)


def logos(contexte: Contexte) -> dict[str, Path]:
    """Logos de marque disponibles, indexés par marque.

    Deux sources : les logos libres de droits livrés avec l'outil, puis ceux
    que l'utilisateur dépose dans son dossier `logos`, nommés d'après la marque
    telle que l'outil l'affiche — `Porsche.png`, `Aston Martin.svg`. Les siens
    l'emportent. Sans logo, une pastille colorée fait l'affaire.

    Le nom demandé par le navigateur n'est JAMAIS transformé en chemin : on
    compare aux fichiers réellement présents. Un paramètre malveillant du
    genre `../../secret` ne correspond alors à rien.
    """
    trouves: dict[str, Path] = {}
    for dossier in (contexte.logos_fournis, contexte.dossier_logos):
        try:
            entrees = sorted(dossier.iterdir())
        except OSError:
            continue
        par_marque: dict[str, Path] = {}
        for fichier in entrees:
            if fichier.is_file() and fichier.suffix.lower() in EXTENSIONS_LOGO:
                par_marque.setdefault(fichier.stem, fichier)
        trouves.update(par_marque)
    return trouves


def _pays(circuit: str) -> dict | None:
    trouve = pays.pays_du_circuit(circuit, emplacements.donnees())
    return {"code": trouve.code, "nom": trouve.nom} if trouve else None


def _lire_index(contexte: Contexte) -> tuple[list, dict[str, ResumeSession], int]:
    """Sessions du disque, ce que l'index en sait, et combien restent à lire.

    Le nom de chaque fichier suffit à dresser la liste, tout de suite. Le reste
    vient de l'index, qui se complète en tâche de fond : la page se précise
    pendant qu'on la regarde.
    """
    reperes = catalogue.lister(contexte.dossier)
    index = Index()
    connues = index.lignes()
    a_lire = balayage.a_lire(reperes, connues)
    balayage.relancer(a_lire, index)
    return reperes, connues, len(a_lire)


#: Heures du jeu, au départ, qui font une séance de nuit : de 20 h à 6 h. Le départ seul
#: compte : une course qui part à 16 h et roule jusqu'à la nuit reste une course de jour.
NUIT_DEBUT = 20
NUIT_FIN = 6


def de_nuit(heure_jeu: str | None) -> bool:
    """Une séance partie de nuit, d'après l'heure du jeu au départ (« 21:00:00 »)."""
    try:
        heure = int((heure_jeu or "").split(":")[0])
    except ValueError:
        return False
    return heure >= NUIT_DEBUT or heure < NUIT_FIN


def sessions(contexte: Contexte) -> dict:
    reperes, connues, restant = _lire_index(contexte)
    voitures = _voitures(contexte)
    drapeaux: dict[str, dict | None] = {}
    dossier_resultats = contexte.dossier_resultats
    seances = resultats.Seances(dossier_resultats) if dossier_resultats is not None else None

    def etiquettes(repere, connue) -> dict:
        """Victoire et séance en ligne viennent des fichiers de résultats du jeu, la nuit
        de l'heure du jeu au départ."""
        trouvees = None
        if seances is not None and repere.enregistre_le is not None:
            trouvees = seances.etiquettes(
                repere.circuit,
                repere.code_type,
                repere.enregistre_le,
                connue.voiture if connue else None,
                connue.pilote if connue else None,
            )
        return {
            "victoire": bool(trouvees and trouvees["victoire"]),
            "en_ligne": bool(trouvees and trouvees["en_ligne"]),
            "nuit": de_nuit(connue.heure_jeu) if connue else False,
        }

    def ligne(repere) -> dict:
        connue = connues.get(str(repere.chemin))
        drapeau = drapeaux.get(repere.circuit, False)
        if drapeau is False:
            drapeau = drapeaux[repere.circuit] = _pays(repere.circuit)
        base = {
            "id": str(repere.chemin),
            "nom": repere.chemin.name,
            "circuit": repere.circuit,
            "pays": drapeau,
            "type": repere.code_type,
            "date": repere.enregistre_le.isoformat() if repere.enregistre_le else None,
            "taille": repere.taille,
            "journal": repere.journal_present,
            **etiquettes(repere, connue),
        }
        if connue is None:
            return base
        return {
            **base,
            "trace": connue.trace,
            "tours": connue.tours,
            "valides": connue.valides,
            "meilleur": connue.meilleur,
            "voiture": _voiture(voitures, connue.voiture),
            "categorie": connue.categorie,
            "indisponible": connue.illisible,
        }

    # Le contour de chaque tracé, une fois pour toutes : il sert de fond aux cartes.
    return {
        "sessions": [ligne(r) for r in reperes],
        "restant": restant,
        "contours": Index().contours(),
    }


def circuits(contexte: Contexte) -> dict:
    """Les records : pour chaque tracé, le meilleur tour de chaque voiture.

    Les variantes d'un circuit restent séparées : leurs chronos ne se comparent
    pas. La page les regroupe sous le nom du circuit.

    Seules comptent les qualifications et les courses, comme au leaderboard : en
    essais, on roule pour régler, pas pour le chrono (demandé le 2026-11-14).
    """
    reperes, connues, restant = _lire_index(contexte)
    voitures = _voitures(contexte)
    contours = Index().contours()

    par_trace: dict[str, list] = {}
    noms: dict[str, str] = {}
    pilotes: Counter = Counter()
    for repere in reperes:
        connue = connues.get(str(repere.chemin))
        if connue is None or connue.trace is None or repere.code_type not in TYPES_COMPTES:
            continue
        par_trace.setdefault(connue.trace, []).append((repere, connue))
        noms[connue.trace] = repere.circuit
        pilotes[connue.pilote] += 1

    def trace(nom: str, lignes: list) -> dict:
        records: dict[tuple[str, str], dict] = {}
        meilleurs: dict[tuple[str, str], dict] = {}
        for repere, connue in lignes:
            if connue.meilleur is None:
                continue
            voiture = _voiture(voitures, connue.voiture)
            classe = voiture["classe"] or connue.categorie or "?"
            record = {
                "classe": classe,
                "voiture": voiture,
                "session": connue.chemin,
                "type": repere.code_type,
                "date": repere.enregistre_le.isoformat() if repere.enregistre_le else None,
                "tour": connue.tour_meilleur,
                "chrono": connue.meilleur,
                "secteurs": [connue.s1, connue.s2, connue.s3],
            }
            for table, cle in (
                (records, (classe, voiture["modele"] or connue.voiture)),
                (meilleurs, (classe, repere.code_type)),
            ):
                if cle not in table or connue.meilleur < table[cle]["chrono"]:
                    table[cle] = record
        return {
            "trace": nom,
            "sessions": len(lignes),
            "tours": sum(connue.tours for _, connue in lignes),
            "voitures": len({c.voiture for _, c in lignes if c.voiture}),
            "longueur": max((c.longueur or 0.0 for _, c in lignes), default=None),
            "contour": contours.get(nom),
            "records": sorted(records.values(), key=lambda r: r["chrono"]),
            # Le meilleur de chaque catégorie en qualifs et en course.
            "meilleurs": list(meilleurs.values()),
        }

    groupes: dict[str, list] = {}
    for nom, lignes in par_trace.items():
        groupes.setdefault(noms[nom], []).append(trace(nom, lignes))
    return {
        "pilote": pilotes.most_common(1)[0][0] if pilotes else None,
        "restant": restant,
        "circuits": [
            {
                "circuit": circuit,
                "pays": _pays(circuit),
                # Le tracé le plus roulé d'abord : c'est celui qu'on affiche.
                "traces": sorted(traces, key=lambda x: -x["sessions"]),
            }
            for circuit, traces in sorted(groupes.items())
        ],
    }


# ----------------------------------------------------------------------
# Une session
# ----------------------------------------------------------------------


def _session_partagee(designation: str) -> dict:
    """Le record d'un ami, présenté comme une session d'un seul tour : la page le choisit
    et l'affiche comme les sessions de ce PC."""
    lu = charger_partage(designation)
    t = lu.tour
    return {
        "id": designation,
        "partage": True,
        "duree": lu.duree,
        "longueur": lu.longueur,
        "circuit": lu.info.trace,
        "pays": _pays(lu.info.trace),
        "type": lu.info.type_session,
        "voiture": lu.voiture,
        "categorie": lu.info.categorie,
        "pilote": lu.info.pilote,
        "meteo": "",
        "debattement_volant": lu.info.debattement_volant,
        "demultiplication": lu.info.demultiplication,
        "date": None,
        "journal": False,
        "tours": [
            {
                "numero": t.numero,
                "chrono": t.chrono,
                "duree_mesuree": t.duree_mesuree,
                "secteurs": list(t.secteurs),
                "valide": t.valide,
                "vitesse_min": round(t.vitesse_min, 1),
                "remarques": [],
            }
        ],
    }


def _noms_du_proprietaire(contexte: Contexte) -> set[str]:
    """Les noms sous lesquels roule le propriétaire de ce PC (`performances.noms_du_proprietaire`)."""
    dossier = contexte.dossier_resultats
    seances = resultats.Seances(dossier).toutes() if dossier is not None and dossier.is_dir() else []
    return noms_du_proprietaire(seances, {r.pilote for r in Index().lignes().values() if r.pilote})


def _seance_designee(contexte: Contexte, designation: str) -> tuple[resultats.ResultatsSession, str | None]:
    """La course que désigne « seance:<membre ou local>/<numéro> » (`groupe/seances.py`), et le
    pilote qui l'a partagée (None pour une course de ce PC)."""
    source, identifiant = analyser_seance(designation)
    if source != LOCAL:
        copie = copie_courante()
        brut = ((copie.performances.get(source) or {}).get(identifiant) if copie else None) or {}
        pilote = brut.get("pilote") if isinstance(brut, dict) and isinstance(brut.get("pilote"), str) else None
        return charger_seance(source, identifiant), pilote
    dossier = contexte.dossier_resultats
    trouvee = None
    if dossier is not None and dossier.is_dir():
        trouvee = next(
            (s for s in resultats.Seances(dossier).toutes() if f"{int(s.debut)}-{s.type}" == identifiant), None
        )
    seance = resultats.lire_session(trouvee.fichier) if trouvee is not None else None
    if seance is None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_seance_introuvable"), "seance_introuvable")
    return seance, None


def _session_seance(contexte: Contexte, designation: str) -> dict:
    """Une course dont on n'a que le classement — celle d'un ami, ou une course de ce PC roulée
    sans enregistrer la télémétrie — présentée comme une session sans tours : l'écran Résultats
    en montre le classement et ses onglets, pas les tours ni la régularité."""
    seance, pilote = _seance_designee(contexte, designation)
    trace = seance.parcours or seance.circuit
    arrivee = max((e.temps_total for e in seance.engages if e.temps_total), default=None)
    return {
        "id": designation,
        "seance": True,
        "partage": pilote is not None,
        "proprietaire": pilote,
        "duree": arrivee or (seance.minutes * 60 if seance.minutes else None),
        "longueur": seance.longueur,
        "circuit": trace,
        "pays": _pays(trace),
        "type": seance.type,
        "voiture": {"engagement": "", "modele": None, "marque": None, "classe": None},
        "categorie": None,
        "pilote": pilote,
        "meteo": "",
        "debattement_volant": None,
        "demultiplication": None,
        "date": seance.debut.isoformat() if seance.debut else None,
        "journal": False,
        "en_ligne": seance.en_ligne,
        "tours": [],
        "tours_seance": max((e.tours for e in seance.engages), default=0),
    }


def session(contexte: Contexte, chemin: str) -> dict:
    if est_partage(chemin):
        return _session_partagee(chemin)
    if est_seance(chemin):
        return _session_seance(contexte, chemin)
    lue = Session.ouvrir(chemin)
    return {
        "id": str(lue.chemin),
        "duree": lue.duree,
        "longueur": lue.longueur,
        # Le tracé plutôt que le circuit : c'est lui qui décrit ce qu'on a
        # roulé. « Monza Curva Grande Circuit » n'a pas les mêmes virages que
        # « Autodromo Nazionale Monza », alors que les deux portent le même
        # `TrackName`.
        "circuit": lue.info.trace,
        "pays": _pays(lue.info.trace),
        "type": lue.info.type_session,
        "voiture": _voiture(_voitures(contexte), lue.info.voiture),
        "categorie": lue.info.categorie,
        "pilote": lue.info.pilote,
        "meteo": lue.info.meteo,
        "debattement_volant": lue.info.debattement_volant,
        "demultiplication": lue.info.demultiplication,
        "date": lue.info.enregistree_le.isoformat() if lue.info.enregistree_le else None,
        "journal": lue.journal_present,
        "tours": [
            {
                "numero": t.numero,
                "chrono": t.chrono,
                "duree_mesuree": t.duree_mesuree,
                "secteurs": list(t.secteurs),
                "valide": t.valide,
                "vitesse_min": round(t.vitesse_min, 1),
                "remarques": [r.json() for r in t.remarques],
            }
            for t in lue.tours
        ],
    }


def classement(contexte: Contexte, chemin: str) -> dict:
    """Le classement de la séance qu'a enregistrée la session `chemin`, d'après le fichier
    de résultats que le jeu a écrit pour elle. `trouve` est faux s'il n'en a pas écrit.

    `chemin` peut aussi désigner une course dont on n'a que le classement (`seance:…`) : « toi »
    y est le propriétaire de ce PC s'il l'a courue, et personne sinon — en ligne, le jeu marque
    tous les humains comme joueurs, et un ami seul humain de sa course passerait pour lui."""
    if est_seance(chemin):
        seance, _ = _seance_designee(contexte, chemin)
        noms = _noms_du_proprietaire(contexte)
        moi = next((e.nom for e in seance.engages if e.nom in noms), None)
        if moi is None:
            seance = replace(seance, engages=tuple(replace(e, joueur=False) for e in seance.engages))
        return {"trouve": True, **classement_json(seance, moi)}
    info = Session.ouvrir(chemin).info
    dossier = contexte.dossier_resultats
    if dossier is None or info.enregistree_le is None:
        return {"trouve": False}
    fichier = resultats.trouver_session(
        info.circuit, info.code_type, info.enregistree_le, info.voiture, dossier
    )
    seance = resultats.lire_session(fichier) if fichier is not None else None
    if seance is None:
        return {"trouve": False}
    return {"trouve": True, **classement_json(seance, info.pilote)}


# ----------------------------------------------------------------------
# Leaderboard
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class MesPerformances:
    """Ce que les fichiers de ce PC disent de son propriétaire."""

    resultats: bool
    """Faux si le dossier des résultats du jeu est introuvable."""

    performances: list[Performance]
    noms: set[str]
    contours: dict[str, list]
    """Le contour de chaque tracé connu de la télémétrie."""


def mes_performances(contexte: Contexte) -> MesPerformances:
    """Les performances du propriétaire de ce PC, tirées des fichiers de résultats du jeu,
    les noms sous lesquels il roule, et les contours que sa télémétrie connaît."""
    dossier = contexte.dossier_resultats
    trouve = dossier is not None and dossier.is_dir()
    seances = resultats.Seances(dossier).toutes() if trouve else []
    index = Index()
    noms = noms_du_proprietaire(seances, {r.pilote for r in index.lignes().values() if r.pilote})
    return MesPerformances(trouve, performances(seances, noms), noms, index.contours())


def leaderboard(contexte: Contexte, params: Mapping[str, list[str]]) -> dict:
    """L'onglet Leaderboard, selon ses filtres (voir `domaine/leaderboard.py`).

    Il mêle les performances du propriétaire, tirées des fichiers de ce PC, et celles des
    autres membres de son groupe, tirées de la copie du groupe (`groupe/synchro.py`).
    `resultats` est faux si on ne trouve pas les fichiers de ce PC. Chaque circuit du menu
    reçoit son drapeau, et le contour de son tracé principal ; la page d'un circuit, le
    contour de son tracé. Les contours de ce PC passent avant ceux du groupe.
    """
    miennes = mes_performances(contexte)
    copie = copie_courante()
    autres = copie.performances_des_autres() if copie else []
    reponse = leaderboard_json(
        miennes.performances + autres,
        {cle: valeurs[0] for cle, valeurs in params.items() if valeurs},
        miennes.noms,
    )
    contours = {**(copie.contours if copie else {}), **miennes.contours}
    for circuit in reponse["circuits"]:
        circuit["pays"] = _pays(circuit["circuit"])
        circuit["contour"] = next(
            (contours[x["nom"]] for x in circuit["traces"] if x["nom"] in contours), None
        )
    if reponse["vue"] == "circuit":
        _tours_enregistres(contexte, reponse)
    _courses_ouvrables(contexte, reponse, copie)
    adhesion = reglages_groupe.adhesion()
    return {
        "resultats": miennes.resultats,
        # Le contour du tracé choisi, en fond de la page de son circuit.
        "contour": contours.get(reponse["filtres"]["trace"]),
        "groupe": (
            None
            if adhesion is None or copie is None
            else {"code": adhesion.code_affiche, "version": copie.version, "membres": len(copie.membres)}
        ),
        **reponse,
    }


def _le_plus_proche(candidats: list, voiture: str, chrono) -> object | None:
    """Le tour enregistré qui représente une ligne : dans la même voiture s'il y en a un,
    sinon le plus rapide de la catégorie."""
    memes = [c for c in candidats if (c.voiture if isinstance(c, Record) else c["voiture"]) == voiture]
    return min(memes or candidats, key=chrono, default=None)


def _tours_enregistres(contexte: Contexte, reponse: dict) -> None:
    """Le tour enregistré de chaque ligne des meilleurs tours, quand il existe : le record de
    ce PC dont la télémétrie est ici, ou celui qu'un ami a partagé (`groupe/tours.py`). La
    page en coche deux pour les comparer dans l'onglet Télémétrie. Ce n'est pas toujours le
    tour du classement : un meilleur tour roulé sans enregistrer n'a pas de télémétrie."""
    trace = reponse["filtres"]["trace"]
    miens: dict[str, list[Record]] = {}
    for record in mes_records(contexte, trace):
        miens.setdefault(famille(record.classe or ""), []).append(record)
    amis: dict[tuple[str, str], list[dict]] = {}
    for tour_ami in tours_des_amis(trace):
        amis.setdefault((tour_ami["pilote"], famille(tour_ami.get("classe") or "")), []).append(tour_ami)
    for categorie in reponse["tours"]:
        for ligne in categorie["lignes"]:
            if ligne["moi"]:
                record = _le_plus_proche(miens.get(categorie["classe"], []), ligne["voiture"], lambda r: r.chrono)
                ligne["enregistre"] = (
                    None
                    if record is None
                    else {"chemin": record.chemin, "numero": record.numero, "chrono": record.chrono, "voiture": record.voiture}
                )
            else:
                tour_ami = _le_plus_proche(
                    amis.get((ligne["pilote"], categorie["classe"]), []), ligne["voiture"], lambda t: t["chrono"]
                )
                ligne["enregistre"] = (
                    None
                    if tour_ami is None
                    else {
                        "chemin": tour_ami["id"],
                        "numero": tour_ami["numero"],
                        "chrono": tour_ami["chrono"],
                        "voiture": tour_ami["voiture"],
                    }
                )


def _courses_ouvrables(contexte: Contexte, reponse: dict, copie) -> None:
    """Ce qui s'ouvre depuis chaque ligne des courses : son classement dans l'onglet Résultats
    (`seance`), et sur la page d'un circuit son meilleur tour enregistré, à comparer dans
    l'onglet Télémétrie (`enregistre`, comme les lignes des meilleurs tours).

    Une course de ce PC s'ouvre par la session qui l'a enregistrée, sinon par son seul fichier
    de résultats ; celle d'un ami, par ce qu'il a partagé (`groupe/seances.py`) : rien tant
    que sa version de l'outil ne le partage pas."""
    lignes = reponse["historique"]["lignes"]
    if not lignes:
        return
    miennes = mes_courses(contexte) if any(l["moi"] for l in lignes) else {}
    # Une performance d'ami se retrouve par son numéro et son pilote : le même départ peut être
    # celui de deux membres, dans la même course.
    membres: dict[tuple[str, str], str] = {}
    for membre, liste in (copie.performances.items() if copie else ()):
        for identifiant, brut in liste.items():
            if isinstance(brut, dict) and isinstance(brut.get("pilote"), str):
                membres[(identifiant, brut["pilote"])] = membre
    circuit = reponse["vue"] == "circuit"
    for ligne in lignes:
        ligne["seance"] = None
        ligne["enregistre"] = None
        if ligne["moi"]:
            course = miennes.get(ligne["id"])
            if course is None:
                continue
            ligne["seance"] = course.tour.chemin if course.tour else designer_seance(LOCAL, ligne["id"])
            if circuit and course.tour:
                t = course.tour
                ligne["enregistre"] = {"chemin": t.chemin, "numero": t.numero, "chrono": t.chrono, "voiture": t.voiture}
            continue
        membre = membres.get((ligne["id"], ligne["pilote"]))
        if membre is None:
            continue
        if ligne["id"] in (copie.seances.get(membre) or {}):
            ligne["seance"] = designer_seance(membre, ligne["id"])
        meta = (copie.tours.get(membre) or {}).get(identifiant_course(ligne["id"]))
        if circuit and meta:
            ligne["enregistre"] = {
                "chemin": designer(membre, identifiant_course(ligne["id"])),
                "numero": meta["numero"],
                "chrono": meta["chrono"],
                "voiture": resultats.modele_canonique(meta["voiture"]),
            }


# ----------------------------------------------------------------------
# Le groupe
# ----------------------------------------------------------------------


def mes_records(contexte: Contexte, trace: str | None = None) -> list[Record]:
    """Les records du propriétaire à partager : sur chaque tracé (ou sur `trace` seul),
    dans chaque voiture, son meilleur tour valide des séances qui comptent au leaderboard
    — qualifications et courses EN LIGNE — dont la télémétrie a été enregistrée. Une séance
    se dit en ligne d'après le fichier de résultats que le jeu a écrit pour elle, comme les
    étiquettes de la colonne des sessions."""
    dossier_resultats = contexte.dossier_resultats
    if dossier_resultats is None or not dossier_resultats.is_dir():
        return []
    try:
        reperes = catalogue.lister(contexte.dossier)
    except ErreurTelemetrie:
        return []
    connues = Index().lignes()
    seances = resultats.Seances(dossier_resultats)
    voitures = _voitures(contexte)
    meilleurs: dict[tuple[str, str], Record] = {}
    for repere in reperes:
        connue = connues.get(str(repere.chemin))
        if (
            connue is None
            or connue.trace is None
            or (trace is not None and connue.trace != trace)
            or connue.meilleur is None
            or connue.tour_meilleur is None
            or repere.enregistre_le is None
            or repere.code_type not in TYPES_COMPTES
        ):
            continue
        etiquettes = seances.etiquettes(
            repere.circuit, repere.code_type, repere.enregistre_le, connue.voiture, connue.pilote
        )
        if not etiquettes["en_ligne"]:
            continue
        voiture = _voiture(voitures, connue.voiture)
        modele = voiture["modele"] or connue.voiture or "?"
        cle = (connue.trace, modele)
        if cle in meilleurs and meilleurs[cle].chrono <= connue.meilleur:
            continue
        meilleurs[cle] = Record(
            id=identifiant_record(connue.trace, modele),
            trace=connue.trace,
            circuit=repere.circuit,
            voiture=modele,
            marque=voiture["marque"],
            classe=voiture["classe"] or connue.categorie,
            pilote=connue.pilote or "?",
            date=repere.enregistre_le.isoformat(),
            type=repere.code_type,
            chemin=str(repere.chemin),
            numero=connue.tour_meilleur,
            chrono=connue.meilleur,
        )
    return sorted(meilleurs.values(), key=lambda r: (r.trace, r.voiture))


@dataclass(frozen=True)
class MaCourse:
    """Une course en ligne du propriétaire de ce PC."""

    id: str
    """Celui de sa performance : « 1794245179-R »."""

    fichier: Path
    """Son fichier de résultats."""

    tour: Record | None
    """Son meilleur tour enregistré, s'il y en a un."""


def mes_courses(contexte: Contexte) -> dict[str, MaCourse]:
    """Les courses en ligne du propriétaire, par numéro de performance, les plus récentes
    d'abord : leur fichier de résultats, dont le classement se partage au groupe, et leur
    meilleur tour enregistré, dont la télémétrie se partage aussi (demandé le 2026-11-14 : les
    tours des courses d'un circuit se comparent depuis l'onglet Courses du leaderboard)."""
    dossier_resultats = contexte.dossier_resultats
    if dossier_resultats is None or not dossier_resultats.is_dir():
        return {}
    seances = resultats.Seances(dossier_resultats)
    connues = Index().lignes()
    toutes = seances.toutes()
    noms = noms_du_proprietaire(toutes, {r.pilote for r in connues.values() if r.pilote})
    # Celles que compte le leaderboard : une course où il n'a pas roulé n'y figure pas.
    courses = {
        f"{int(s.debut)}-R": s
        for s in toutes
        if s.type == "R" and s.en_ligne and any(e.nom in noms and comptee(performance(s, e)) for e in s.joueurs)
    }
    try:
        reperes = catalogue.lister(contexte.dossier)
    except ErreurTelemetrie:
        reperes = []
    voitures = _voitures(contexte)
    tours: dict[str, Record] = {}
    for repere in reperes:
        connue = connues.get(str(repere.chemin))
        if (
            repere.code_type != "R"
            or repere.enregistre_le is None
            or connue is None
            or connue.trace is None
            or connue.meilleur is None
            or connue.tour_meilleur is None
        ):
            continue
        seance = seances.seance(repere.circuit, "R", repere.enregistre_le, connue.voiture)
        identifiant = f"{int(seance.debut)}-R" if seance is not None else None
        if identifiant not in courses or (identifiant in tours and tours[identifiant].chrono <= connue.meilleur):
            continue
        voiture = _voiture(voitures, connue.voiture)
        tours[identifiant] = Record(
            id=identifiant_course(identifiant),
            trace=connue.trace,
            circuit=repere.circuit,
            voiture=voiture["modele"] or connue.voiture or "?",
            marque=voiture["marque"],
            classe=voiture["classe"] or connue.categorie,
            pilote=connue.pilote or "?",
            date=datetime.fromtimestamp(seance.debut, timezone.utc).isoformat(),
            type="R",
            chemin=str(repere.chemin),
            numero=connue.tour_meilleur,
            chrono=connue.meilleur,
        )
    return {
        identifiant: MaCourse(identifiant, s.fichier, tours.get(identifiant))
        for identifiant, s in sorted(courses.items(), key=lambda x: -x[1].debut)
    }


def _signature_fichier(chemin: Path) -> str:
    try:
        etat = chemin.stat()
    except OSError:
        return ""
    return f"{etat.st_mtime_ns}|{etat.st_size}"


def sources_du_groupe(
    contexte: Contexte,
) -> tuple[list[Performance], dict, list[Record], list[CourseAPartager]]:
    """Ce que la synchronisation envoie : les performances du propriétaire, les contours de
    ce PC, ses tours à partager (ses records, puis le meilleur tour de chacune de ses courses,
    les plus récentes d'abord), et ses courses dont le classement part."""
    miennes = mes_performances(contexte)
    courses = mes_courses(contexte)
    tours = mes_records(contexte) + [c.tour for c in courses.values() if c.tour is not None]
    return (
        miennes.performances,
        miennes.contours,
        tours,
        [CourseAPartager(c.id, str(c.fichier), _signature_fichier(c.fichier)) for c in courses.values()],
    )


def tours_du_groupe(params: Mapping[str, list[str]]) -> dict:
    """Les records des amis à comparer, sur un tracé (`trace`) ou sur tous."""
    trace = (params.get("trace") or [None])[0]
    return {"tours": tours_des_amis(trace)}


def _service() -> Service:
    adresse = reglages_groupe.adresse_service()
    if adresse is None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_sans_service"), "sans_service")
    return Service(adresse)


def _nom_dans_le_groupe(charge: Mapping) -> str:
    nom = charge.get("nom")
    if not isinstance(nom, str) or not 1 <= len(nom.strip()) <= 40:
        raise ErreurGroupe(Message("serveur.erreur.groupe_nom"), "nom_invalide")
    return nom.strip()


def groupe(contexte: Contexte, synchroniseur: Synchroniseur) -> dict:
    """Ce que montre l'écran Groupe : le service, le groupe de ce PC et ses membres, l'état
    de la synchronisation, et le nom à proposer pour rejoindre (le plus roulé)."""
    adhesion = reglages_groupe.adhesion()
    copie = copie_courante()
    noms = Counter(p.pilote for p in mes_performances(contexte).performances if p.en_ligne)
    return {
        "service": reglages_groupe.adresse_service() is not None,
        "groupe": (
            None
            if adhesion is None or copie is None
            else {
                "code": adhesion.code_affiche,
                "nom": adhesion.nom,
                "version": copie.version,
                "derniere": copie.derniere,
                "membres": [{**m, "moi": m["id"] == adhesion.membre} for m in copie.membres],
            }
        ),
        "synchro": synchroniseur.etat,
        "nom_propose": noms.most_common(1)[0][0] if noms else "",
    }


def creer_groupe(contexte: Contexte, synchroniseur: Synchroniseur, charge: Mapping) -> dict:
    """Crée un groupe dont ce PC est le premier membre, puis y envoie ses performances."""
    if reglages_groupe.adhesion() is not None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_deja"), "deja")
    reglages_groupe.enregistrer(_service().creer(_nom_dans_le_groupe(charge)))
    synchroniseur.maintenant()
    return groupe(contexte, synchroniseur)


def rejoindre_groupe(contexte: Contexte, synchroniseur: Synchroniseur, charge: Mapping) -> dict:
    """Fait entrer ce PC dans un groupe avec son code, puis synchronise."""
    if reglages_groupe.adhesion() is not None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_deja"), "deja")
    nom = _nom_dans_le_groupe(charge)
    reglages_groupe.enregistrer(_service().rejoindre(str(charge.get("code") or ""), nom))
    synchroniseur.maintenant()
    return groupe(contexte, synchroniseur)


def quitter_groupe(contexte: Contexte, synchroniseur: Synchroniseur) -> dict:
    """Retire ce PC de son groupe : le service efface ses performances, et ce PC oublie la
    copie du groupe. Si le service ne répond pas, ce PC reste dans le groupe : ses
    performances ne doivent pas y rester à son insu."""
    adhesion = reglages_groupe.adhesion()
    if adhesion is not None:
        try:
            _service().quitter(adhesion)
        except ErreurGroupe as erreur:
            # Déjà parti, ou groupe disparu : il n'y a plus rien à effacer là-bas.
            if erreur.code not in ("non_membre", "groupe_introuvable"):
                raise
        reglages_groupe.enregistrer(None)
        fichier_copie().unlink(missing_ok=True)
        shutil.rmtree(dossier_tours(), ignore_errors=True)
        shutil.rmtree(dossier_seances(), ignore_errors=True)
        synchroniseur.oublier()
    return groupe(contexte, synchroniseur)


def synchroniser_groupe(contexte: Contexte, synchroniseur: Synchroniseur) -> dict:
    """Le bouton « Synchroniser maintenant »."""
    synchroniseur.maintenant()
    return groupe(contexte, synchroniseur)


# ----------------------------------------------------------------------
# Comparaison de deux tours
# ----------------------------------------------------------------------


def _charger_tour(designation: str, numero: int):
    """Un tour de ce PC (le chemin de sa session), ou le record d'un ami
    (« groupe:<membre>/<numéro> », voir `groupe/tours.py`) : les deux se comparent pareil."""
    return charger_partage(designation) if est_partage(designation) else charger(designation, numero)


def comparaison(contexte: Contexte, params: dict[str, list[str]]) -> dict:
    # Sans tour comparé, le tour se compare à lui-même : la page n'en montre alors
    # que la référence.
    resultat = comparer(
        _charger_tour(params["ref"][0], int(params["tour_ref"][0])),
        _charger_tour(params.get("cmp", params["ref"])[0], int(params.get("tour_cmp", params["tour_ref"])[0])),
    )
    voitures = _voitures(contexte)

    traces = {
        nom: {
            "reference": _arrondir(ref, DECIMALES[nom]),
            "compare": _arrondir(cmp, DECIMALES[nom]),
        }
        for nom, (ref, cmp) in resultat.traces.items()
        if nom in DECIMALES
    }

    def resume(donnees) -> dict:
        # Le record d'un ami n'a pas de fichier sur ce PC : sa désignation en tient lieu,
        # et sa voiture est celle que le PC de l'ami connaît.
        partage = isinstance(donnees, TourPartage)
        return {
            "session": donnees.info.pilote if partage else donnees.chemin.name,
            "chemin": donnees.identifiant if partage else str(donnees.chemin),
            "partage": partage,
            "circuit": donnees.info.trace,
            "pays": _pays(donnees.info.trace),
            "type": donnees.info.code_type,
            "pilote": donnees.info.pilote,
            "categorie": donnees.info.categorie,
            "voiture": donnees.voiture if partage else _voiture(voitures, donnees.info.voiture),
            "debattement_volant": donnees.info.debattement_volant,
            "numero": donnees.tour.numero,
            "chrono": donnees.tour.chrono,
            "secteurs": list(donnees.tour.secteurs),
            "longueur": round(donnees.longueur, 1),
            "remarques": [r.json() for r in donnees.tour.remarques],
            "temps": _arrondir(donnees.temps_a_distance(resultat.distance), 3),
            **asdict(bilan(donnees)),
        }

    return {
        "piste": _piste(resultat),
        # L'axe est régulier : on envoie sa définition, pas ses 5 776 valeurs.
        "distance": {
            "debut": float(resultat.distance[0]),
            "pas": float(resultat.distance[1] - resultat.distance[0]),
            "nombre": int(resultat.distance.size),
        },
        "delta": _arrondir(resultat.delta, 3),
        "traces": traces,
        "reference": resume(resultat.reference),
        "compare": resume(resultat.compare),
        "ecart_final": round(resultat.ecart_final, 3),
        "ecart_chronos": resultat.ecart_chronos,
        "coherent": resultat.coherent,
        "avertissements": [a.json() for a in resultat.avertissements],
        "troncons": [
            {"distance": d, "delta": round(v, 3)} for d, v in resultat.perte_par_troncon()
        ],
    }


def _piste(resultat) -> dict:
    """Géométrie de la route et trajectoires des deux tours, en mètres.

    Les coordonnées brutes valent près de 6,7 millions de mètres (60° de
    latitude × 111 320) : on retranche une origine, sans quoi chaque nombre
    pèserait dix chiffres pour deux décimales utiles.
    """
    tours = [resultat.reference, resultat.compare]
    geometrie = construire_piste(tours, resultat.distance)
    chemins = trajectoires(tours, resultat.distance)

    tous = np.vstack([geometrie.axe, geometrie.bord_gauche, geometrie.bord_droit, *chemins])
    origine = np.nanmin(tous, axis=0)

    def xy(points: np.ndarray) -> dict:
        decale = points - origine
        # Au décimètre : la position GPS du jeu est quantifiée à 0,42 m, une
        # précision supérieure serait du bruit et doublerait la taille du JSON.
        return {
            "x": _arrondir(decale[:, 0], 1),
            "y": _arrondir(decale[:, 1], 1),
        }

    return {
        "axe": xy(geometrie.axe),
        "bord_gauche": xy(geometrie.bord_gauche),
        "bord_droit": xy(geometrie.bord_droit),
        # 1 là où les deux bords sont mesurés, 0 là où l'un est estimé.
        "mesure": [int(v) for v in geometrie.mesure],
        # Et pour chaque bord séparément : un bord longé est mesuré, que
        # l'autre le soit ou non.
        "mesure_gauche": [int(v) for v in geometrie.mesure_gauche],
        "mesure_droit": [int(v) for v in geometrie.mesure_droit],
        "trace_reference": xy(chemins[0]),
        "trace_compare": xy(chemins[1]),
        "largeur": round(geometrie.largeur_mediane, 2),
        "part_mesuree": round(geometrie.part_mesuree, 3),
        "ecart_axes": round(geometrie.ecart_axes, 3),
    }


# ----------------------------------------------------------------------
# Virages
# ----------------------------------------------------------------------


def definition(contexte: Contexte, lue: Session) -> tuple[DefinitionCircuit, Path]:
    return definition_circuit(lue, contexte.dossier_virages, contexte.virages_fournis)


def virages(contexte: Contexte, params: dict[str, list[str]]) -> dict:
    chemin_ref = params["ref"][0]
    chemin_cmp = params.get("cmp", params["ref"])[0]
    reference = _charger_tour(chemin_ref, int(params["tour_ref"][0]))
    compare = _charger_tour(chemin_cmp, int(params["tour_cmp"][0]))
    if est_partage(chemin_ref):
        # Le record d'un ami en référence : pas de session de ce PC d'où tirer le découpage.
        circuit, fichier = definition_depuis_tours(
            reference.info.trace, [reference, compare], contexte.dossier_virages, contexte.virages_fournis
        )
    else:
        circuit, fichier = definition(contexte, Session.ouvrir(chemin_ref))
    ecarts = ecarts_par_virage(reference, compare, circuit, parametres.lire().virages)

    def ligne(ecart) -> dict:
        a, b = ecart.reference, ecart.compare

        def paire(nom: str) -> dict:
            va = getattr(a, nom)
            vb = getattr(b, nom) if b else None
            difference = None if va is None or vb is None else vb - va
            return {"reference": va, "compare": vb, "ecart": difference}

        return {
            "numero": a.virage.numero,
            "nom": a.virage.libelle,
            "sens": a.virage.sens_libelle,
            "delta_zone": ecart.delta_zone,
            "debut": a.virage.debut,
            "fin": a.virage.fin,
            "rayon_min": round(a.virage.rayon_min, 1),
            "remarques": [r.json() for r in (*a.remarques, *(b.remarques if b else ()))],
            "mesures": {nom: paire(nom) for nom in MESURES_VIRAGE},
        }

    return {
        "circuit": circuit.circuit,
        "fichier": str(fichier),
        "automatique": circuit.automatique,
        "virages": [ligne(e) for e in ecarts],
        "coasting_total": {
            "reference": round(sum(e.reference.temps_coasting for e in ecarts), 2),
            "compare": round(
                sum(e.compare.temps_coasting for e in ecarts if e.compare), 2
            ),
        },
    }


# ----------------------------------------------------------------------
# Régularité
# ----------------------------------------------------------------------


def regularite(contexte: Contexte, params: dict[str, list[str]]) -> dict:
    chemin = params["chemin"][0]
    circuit, fichier = definition(contexte, Session.ouvrir(chemin))
    r = analyser(chemin, circuit, seuils=parametres.lire().virages)

    return {
        "circuit": r.circuit,
        "type_session": r.type_session,
        "voiture": r.voiture,
        "fichier_virages": str(fichier),
        # Un tour de course se juge autrement : trafic, stratégie et drapeaux
        # pèsent sur les chronos sans rien dire du pilotage.
        "course": r.type_session.lower() == "race",
        "fiable": r.fiable,
        "tours": [
            {"numero": n, "chrono": round(c, 3)} for n, c in zip(r.numeros, r.chronos)
        ],
        "meilleur": round(r.meilleur, 3),
        "median": round(r.median, 3),
        "ecart_type": round(r.ecart_type, 3),
        "ecart_meilleur_median": round(r.ecart_meilleur_median, 3),
        "tour_ideal": round(r.tour_ideal, 3),
        "marge_de_regularite": round(r.marge_de_regularite, 3),
        "tendance": round(r.tendance, 3),
        "moitie_debut": round(r.moitie_debut, 3),
        "moitie_fin": round(r.moitie_fin, 3),
        "virages": [
            {
                "numero": v.virage.numero,
                "nom": v.virage.libelle,
                "sens": v.virage.sens_libelle,
                "debut": v.virage.debut,
                "fin": v.virage.fin,
                "temps_median": round(v.temps_median, 3),
                "temps_meilleur": round(v.temps_meilleur, 3),
                "dispersion": round(v.dispersion_robuste, 3),
                "ecart_type": round(v.dispersion, 3),
                "potentiel": round(v.potentiel, 3),
                "dispersion_freinage": (
                    round(v.dispersion_freinage, 1)
                    if v.dispersion_freinage is not None
                    else None
                ),
                "dispersion_vitesse_min": round(v.dispersion_vitesse_min, 1),
                "passage_aberrant": v.passage_aberrant,
                "tour_le_plus_lent": v.tour_le_plus_lent,
                "passages": [
                    {"tour": p.tour, "temps": round(p.temps, 3)} for p in v.passages
                ],
            }
            for v in r.classement
        ],
    }
