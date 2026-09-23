"""Découpage d'une session en tours, avec chronos et validité.

Ce module ne connaît rien à DuckDB ni au format du jeu : il ne parle qu'aux
objets fournis par `reader.py`. C'est ce qui permet de le tester sans le jeu, et
de survivre à un changement de format côté LMU.

--------------------------------------------------------------------------
Comment les tours sont reconstruits
--------------------------------------------------------------------------

Le jeu fournit lui-même les frontières et les chronos ; on ne redétecte rien.

* L'événement `Lap` donne l'instant de franchissement de la ligne et le numéro
  du tour qui COMMENCE à cet instant.

* L'événement `Lap Time` est DÉCALÉ D'UN TOUR : le chrono écrit à l'instant où
  commence le tour N est la durée du tour N-1. Vérifié sur une course de 13
  tours, où le chrono officiel colle à la durée mesurée entre deux événements
  `Lap` à moins de 20 ms près.

* Quand le jeu n'écrit AUCUN chrono pour un tour pourtant bouclé hors des
  stands, c'est qu'il l'a invalidé (limites de piste). On prend ce verdict tel
  quel plutôt que de recalculer les limites de piste nous-mêmes. Contrôle :
  71 % de ces tours contiennent des échantillons hors piste, contre 36 % des
  tours validés.

--------------------------------------------------------------------------
Pourquoi il n'y a pas de détection de tête-à-queue
--------------------------------------------------------------------------

Le brief demandait de repérer les tête-à-queue par un yaw rate anormal. Le
fichier du jeu ne contient pas de yaw rate ; il n'existe que dans la shared
memory. J'ai essayé de le reconstruire à partir de la trajectoire GPS, et je
l'ai écarté après mesure : la position GPS est quantifiée à 0,42 m et
échantillonnée à 10 Hz seulement. L'indicateur obtenu ne corrèle pas avec la
référence physique (a_lat / v) — 0,11 de corrélation — et donnait des
tête-à-queue imaginaires sur des tours parfaitement propres.

À la place, on signale un fait mesurable et non ambigu : la voiture s'est-elle
quasiment arrêtée en piste. C'est vérifiable, c'est descriptif, et ça attrape
les incidents réels sans prétendre en connaître la cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .reader import SURFACES_HORS_PISTE, FichierSession, InfoSession
from .textes import Message

#: Vitesse (km/h) en dessous de laquelle on considère que la voiture s'est
#: quasiment arrêtée en piste : tête-à-queue, sortie, ou arrêt volontaire.
#:
#: Calibré sur les 420 tours valides enregistrés : la vitesse minimale médiane
#: d'un tour va de 54 à 69 km/h selon le circuit — c'est le virage le plus lent.
#: En dessous de 30 km/h il ne s'agit plus d'un virage mais d'un incident.
#: Sur ces données, 13 à 19 % des tours pourtant chronométrés par le jeu
#: contiennent un tel arrêt.
SEUIL_QUASI_ARRET = 30.0

#: Durée minimale hors piste (toutes roues confondues) au-delà de laquelle on
#: le signale comme une sortie, et non comme un simple passage sur l'herbe.
DUREE_SORTIE_SIGNALEE = 0.6

#: Précision réelle (s) de la durée mesurée entre deux événements `Lap`.
#:
#: Le chrono du jeu est exact : c'est l'instant interpolé du franchissement.
#: L'événement `Lap`, lui, n'est inscrit qu'au cycle de mise à jour suivant.
#: Chaque frontière porte donc un retard, et la durée mesurée — une différence
#: de deux frontières — porte la différence de ces deux retards.
#:
#: Mesuré sur les 415 tours cohérents du disque : écart signé entre -18,96 et
#: +18,75 ms, moyenne +0,19 ms, écart-type 7,87 ms. Une différence de deux
#: retards tirés uniformément dans un cycle de 20 ms suit une loi triangulaire
#: de bornes ±20 ms et d'écart-type 20/√6 = 8,2 ms. L'accord est net.
#:
#: Conséquence pour l'affichage : ne jamais présenter la durée mesurée au
#: millième, on ne l'a pas.
PRECISION_DUREE_MESUREE = 0.02

#: Écart toléré (s) entre le chrono du jeu et la durée mesurée entre deux
#: franchissements de ligne.
#:
#: Mesuré sur les 435 tours chronométrés du disque : la distribution est
#: franchement bimodale. 415 tours concordent à 6 ms près (médiane), et les
#: 20 restants divergent de 55 à 132 s — ce sont TOUS des tours 0 de course,
#: où la voiture attend le départ sur la grille. La fenêtre de télémétrie ne
#: correspond alors pas au chrono, et le tour n'est comparable à aucun autre.
#: N'importe quel seuil entre 0,05 s et 5 s isole exactement les mêmes 20 tours.
TOLERANCE_CHRONO = 0.5


@dataclass(frozen=True)
class Tour:
    """Un tour, tel que le jeu l'a délimité."""

    numero: int
    """Numéro donné par le jeu (l'événement `Lap`)."""

    index: int
    """Position dans la session, à partir de 0."""

    debut: float
    """Instant de franchissement de la ligne, en secondes de session."""

    fin: float | None
    """Instant du franchissement suivant. None si la session s'arrête avant."""

    chrono: float | None
    """Chrono officiel du jeu, en secondes. None si le tour n'est pas chronométré."""

    cumul_s1: float | None
    """Temps cumulé à la fin du secteur 1, en secondes. None si non fourni."""

    cumul_s2: float | None
    """Temps cumulé à la fin du secteur 2, en secondes. None si non fourni."""

    stands: bool
    """Le tour passe par les stands (garage, entrée ou sortie)."""

    contacts: int
    """Nombre de chocs détectés pendant le tour."""

    duree_hors_piste: float
    """Temps passé avec au moins une roue sur l'herbe, la terre ou le gravier."""

    vitesse_min: float
    """Vitesse la plus basse atteinte pendant le tour, en km/h."""

    duree_quasi_arret: float
    """Temps passé sous SEUIL_QUASI_ARRET, en secondes."""

    remarques: tuple[Message, ...] = field(default_factory=tuple)
    """Ce qui a été observé sur ce tour. Descriptif, jamais un jugement."""

    @property
    def complet(self) -> bool:
        """Le tour a-t-il été bouclé, ou la session s'est-elle arrêtée avant ?"""
        return self.fin is not None

    @property
    def chronometre(self) -> bool:
        return self.chrono is not None

    @property
    def duree_mesuree(self) -> float | None:
        """Durée entre les deux franchissements, indépendante du chrono du jeu."""
        return None if self.fin is None else self.fin - self.debut

    @property
    def secteurs(self) -> tuple[float | None, float | None, float | None]:
        """Durées des trois secteurs, obtenues par différence des temps cumulés."""
        s1 = self.cumul_s1
        s2 = None if (self.cumul_s2 is None or s1 is None) else self.cumul_s2 - s1
        s3 = None if (self.chrono is None or self.cumul_s2 is None) else self.chrono - self.cumul_s2
        return s1, s2, s3

    @property
    def quasi_arret(self) -> bool:
        """La voiture s'est-elle quasiment arrêtée pendant le tour ?

        On s'en tient au constat. Un arrêt peut venir d'un tête-à-queue, d'une
        sortie, d'un abandon de tour ou du trafic en course : la télémétrie ne
        permet pas de trancher, et l'outil ne prétend pas le faire.
        """
        return self.vitesse_min < SEUIL_QUASI_ARRET

    @property
    def ecart_chrono(self) -> float | None:
        """Écart entre le chrono du jeu et la durée mesurée, en secondes.

        C'est le contrôle d'intégrité de tout le module : si ces deux valeurs,
        obtenues par deux chemins indépendants, ne coïncident pas, c'est que la
        fenêtre de télémétrie ne correspond pas au tour chronométré.
        """
        if self.chrono is None or self.duree_mesuree is None:
            return None
        return abs(self.chrono - self.duree_mesuree)

    @property
    def coherent(self) -> bool:
        """Le chrono du jeu et la durée mesurée concordent-ils ?"""
        return self.ecart_chrono is None or self.ecart_chrono <= TOLERANCE_CHRONO

    @property
    def valide(self) -> bool:
        """Un tour est valide s'il est bouclé, chronométré, hors stands, cohérent.

        On ne réinvente pas les limites de piste : l'absence de chrono EST le
        verdict d'invalidité du jeu. Le hors-piste et les chocs sont signalés
        dans les remarques mais ne disqualifient pas à eux seuls un tour que le
        jeu a chronométré — c'est lui qui arbitre.
        """
        return self.complet and self.chronometre and not self.stands and self.coherent


