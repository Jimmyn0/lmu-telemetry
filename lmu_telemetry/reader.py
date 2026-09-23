"""Couche d'abstraction sur les fichiers de télémétrie de Le Mans Ultimate.

C'EST LE SEUL MODULE QUI CONNAÎT LE FORMAT DU JEU.

Tout le reste de l'outil ne manipule que les objets définis ici. Si une mise à
jour de LMU change la structure des fichiers, c'est ce fichier-là qu'il faut
corriger, et lui seul.

--------------------------------------------------------------------------
Rappel du format réel, vérifié le 2026-09-08 sur 377 fichiers,
revérifié le 2026-09-23 sur 441
(détails complets dans docs/01-decouverte.md)
--------------------------------------------------------------------------

Un fichier de session est une base DuckDB contenant trois formes de tables :

1. `metadata`, `channelsList`, `eventsList` : les tables descriptives.

2. Les CANAUX, un par table, listés dans `channelsList` avec leur fréquence.
   Ils n'ont AUCUNE colonne de temps : juste `value` (ou `value1..value4` pour
   les données par roue), une ligne par échantillon dans l'ordre d'acquisition.
   Le temps se reconstruit par :  t(i) = t0 + i / fréquence

3. Les ÉVÉNEMENTS, un par table, listés dans `eventsList`. Ceux-là ont une
   colonne `ts` en secondes, et une ligne est écrite uniquement quand la valeur
   change. D'où des tables très courtes.

`t0` est le `ts` du tout premier événement du fichier. Ce recalage a été
vérifié : la remise à zéro de `Lap Dist` tombe bien sur les événements `Lap`,
sans dérive sur toute une session.

Ordre des roues dans `value1..value4` : AVG, AVD, ARG, ARD. Déterminé
empiriquement sur trois circuits et trois catégories de voiture (températures
de frein pour l'axe avant/arrière, températures de bord de pneu pour l'axe
gauche/droite), pas repris d'une documentation.

Le champ `metadata.CarSetup` contient le réglage complet de la voiture, en
JSON. On n'en lit qu'UNE valeur, `VM_STEER_LOCK`, et uniquement pour convertir
l'angle volant en degrés (voir `_debattement`). Rien d'autre n'en est exploité,
et aucun fichier de setup du jeu n'est ouvert : celui-ci est une copie que le
jeu a lui-même écrite dans le fichier de télémétrie.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import duckdb
import numpy as np

from .errors import (
    DonneeManquante,
    FichierIntrouvable,
    SchemaInconnu,
    SessionEnCours,
)

#: Versions du champ metadata.Version que ce module sait lire.
SCHEMAS_SUPPORTES = frozenset({"1"})

#: Ordre des colonnes value1..value4 pour les canaux par roue.
ROUES = ("AVG", "AVD", "ARG", "ARD")

#: Valeurs de SurfaceTypes considérées comme hors piste.
#: Vérifié statistiquement : l'écart médian à l'axe de piste vaut 2,7 m pour la
#: valeur 0, 6,6 m pour 5 et 5,0 m pour 6 (vibreurs, donc en piste), contre
#: 10,8 m pour 2 et 22,5 m pour 4. Les valeurs 2/3/4 sont donc bien hors piste.
SURFACES_HORS_PISTE = frozenset({2, 3, 4})

#: Fragments de message d'erreur DuckDB signalant un fichier verrouillé.
#: Le message système est traduit selon la langue de Windows, d'où plusieurs
#: variantes ; « already open in » vient de DuckDB lui-même et est stable.
_SIGNES_VERROU = (
    "already open in",
    "another process",
    "autre processus",
    "being used by",
)

#: Bornes de vraisemblance du débattement volant, en degrés d'une butée à
#: l'autre. Observé de 336° (Oreca 07) à 584° (Porsche 911 GT3 R) sur les
#: 26 voitures pilotées. Les bornes sont larges : elles ne servent qu'à rejeter
#: une chaîne mal comprise, pas à valider un réglage.
_DEBATTEMENT_PLAUSIBLE = (90.0, 1500.0)

#: Idem pour l'angle des roues avant à fond de braquage. Observé de 13° à 20,8°.
_ANGLE_ROUES_PLAUSIBLE = (2.0, 60.0)


@dataclass(frozen=True)
class InfoCanal:
    """Description d'un canal échantillonné à fréquence fixe."""

    nom: str
    frequence: int
    unite: str
    par_roue: bool
    echantillons: int

    @property
    def duree(self) -> float:
        """Durée couverte par le canal, en secondes."""
        return self.echantillons / self.frequence


