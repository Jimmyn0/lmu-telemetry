"""Ce qu'on sait de chaque session, sans avoir à rouvrir son fichier.

La liste des sessions et les records par circuit ont besoin de connaître toutes
les sessions du disque : tracé, voiture, nombre de tours, meilleur chrono. Ouvrir
les 583 fichiers prend environ 80 s. Ces informations sont donc gardées dans
`index.sqlite`, et seuls les fichiers nouveaux ou modifiés sont relus.

L'index n'est qu'un cache : les fichiers du jeu font foi. Une session réécrite
change de date ou de taille et se relit toute seule, et un index abîmé ou d'une
ancienne version se reconstruit sans rien perdre.

--------------------------------------------------------------------------
Pourquoi SQLite
--------------------------------------------------------------------------

Le serveur répond sur plusieurs fils pendant que le balayage écrit, et le fichier
doit survivre à un arrêt brutal. SQLite gère les deux. Il fait partie de Python :
aucune dépendance de plus.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import astuple, dataclass, fields
from pathlib import Path

import numpy as np

from .. import emplacements
from ..domaine.donnees_tour import charger_tours
from ..domaine.piste import CANAUX_GPS, positions
from ..domaine.session import Session
from ..errors import ErreurTelemetrie, SessionEnCours
from ..sources.catalogue import FichierRepere
from ..sources.reader import cle_fichier

#: À augmenter quand une colonne change : l'index se reconstruit alors de lui-même.
VERSION_SCHEMA = 1

#: Nombre de sessions écrites à la fois. Écrire une par une obligerait le disque à
#: confirmer chaque ligne, et un arrêt ne perd au pire que ce paquet.
TAILLE_PAQUET = 20

#: Délai (s) avant de réessayer une session verrouillée par le jeu.
ATTENTE_SESSION_EN_COURS = 60.0

#: Nombre de points du contour d'un circuit : de quoi le reconnaître dans une carte
#: de 300 pixels, sans alourdir la réponse envoyée à la page.
POINTS_CONTOUR = 240


@dataclass(frozen=True)
class ResumeSession:
    """Une ligne de l'index."""

    chemin: str
    mtime_ns: int
    taille: int
    illisible: str | None = None
    """Pourquoi le fichier n'a pas pu être lu, ou None s'il l'a été."""

    trace: str | None = None
    pilote: str | None = None
    voiture: str | None = None
    categorie: str | None = None
    meteo: str | None = None
    duree: float | None = None
    longueur: float | None = None
    tours: int = 0
    valides: int = 0
    meilleur: float | None = None
    tour_meilleur: int | None = None
    s1: float | None = None
    s2: float | None = None
    s3: float | None = None


_COLONNES = [f.name for f in fields(ResumeSession)]


def resumer(chemin: Path) -> ResumeSession | None:
    """Lit une session. None si le jeu la tient ouverte : on réessaiera plus tard."""
    cle = cle_fichier(chemin)
    if cle is None:
        return None
    _, mtime_ns, taille = cle
    try:
        session = Session.ouvrir(chemin)
    except SessionEnCours:
        return None
    except ErreurTelemetrie as erreur:
        return ResumeSession(str(chemin), mtime_ns, taille, illisible=str(erreur))

    meilleur = session.meilleur_tour
    s1, s2, s3 = meilleur.secteurs if meilleur else (None, None, None)
    return ResumeSession(
        chemin=str(chemin),
        mtime_ns=mtime_ns,
        taille=taille,
        trace=session.info.trace,
        pilote=session.info.pilote,
        voiture=session.info.voiture,
        categorie=session.info.categorie,
        meteo=session.info.meteo,
        duree=session.duree,
        longueur=session.longueur,
        tours=len(session.tours),
        valides=len(session.tours_valides),
        meilleur=meilleur.chrono if meilleur else None,
        tour_meilleur=meilleur.numero if meilleur else None,
        s1=s1,
        s2=s2,
        s3=s3,
    )


def contour(resume: ResumeSession) -> list[list[float]] | None:
    """Forme du circuit d'après le meilleur tour d'une session, ramenée à [0, 1].

    Les proportions sont conservées : la plus grande dimension vaut 1.
    """
    if resume.tour_meilleur is None:
        return None
    try:
        tour = charger_tours(resume.chemin, [resume.tour_meilleur], CANAUX_GPS, ())[0]
        points = positions(tour)
    except (ErreurTelemetrie, KeyError):
        return None
    points = points[np.linspace(0, len(points) - 1, POINTS_CONTOUR).astype(int)]
    points = points - points.min(axis=0)
    cote = float(points.max()) or 1.0
    # Le nord vers le haut : l'axe vertical de l'écran descend.
    points = np.column_stack([points[:, 0], points[:, 1].max() - points[:, 1]]) / cote
    return np.round(points, 4).tolist()