@dataclass(frozen=True)
class Session:
    """Une session de roulage, découpée en tours."""

    chemin: Path
    info: InfoSession
    tours: tuple[Tour, ...]
    journal_present: bool
    """Un .wal traînait à côté : la fin de la session peut manquer."""

    # ------------------------------------------------------------------

    @classmethod
    def ouvrir(cls, chemin: Path | str) -> "Session":
        """Lit un fichier de session et en extrait les tours."""
        with FichierSession(chemin) as fichier:
            return cls(
                chemin=fichier.chemin,
                info=fichier.info,
                tours=tuple(_construire_tours(fichier)),
                journal_present=fichier.journal_present,
            )

    # ------------------------------------------------------------------

    @property
    def tours_valides(self) -> tuple[Tour, ...]:
        return tuple(t for t in self.tours if t.valide)

    @property
    def meilleur_tour(self) -> Tour | None:
        valides = [t for t in self.tours_valides if t.chrono is not None]
        return min(valides, key=lambda t: t.chrono) if valides else None

    @property
    def duree_roulage(self) -> float:
        """Durée cumulée des tours bouclés, en secondes."""
        return sum(t.duree_mesuree or 0.0 for t in self.tours)


# ----------------------------------------------------------------------
# Construction des tours
# ----------------------------------------------------------------------


