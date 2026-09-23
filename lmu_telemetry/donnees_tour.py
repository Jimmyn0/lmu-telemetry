"""Extraction d'un tour, ramené sur un axe de distance.

Comme `session.py`, ce module ne connaît rien à DuckDB : il ne parle qu'au
lecteur. Il produit l'objet que manipuleront la comparaison de tours et, plus
tard, le découpage en virages.

--------------------------------------------------------------------------
Pourquoi la distance, et pas le temps
--------------------------------------------------------------------------

Superposer deux tours en fonction du temps ne veut rien dire : au bout de dix
secondes, les deux voitures ne sont pas au même endroit du circuit. Il faut les
aligner sur la DISTANCE PARCOURUE, pour comparer ce qui se passe au même point
de la piste.

--------------------------------------------------------------------------
Quelle distance
--------------------------------------------------------------------------

Le canal `Lap Dist` mesure l'avancement le long de la piste. C'est bien celui
qu'il faut : deux tours qui prennent des trajectoires différentes doivent quand
même se comparer au même endroit du circuit.

Ce n'est PAS la distance réellement parcourue par la voiture, qui est plus
longue dès qu'on s'écarte de l'axe. Mesuré : intégrer `Ground Speed` sur un tour
donne 10 à 40 m de plus que `Lap Dist` sur 5 776 m, soit 0,2 à 0,7 %. Les deux
sont justes, ils ne mesurent simplement pas la même chose. Une intégration de la
vitesse recalée sur `Lap Dist`, comme envisagé au départ, mélangerait les deux
et n'apporterait rien.

--------------------------------------------------------------------------
Passer de 10 Hz à 100 Hz
--------------------------------------------------------------------------

`Lap Dist` n'est échantillonné qu'à 10 Hz, soit un point tous les 6 m à
227 km/h, alors que la vitesse et l'angle volant sont à 100 Hz. On interpole
donc la distance sur la grille 100 Hz.

Une interpolation LINÉAIRE suffit, et ce n'est pas une approximation grossière :
comparée à une interpolation cubique sur les mêmes données, l'écart médian est
de 2 mm et le 99e centile de 3 cm. Sur 0,1 s l'accélération ne courbe pas assez
la distance pour que ça se voie.

Le seul vrai piège est aux BORDS du tour : le dernier échantillon de `Lap Dist`
tombe jusqu'à 0,1 s avant la ligne d'arrivée, et une interpolation classique
figerait la distance sur cette fin de tour — jusqu'à 5 m perdus à 227 km/h. On
extrapole donc linéairement au-delà du dernier point, en prolongeant la pente
locale, qui n'est autre que la vitesse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .errors import ErreurTelemetrie
from .reader import SURFACES_HORS_PISTE, FichierSession, InfoSession
from .session import Session, Tour

#: Canaux chargés par défaut : ceux que le brief demande de superposer (§4.4),
#: plus les coordonnées GPS qui servent à tracer la carte du circuit.
CANAUX_PAR_DEFAUT = (
    "Ground Speed",
    "Throttle Pos",
    "Brake Pos",
    "Steering Pos",
    "Engine RPM",
    "GPS Latitude",
    "GPS Longitude",
    # Position latérale dans la piste et bord de piste : servent à reconstruire
    # la géométrie de la route pour la vue rapprochée (voir piste.py).
    "Path Lateral",
    "Track Edge",
)

#: Événements transformés en signal en escalier sur la grille du tour.
#: Le rapport engagé est un événement, pas un canal : il n'est écrit qu'aux
#: changements de vitesse.
EVENEMENTS_PAR_DEFAUT = ("Gear",)

#: Canaux DISCONTINUS, à rééchantillonner au plus proche voisin et non par
#: interpolation linéaire.
#:
#: `Track Edge` donne la position du bord de piste du côté où se trouve la
#: voiture : il saute donc d'un bord à l'autre, d'un coup, quand la voiture
#: franchit l'axe. Vérifié sur un tour de Monza : la valeur passe de -5,22 à
#: +4,78 entre deux échantillons consécutifs, et AUCUN des 1 143 échantillons
#: bruts ne vaut moins de 2 m en valeur absolue. Interpoler linéairement à
#: travers ce saut fabrique des positions de bord qui n'existent pas — au
#: milieu de la piste — 26 fois par tour.
CANAUX_DISCONTINUS = frozenset({"Track Edge", "Hors Piste"})

#: Canal calculé : 1 quand au moins une roue est hors piste, 0 sinon.
#:
#: `SurfaceTypes` donne la nature du sol SOUS CHAQUE ROUE, à 5 Hz. C'est un
#: canal par roue, que le rééchantillonnage ordinaire refuse : il faut d'abord
#: le réduire à une seule valeur par instant. D'où ce canal calculé.
#:
#: Il sert à écarter les passages hors piste de la reconstruction de la
#: géométrie (voir `piste.py`) : une sortie de route déplace la trajectoire de
#: plusieurs dizaines de mètres et fausserait l'axe du circuit.
CANAL_HORS_PISTE = "Hors Piste"
CANAL_SURFACES = "SurfaceTypes"

#: Fréquence de la grille de travail, en Hz. C'est celle des canaux les plus
#: rapides du jeu : on ne fabrique pas de résolution qui n'existe pas.
FREQUENCE_GRILLE = 100

#: Canal calculé : l'angle au volant en degrés, déduit de `Steering Pos`.
#:
#: Le jeu n'enregistre le braquage qu'en POURCENTAGE du braquage maximal, ce
#: qui n'est comparable qu'à l'intérieur d'une même voiture réglée pareil :
#: 40 % valent 117° sur la Porsche 911 GT3 R (584° de débattement) mais 67°
#: sur l'Oreca 07 (336°). Le débattement figurant dans le fichier (voir
#: `reader._debattement`), on convertit une fois pour toutes.
#:
#: Le canal en pourcentage reste disponible : on ajoute, on ne remplace pas.
CANAL_VOLANT = "Angle Volant"
CANAL_BRAQUAGE = "Steering Pos"


class TourIntrouvable(ErreurTelemetrie):
    def __init__(self, numero: int, disponibles: list[int]) -> None:
        super().__init__(
            f"Le tour {numero} n'existe pas dans cette session.\n"
            f"Tours disponibles : {', '.join(map(str, disponibles)) or 'aucun'}"
        )


@dataclass(frozen=True)
class DonneesTour:
    """Un tour, échantillonné à 100 Hz, avec son axe de distance."""

    tour: Tour
    info: InfoSession
    chemin: Path

    temps: np.ndarray
    """Secondes depuis le franchissement de la ligne."""

    distance: np.ndarray
    """Mètres parcourus le long de la piste depuis la ligne. Croissante."""

    canaux: dict[str, np.ndarray]
    """Canaux et événements ramenés sur la même grille que `temps`."""

    @property
    def longueur(self) -> float:
        """Distance couverte par le tour, en mètres."""
        return float(self.distance[-1])

    @property
    def duree(self) -> float:
        return float(self.temps[-1])

    def canal(self, nom: str) -> np.ndarray:
        if nom not in self.canaux:
            raise ErreurTelemetrie(
                f"« {nom} » n'a pas été chargé pour ce tour.\n"
                f"Chargés : {', '.join(sorted(self.canaux))}"
            )
        return self.canaux[nom]

    # ------------------------------------------------------------------

    def temps_a_distance(self, distances: np.ndarray) -> np.ndarray:
        """Instant auquel le tour a atteint chaque distance donnée.

        C'est l'inverse de la fonction distance(temps). Il faut que la distance
        soit croissante : quand la voiture s'arrête, elle stagne, et plusieurs
        instants correspondent alors à la même distance. On rend dans ce cas le
        plus TARDIF — celui où la voiture repart —, sinon un arrêt de trois
        secondes disparaîtrait purement et simplement du calcul de delta.
        """
        croissante = np.maximum.accumulate(self.distance)
        # np.interp veut des abscisses strictement croissantes : on ne garde
        # que le dernier instant de chaque palier.
        garde = np.append(np.diff(croissante) > 0, True)
        return np.interp(distances, croissante[garde], self.temps[garde])

    def sur_distance(self, distances: np.ndarray) -> dict[str, np.ndarray]:
        """Rééchantillonne tous les canaux sur un axe de distance donné.

        Les canaux discontinus sont pris au plus proche voisin : les interpoler
        inventerait des valeurs intermédiaires qui n'existent pas.
        """
        croissante = np.maximum.accumulate(self.distance)
        garde = np.append(np.diff(croissante) > 0, True)
        x = croissante[garde]
        return {
            nom: (
                _plus_proche(distances, x, valeurs[garde])
                if nom in CANAUX_DISCONTINUS
                else np.interp(distances, x, valeurs[garde])
            )
            for nom, valeurs in self.canaux.items()
        }


# ----------------------------------------------------------------------
# Chargement
# ----------------------------------------------------------------------


def charger(
    chemin: Path | str,
    numero: int,
    canaux: tuple[str, ...] = CANAUX_PAR_DEFAUT,
    evenements: tuple[str, ...] = EVENEMENTS_PAR_DEFAUT,
) -> DonneesTour:
    """Charge un tour d'une session, prêt à être comparé."""
    session = Session.ouvrir(chemin)
    tours = {t.numero: t for t in session.tours}
    if numero not in tours:
        raise TourIntrouvable(numero, sorted(tours))
    tour = tours[numero]
    if tour.fin is None:
        raise ErreurTelemetrie(
            f"Le tour {numero} n'a pas été bouclé : il n'y a rien à comparer."
        )

    with FichierSession(chemin) as fichier:
        grille = _grille(tour)
        distance = _distance_sur(fichier, tour, grille)
        valeurs = {
            nom: _canal_sur(fichier, nom, grille)
            for nom in canaux
            if nom in fichier.canaux
        }
        valeurs.update(
            {
                nom: _evenement_sur(fichier, nom, grille)
                for nom in evenements
                if nom in fichier.evenements
            }
        )
        _ajouter_volant(valeurs, session.info)
        _ajouter_hors_piste(fichier, valeurs, grille)

    return DonneesTour(
        tour=tour,
        info=session.info,
        chemin=session.chemin,
        temps=grille - tour.debut,
        distance=distance,
        canaux=valeurs,
    )


