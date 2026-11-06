"""Reconstruction de la géométrie de la piste à partir des tours enregistrés.

Sert à dessiner une vue rapprochée de la route, sur laquelle on compare les
trajectoires de deux tours au même endroit.

--------------------------------------------------------------------------
Ce que le jeu fournit, et ce qu'il faut en déduire
--------------------------------------------------------------------------

Trois canaux, tous à 10 Hz :

* `GPS Latitude` / `GPS Longitude` : la position de la voiture. Les coordonnées
  sont locales et fictives (origine vers 60°N, 0°E), mais la forme est juste.
* `Path Lateral` : l'écart de la voiture à l'axe de la piste, en mètres, signé.
* `Track Edge` : **la position latérale du bord de piste DU CÔTÉ OÙ SE TROUVE
  LA VOITURE**, dans le même repère que `Path Lateral`.

Cette dernière sémantique n'est documentée nulle part ; elle a été établie en
mesurant. Au même endroit du circuit, deux tours passant du même côté donnent
la même valeur à 9 mm près ; deux tours passant de côtés opposés donnent des
valeurs distantes de 10,5 m. Et le signe de `Track Edge` suit celui de
`Path Lateral` dans 100 % des cas.

Conséquence pratique : un seul tour ne renseigne qu'UN bord, celui de son côté.
Deux tours qui se croisent en renseignent deux. On rassemble donc ce que
plusieurs tours ont vu, et on ne dessine que les bords réellement mesurés.

--------------------------------------------------------------------------
Reconstruire l'axe de la piste
--------------------------------------------------------------------------

La position GPS est celle de la VOITURE, pas de l'axe. L'axe s'obtient en
retirant l'écart latéral, perpendiculairement au sens de marche :

    axe(d) = position(d) - Path Lateral(d) × normale(d)

La normale dépend de la direction de l'axe, qu'on ne connaît pas encore : on
part de la direction de la trajectoire, on en déduit un premier axe, puis on
recommence. Deux passes suffisent.

Contrôle intégré : deux tours qui prennent des trajectoires DIFFÉRENTES doivent
donner le MÊME axe. C'est ce que vérifie `ecart_axes`, et c'est ce qui prouve
que la reconstruction est juste.

--------------------------------------------------------------------------
Pourquoi les sorties de piste sont écartées
--------------------------------------------------------------------------

L'axe est la moyenne de ce que chaque tour en déduit. Un tour parti dans le
dégagement fausse donc cette moyenne, et pas qu'un peu.

Cas mesuré, sortie de la première chicane de Monza : sur quatre tours d'une
session, UN SEUL a un `Path Lateral` qui descend à −31,4 m — la piste en fait
10 de large. Ce tour tire l'axe moyen de plus de 8 m sur une vingtaine de
mètres. Ailleurs, les axes reconstruits par deux sessions différentes
coïncident à 0,31 m près en médiane ; là, ils s'écartent de 10,4 m.

Conséquence : la courbure calculée sur cet axe part dans tous les sens — le cap
tourne de 48° par mètre —, ce qui fabrique un virage qui n'existe pas et soude
la chicane à la courbe suivante. La même session donnait 7 virages à Monza
quand les autres en donnaient 8.

Les échantillons hors piste sont donc écartés, tour par tour. Le canal qui les
signale vient de `SurfaceTypes`, la réponse du jeu lui-même (voir
`donnees_tour._ajouter_hors_piste`).

Une règle plus simple avait été essayée d'abord — être hors piste, c'est avoir
`|Path Lateral| > |Track Edge|`, deux canaux déjà chargés. Elle a été écartée
après mesure : sur 106 000 échantillons, elle signale 3,2 % du temps contre
0,84 % pour `SurfaceTypes`, soit une précision de 23 %. Elle attrape en fait
les VIBREURS, qui débordent du bord de piste sans être hors piste. Rouler sur
un vibreur est normal et ne déplace l'axe que d'un mètre ou deux : l'exclure
aurait retiré de la donnée saine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .donnees_tour import DonneesTour

#: Mètres par degré de latitude. Les coordonnées du jeu sont fictives mais
#: suivent une projection classique : sans le cos(latitude) sur la longitude,
#: le circuit serait étiré dans un sens.
METRES_PAR_DEGRE = 111_320.0

#: Longueur (m) sur laquelle on lisse avant de calculer une direction.
#:
#: La position GPS est quantifiée à 0,42 m : sur une base trop courte, la
#: direction n'est que du bruit. Sur 11 m, l'erreur d'angle tombe sous 2,5°,
#: et le virage le plus serré de Monza (rayon ~25 m) ne tourne que de 25° sur
#: cette longueur — assez peu pour que la normale reste juste.
LISSAGE_DIRECTION = 11.0

#: Marge (m) ajoutée de part et d'autre d'une sortie de piste avant de l'écarter.
#:
#: La direction de l'axe se calcule sur une base lissée de `LISSAGE_DIRECTION`
#: mètres : une position fausse contamine donc l'orientation jusqu'à une
#: demi-fenêtre de chaque côté, et l'axe est calculé en deux passes. On élargit
#: donc d'une fenêtre entière, ce qui couvre largement les deux passes.
MARGE_HORS_PISTE = 11.0

#: Au-delà de ce multiple de la demi-largeur typique du circuit, une mesure de
#: bord n'est pas le bord de la piste et n'est pas retenue.
#:
#: `Track Edge` donne la limite de la surface roulable, qui s'ouvre parfois sur
#: autre chose que la piste. Cas réel à la sortie de l'épingle de Long Beach :
#: le bord droit passe de 6,5 m à 21,9 m sur une dizaine de mètres, puis
#: revient — l'entrée de la voie des stands. La route s'y dessinait sur 28 m de
#: large.
#:
#: Le seuil est calé sur les neuf tracés enregistrés. Au-delà de 2,5 fois la
#: demi-largeur, on ne trouve QUE ce pic de Long Beach (3,3 fois), soit 0,08 %
#: des mesures de ce circuit et aucune ailleurs. Les vrais élargissements
#: restent en dessous : l'épingle de Long Beach s'évase à 1,9 fois.
FACTEUR_BORD_ABERRANT = 2.5


@dataclass(frozen=True)
class Geometrie:
    """Géométrie d'une portion de circuit, en mètres, sur l'axe de distance."""

    distance: np.ndarray
    """Axe de distance commun, en mètres depuis la ligne."""

    axe: np.ndarray
    """Axe de la piste, tableau (n, 2) de coordonnées x, y en mètres."""

    normale: np.ndarray
    """Vecteur unitaire perpendiculaire à l'axe, tableau (n, 2)."""

    bord_gauche: np.ndarray
    """Bord de piste côté négatif, (n, 2)."""

    bord_droit: np.ndarray
    """Bord de piste côté positif, (n, 2)."""

    mesure: np.ndarray
    """Par point : True si les DEUX bords ont été réellement mesurés.

    Ailleurs, le bord du côté où aucun tour n'est passé est estimé en
    interpolant ses propres mesures, prises avant et après. C'est une
    estimation, pas une mesure, et l'interface la dessine différemment.
    """

    largeur_mediane: float
    """Largeur de piste médiane réellement mesurée, en mètres."""

    ecart_axes: float
    """Dispersion des axes reconstruits séparément par chaque tour.

    C'est le contrôle de la reconstruction : des tours de trajectoires
    différentes doivent retrouver le même axe. Une valeur de l'ordre du
    décimètre valide la méthode ; plusieurs mètres l'invalideraient.
    """

    mesure_gauche: np.ndarray | None = None
    """Par point : True si le bord GAUCHE a été réellement longé."""

    mesure_droit: np.ndarray | None = None
    """Par point : True si le bord DROIT a été réellement longé.

    Distinct de `mesure`, qui exige les deux. Un bord longé doit s'afficher
    comme mesuré même quand l'autre ne l'est pas : dans l'épingle de Long
    Beach, le bord extérieur, bel et bien mesuré, s'affichait en pointillé
    parce que personne n'était passé à l'intérieur.
    """

    @property
    def part_mesuree(self) -> float:
        """Proportion de l'axe où les deux bords sont réellement mesurés."""
        return float(self.mesure.mean())