def _construire_tours(fichier: FichierSession) -> list[Tour]:
    ts_lap, numeros = fichier.evenement("Lap")
    if ts_lap.size == 0:
        return []

    # `Last Sector1/2` obéissent au même décalage d'un tour que `Lap Time` : la
    # valeur écrite au franchissement de ligne concerne le tour qui s'achève.
    # Ce sont des temps CUMULÉS depuis la ligne, pas des durées de secteur.
    ts_chrono, chronos = fichier.evenement("Lap Time")
    ts_s1, s1 = fichier.evenement("Last Sector1")
    ts_s2, s2 = fichier.evenement("Last Sector2")

    stands = _intervalles_stands(fichier)
    chocs = _instants_chocs(fichier)
    hors_piste = _intervalles_hors_piste(fichier)
    vitesse = fichier.canal("Ground Speed")
    freq_vitesse = fichier.canaux["Ground Speed"].frequence

    tours: list[Tour] = []
    for i, debut in enumerate(ts_lap):
        fin = float(ts_lap[i + 1]) if i + 1 < len(ts_lap) else None

        # Le chrono du tour i est écrit à l'instant où commence le tour i+1.
        chrono = _valeur_a_instant(ts_chrono, chronos, fin) if fin is not None else None
        if chrono is not None and chrono <= 0:
            chrono = None

        borne = fin if fin is not None else fichier.t0 + fichier.duree
        segment = vitesse[
            int((debut - fichier.t0) * freq_vitesse) : int((borne - fichier.t0) * freq_vitesse)
        ]
        tours.append(
            _assembler_tour(
                index=i,
                numero=int(numeros[i]),
                debut=float(debut),
                fin=fin,
                chrono=chrono,
                cumul_s1=_valeur_a_instant(ts_s1, s1, fin),
                cumul_s2=_valeur_a_instant(ts_s2, s2, fin),
                stands=_recouvre(stands, float(debut), borne),
                contacts=int(np.count_nonzero((chocs > debut) & (chocs <= borne))),
                duree_hors_piste=_duree_recouvrement(hors_piste, float(debut), borne),
                vitesse_min=float(segment.min()) if segment.size else 0.0,
                duree_quasi_arret=(
                    float(np.count_nonzero(segment < SEUIL_QUASI_ARRET)) / freq_vitesse
                    if segment.size
                    else 0.0
                ),
            )
        )
    return tours


