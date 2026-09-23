"""Serveur local pour l'interface web.

Rien ne sort de la machine : le serveur n'écoute que sur 127.0.0.1, et la page
ne charge aucune ressource extérieure. L'outil fonctionne donc sans connexion.

Il s'appuie sur `http.server` de la bibliothèque standard plutôt que sur un
cadriciel : le besoin est de servir une page et quelques routes JSON, ce n'est
pas la peine d'ajouter une dépendance et un vocabulaire de plus à apprendre.

Trois protections, parce qu'un serveur local n'est pas pour autant à l'abri :

* seuls les fichiers `.duckdb` du dossier de télémétrie peuvent être ouverts,
  quel que soit le chemin que la page transmet ;
* seules les requêtes adressées à « 127.0.0.1 » ou « localhost » sont servies,
  ce qui ferme la porte à une page web qui ferait pointer son propre nom de
  domaine vers la machine (« DNS rebinding ») ;
* la seule route qui modifie quelque chose — le choix du dossier de
  télémétrie — exige une requête venue de la page de l'outil elle-même (en-tête
  Origin), en JSON : un autre site ouvert dans le navigateur ne peut pas la
  déclencher.
"""

from __future__ import annotations

import errno
import json
import math
import shutil
import socket
import sys
import threading
import traceback
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from .. import __version__, catalogue, emplacements, pays, resultats
from ..comparaison import comparer_fichiers
from ..donnees_tour import charger
from ..piste import construire as construire_piste
from ..regularite import analyser
from ..virages import (
    DefinitionCircuit,
    detecter,
    fichier_definition,
    mesurer,
    secteurs,
)
from ..errors import DossierIntrouvable, ErreurTelemetrie
from ..reader import FichierSession
from ..session import Session

STATIQUE = Path(__file__).parent / "statique"

TYPES_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

#: Extensions acceptées pour un logo de marque déposé par l'utilisateur.
EXTENSIONS_LOGO = (".svg", ".png", ".webp", ".jpg", ".jpeg", ".gif")


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
# Mise en forme des réponses
# ----------------------------------------------------------------------


def _arrondir(valeurs: np.ndarray, decimales: int) -> list[float | None]:
    """Arrondit un tableau pour le JSON, en remplaçant les NaN par null.

    Sans arrondi, une comparaison de deux tours pèse plusieurs mégaoctets de
    chiffres dont les douze décimales ne veulent rien dire.
    """
    arrondi = np.round(np.asarray(valeurs, dtype=float), decimales)
    return [None if math.isnan(v) else float(v) for v in arrondi]


#: Nombre de décimales conservé par canal, selon ce que la donnée vaut vraiment.
DECIMALES = {
    "delta": 3,
    "Ground Speed": 1,
    "Throttle Pos": 1,
    "Brake Pos": 1,
    "Steering Pos": 2,
    "Angle Volant": 1,
    "Engine RPM": 0,
    "Gear": 0,
    "GPS Latitude": 7,
    "GPS Longitude": 7,
}


def _sessions(contexte: Contexte) -> list[dict]:
    return [
        {
            "id": str(f.chemin),
            "nom": f.chemin.name,
            "circuit": f.circuit,
            "pays": _pays(f.circuit),
            "type": f.code_type,
            "date": f.enregistre_le.isoformat() if f.enregistre_le else None,
            "taille": f.taille,
            "journal": f.journal_present,
        }
        for f in catalogue.lister(contexte.dossier)
    ]


#: Tracé de chaque session, indexé comme les résumés.
#:
#: LMU propose plusieurs variantes du même circuit — « Monza Curva Grande
#: Circuit » à côté d'« Autodromo Nazionale Monza », « Bahrain Outer Circuit »
#: à côté du tracé complet — et elles n'ont ni la même longueur ni les mêmes
#: virages. Le NOM DU FICHIER ne porte que `TrackName` : les deux Monza
#: s'appellent pareil sur le disque, et rien ne les distingue sans ouvrir le
#: fichier.
#:
#: Ouvrir les 388 sessions coûte 9,7 s — trop pour une liste censée être
#: instantanée. On les lit donc en tâche de fond, et la liste se précise
#: pendant que l'utilisateur la regarde.
_traces: dict[tuple[str, int, int], str] = {}
_verrou_traces = threading.Lock()
_scan_traces: threading.Thread | None = None