def positions(tour: DonneesTour) -> np.ndarray:
    """Position de la voiture en mètres, sur la grille de distance du tour."""
    lat = tour.canal("GPS Latitude")
    lon = tour.canal("GPS Longitude")
    # Un seul cosinus pour tout le circuit : sur 5 km, la latitude varie de
    # 0,02°, ce qui change l'échelle de 3 dix-millièmes.
    k = math.cos(math.radians(float(np.mean(lat))))
    return np.column_stack([lon * METRES_PAR_DEGRE * k, lat * METRES_PAR_DEGRE])


def _lisser(valeurs: np.ndarray, fenetre: int) -> np.ndarray:
    """Moyenne glissante centrée, sans décalage."""
    if fenetre < 3:
        return valeurs
    fenetre |= 1  # impair, pour rester centré
    noyau = np.ones(fenetre) / fenetre
    marge = fenetre // 2
    sortie = np.empty_like(valeurs)
    for colonne in range(valeurs.shape[1]):
        etendu = np.pad(valeurs[:, colonne], marge, mode="edge")
        sortie[:, colonne] = np.convolve(etendu, noyau, mode="valid")
    return sortie


def _normales(points: np.ndarray, pas: float) -> np.ndarray:
    """Vecteurs unitaires perpendiculaires au chemin, tournés vers la droite."""
    lisses = _lisser(points, int(round(LISSAGE_DIRECTION / pas)))
    tangente = np.column_stack(
        [np.gradient(lisses[:, 0]), np.gradient(lisses[:, 1])]
    )
    norme = np.hypot(tangente[:, 0], tangente[:, 1])
    norme[norme == 0] = 1.0
    tangente /= norme[:, None]
    # Rotation de -90° : (x, y) -> (y, -x)
    return np.column_stack([tangente[:, 1], -tangente[:, 0]])