# ----------------------------------------------------------------------
# Rééchantillonnage
# ----------------------------------------------------------------------


def _ajouter_volant(valeurs: dict[str, np.ndarray], info: InfoSession) -> None:
    """Ajoute l'angle volant en degrés, si le débattement de la voiture est connu.

    `Steering Pos` sature à exactement 100 % à la butée — vérifié sur 388
    sessions, dont 149 l'atteignent — donc 100 % correspond au braquage maximal
    d'un côté, soit la MOITIÉ du débattement total annoncé par le réglage.

    Rien n'est ajouté si le débattement manque : mieux vaut continuer à
    afficher un pourcentage honnête qu'un angle inventé.
    """
    if CANAL_BRAQUAGE not in valeurs or not info.debattement_volant:
        return
    valeurs[CANAL_VOLANT] = valeurs[CANAL_BRAQUAGE] * info.debattement_volant / 200.0


def _ajouter_hors_piste(
    fichier: FichierSession, valeurs: dict[str, np.ndarray], grille: np.ndarray
) -> None:
    """Ajoute le canal hors piste, réduit des quatre roues à une seule valeur.

    Une roue suffit : c'est le critère déjà retenu par `session.py` pour
    annoter les tours, et il n'y a pas de raison d'en changer ici.

    Le rééchantillonnage se fait au plus proche voisin. C'est un ÉTAT, pas une
    grandeur continue : une valeur de 0,5 entre « sur la piste » et « dans le
    gravier » ne voudrait rien dire. `SurfaceTypes` est d'ailleurs à 5 Hz, deux
    fois plus lent que la position, donc chaque valeur couvre 0,2 s.

    Rien n'est ajouté si le canal manque : le reste de l'outil doit continuer
    de marcher, simplement sans pouvoir écarter les sorties de piste.
    """
    if CANAL_SURFACES not in fichier.canaux:
        return
    surfaces = fichier.canal(CANAL_SURFACES)
    if surfaces.ndim != 2:
        return
    dehors = np.isin(surfaces, list(SURFACES_HORS_PISTE)).any(axis=1)
    valeurs[CANAL_HORS_PISTE] = _plus_proche(
        grille, fichier.temps_canal(CANAL_SURFACES), dehors.astype(float)
    )