def _cle_fichier(chemin: Path) -> tuple[str, int, int] | None:
    try:
        etat = chemin.stat()
    except OSError:
        return None
    return (str(chemin), etat.st_mtime_ns, etat.st_size)


def _traces_connues(contexte: Contexte) -> dict:
    """Tracés déjà lus, et combien il en reste. Lance le balayage au besoin."""
    global _scan_traces

    reperes = catalogue.lister(contexte.dossier)
    cles = {r.chemin: _cle_fichier(r.chemin) for r in reperes}
    with _verrou_traces:
        connus = {
            str(chemin): _traces[cle]
            for chemin, cle in cles.items()
            if cle in _traces and _traces[cle]
        }
        restant = sum(1 for cle in cles.values() if cle and cle not in _traces)

    if restant and (_scan_traces is None or not _scan_traces.is_alive()):
        _scan_traces = threading.Thread(
            target=_balayer_traces, args=(list(cles.items()),), daemon=True
        )
        _scan_traces.start()

    return {"traces": connus, "restant": restant}


def _balayer_traces(fichiers: list) -> None:
    """Lit le tracé de chaque session, une par une, en tâche de fond.

    Un fichier illisible — session en cours d'enregistrement, format inconnu —
    est mémorisé comme vide plutôt que retenté sans fin.
    """
    for chemin, cle in fichiers:
        if cle is None:
            continue
        with _verrou_traces:
            if cle in _traces:
                continue
        trace = ""
        try:
            with FichierSession(chemin) as fichier:
                trace = fichier.info.trace
        except (ErreurTelemetrie, Exception):  # noqa: BLE001
            trace = ""
        with _verrou_traces:
            _traces[cle] = trace


#: Résumés déjà calculés, indexés par (chemin, date de modification, taille).
#: Parcourir les 378 sessions du disque prend une douzaine de secondes ; on ne
#: le refait pas à chaque affichage de la liste. La clé inclut la taille et la
#: date pour qu'une session réécrite par le jeu soit recalculée.
_cache_resumes: dict[tuple[str, int, int], dict] = {}


def _voiture(contexte: Contexte, engagement: str) -> dict:
    """Ce qu'on affiche d'une voiture : l'engagement, et si on le sait le modèle.

    Le fichier de télémétrie ne connaît que l'engagement — « Manthey DK
    Engineering 2026 #91:WEC » — qui est l'écurie et le numéro, pas la voiture.
    Le modèle vient des fichiers de résultats du jeu (voir `resultats.py`).
    S'ils manquent, `modele` et `marque` sont nuls et la page se rabat sur
    l'engagement seul.
    """
    trouvee = resultats.voiture(engagement, contexte.dossier_resultats)
    return {
        "engagement": engagement,
        "modele": trouvee.modele if trouvee else None,
        "marque": trouvee.marque if trouvee else None,
        "classe": trouvee.classe if trouvee else None,
    }


def _logos(contexte: Contexte) -> dict[str, Path]:
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


def _resumes(contexte: Contexte, params: dict[str, list[str]]) -> list[dict]:
    """Nombre de tours et meilleur chrono, pour les sessions DEMANDÉES.

    Chaque résumé oblige à ouvrir le fichier : analyser les 378 sessions du
    disque prend une douzaine de secondes, ce qui est insupportable à chaque
    ouverture de la liste. Le navigateur ne demande donc que les sessions qu'il
    affiche réellement, une dizaine à la fois.
    """
    resumes = []
    for brut in params.get("chemin", []):
        chemin = Path(brut)
        try:
            etat = chemin.stat()
        except OSError:
            continue
        cle = (str(chemin), etat.st_mtime_ns, etat.st_size)
        if cle not in _cache_resumes:
            _cache_resumes[cle] = _resumer(contexte, chemin)
        resumes.append({"id": str(chemin), **_cache_resumes[cle]})
    return resumes


def _resumer(contexte: Contexte, chemin: Path) -> dict:
    try:
        session = Session.ouvrir(chemin)
    except ErreurTelemetrie as erreur:
        return {"tours": 0, "valides": 0, "meilleur": None, "indisponible": str(erreur)}
    meilleur = session.meilleur_tour
    return {
        "tours": len(session.tours),
        "valides": len(session.tours_valides),
        "meilleur": meilleur.chrono if meilleur else None,
        "trace": session.info.trace,
        "voiture": _voiture(contexte, session.info.voiture),
        "indisponible": None,
    }