def _sur_piste(tour: DonneesTour, distance: np.ndarray) -> np.ndarray:
    """Par point de l'axe de distance : ce tour était-il utilisable ici ?

    False là où au moins une roue était hors piste, plus une marge de part et
    d'autre parce que la direction se calcule sur une base lissée.

    Sans le canal — vieille session, ou canal absent d'une future version du
    jeu —, tout est considéré comme utilisable : on retrouve le comportement
    d'avant, ce qui vaut mieux que de tout écarter.
    """
    from .donnees_tour import CANAL_HORS_PISTE

    if CANAL_HORS_PISTE not in tour.canaux or distance.size == 0:
        return np.ones(distance.shape, dtype=bool)

    dehors = tour.sur_distance(distance)[CANAL_HORS_PISTE] > 0.5
    pas = float(distance[1] - distance[0]) if len(distance) > 1 else 1.0
    marge = max(1, int(round(MARGE_HORS_PISTE / pas)))

    # Portion plus courte que la dilatation elle-même : `np.convolve` en mode
    # « same » rendrait alors un tableau de la taille du NOYAU, pas de l'entrée,
    # et le masque ne serait plus alignable. Sur si peu de points, tout ou rien
    # est de toute façon la seule réponse sensée.
    if dehors.size <= 2 * marge:
        return np.full(distance.shape, not dehors.any())

    # Dilatation : une convolution sur un masque booléen suffit, et évite une
    # dépendance à scipy pour trois lignes.
    elargi = np.convolve(dehors.astype(float), np.ones(2 * marge + 1), mode="same") > 0
    return ~elargi