class Index:
    """Accès au fichier de l'index. Une connexion par opération : le serveur
    répond sur plusieurs fils, et une connexion SQLite ne se partage pas entre
    eux."""

    def __init__(self, chemin: Path | None = None) -> None:
        self.chemin = chemin or emplacements.fichier_index()

    def _connecter(self) -> sqlite3.Connection:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        connexion = sqlite3.connect(self.chemin, timeout=10.0)
        try:
            version = connexion.execute("PRAGMA user_version").fetchone()[0]
            if version != VERSION_SCHEMA:
                connexion.executescript(
                    "DROP TABLE IF EXISTS sessions; DROP TABLE IF EXISTS contours;"
                )
                definition = ", ".join(
                    f"{nom} PRIMARY KEY" if nom == "chemin" else nom for nom in _COLONNES
                )
                connexion.executescript(
                    f"CREATE TABLE sessions ({definition});"
                    "CREATE TABLE contours (trace PRIMARY KEY, points);"
                    f"PRAGMA user_version = {VERSION_SCHEMA};"
                )
        except sqlite3.Error:
            # Sous Windows, un fichier ouvert ne peut pas être supprimé.
            connexion.close()
            raise
        return connexion

    def _executer(self, operation):
        """Lance une opération, en repartant de zéro si le fichier est abîmé."""
        for essai in (1, 2):
            try:
                connexion = self._connecter()
                try:
                    with connexion:
                        return operation(connexion)
                finally:
                    connexion.close()
            except sqlite3.DatabaseError:
                # Un index n'est qu'un cache : mieux vaut le refaire que d'échouer.
                if essai == 2:
                    raise
                self.chemin.unlink(missing_ok=True)

    def lignes(self) -> dict[str, ResumeSession]:
        """Toute l'index, par chemin de fichier."""
        requete = f"SELECT {', '.join(_COLONNES)} FROM sessions"
        return self._executer(
            lambda c: {
                ligne[0]: ResumeSession(*ligne) for ligne in c.execute(requete).fetchall()
            }
        )

    def enregistrer(self, resumes: list[ResumeSession]) -> None:
        emplacements_valeurs = ", ".join("?" for _ in _COLONNES)
        self._executer(
            lambda c: c.executemany(
                f"INSERT OR REPLACE INTO sessions VALUES ({emplacements_valeurs})",
                [astuple(r) for r in resumes],
            )
        )

    def contours(self) -> dict[str, list[list[float]]]:
        return self._executer(
            lambda c: {
                trace: json.loads(points)
                for trace, points in c.execute("SELECT trace, points FROM contours")
            }
        )

    def enregistrer_contour(self, trace: str, points: list[list[float]]) -> None:
        self._executer(
            lambda c: c.execute(
                "INSERT OR REPLACE INTO contours VALUES (?, ?)", (trace, json.dumps(points))
            )
        )


class Balayage:
    """Tient l'index à jour en tâche de fond, sans faire attendre la page."""

    def __init__(self) -> None:
        self._fil: threading.Thread | None = None
        self._verrou = threading.Lock()
        self._en_cours: dict[tuple[str, int, int], float] = {}

    def a_lire(self, reperes: list[FichierRepere], connues: dict) -> list[Path]:
        """Sessions absentes de l'index, ou modifiées depuis leur lecture."""
        maintenant = time.monotonic()
        fichiers = []
        for repere in reperes:
            cle = cle_fichier(repere.chemin)
            if cle is None:
                continue
            ligne = connues.get(cle[0])
            if ligne is not None and (ligne.mtime_ns, ligne.taille) == cle[1:]:
                continue
            if maintenant - self._en_cours.get(cle, -ATTENTE_SESSION_EN_COURS) < (
                ATTENTE_SESSION_EN_COURS
            ):
                continue  # le jeu l'écrit encore : inutile d'insister
            fichiers.append(repere.chemin)
        return fichiers

    def relancer(self, fichiers: list[Path], index: Index) -> None:
        """Lance la lecture de ces fichiers, si elle ne tourne pas déjà."""
        if not fichiers:
            return
        with self._verrou:
            if self._fil is not None and self._fil.is_alive():
                return
            self._fil = threading.Thread(
                target=self._lire, args=(fichiers, index), daemon=True
            )
            self._fil.start()

    def attendre(self, delai: float | None = None) -> None:
        """Attend la fin de la lecture en cours."""
        fil = self._fil
        if fil is not None:
            fil.join(delai)

    def _lire(self, fichiers: list[Path], index: Index) -> None:
        # Les plus récentes d'abord : ce sont celles qu'on regarde en premier.
        fichiers = sorted(fichiers, key=lambda f: f.name[-25:], reverse=True)
        contours = set(index.contours())
        paquet: list[ResumeSession] = []
        for chemin in fichiers:
            try:
                resume = resumer(chemin)
            except Exception as erreur:  # noqa: BLE001 — un fichier ne bloque pas les autres
                cle = cle_fichier(chemin)
                if cle is None:
                    continue
                resume = ResumeSession(str(chemin), cle[1], cle[2], illisible=str(erreur))
            if resume is None:
                cle = cle_fichier(chemin)
                if cle is not None:
                    self._en_cours[cle] = time.monotonic()
                continue
            paquet.append(resume)
            if resume.trace and resume.trace not in contours:
                points = contour(resume)
                if points:
                    index.enregistrer_contour(resume.trace, points)
                    contours.add(resume.trace)
            if len(paquet) >= TAILLE_PAQUET:
                index.enregistrer(paquet)
                paquet = []
        if paquet:
            index.enregistrer(paquet)


#: Une seule lecture à la fois pour tout le programme.
balayage = Balayage()
