"""Ce qui se voit sans référence, dès le premier tour.

Chaque passage est d'abord mesuré, qu'il y ait faute ou non : `mesurer` rend des
nombres, `constats` les compare aux seuils. Les deux étapes sont séparées pour que
les seuils se calent sur ce que le pilote fait vraiment (voir tools/bilan_coach.py).

Tout est lu sur le geste du pilote, jamais sur le résultat filtré par la voiture :
`Throttle Pos` porte les coupures du changement de rapport et de l'antipatinage, qui
font passer 83 % des remises des gaz pour hésitantes, contre 3,8 % avec le canal brut.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..parametres import SeuilsCoach, SeuilsVirage
from ..textes import Message
from .passage import Passage
from .roues import glissements

#: Un coup de frein plus court, ou moins appuyé, n'est pas un freinage : le pied qui
#: effleure la pédale en sortie de virage ne doit pas passer pour la fin du freinage.
DUREE_FREINAGE_MINIMALE = 0.25
PIC_FREINAGE_MINIMAL = 15.0

#: Deux appuis plus proches que ça (s) sont un seul freinage, repris du bout du pied.
ECART_FREINAGE = 0.15

#: Bruit du pied sur l'accélérateur (%) : en dessous, ce n'est pas un mouvement.
BRUIT_GAZ = 5.0

#: Accélérateur (%) à partir duquel la remise des gaz est terminée. Lever ensuite le
#: pied n'est plus une hésitation : c'est souvent le virage suivant qui l'impose, comme
#: dans les doubles courbes de Spa.
GAZ_PLEIN = 95.0

#: Après un creux, il faut que le pied revienne d'au moins cette part : un lever qui
#: ne reprend pas prépare le virage suivant, ce n'est pas une hésitation.
REPRISE_MINIMALE = 0.5

#: Durée du lissage du volant (s), contre le bruit du capteur.
LISSAGE_VOLANT = 0.06


@dataclass(frozen=True)
class Mesures:
    """Ce qui a été relevé sur un passage."""

    roue_libre_avant: float = 0.0
    """Temps sans pédale entre le lever de pied et le frein, en secondes."""

    roue_libre_virage: float = 0.0
    """Temps sans pédale entre la fin du freinage et les gaz, en secondes."""

    chute_frein: float = 0.0
    """Plus forte baisse du frein, en points de pédale sur `fenetre_chute`."""

    creux_gaz: float = 0.0
    """Plus grand recul de l'accélérateur en sortie, en points de pédale."""

    correction: float = 0.0
    """Plus grand retour de volant à contresens, en % de braquage."""

    blocage: float | None = None
    """Glissement tenu au freinage, en %. None si la source ne voit pas les roues."""

    blocage_avant: bool = True
    """Le blocage vient de l'essieu avant."""

    patinage: float | None = None
    """Glissement tenu à l'accélération, en %. None si la source ne voit pas les roues."""


@dataclass(frozen=True)
class Constat:
    """Une faute, et la phrase qui dit quoi faire."""

    code: str
    message: Message


# ----------------------------------------------------------------------
# Petits outils
# ----------------------------------------------------------------------


def _plages(masque: np.ndarray) -> list[tuple[int, int]]:
    """Les portions vraies d'un masque, en (début, fin exclue)."""
    bords = np.flatnonzero(np.diff(np.r_[0, masque.astype(np.int8), 0]))
    return list(zip(bords[::2].tolist(), bords[1::2].tolist()))


def _zigzag(valeurs: np.ndarray, seuil: float) -> list[int]:
    """Les indices des extrema d'une courbe, oscillations sous `seuil` ignorées.

    C'est ce qui distingue un mouvement du bruit : un extremum n'est retenu qu'une
    fois que la courbe en est repartie d'au moins `seuil`.
    """
    liste = valeurs.tolist()
    extrema = [0]
    sens = 0
    for i, valeur in enumerate(liste):
        reference = liste[extrema[-1]]
        if sens == 0:
            if abs(valeur - reference) >= seuil:
                sens = 1 if valeur > reference else -1
                extrema.append(i)
        elif (valeur - reference) * sens >= 0:
            extrema[-1] = i
        elif abs(valeur - reference) >= seuil:
            sens = -sens
            extrema.append(i)
    return extrema