def _moyenne_valide(valeurs: np.ndarray, valides: np.ndarray) -> np.ndarray:
    """Moyenne des tours, point par point, en ne comptant que les tours valides.

    `valeurs` est de forme (tours, points, 2), `valides` de forme (tours,
    points). Là où AUCUN tour n'est valide — une sortie prise par tout le monde
    au même endroit —, on retombe sur la moyenne de tous : un axe approximatif
    reste préférable à un trou.
    """
    poids = valides.astype(float)
    orphelins = poids.sum(axis=0) == 0
    poids[:, orphelins] = 1.0
    return (valeurs * poids[:, :, None]).sum(axis=0) / poids.sum(axis=0)[:, None]


def _axe_dun_tour(
    tour: DonneesTour, distance: np.ndarray, signe: float
) -> tuple[np.ndarray, np.ndarray]:
    """Axe de piste et normale déduits d'un seul tour.

    `signe` fixe l'orientation de `Path Lateral` par rapport à la normale : la
    convention du jeu n'est pas documentée, on l'établit en comparant les deux
    possibilités (voir `construire`).
    """
    valeurs = tour.sur_distance(distance)
    xy = np.column_stack(
        [
            valeurs["GPS Longitude"],
            valeurs["GPS Latitude"],
        ]
    )
    k = math.cos(math.radians(float(np.mean(valeurs["GPS Latitude"]))))
    xy = np.column_stack([xy[:, 0] * METRES_PAR_DEGRE * k, xy[:, 1] * METRES_PAR_DEGRE])

    pas = float(distance[1] - distance[0])
    lateral = valeurs["Path Lateral"] * signe

    normale = _normales(xy, pas)
    for _ in range(2):  # deux passes : l'axe affine la normale, qui affine l'axe
        axe = xy - lateral[:, None] * normale
        normale = _normales(axe, pas)
    return xy - lateral[:, None] * normale, normale