@dataclass(frozen=True)
class InfoEvenement:
    """Description d'un événement horodaté."""

    nom: str
    unite: str
    par_roue: bool
    lignes: int


@dataclass(frozen=True)
class InfoSession:
    """Métadonnées d'une session, normalisées."""

    pilote: str
    circuit: str
    trace: str
    type_session: str
    voiture: str
    categorie: str
    meteo: str
    enregistree_le: datetime | None
    version_schema: str
    setup_brut: str | None  # JSON du setup, conservé tel quel, non interprété

    #: Débattement du volant d'une butée à l'autre, en degrés, ou None si le
    #: réglage est absent ou illisible. Sert à convertir `Steering Pos`, qui
    #: est un pourcentage, en degrés au volant.
    debattement_volant: float | None = None

    #: Angle des roues avant à fond de braquage, en degrés. Lu au même endroit,
    #: conservé parce qu'il donne la démultiplication de la direction.
    angle_roues_max: float | None = None

    @property
    def demultiplication(self) -> float | None:
        """Tours de volant par degré de roue : 14,4:1 sur la 911 GT3 R."""
        if not self.debattement_volant or not self.angle_roues_max:
            return None
        return (self.debattement_volant / 2) / self.angle_roues_max

    @property
    def code_type(self) -> str:
        """P, Q ou R selon le type de session."""
        return {"practice": "P", "qualifying": "Q", "race": "R"}.get(
            self.type_session.lower(), self.type_session[:1].upper()
        )