def _session(contexte: Contexte, chemin: str) -> dict:
    session = Session.ouvrir(chemin)
    return {
        "id": str(session.chemin),
        # Le tracé plutôt que le circuit : c'est lui qui décrit ce qu'on a
        # roulé. « Monza Curva Grande Circuit » n'a pas les mêmes virages que
        # « Autodromo Nazionale Monza », alors que les deux portent le même
        # `TrackName`.
        "circuit": session.info.trace,
        "pays": _pays(session.info.trace),
        "type": session.info.type_session,
        "voiture": _voiture(contexte, session.info.voiture),
        "categorie": session.info.categorie,
        "pilote": session.info.pilote,
        "meteo": session.info.meteo,
        "debattement_volant": session.info.debattement_volant,
        "demultiplication": session.info.demultiplication,
        "date": (
            session.info.enregistree_le.isoformat()
            if session.info.enregistree_le
            else None
        ),
        "journal": session.journal_present,
        "tours": [
            {
                "numero": t.numero,
                "chrono": t.chrono,
                "duree_mesuree": t.duree_mesuree,
                "secteurs": list(t.secteurs),
                "valide": t.valide,
                "vitesse_min": round(t.vitesse_min, 1),
                "remarques": list(t.remarques),
            }
            for t in session.tours
        ],
    }


def _comparaison(contexte: Contexte, params: dict[str, list[str]]) -> dict:
    comparaison = comparer_fichiers(
        params["ref"][0],
        int(params["tour_ref"][0]),
        params.get("cmp", params["ref"])[0],
        int(params["tour_cmp"][0]),
    )

    traces = {
        nom: {
            "reference": _arrondir(ref, DECIMALES.get(nom, 3)),
            "compare": _arrondir(cmp, DECIMALES.get(nom, 3)),
        }
        for nom, (ref, cmp) in comparaison.traces.items()
    }

    def resume(donnees) -> dict:
        return {
            "session": donnees.chemin.name,
            "circuit": donnees.info.trace,
            "voiture": _voiture(contexte, donnees.info.voiture),
            "debattement_volant": donnees.info.debattement_volant,
            "numero": donnees.tour.numero,
            "chrono": donnees.tour.chrono,
            "longueur": round(donnees.longueur, 1),
            "remarques": list(donnees.tour.remarques),
        }

    return {
        "piste": _piste(comparaison),
        # L'axe est régulier : on envoie sa définition, pas ses 5 776 valeurs.
        "distance": {
            "debut": float(comparaison.distance[0]),
            "pas": float(comparaison.distance[1] - comparaison.distance[0]),
            "nombre": int(comparaison.distance.size),
        },
        "delta": _arrondir(comparaison.delta, 3),
        "traces": traces,
        "reference": resume(comparaison.reference),
        "compare": resume(comparaison.compare),
        "ecart_final": round(comparaison.ecart_final, 3),
        "ecart_chronos": comparaison.ecart_chronos,
        "coherent": comparaison.coherent,
        "avertissements": list(comparaison.avertissements),
        "troncons": [
            {"distance": d, "delta": round(v, 3)}
            for d, v in comparaison.perte_par_troncon()
        ],
    }


def _piste(comparaison) -> dict:
    """Géométrie de la route et trajectoires des deux tours, en mètres.

    Les coordonnées brutes valent près de 6,7 millions de mètres (60° de
    latitude × 111 320) : on retranche une origine, sans quoi chaque nombre
    pèserait dix chiffres pour deux décimales utiles.
    """
    tours = [comparaison.reference, comparaison.compare]
    geometrie = construire_piste(tours, comparaison.distance)

    traces = [
        np.column_stack(
            [
                t.sur_distance(comparaison.distance)["GPS Longitude"],
                t.sur_distance(comparaison.distance)["GPS Latitude"],
            ]
        )
        for t in tours
    ]
    k = math.cos(math.radians(float(np.mean(traces[0][:, 1]))))
    traces = [
        np.column_stack([tr[:, 0] * 111_320.0 * k, tr[:, 1] * 111_320.0]) for tr in traces
    ]

    tous = np.vstack([geometrie.axe, geometrie.bord_gauche, geometrie.bord_droit, *traces])
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
        "trace_reference": xy(traces[0]),
        "trace_compare": xy(traces[1]),
        "largeur": round(geometrie.largeur_mediane, 2),
        "part_mesuree": round(geometrie.part_mesuree, 3),
        "ecart_axes": round(geometrie.ecart_axes, 3),
    }


