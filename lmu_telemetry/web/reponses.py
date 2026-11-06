"""Ce que le serveur répond : la mise en forme JSON des analyses.

Aucun calcul de pilotage ici, et rien sur HTTP : ce module traduit les objets du
domaine en ce que la page attend.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import emplacements, parametres
from ..cache import CacheBorne
from ..domaine import pays
from ..domaine.circuits import definition_circuit
from ..domaine.comparaison import comparer_fichiers
from ..domaine.donnees_tour import charger
from ..domaine.piste import construire as construire_piste
from ..domaine.piste import trajectoires
from ..domaine.regularite import analyser
from ..domaine.session import Session
from ..domaine.virages import DefinitionCircuit, ecarts_par_virage
from ..errors import ErreurTelemetrie
from ..sources import catalogue, resultats
from ..sources.reader import FichierSession, cle_fichier

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
    "Brake Pos": 1,
    "Steering Pos": 2,
    "Angle Volant": 1,
    "Engine RPM": 0,
    "Gear": 0,
    "GPS Latitude": 7,
    "GPS Longitude": 7,
}


# ----------------------------------------------------------------------
# Liste des sessions
# ----------------------------------------------------------------------


def sessions(contexte: Contexte) -> list[dict]:
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
_traces: CacheBorne[tuple[str, int, int], str] = CacheBorne(8192)
_scan_traces: threading.Thread | None = None


def traces_connues(contexte: Contexte) -> dict:
    """Tracés déjà lus, et combien il en reste. Lance le balayage au besoin."""
    global _scan_traces

    reperes = catalogue.lister(contexte.dossier)
    cles = {r.chemin: cle_fichier(r.chemin) for r in reperes}
    connus = {str(chemin): _traces.get(cle) for chemin, cle in cles.items() if cle}
    restant = sum(1 for cle in cles.values() if cle and cle not in _traces)

    if restant and (_scan_traces is None or not _scan_traces.is_alive()):
        _scan_traces = threading.Thread(
            target=_balayer_traces, args=(list(cles.items()),), daemon=True
        )
        _scan_traces.start()

    return {"traces": {c: t for c, t in connus.items() if t}, "restant": restant}


def _balayer_traces(fichiers: list) -> None:
    """Lit le tracé de chaque session, une par une, en tâche de fond.

    Un fichier illisible — session en cours d'enregistrement, format inconnu —
    est mémorisé comme vide plutôt que retenté sans fin.
    """
    for chemin, cle in fichiers:
        if cle is None or cle in _traces:
            continue
        trace = ""
        try:
            with FichierSession(chemin) as fichier:
                trace = fichier.info.trace
        except Exception:  # noqa: BLE001 — une tâche de fond ne doit pas mourir
            trace = ""
        _traces[cle] = trace


#: Résumés déjà calculés, indexés par (chemin, date de modification, taille).
#: Parcourir les 378 sessions du disque prend une douzaine de secondes ; on ne
#: le refait pas à chaque affichage de la liste. La clé inclut la taille et la
#: date pour qu'une session réécrite par le jeu soit recalculée.
_cache_resumes: CacheBorne[tuple[str, int, int], dict] = CacheBorne(8192)


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


def resumes(contexte: Contexte, params: dict[str, list[str]]) -> list[dict]:
    """Nombre de tours et meilleur chrono, pour les sessions DEMANDÉES.

    Chaque résumé oblige à ouvrir le fichier : analyser les 378 sessions du
    disque prend une douzaine de secondes, ce qui est insupportable à chaque
    ouverture de la liste. Le navigateur ne demande donc que les sessions qu'il
    affiche réellement, une dizaine à la fois.
    """
    trouves = []
    for brut in params.get("chemin", []):
        chemin = Path(brut)
        cle = cle_fichier(chemin)
        if cle is None:
            continue
        resume = _cache_resumes.obtenir(cle, lambda: _resumer(contexte, chemin))
        trouves.append({"id": str(chemin), **resume})
    return trouves


def _resumer(contexte: Contexte, chemin: Path) -> dict:
    try:
        session_lue = Session.ouvrir(chemin)
    except ErreurTelemetrie as erreur:
        return {"tours": 0, "valides": 0, "meilleur": None, "indisponible": str(erreur)}
    meilleur = session_lue.meilleur_tour
    return {
        "tours": len(session_lue.tours),
        "valides": len(session_lue.tours_valides),
        "meilleur": meilleur.chrono if meilleur else None,
        "trace": session_lue.info.trace,
        "voiture": _voiture(contexte, session_lue.info.voiture),
        "indisponible": None,
    }


# ----------------------------------------------------------------------
# Une session
# ----------------------------------------------------------------------


def session(contexte: Contexte, chemin: str) -> dict:
    lue = Session.ouvrir(chemin)
    return {
        "id": str(lue.chemin),
        # Le tracé plutôt que le circuit : c'est lui qui décrit ce qu'on a
        # roulé. « Monza Curva Grande Circuit » n'a pas les mêmes virages que
        # « Autodromo Nazionale Monza », alors que les deux portent le même
        # `TrackName`.
        "circuit": lue.info.trace,
        "pays": _pays(lue.info.trace),
        "type": lue.info.type_session,
        "voiture": _voiture(contexte, lue.info.voiture),
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


# ----------------------------------------------------------------------
# Comparaison de deux tours
# ----------------------------------------------------------------------


def comparaison(contexte: Contexte, params: dict[str, list[str]]) -> dict:
    resultat = comparer_fichiers(
        params["ref"][0],
        int(params["tour_ref"][0]),
        params.get("cmp", params["ref"])[0],
        int(params["tour_cmp"][0]),
    )

    traces = {
        nom: {
            "reference": _arrondir(ref, DECIMALES[nom]),
            "compare": _arrondir(cmp, DECIMALES[nom]),
        }
        for nom, (ref, cmp) in resultat.traces.items()
        if nom in DECIMALES
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
            "remarques": [r.json() for r in donnees.tour.remarques],
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
    circuit, fichier = definition(contexte, Session.ouvrir(chemin_ref))
    ecarts = ecarts_par_virage(
        charger(chemin_ref, int(params["tour_ref"][0])),
        charger(chemin_cmp, int(params["tour_cmp"][0])),
        circuit,
        parametres.lire().virages,
    )

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