class FichierSession:
    """Accès en lecture seule à un fichier .duckdb de télémétrie LMU.

    À utiliser comme gestionnaire de contexte :

        with FichierSession(chemin) as f:
            vitesse = f.canal("Ground Speed")

    Le fichier n'est jamais modifié : la connexion est ouverte en `read_only`.
    """

    def __init__(self, chemin: Path | str) -> None:
        self.chemin = Path(chemin)
        if not self.chemin.exists():
            raise FichierIntrouvable(self.chemin)

        try:
            self._con = duckdb.connect(str(self.chemin), read_only=True)
        except duckdb.Error as exc:
            texte = str(exc)
            if any(signe in texte.lower() for signe in _SIGNES_VERROU):
                raise SessionEnCours(self.chemin, texte.strip()) from exc
            raise

        self._cache: dict[str, np.ndarray] = {}
        self._info: InfoSession | None = None
        self._canaux: dict[str, InfoCanal] | None = None
        self._evenements: dict[str, InfoEvenement] | None = None
        self._t0: float | None = None
        self._tables: dict[str, tuple[list[str], int]] | None = None

        self._verifier_schema()

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def __enter__(self) -> "FichierSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.fermer()

    def fermer(self) -> None:
        self._con.close()

    @property
    def journal_present(self) -> bool:
        """True si un .wal traîne à côté : session non refermée proprement."""
        return self.chemin.with_suffix(self.chemin.suffix + ".wal").exists()

    # ------------------------------------------------------------------
    # Métadonnées
    # ------------------------------------------------------------------

    def _verifier_schema(self) -> None:
        version = self.metadonnees_brutes.get("Version")
        if version not in SCHEMAS_SUPPORTES:
            self.fermer()
            raise SchemaInconnu(self.chemin, version, set(SCHEMAS_SUPPORTES))

    @property
    def metadonnees_brutes(self) -> dict[str, str]:
        """Table `metadata` telle quelle, sans interprétation."""
        return dict(self._con.execute("SELECT * FROM metadata").fetchall())

    @property
    def info(self) -> InfoSession:
        if self._info is None:
            m = self.metadonnees_brutes
            debattement, roues = _debattement(m.get("CarSetup"))
            self._info = InfoSession(
                pilote=m.get("DriverName", "?"),
                circuit=m.get("TrackName", "?"),
                trace=m.get("TrackLayout", m.get("TrackName", "?")),
                type_session=m.get("SessionType", "?"),
                voiture=m.get("CarName", "?"),
                categorie=m.get("CarClass", "?"),
                meteo=m.get("WeatherConditions", "?"),
                enregistree_le=_horodatage(m.get("RecordingTime")),
                version_schema=m.get("Version", "?"),
                setup_brut=m.get("CarSetup"),
                debattement_volant=debattement,
                angle_roues_max=roues,
            )
        return self._info

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------

    @property
    def canaux(self) -> Mapping[str, InfoCanal]:
        if self._canaux is None:
            self._canaux = {}
            for nom, freq, unite in self._con.execute(
                "SELECT channelName, frequency, unit FROM channelsList"
            ).fetchall():
                colonnes = self._colonnes(nom)
                if colonnes is None:
                    continue  # canal déclaré mais table absente : on l'ignore
                self._canaux[nom] = InfoCanal(
                    nom=nom,
                    frequence=freq,
                    unite=unite or "",
                    par_roue=len(colonnes) == 4,
                    echantillons=self._compter(nom),
                )
        return self._canaux

    @property
    def evenements(self) -> Mapping[str, InfoEvenement]:
        if self._evenements is None:
            self._evenements = {}
            for nom, unite in self._con.execute(
                "SELECT eventName, unit FROM eventsList"
            ).fetchall():
                colonnes = self._colonnes(nom)
                if colonnes is None:
                    continue
                self._evenements[nom] = InfoEvenement(
                    nom=nom,
                    unite=unite or "",
                    par_roue=len([c for c in colonnes if c != "ts"]) == 4,
                    lignes=self._compter(nom),
                )
        return self._evenements

    # ------------------------------------------------------------------
    # Temps
    # ------------------------------------------------------------------

    @property
    def t0(self) -> float:
        """Instant de départ de l'enregistrement, en secondes de session.

        C'est le `ts` du premier événement du fichier. Les canaux, qui n'ont
        pas d'horodatage, sont recalés dessus.
        """
        if self._t0 is None:
            noms = list(self.evenements)
            valeur = (
                self._con.execute(
                    "SELECT min(debut) FROM ("
                    + " UNION ALL ".join(
                        f"SELECT min(ts) AS debut FROM {_echapper(n)}" for n in noms
                    )
                    + ")"
                ).fetchone()[0]
                if noms
                else None
            )
            self._t0 = float(valeur) if valeur is not None else 0.0
        return self._t0

    @property
    def duree(self) -> float:
        """Durée de l'enregistrement en secondes, d'après le canal le plus rapide."""
        return max((c.duree for c in self.canaux.values()), default=0.0)

    def indice(self, canal: str, temps: float) -> int:
        """Indice de l'échantillon d'un canal correspondant à un temps absolu.

        Le résultat est borné aux limites du canal. Attention : à basse
        fréquence, l'arrondi peut décaler d'un échantillon — voir la note sur
        les frontières de tours dans docs/01-decouverte.md.
        """
        info = self._info_canal(canal)
        i = round((temps - self.t0) * info.frequence)
        return max(0, min(info.echantillons - 1, i))

    # ------------------------------------------------------------------
    # Lecture des données
    # ------------------------------------------------------------------

    def canal(self, nom: str) -> np.ndarray:
        """Valeurs d'un canal.

        Renvoie un tableau de forme (n,) pour un canal simple, (n, 4) pour un
        canal par roue, les colonnes étant dans l'ordre AVG, AVD, ARG, ARD.
        """
        if nom in self._cache:
            return self._cache[nom]
        self._info_canal(nom)  # lève DonneeManquante si inconnu
        colonnes = self._colonnes(nom) or []
        lignes = self._con.execute(
            f"SELECT {', '.join(colonnes)} FROM {_echapper(nom)}"
        ).fetchall()
        tableau = np.array(lignes, dtype=float)
        if tableau.ndim == 2 and tableau.shape[1] == 1:
            tableau = tableau[:, 0]
        self._cache[nom] = tableau
        return tableau

    def temps_canal(self, nom: str) -> np.ndarray:
        """Temps absolus, en secondes, de chaque échantillon d'un canal."""
        info = self._info_canal(nom)
        return self.t0 + np.arange(info.echantillons) / info.frequence

    def evenement(self, nom: str) -> tuple[np.ndarray, np.ndarray]:
        """Événement horodaté : renvoie (temps, valeurs).

        `valeurs` est de forme (n,) ou (n, 4) pour les événements par roue.
        Les valeurs restent typées comme dans le fichier (booléens, entiers,
        flottants), sans conversion.
        """
        if nom not in self.evenements:
            raise DonneeManquante(nom, list(self.evenements))
        colonnes = [c for c in (self._colonnes(nom) or []) if c != "ts"]
        lignes = self._con.execute(
            f"SELECT ts, {', '.join(colonnes)} FROM {_echapper(nom)} ORDER BY ts"
        ).fetchall()
        if not lignes:
            return np.empty(0), np.empty(0)
        temps = np.array([l[0] for l in lignes], dtype=float)
        brut = [l[1:] for l in lignes]
        valeurs = np.array([v[0] for v in brut]) if len(colonnes) == 1 else np.array(brut)
        return temps, valeurs

    def valeur_a(self, evenement: str, temps: float, defaut=None):
        """Dernière valeur connue d'un événement à un instant donné.

        Les événements n'étant écrits qu'au changement, connaître l'état à un
        instant t revient à prendre la dernière ligne dont le `ts` est ≤ t.
        """
        ts, valeurs = self.evenement(evenement)
        anterieurs = np.nonzero(ts <= temps)[0]
        if anterieurs.size == 0:
            return defaut
        return valeurs[anterieurs[-1]]

    # ------------------------------------------------------------------
    # Utilitaires internes
    # ------------------------------------------------------------------

    def _info_canal(self, nom: str) -> InfoCanal:
        if nom not in self.canaux:
            raise DonneeManquante(nom, list(self.canaux))
        return self.canaux[nom]

    def _structure(self) -> dict[str, tuple[list[str], int]]:
        """Colonnes et nombre de lignes de TOUTES les tables, en deux requêtes.

        Première version : un `DESCRIBE` puis un `count(*)` par table, soit
        256 requêtes pour ouvrir une session — 67 % du temps d'ouverture,
        mesuré au profileur. Le transfert des données lui-même n'en pesait que
        4 %. C'est ce qui rendait lents le résumé des sessions de la liste et
        le tri par chrono.

        Les comptes restent EXACTS : un seul `count(*)` par table, simplement
        regroupés dans une même requête. DuckDB fournit aussi un nombre de
        lignes estimé, qui s'est révélé égal au vrai sur les 44 541 tables des
        441 fichiers du disque ; mais c'est une propriété interne, pas une
        garantie, et la reconstruction du temps (t = t0 + i / f) ne tolère pas
        un compte faux.
        """
        if self._tables is None:
            colonnes: dict[str, list[str]] = {}
            # Les seules tables du fichier : `duckdb_columns()` liste aussi les
            # vues système de DuckDB (`information_schema`…), qu'on ne peut pas
            # compter depuis le schéma principal.
            for table, colonne in self._con.execute(
                "SELECT table_name, column_name FROM duckdb_columns() "
                "WHERE NOT internal AND schema_name = 'main' "
                "AND database_name = current_database() "
                "ORDER BY table_name, column_index"
            ).fetchall():
                colonnes.setdefault(table, []).append(colonne)
            comptes = dict(
                self._con.execute(
                    " UNION ALL ".join(
                        f"SELECT {_litteral(t)}, count(*) FROM {_echapper(t)}"
                        for t in colonnes
                    )
                ).fetchall()
            ) if colonnes else {}
            self._tables = {t: (c, comptes.get(t, 0)) for t, c in colonnes.items()}
        return self._tables

    def _colonnes(self, table: str) -> list[str] | None:
        trouve = self._structure().get(table)
        return trouve[0] if trouve else None

    def _compter(self, table: str) -> int:
        trouve = self._structure().get(table)
        return trouve[1] if trouve else 0