#: Découpages de circuits déjà calculés, par chemin de fichier de définition.
#:
#: Indexé par la date de modification ET la taille du fichier, pas par son seul
#: chemin : le README invite à retoucher ce fichier à la main, et une retouche
#: faite pendant que le serveur tournait était ignorée jusqu'au redémarrage,
#: sans aucun signe.
_cache_virages: dict[tuple[str, int, int], DefinitionCircuit] = {}

#: Deux requêtes simultanées sur un circuit pas encore découpé détecteraient
#: chacune les virages et écriraient le même fichier en même temps.
_verrou_virages = threading.Lock()


def _definition(contexte: Contexte, session: Session) -> tuple[DefinitionCircuit, Path]:
    """Découpage du circuit, lu sur disque ou détecté puis enregistré.

    Le fichier est fait pour être retouché à la main : une fois écrit, on ne le
    régénère jamais, même si la détection donnerait autre chose.
    """
    chemin = fichier_definition(contexte.dossier_virages, session.info.trace)
    with _verrou_virages:
        # Un découpage livré avec l'outil est recopié chez l'utilisateur la
        # première fois : c'est la copie qu'il retouchera, et elle survivra au
        # remplacement de l'outil par une nouvelle version.
        fourni = fichier_definition(contexte.virages_fournis, session.info.trace)
        if not chemin.exists() and fourni.is_file():
            chemin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fourni, chemin)
        cle = _cle_fichier(chemin)
        if cle is not None:
            if cle not in _cache_virages:
                _cache_virages[cle] = DefinitionCircuit.lire(chemin)
            return _cache_virages[cle], chemin

        # Plusieurs tours valent mieux qu'un : la géométrie de la piste s'en
        # trouve mieux contrainte, et les deux bords sont connus sur une plus
        # grande part du tour.
        numeros = [t.numero for t in session.tours_valides if t.chrono][:5]
        if not numeros:
            raise ErreurTelemetrie(
                "Aucun tour valide dans cette session : impossible de découper le "
                "circuit en virages. Ouvre une session où tu as bouclé au moins un "
                "tour propre."
            )
        definition = detecter([charger(session.chemin, n) for n in numeros])
        definition.enregistrer(chemin)
        cle = _cle_fichier(chemin)
        if cle is not None:
            _cache_virages[cle] = definition
        return definition, chemin