def _grille(tour: Tour) -> np.ndarray:
    """Instants absolus de la grille de travail du tour."""
    assert tour.fin is not None
    nombre = int(round((tour.fin - tour.debut) * FREQUENCE_GRILLE)) + 1
    return tour.debut + np.arange(nombre) / FREQUENCE_GRILLE


def _interpoler(
    cible: np.ndarray, x: np.ndarray, y: np.ndarray, extrapoler: bool
) -> np.ndarray:
    """Interpolation linéaire, avec ou sans prolongement au-delà des bords.

    `np.interp` fige la valeur en dehors de l'intervalle connu. Pour la distance
    c'est inacceptable : la fin du tour se retrouverait immobile. Pour les
    autres canaux, en revanche, figer est le bon comportement — prolonger la
    pente d'une pédale de frein n'aurait aucun sens.
    """
    valeurs = np.interp(cible, x, y)
    if not extrapoler or len(x) < 2:
        return valeurs

    avant = cible < x[0]
    if avant.any():
        pente = (y[1] - y[0]) / (x[1] - x[0])
        valeurs[avant] = y[0] + pente * (cible[avant] - x[0])

    apres = cible > x[-1]
    if apres.any():
        pente = (y[-1] - y[-2]) / (x[-1] - x[-2])
        valeurs[apres] = y[-1] + pente * (cible[apres] - x[-1])
    return valeurs