# ----------------------------------------------------------------------
# Fonctions libres
# ----------------------------------------------------------------------


def _echapper(nom: str) -> str:
    """Entoure un nom de table de guillemets : beaucoup contiennent des espaces."""
    return '"' + nom.replace('"', '""') + '"'


def _litteral(texte: str) -> str:
    """Chaîne SQL entre apostrophes, pour renvoyer un nom de table en valeur."""
    return "'" + texte.replace("'", "''") + "'"


def _debattement(setup: str | None) -> tuple[float | None, float | None]:
    """Débattement du volant et angle des roues, lus dans le setup embarqué.

    Le réglage se présente ainsi dans `metadata.CarSetup` :

        "VM_STEER_LOCK": {"caption": "Wheel Range (Lock)",
                          "stringValue": "584 (20.3) deg", ...}

    Le premier nombre est le débattement TOTAL du volant, d'une butée à
    l'autre ; le second l'angle des roues avant à fond de braquage.

    --- Pourquoi une lecture aussi tolérante ---

    La chaîne n'a pas de format stable. Trois écritures différentes coexistent
    sur les 26 voitures pilotées :

        "584 (20.3) deg"      la plus courante
        "524deg (18.5deg)"    McLaren 720S
        "516 deg(19.7 )"      BMW M4

    On extrait donc les nombres sans rien supposer de la ponctuation, et on
    rejette le résultat s'il sort des bornes plausibles : mieux vaut afficher
    des pourcentages que des degrés faux.

    --- Pourquoi c'est bien le débattement total ---

    Parce que `Steering Pos` sature à exactement 100,000 % et ne dépasse jamais
    cette valeur : mesuré sur 388 sessions, dont 149 atteignent la butée. Le
    pourcentage est donc une fraction du braquage maximal d'UN côté, et
    l'angle au volant vaut `pourcentage / 100 x débattement / 2`.

    Recoupement : la démultiplication qui en découle vaut 14,4:1 sur la
    911 GT3 R et 12,9:1 sur l'Oreca 07, ce qui est l'ordre de grandeur attendu
    pour ces voitures. Et sur un tour, l'angle ainsi obtenu suit la courbure de
    la trajectoire avec une corrélation de 0,84 à 0,94 par tranche de vitesse :
    la relation est bien linéaire.
    """
    if not setup:
        return None, None
    try:
        reglage = json.loads(setup).get("VM_STEER_LOCK") or {}
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None, None

    nombres = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(reglage.get("stringValue", "")))]
    if len(nombres) < 2:
        return None, None

    volant, roues = nombres[0], nombres[1]
    if not _DEBATTEMENT_PLAUSIBLE[0] <= volant <= _DEBATTEMENT_PLAUSIBLE[1]:
        return None, None
    if not _ANGLE_ROUES_PLAUSIBLE[0] <= roues <= _ANGLE_ROUES_PLAUSIBLE[1]:
        return volant, None
    return volant, roues


def _horodatage(brut: str | None) -> datetime | None:
    """Convertit `2026-09-08T12_12_19Z` en datetime.

    Le jeu remplace les deux-points par des underscores, un nom de fichier
    Windows ne pouvant pas contenir de « : ».
    """
    if not brut:
        return None
    try:
        date, _, heure = brut.partition("T")
        return datetime.fromisoformat(
            f"{date}T{heure.rstrip('Z').replace('_', ':')}"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