def _lisser(valeurs: np.ndarray, largeur: int) -> np.ndarray:
    largeur = max(1, largeur) | 1
    return np.convolve(
        np.pad(valeurs, largeur // 2, mode="edge"), np.ones(largeur) / largeur, mode="valid"
    )


def _pas(passage: Passage) -> float:
    return float(np.median(np.diff(passage.temps)))


def _freinages(passage: Passage, seuil: float) -> list[tuple[int, int]]:
    """Les freinages d'un passage, en (début, fin exclue)."""
    t, frein = passage.temps, passage.frein
    reunis: list[list[int]] = []
    for debut, fin in _plages(frein > seuil):
        if reunis and t[debut] - t[reunis[-1][1] - 1] < ECART_FREINAGE:
            reunis[-1][1] = fin
        else:
            reunis.append([debut, fin])
    return [
        (debut, fin)
        for debut, fin in reunis
        if t[fin - 1] - t[debut] >= DUREE_FREINAGE_MINIMALE
        and frein[debut:fin].max() >= PIC_FREINAGE_MINIMAL
    ]


# ----------------------------------------------------------------------
# Mesures
# ----------------------------------------------------------------------


def _roue_libre_avant(p: Passage, freinages: list[tuple[int, int]], v: SeuilsVirage) -> float:
    """Le plus long temps sans pédale juste avant l'attaque d'un freinage."""
    pedale = (p.gaz > v.coasting_gaz) | (p.frein > v.coasting_frein)
    pire = 0.0
    for debut, _fin in freinages:
        derniere = np.flatnonzero(pedale[:debut])
        if derniere.size:
            pire = max(pire, float(p.temps[debut] - p.temps[derniere[-1]]))
    return pire


def _roue_libre_virage(p: Passage, depart: int | None, v: SeuilsVirage) -> float:
    """Le temps entre la fin du freinage et le premier geste qui suit."""
    if depart is None:
        return 0.0
    geste = np.flatnonzero((p.gaz[depart:] > v.coasting_gaz) | (p.frein[depart:] > v.coasting_frein))
    fin = depart + int(geste[0]) if geste.size else p.temps.size - 1
    return float(p.temps[fin] - p.temps[depart])


def _chute_frein(p: Passage, freinages: list[tuple[int, int]], fenetre: float) -> float:
    """La baisse de frein la plus rapide. L'échantillon d'après la fin compte : c'est
    lui qui voit la pédale retomber à zéro."""
    largeur = max(1, int(round(fenetre / _pas(p))))
    pire = 0.0
    for debut, fin in freinages:
        pedale = p.frein[debut : fin + 1]
        if pedale.size > largeur:
            pire = max(pire, float((pedale[:-largeur] - pedale[largeur:]).max()))
    return pire


def _creux_gaz(p: Passage, depart: int | None, fin: int) -> float:
    """Le plus grand recul de l'accélérateur pendant la remise des gaz.

    Le premier extremum ne compte pas : dans une chicane, le pied peut arriver au
    dernier virage encore enfoncé, et le lever à cet endroit fait partie du geste.
    """
    if depart is None or fin - depart < 3:
        return 0.0
    gaz = p.gaz[depart:fin]
    plein = np.flatnonzero(gaz >= GAZ_PLEIN)
    if plein.size:
        gaz = gaz[: plein[0] + 1]
    extrema = _zigzag(gaz, BRUIT_GAZ)
    pire = 0.0
    for avant, bas, apres in zip(extrema[1:], extrema[2:], extrema[3:]):
        recul = float(gaz[avant] - gaz[bas])
        if recul > 0 and gaz[apres] - gaz[bas] >= REPRISE_MINIMALE * recul:
            pire = max(pire, recul)
    return pire


def _correction(p: Passage, c: SeuilsCoach) -> float:
    """Le plus grand retour de volant à contresens du virage.

    Un virage propre, c'est un seul aller-retour : le braquage monte jusqu'à son
    maximum puis redescend. Tout mouvement inverse avant ou après ce maximum est une
    correction. La vitesse sépare le rattrapage d'un ajustement tranquille de
    trajectoire, comme dans la longue courbe de la Parabolique.
    """
    largeur = int(round(LISSAGE_VOLANT / _pas(p)))
    pire = 0.0
    for virage in p.zone.virages:
        portion = p.bornes(virage.debut, virage.fin)
        if portion.stop - portion.start < 5:
            continue
        volant = _lisser(p.volant[portion], largeur)
        # Le volant est positif à droite, le sens du virage positif à gauche.
        braquage = volant * (-virage.sens if virage.sens else 1.0)
        extrema = _zigzag(braquage, c.bruit_volant)
        niveaux = braquage[extrema]
        sommet = int(np.argmax(niveaux))
        temps = p.temps[portion][extrema]
        for j in range(1, len(extrema)):
            ecart = float(niveaux[j] - niveaux[j - 1])
            contresens = ecart < 0 if j <= sommet else ecart > 0
            duree = float(temps[j] - temps[j - 1])
            if contresens and duree > 0 and abs(ecart) / duree >= c.vitesse_correction:
                pire = max(pire, abs(ecart))
    return pire


def mesurer(
    passage: Passage,
    echelle_roues: np.ndarray | None = None,
    coach: SeuilsCoach = SeuilsCoach(),
    virages: SeuilsVirage = SeuilsVirage(),
) -> Mesures:
    """Relève tout ce qui peut se mesurer sur un passage."""
    p = passage
    dernier = p.zone.virages[-1]
    portion = p.bornes(dernier.debut, dernier.fin)
    if portion.stop <= portion.start:
        portion = slice(0, p.temps.size)
    apex = portion.start + int(np.argmin(p.vitesse[portion]))

    # Le frein qui suit le point le plus lent appartient au virage d'après.
    tous = _freinages(p, virages.frein)
    freinages = [f for f in tous if f[0] <= apex]
    suivants = [f[0] for f in tous if f[0] > apex]

    # Dans une chicane, on n'attend pas les gaz entre les deux moitiés : la sortie
    # se juge sur le dernier virage.
    depart = max(freinages[-1][1], portion.start) if freinages else None
    if depart == p.temps.size:
        depart = None  # le freinage court jusqu'au bout de la zone : pas de sortie à juger
    fin_sortie = suivants[0] if suivants else p.temps.size

    blocage = avant = patinage = None
    if p.roues is not None:
        blocage, avant, patinage = glissements(
            p, np.ones(4) if echelle_roues is None else echelle_roues, coach
        )
    return Mesures(
        roue_libre_avant=_roue_libre_avant(p, freinages, virages),
        roue_libre_virage=_roue_libre_virage(p, depart, virages),
        chute_frein=_chute_frein(p, freinages, coach.fenetre_chute),
        creux_gaz=_creux_gaz(p, depart, fin_sortie),
        correction=_correction(p, coach),
        blocage=blocage,
        blocage_avant=True if avant is None else avant,
        patinage=patinage,
    )


# ----------------------------------------------------------------------
# Constats
# ----------------------------------------------------------------------


def constats(m: Mesures, virage: str, c: SeuilsCoach = SeuilsCoach()) -> list[Constat]:
    """Ce qui dépasse les seuils, le plus important d'abord.

    L'ordre vient de ce que chaque faute coûte sur les tours du pilote : 0,2 s pour la
    roue libre avant le frein, autour de 0,1 s pour une correction et pour des gaz
    hésitants. La correction passe devant, parce qu'elle explique souvent le lever de
    pied qui la suit. Rien de mesurable pour le frein brutal et la roue libre en virage,
    qui viennent donc après (voir docs/15-moteur-de-conseils.md). Le blocage et le
    patinage ne se voient pas dans les fichiers : leur rang est un choix.

    Un seuil à zéro désactive son détecteur.
    """
    trouves: list[Constat] = []

    def relever(code: str, mesure: float | None, seuil: float, cle: str, **valeurs) -> None:
        if mesure is not None and seuil > 0 and mesure >= seuil:
            trouves.append(Constat(code, Message(cle, {"virage": virage, **valeurs})))

    relever(
        "blocage",
        m.blocage,
        c.blocage,
        "coach.blocage_avant" if m.blocage_avant else "coach.blocage_arriere",
    )
    relever(
        "roue_libre_avant",
        m.roue_libre_avant,
        c.roue_libre_avant,
        "coach.roue_libre_avant",
        duree=round(m.roue_libre_avant, 1),
    )
    relever("correction", m.correction, c.correction, "coach.correction")
    relever("patinage", m.patinage, c.patinage, "coach.patinage")
    relever("gaz_hesitant", m.creux_gaz, c.creux_gaz, "coach.gaz_hesitant")
    relever("frein_brutal", m.chute_frein, c.chute_frein, "coach.frein_brutal")
    relever(
        "roue_libre_virage",
        m.roue_libre_virage,
        c.roue_libre_virage,
        "coach.roue_libre_virage",
        duree=round(m.roue_libre_virage, 1),
    )
    return trouves