def _distance_sur(fichier: FichierSession, tour: Tour, grille: np.ndarray) -> np.ndarray:
    """Distance parcourue depuis la ligne, sur la grille du tour."""
    assert tour.fin is not None
    temps = fichier.temps_canal("Lap Dist")
    valeurs = fichier.canal("Lap Dist")

    # On ne garde que les échantillons du tour. La borne haute est stricte :
    # au franchissement suivant, `Lap Dist` est déjà retombé à zéro.
    dedans = (temps >= tour.debut) & (temps < tour.fin)
    if dedans.sum() < 2:
        raise ErreurTelemetrie(
            f"Le tour {tour.numero} est trop court pour être exploité "
            f"({dedans.sum()} échantillon(s) de distance)."
        )

    distance = _interpoler(grille, temps[dedans], valeurs[dedans], extrapoler=True)
    # La ligne est l'origine : le premier échantillon utile est rarement
    # exactement à 0 m, et le tour ne commence pas à 3 m.
    return distance - distance[0]


def _plus_proche(cible: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Rééchantillonnage au plus proche voisin, sans rien interpoler."""
    if len(x) < 2:
        return np.full(np.shape(cible), y[0] if len(y) else 0.0)
    i = np.clip(np.searchsorted(x, cible), 1, len(x) - 1)
    avant = np.abs(cible - x[i - 1]) <= np.abs(x[i] - cible)
    return np.where(avant, y[i - 1], y[i])


def _canal_sur(fichier: FichierSession, nom: str, grille: np.ndarray) -> np.ndarray:
    valeurs = fichier.canal(nom)
    if valeurs.ndim != 1:
        raise ErreurTelemetrie(
            f"« {nom} » est un canal par roue ; il faut choisir une roue avant "
            "de le ramener sur la grille du tour."
        )
    temps = fichier.temps_canal(nom)
    if nom in CANAUX_DISCONTINUS:
        return _plus_proche(grille, temps, valeurs)
    return _interpoler(grille, temps, valeurs, extrapoler=False)


def _evenement_sur(fichier: FichierSession, nom: str, grille: np.ndarray) -> np.ndarray:
    """Transforme un événement en signal en escalier.

    Un événement n'est écrit qu'au changement : entre deux écritures, la valeur
    reste celle de la dernière. On ne fait donc surtout pas d'interpolation, qui
    inventerait des rapports intermédiaires entre la 3e et la 4e.
    """
    temps, valeurs = fichier.evenement(nom)
    if temps.size == 0:
        return np.zeros(grille.shape)
    indices = np.clip(np.searchsorted(temps, grille, side="right") - 1, 0, None)
    return np.asarray(valeurs, dtype=float)[indices]