def construire(tours: list[DonneesTour], distance: np.ndarray) -> Geometrie:
    """Reconstruit la géométrie de la piste à partir d'un ou plusieurs tours.

    Plus il y a de tours, plus les deux bords sont renseignés : chaque tour ne
    renseigne que celui de son côté.
    """
    if not tours:
        raise ValueError("il faut au moins un tour pour reconstruire la piste")

    # Les passages hors piste faussent l'axe : on repère une fois pour toutes
    # où chaque tour est exploitable. Le masque ne dépend pas du signe testé
    # plus bas, on ne le calcule donc qu'une fois.
    valides = np.stack([_sur_piste(t, distance) for t in tours])

    # La convention de signe de `Path Lateral` n'est pas documentée. On essaie
    # les deux, et on garde celle qui rapproche le plus les axes déduits des
    # différents tours — le bon signe les fait coïncider, le mauvais les écarte
    # du double de l'écart latéral.
    meilleur = None
    for signe in (1.0, -1.0):
        essais = [_axe_dun_tour(t, distance, signe) for t in tours]
        axes = np.stack([a for a, _ in essais])
        moyen = _moyenne_valide(axes, valides)
        # La dispersion se mesure sur les seuls échantillons retenus : sinon
        # une sortie de piste la ferait exploser et le choix du signe se
        # jouerait sur du bruit.
        ecarts = np.hypot(*(axes - moyen).transpose(2, 0, 1))[valides]
        ecart = float(np.median(ecarts)) if ecarts.size else float("nan")
        if meilleur is None or ecart < meilleur[0]:
            meilleur = (ecart, signe, essais)

    ecart, signe, essais = meilleur
    axe = _moyenne_valide(np.stack([a for a, _ in essais]), valides)
    normale = _normales(axe, float(distance[1] - distance[0]))

    # Chaque tour ne renseigne que le bord de SON côté : on prend l'extrême de
    # chaque côté parmi ce que les tours ont réellement vu.
    #
    # Les échantillons hors piste sont écartés ici aussi : `Track Edge` y donne
    # le bord vu depuis le dégagement, du mauvais côté. Mesuré au même endroit
    # de Monza : −4,4 m sur le tour sorti contre +5,6 m sur les trois autres.
    gauche = np.full(distance.shape, np.nan)
    droit = np.full(distance.shape, np.nan)
    bords = [tour.sur_distance(distance)["Track Edge"] * signe for tour in tours]
    # Demi-largeur typique : la médiane des distances au bord mesurées, tous
    # tours et deux côtés confondus. Sert de référence pour écarter les
    # mesures aberrantes (voir FACTEUR_BORD_ABERRANT).
    distances_bord = np.abs(np.concatenate(bords))
    distances_bord = distances_bord[np.isfinite(distances_bord)]
    demi_typique = float(np.median(distances_bord)) if distances_bord.size else np.inf
    for bord, utilisable in zip(bords, valides):
        plausible = utilisable & (np.abs(bord) <= FACTEUR_BORD_ABERRANT * demi_typique)
        cote_gauche = plausible & (bord < 0)
        cote_droit = plausible & (bord >= 0)
        gauche[cote_gauche] = np.fmin(gauche[cote_gauche], bord[cote_gauche])
        droit[cote_droit] = np.fmax(droit[cote_droit], bord[cote_droit])

    mesure_gauche = ~np.isnan(gauche)
    mesure_droit = ~np.isnan(droit)
    mesure = mesure_gauche & mesure_droit
    largeur = float(np.median((droit - gauche)[mesure])) if mesure.any() else 12.0

    # Là où un bord n'a pas été longé — le cas le plus fréquent, puisqu'on
    # reste du même côté sur une trajectoire de course —, on l'estime à partir
    # de SES PROPRES mesures, prises avant et après.
    #
    # Première version : on le déduisait de l'AUTRE bord, en reportant la
    # largeur de piste. Il copiait donc tous les accidents du bord longé. Cas
    # réel de l'épingle de Long Beach : au sommet, le bord extérieur s'écarte de
    # 6 m — les deux tours donnent la même valeur, l'épingle s'évase —, et le
    # bord intérieur, que personne n'avait longé, se trouvait tiré de 6 m vers
    # la trajectoire, dessinant une encoche en travers de la route. Les deux
    # bords d'une route sont indépendants : chacun suit les siens.
    indices = np.arange(len(distance), dtype=float)
    gauche_complet = _completer(gauche, indices)
    droit_complet = _completer(droit, indices)

    # Un bord jamais longé sur tout le tour — un seul tour fourni, par exemple —
    # n'a aucune mesure à interpoler : on se rabat alors sur la largeur.
    if gauche_complet is None and droit_complet is None:
        gauche_complet = np.full(distance.shape, -largeur / 2)
        droit_complet = np.full(distance.shape, largeur / 2)
    elif gauche_complet is None:
        gauche_complet = droit_complet - largeur
    elif droit_complet is None:
        droit_complet = gauche_complet + largeur

    return Geometrie(
        distance=distance,
        axe=axe,
        normale=normale,
        bord_gauche=axe + gauche_complet[:, None] * normale,
        bord_droit=axe + droit_complet[:, None] * normale,
        mesure=mesure,
        largeur_mediane=largeur,
        ecart_axes=ecart,
        mesure_gauche=mesure_gauche,
        mesure_droit=mesure_droit,
    )


def _completer(bord: np.ndarray, indices: np.ndarray) -> np.ndarray | None:
    """Comble les trous d'un bord en interpolant entre ses propres mesures.

    Le tour est une BOUCLE : un trou qui chevauche la ligne se comble entre la
    dernière mesure du tour et la première, et non en figeant la valeur du
    bout. D'où les copies décalées d'un tour de part et d'autre.

    Renvoie None si le bord n'a jamais été mesuré.
    """
    connu = ~np.isnan(bord)
    if not connu.any():
        return None
    n = len(bord)
    x = indices[connu]
    y = bord[connu]
    return np.interp(
        indices,
        np.concatenate([x - n, x, x + n]),
        np.concatenate([y, y, y]),
    )