def _assembler_tour(**champs) -> Tour:
    """Crée le tour puis y attache les remarques observées."""
    tour = Tour(**champs, remarques=())
    remarques: list[Message] = []

    if not tour.complet:
        remarques.append(Message("serveur.tour.non_boucle"))
    if tour.stands:
        remarques.append(Message("serveur.tour.stands"))
    if tour.complet and not tour.chronometre and not tour.stands:
        remarques.append(Message("serveur.tour.invalide"))
    if not tour.coherent:
        remarques.append(
            Message("serveur.tour.incoherent", {"ecart": f"{tour.ecart_chrono:.0f}"})
        )
    if tour.duree_hors_piste >= DUREE_SORTIE_SIGNALEE:
        remarques.append(
            Message("serveur.tour.hors_piste", {"duree": f"{tour.duree_hors_piste:.1f}"})
        )
    if tour.contacts:
        cle = "serveur.tour.chocs.un" if tour.contacts == 1 else "serveur.tour.chocs.plusieurs"
        remarques.append(Message(cle, {"n": tour.contacts}))
    if tour.quasi_arret and not tour.stands:
        remarques.append(
            Message(
                "serveur.tour.quasi_arret",
                {
                    "vitesse": f"{tour.vitesse_min:.0f}",
                    "duree": f"{tour.duree_quasi_arret:.1f}",
                },
            )
        )

    # `remarques` est figé dans le dataclass : on reconstruit l'objet.
    return Tour(
        **{k: v for k, v in tour.__dict__.items() if k != "remarques"},
        remarques=tuple(remarques),
    )


# ----------------------------------------------------------------------
# Extraction des signaux annexes
# ----------------------------------------------------------------------


def _intervalles_stands(fichier: FichierSession) -> list[tuple[float, float]]:
    """Périodes où la voiture est aux stands, d'après `In Pits`.

    `In Pits` vaut 1 dans la voie des stands et le garage, 0 en piste, et n'est
    écrit qu'au changement : on reconstruit donc les intervalles.
    """
    ts, valeurs = fichier.evenement("In Pits")
    if ts.size == 0:
        return []
    fin_session = fichier.t0 + fichier.duree
    intervalles = []
    for i, instant in enumerate(ts):
        if valeurs[i]:
            suivant = float(ts[i + 1]) if i + 1 < len(ts) else fin_session
            intervalles.append((float(instant), suivant))
    return intervalles


def _instants_chocs(fichier: FichierSession) -> np.ndarray:
    """Instants des chocs, d'après les passages à True de `LastImpactMagnitude`.

    La valeur présente à t0 est l'état initial et non un choc : on l'écarte.
    """
    ts, valeurs = fichier.evenement("LastImpactMagnitude")
    if ts.size == 0:
        return np.empty(0)
    montees = [
        float(ts[i])
        for i in range(len(ts))
        if valeurs[i] and (i == 0 or not valeurs[i - 1]) and ts[i] > fichier.t0
    ]
    return np.array(montees)


def _intervalles_hors_piste(fichier: FichierSession) -> list[tuple[float, float]]:
    """Périodes où au moins une roue est sur l'herbe, la terre ou le gravier."""
    if "SurfaceTypes" not in fichier.canaux:
        return []
    surfaces = fichier.canal("SurfaceTypes")
    temps = fichier.temps_canal("SurfaceTypes")
    pas = 1.0 / fichier.canaux["SurfaceTypes"].frequence
    dehors = np.isin(surfaces, list(SURFACES_HORS_PISTE)).any(axis=1)
    return [(float(t), float(t) + pas) for t, d in zip(temps, dehors) if d]



# ----------------------------------------------------------------------
# Petits utilitaires
# ----------------------------------------------------------------------


def _valeur_a_instant(
    ts: np.ndarray, valeurs: np.ndarray, instant: float | None
) -> float | None:
    """Valeur écrite exactement à `instant`, à la tolérance d'horodatage près.

    Renvoie None si rien n'a été écrit à cet instant, ou si la valeur est nulle
    ou négative : le jeu écrit 0.0 comme valeur initiale de tous ces
    événements, ce qui ne correspond à aucun temps réel.
    """
    if instant is None or ts.size == 0:
        return None
    candidats = np.nonzero(np.isclose(ts, instant, atol=1e-3))[0]
    if candidats.size == 0:
        return None
    valeur = float(valeurs[candidats[-1]])
    return valeur if valeur > 0 else None


def _recouvre(intervalles: list[tuple[float, float]], debut: float, fin: float) -> bool:
    return any(a < fin and b > debut for a, b in intervalles)


def _duree_recouvrement(
    intervalles: list[tuple[float, float]], debut: float, fin: float
) -> float:
    return sum(max(0.0, min(b, fin) - max(a, debut)) for a, b in intervalles)