def _virages(contexte: Contexte, params: dict[str, list[str]]) -> dict:
    chemin_ref = params["ref"][0]
    chemin_cmp = params.get("cmp", params["ref"])[0]
    definition, fichier = _definition(contexte, Session.ouvrir(chemin_ref))

    reference = charger(chemin_ref, int(params["tour_ref"][0]))
    compare = charger(chemin_cmp, int(params["tour_cmp"][0]))
    mesures_ref = mesurer(reference, definition)
    mesures_cmp = {m.virage.numero: m for m in mesurer(compare, definition)}

    # Temps gagné ou perdu, réparti sur tout le tour : chaque mètre appartient
    # à un virage et à un seul, donc la colonne s'additionne exactement à
    # l'écart final. Une colonne qui ne totalise pas serait trompeuse.
    axe = np.arange(0.0, min(reference.longueur, compare.longueur), 1.0)
    delta = compare.temps_a_distance(axe) - reference.temps_a_distance(axe)
    portions = dict(zip((v.numero for v in definition.virages), secteurs(definition)))

    def delta_zone(virage) -> float | None:
        borne = portions.get(virage.numero)
        if borne is None:
            return None
        a, b = min(borne[0], axe[-1]), min(borne[1], axe[-1])
        return float(np.interp(b, axe, delta) - np.interp(a, axe, delta))

    def ligne(a) -> dict:
        b = mesures_cmp.get(a.virage.numero)

        def paire(nom):
            va = getattr(a, nom)
            vb = getattr(b, nom) if b else None
            ecart = None if va is None or vb is None else vb - va
            return {"reference": va, "compare": vb, "ecart": ecart}

        return {
            "numero": a.virage.numero,
            "nom": a.virage.libelle,
            "sens": a.virage.sens_libelle,
            "delta_zone": delta_zone(a.virage),
            "debut": a.virage.debut,
            "fin": a.virage.fin,
            "rayon_min": round(a.virage.rayon_min, 1),
            "remarques": list(a.remarques) + list(b.remarques if b else []),
            "mesures": {
                nom: paire(nom)
                for nom in (
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
            },
        }

    return {
        "circuit": definition.circuit,
        "fichier": str(fichier),
        "automatique": definition.automatique,
        "virages": [ligne(m) for m in mesures_ref],
        "coasting_total": {
            "reference": round(sum(m.temps_coasting for m in mesures_ref), 2),
            "compare": round(sum(m.temps_coasting for m in mesures_cmp.values()), 2),
        },
    }


def _regularite(contexte: Contexte, params: dict[str, list[str]]) -> dict:
    chemin = params["chemin"][0]
    session = Session.ouvrir(chemin)
    definition, fichier = _definition(contexte, session)
    r = analyser(chemin, definition)

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
            {"numero": n, "chrono": round(c, 3)}
            for n, c in zip(r.numeros, r.chronos)
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


# ----------------------------------------------------------------------
# Serveur
# ----------------------------------------------------------------------


#: Paramètres qui désignent un fichier de session sur le disque.
PARAMETRES_CHEMIN = ("chemin", "ref", "cmp")

#: Noms d'hôte sous lesquels la page a le droit de joindre le serveur.
HOTES_ACCEPTES = frozenset({"127.0.0.1", "localhost"})


class CheminRefuse(ErreurTelemetrie):
    def __init__(self, brut: str) -> None:
        super().__init__(
            f"Ce fichier n'est pas une session du dossier de télémétrie :\n  {brut}\n"
            "L'interface n'ouvre que les fichiers .duckdb de ce dossier."
        )


def _verifier_chemins(contexte: Contexte, params: dict[str, list[str]]) -> None:
    """Refuse tout chemin qui ne désigne pas une session du dossier de télémétrie.

    La page transmet le chemin des fichiers qu'elle veut ouvrir, et le serveur
    l'ouvrait tel quel : n'importe quel fichier du disque pouvait être demandé.
    Rien ne justifie d'en ouvrir d'autres que ceux du dossier — y compris le
    fichier d'un autre pilote, qu'on y dépose.
    """
    demandes = [brut for cle in PARAMETRES_CHEMIN for brut in params.get(cle, [])]
    # Rien à vérifier : surtout, ne pas chercher le dossier. Sans lui, la page
    # elle-même refusait de s'afficher — et avec elle l'écran qui permet de
    # l'indiquer.
    if not demandes:
        return
    racine = catalogue.dossier_telemetrie(contexte.dossier).resolve()
    for cle in PARAMETRES_CHEMIN:
        for brut in params.get(cle, []):
            chemin = Path(brut).resolve()
            if chemin.suffix.lower() != ".duckdb" or racine not in chemin.parents:
                raise CheminRefuse(brut)


def _etat_dossier(contexte: Contexte) -> dict:
    """Dossier de télémétrie utilisé, ou pourquoi il n'y en a pas."""
    impose = contexte.dossier is not None
    try:
        dossier = catalogue.dossier_telemetrie(contexte.dossier)
    except DossierIntrouvable as erreur:
        return {"dossier": None, "erreur": str(erreur), "impose": impose}
    return {"dossier": str(dossier), "erreur": None, "impose": impose}


def _choisir_dossier(contexte: Contexte, charge: dict) -> dict:
    """Retient le dossier de télémétrie indiqué dans l'interface.

    On refuse un dossier sans aucune session : c'est presque toujours une
    erreur de niveau (le dossier du jeu, ou `UserData`, au lieu de
    `UserData\\Telemetry`), et l'accepter donnerait une liste vide sans
    explication.
    """
    if contexte.dossier is not None:
        raise ErreurTelemetrie(
            "Le dossier est imposé par l'option --dossier de la ligne de commande : "
            "il ne peut pas être changé depuis l'interface."
        )
    brut = str(charge.get("dossier") or "").strip().strip('"')
    if not brut:
        raise ErreurTelemetrie("Indique un dossier.")
    chemin = Path(brut)
    if not chemin.is_dir():
        raise DossierIntrouvable(chemin)
    if not any(chemin.glob("*.duckdb")):
        indice = ""
        if (chemin / "UserData" / "Telemetry").is_dir():
            indice = "\nC'est le dossier du jeu : choisis son sous-dossier UserData\\Telemetry."
        elif (chemin / "Telemetry").is_dir():
            indice = "\nChoisis son sous-dossier Telemetry."
        raise ErreurTelemetrie(
            f"Aucune session (fichier .duckdb) dans ce dossier :\n  {chemin}{indice}"
        )
    reglages = emplacements.lire_reglages()
    reglages[catalogue.REGLAGE_DOSSIER] = str(chemin)
    emplacements.enregistrer_reglages(reglages)
    return _etat_dossier(contexte)


def _origine_acceptee(origine: str | None, hote: str | None) -> bool:
    """La requête vient-elle de la page de l'outil lui-même ?

    Le navigateur joint l'en-tête Origin à toute requête POST, et un site tiers
    ne peut pas le falsifier : il ne vaut « http://127.0.0.1:8770 » que si
    c'est la page de l'outil qui écrit.
    """
    if not origine or not hote:
        return False
    return origine.lower() == f"http://{hote.lower()}" and _hote_accepte(hote)


def _hote_accepte(entete: str | None) -> bool:
    """La requête vise-t-elle bien le serveur local sous son nom local ?

    Le serveur n'écoute que sur 127.0.0.1, mais une page web quelconque peut
    faire résoudre son propre nom de domaine vers 127.0.0.1 (« DNS rebinding »)
    et lire alors les réponses comme si elles venaient de chez elle. Le
    navigateur envoie toujours le nom demandé dans l'en-tête Host : il suffit
    de refuser tout ce qui n'est pas un nom local.
    """
    if not entete:
        return False
    hote = entete.rsplit(":", 1)[0] if entete.count(":") == 1 else entete
    return hote.strip("[]").lower() in HOTES_ACCEPTES


class Gestionnaire(BaseHTTPRequestHandler):
    contexte = Contexte()

    # Les journaux ligne par ligne d'http.server polluent le terminal sans rien
    # apprendre : on ne garde que les erreurs.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802  (nom imposé par http.server)
        url = urlparse(self.path)
        params = parse_qs(url.query)
        if not _hote_accepte(self.headers.get("Host")):
            self.send_error(403, "Hote non autorise")
            return
        try:
            _verifier_chemins(self.contexte, params)
            if url.path == "/api/sessions":
                self._json(_sessions(self.contexte))
            elif url.path == "/api/resumes":
                self._json(_resumes(self.contexte, params))
            elif url.path == "/api/session":
                self._json(_session(self.contexte, params["chemin"][0]))
            elif url.path == "/api/comparaison":
                self._json(_comparaison(self.contexte, params))
            elif url.path == "/api/virages":
                self._json(_virages(self.contexte, params))
            elif url.path == "/api/regularite":
                self._json(_regularite(self.contexte, params))
            elif url.path == "/api/traces":
                self._json(_traces_connues(self.contexte))
            elif url.path == "/api/logos":
                self._json(sorted(_logos(self.contexte)))
            elif url.path == "/api/version":
                self._json({"version": __version__, "donnees": str(emplacements.donnees())})
            elif url.path == "/api/dossier":
                self._json(_etat_dossier(self.contexte))
            elif url.path == "/logo":
                self._logo(params)
            else:
                self._fichier(url.path)
        except Exception as erreur:  # noqa: BLE001
            self._erreur(erreur)

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        hote = self.headers.get("Host")
        if not _hote_accepte(hote) or not _origine_acceptee(self.headers.get("Origin"), hote):
            self.send_error(403, "Origine non autorisee")
            return
        # Exiger du JSON oblige un site tiers à une requête « préalable » que
        # le serveur ne sait pas traiter : le navigateur n'envoie alors rien.
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self.send_error(415, "JSON attendu")
            return
        try:
            longueur = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
            charge = json.loads(self.rfile.read(longueur) or b"{}")
            if not isinstance(charge, dict):
                raise ValueError("objet JSON attendu")
            if url.path == "/api/dossier":
                self._json(_choisir_dossier(self.contexte, charge))
            else:
                self.send_error(404, "Route inconnue")
        except Exception as erreur:  # noqa: BLE001
            self._erreur(erreur)

    def _erreur(self, erreur: Exception) -> None:
        """Répond par un message lisible, jamais par une trace de pile."""
        if isinstance(erreur, BrokenPipeError | ConnectionResetError):
            return  # le navigateur a fermé l'onglet en cours de route
        if isinstance(erreur, ErreurTelemetrie):
            charge = {"erreur": str(erreur)}
            if isinstance(erreur, DossierIntrouvable):
                charge["code"] = "dossier_introuvable"
            self._json(charge, code=400)
        elif isinstance(erreur, KeyError | ValueError):
            self._json({"erreur": f"Requête incomplète : {erreur}"}, code=400)
        else:
            # Un défaut de l'outil, pas une erreur de l'utilisateur : on le dit,
            # avec de quoi le signaler, et la trace complète va dans la console.
            traceback.print_exception(erreur)
            self._json(
                {
                    "erreur": (
                        "L'outil a rencontré un problème inattendu. Ce n'est pas de ta "
                        "faute : signale-le à qui t'a donné l'outil, en précisant ce "
                        "que tu faisais.\n\nDétail technique : "
                        f"{type(erreur).__name__}: {erreur}"
                    )
                },
                code=500,
            )

    # ------------------------------------------------------------------

    def _json(self, charge: object, code: int = 200) -> None:
        corps = json.dumps(charge, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _logo(self, params: dict[str, list[str]]) -> None:
        """Sert le logo d'une marque, s'il a été déposé dans `logos/`."""
        marque = (params.get("marque") or [""])[0]
        cible = _logos(self.contexte).get(marque)
        if cible is None:
            self.send_error(404, "Pas de logo pour cette marque")
            return
        self._envoyer(cible.read_bytes(), TYPES_MIME.get(cible.suffix.lower(), "image/png"))

    def _fichier(self, chemin: str) -> None:
        nom = "index.html" if chemin in ("/", "") else chemin.lstrip("/")
        cible = (STATIQUE / nom).resolve()
        # Un chemin comme /../../secret.txt ne doit pas sortir du dossier servi.
        if not cible.is_file() or STATIQUE.resolve() not in cible.parents:
            self.send_error(404, "Page introuvable")
            return
        self._envoyer(
            cible.read_bytes(),
            TYPES_MIME.get(cible.suffix, "application/octet-stream"),
        )

    def _envoyer(self, corps: bytes, type_mime: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", type_mime)
        self.send_header("Content-Length", str(len(corps)))
        # Rien n'est mis en cache : les fichiers sont lus sur le disque local,
        # donc gratuits à recharger, et une page servie depuis le cache après
        # une mise à jour de l'outil donne un mélange incohérent d'ancien et de
        # nouveau code — constaté en développement.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)


class PortOccupe(ErreurTelemetrie):
    def __init__(self, port: int) -> None:
        self.port = port
        super().__init__(
            f"Le port {port} est déjà utilisé : l'outil tourne peut-être déjà dans\n"
            "une autre fenêtre. Sinon, choisis un autre port, par exemple :\n"
            f"  python -m lmu_telemetry web --port {port + 1}"
        )


class ServeurLocal(ThreadingHTTPServer):
    """Serveur HTTP qui refuse de partager son port.

    `http.server` active SO_REUSEADDR, qui sous Windows ne veut pas dire la même
    chose qu'ailleurs : il laisse un SECOND programme s'installer sur un port
    déjà pris. Constaté : deux lancements de l'outil tournaient côte à côte sur
    le port 8770, et le navigateur tombait sur l'un ou l'autre au hasard. On
    demande au contraire l'usage exclusif du port.
    """

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def creer_serveur(port: int, dossier: Path | None = None) -> ThreadingHTTPServer:
    """Prépare le serveur sur 127.0.0.1 — rien n'est exposé sur le réseau local."""
    Gestionnaire.contexte = Contexte(dossier=dossier)
    try:
        return ServeurLocal(("127.0.0.1", port), Gestionnaire)
    except OSError as erreur:
        if erreur.errno in (errno.EADDRINUSE, 10048) or getattr(erreur, "winerror", None) in (
            10013,
            10048,
        ):
            raise PortOccupe(port) from None
        raise


def demarrer(port: int = 8770, dossier: Path | None = None, ouvrir: bool = True) -> None:
    """Lance le serveur et ouvre le navigateur."""
    serveur = creer_serveur(port, dossier)
    adresse = f"http://127.0.0.1:{port}/"

    print(f"Interface disponible sur {adresse}")
    print("Ctrl+C pour arrêter.")
    if ouvrir:
        threading.Timer(0.5, lambda: webbrowser.open(adresse)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        serveur.server_close()
