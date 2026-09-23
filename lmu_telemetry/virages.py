"""Découpage d'un circuit en virages, et métriques de pilotage par virage.

--------------------------------------------------------------------------
Pourquoi la courbure de la piste, et rien d'autre
--------------------------------------------------------------------------

Le brief proposait de détecter les virages au seuil d'accélération latérale, ou
à l'angle volant. Les deux ont été essayés et écartés, après mesure :

* `G Force Lat` n'est qu'à **10 Hz**, trop lent pour délimiter proprement une
  entrée de virage.
* `Steering Pos` est en **pourcentage de braquage**, donc dépend de la
  démultiplication de la direction — donc de la voiture. Un seuil dessus donnait
  8 virages sur une session et 9 sur une autre du même circuit, et confondait la
  Curva Grande avec la première chicane de Monza selon la catégorie.

On détecte donc sur la **courbure de l'axe de la piste**, reconstruit par
`piste.py`. C'est une propriété du CIRCUIT : elle ne dépend ni de la voiture, ni
du tour, ni du pilote.

Un virage par apex, comme sur les cartes officielles : les deux moitiés d'une
chicane sont deux virages. À Monza, la détection retrouve exactement les onze
virages de la numérotation officielle, de la Variante del Rettifilo (T1-T2) à
la Parabolica (T11). Sur trois sessions par tracé, le nombre de virages est
identique pour Monza, sa variante Curva Grande, Spa, Fuji et Long Beach ;
Portimão varie d'un virage. Voir docs/08-numerotation.md.

Cette stabilité suppose que l'axe de la piste soit propre. Elle a été mise en
défaut par un tour parti dans le dégagement, qui faussait l'axe de 8 m sur une
vingtaine de mètres. Les sorties de piste sont depuis écartées de la
reconstruction : voir `piste.py` et docs/07-sorties-de-piste.md.

--------------------------------------------------------------------------
Une définition par circuit, éditable
--------------------------------------------------------------------------

Les virages sont détectés UNE FOIS par circuit et enregistrés dans un fichier
JSON modifiable à la main. Deux raisons :

1. Comparer deux tours virage par virage n'a de sens que si les bornes sont les
   mêmes pour les deux. Redétecter à chaque tour donnerait des colonnes qui ne
   se correspondent pas.
2. Aucune détection automatique n'est parfaite. Un circuit où deux virages
   s'enchaînent peut se découper en un ou en deux selon le réglage ; c'est au
   pilote de trancher, pas à l'outil.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .donnees_tour import DonneesTour
from .errors import ErreurTelemetrie
from .textes import Message
from .piste import construire

#: Rayon (m) en dessous duquel on parle de virage.
#:
#: À 400 m, la détection retrouve à Monza les onze virages officiels, Curva
#: Grande comprise — qui se passe à fond mais reste un virage qu'on peut mieux ou
#: moins bien négocier. Un seuil plus serré la ferait disparaître.
RAYON_MAXIMAL = 400.0

#: Longueur (m) sur laquelle la courbure est lissée avant d'être seuillée.
#: La position de l'axe porte 0,3 m de bruit ; sans lissage, la courbure n'est
#: que du bruit. Sur 15 m, le virage le plus serré de Monza (13 m de rayon) reste
#: parfaitement détecté.
LISSAGE_COURBURE = 15.0

#: Distance (m) en deçà de laquelle deux plages tournant DANS LE MÊME SENS
#: sont recollées en un seul virage.
#:
#: Le recollage ne joue jamais entre deux sens opposés : les deux moitiés d'une
#: chicane restent donc toujours distinctes, quelle que soit leur proximité.
ECART_FUSION = 40.0

#: Angle (degrés) qu'une portion de piste doit balayer pour compter comme un
#: virage.
#:
#: C'est l'ANGLE, pas la longueur. Un seuil en longueur se trompe des deux
#: côtés : à Portimão, un virage de 14 m de rayon qui tourne de 90° ne mesure
#: que 22 m et se faisait jeter par un seuil à 20 m ; à l'inverse, un coude de
#: 400 m de rayon long de 30 m ne tourne que 4° et passait pour un virage.
#:
#: Réglé à 15° par mesure, sur deux critères et dans cet ordre : que trois
#: sessions du même circuit donnent le MÊME nombre de virages, et que ce nombre
#: approche le compte officiel. À 15°, Monza donne 11 virages sur les trois
#: sessions essayées — exactement sa numérotation officielle. En dessous, un
#: frémissement de 12° à l'intérieur de la chicane la découpait en quatre sur
#: une session sur trois. Voir docs/08-numerotation.md.
ANGLE_MINIMAL = 15.0

#: Longueur (m) en dessous de laquelle ce qu'on nous donne n'est pas un tour.
#: Sert de garde-fou : un « tour » de quelques mètres fait échouer la
#: reconstruction de la géométrie avec une erreur incompréhensible.
LONGUEUR_TOUR_MINIMALE = 100.0

#: Distance maximale remontée en amont d'un virage pour y chercher le freinage.
REMONTEE_FREINAGE = 350.0

#: Distance conservée en aval pour observer la sortie.
PROLONGEMENT_SORTIE = 100.0

#: Seuils de pédale, en pourcentage de course.
SEUIL_FREIN = 3.0
SEUIL_GAZ = 15.0

#: En dessous de ces deux valeurs, la voiture roule sur son erre : c'est le
#: « coasting », révélateur chez les débutants d'après le brief.
SEUIL_COASTING_FREIN = 3.0
SEUIL_COASTING_GAZ = 5.0

#: Remarque « pris sans freiner » : la page l'affiche comme une étiquette dans
#: la case du virage, et non comme une remarque, d'où une clé nommée.
SANS_FREINER = "serveur.virage.sans_freiner"


@dataclass(frozen=True)
class Virage:
    """Un virage, délimité par deux distances depuis la ligne."""

    numero: int
    debut: float
    fin: float
    rayon_min: float
    nom: str = ""

    sens: int = 0
    """+1 à gauche, -1 à droite, 0 si on ne sait pas (ancien fichier)."""

    chicane: bool = False
    """Obsolète, toujours False : gardé pour relire les anciens fichiers.

    Les premières versions détectaient une chicane comme UN virage et le
    signalaient ici. Depuis le découpage par apex, ses deux moitiés sont deux
    virages distincts, chacun dans son sens.
    """

    @property
    def longueur(self) -> float:
        return self.fin - self.debut

    @property
    def sens_libelle(self) -> str:
        if self.chicane:
            return "chicane"
        return {1: "gauche", -1: "droite"}.get(self.sens, "")

    @property
    def libelle(self) -> str:
        """« T3 », ou « T3 — Curva Grande » si un nom a été écrit à la main.

        Le numéro passe devant : c'est lui qui sert à se repérer d'un tableau à
        l'autre et à parler d'un virage sans ambiguïté. Aucun nom n'est posé
        automatiquement.
        """
        return f"T{self.numero}" + (f" — {self.nom}" if self.nom else "")


@dataclass(frozen=True)
class DefinitionCircuit:
    """Le découpage d'un circuit en virages."""

    circuit: str
    longueur: float
    virages: tuple[Virage, ...]
    automatique: bool = True
    """False dès que le fichier a été retouché à la main."""

    # ------------------------------------------------------------------

    def enregistrer(self, chemin: Path) -> None:
        """Écrit le fichier d'un seul bloc.

        On écrit d'abord à côté, puis on remplace : un arrêt en pleine écriture
        laisserait sinon un fichier tronqué, que `lire` refuserait ensuite, et
        le découpage — peut-être retouché à la main — serait perdu.
        """
        chemin.parent.mkdir(parents=True, exist_ok=True)
        provisoire = chemin.with_suffix(chemin.suffix + ".tmp")
        provisoire.write_text(
            json.dumps(
                {
                    "circuit": self.circuit,
                    "longueur": round(self.longueur, 1),
                    "automatique": self.automatique,
                    "_aide": (
                        "Distances en mètres depuis la ligne de départ. "
                        "Ce fichier est fait pour être modifié à la main : "
                        "ajuste debut/fin, donne un nom aux virages, ou "
                        "supprime ceux qui ne t'intéressent pas. Mets "
                        "\"automatique\" à false pour que l'outil ne le "
                        "regénère jamais."
                    ),
                    "virages": [
                        {
                            "numero": v.numero,
                            "nom": v.nom,
                            "debut": round(v.debut, 1),
                            "fin": round(v.fin, 1),
                            "rayon_min": round(v.rayon_min, 1),
                            "sens": v.sens,
                            "chicane": v.chicane,
                        }
                        for v in self.virages
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(provisoire, chemin)

    @classmethod
    def lire(cls, chemin: Path) -> "DefinitionCircuit":
        """Relit un fichier de définition, retouché à la main ou non.

        Une retouche maladroite — une virgule oubliée, un champ effacé, un
        nombre écrit « 120 m » — donne un message qui désigne le fichier, et
        non une erreur Python incompréhensible.
        """
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
            return cls(
                circuit=brut["circuit"],
                longueur=float(brut["longueur"]),
                automatique=bool(brut.get("automatique", True)),
                virages=tuple(
                    Virage(
                        numero=int(v["numero"]),
                        nom=v.get("nom", ""),
                        debut=float(v["debut"]),
                        fin=float(v["fin"]),
                        rayon_min=float(v.get("rayon_min", 0.0)),
                        # Absents des fichiers écrits avant l'ajout du sens : un
                        # ancien fichier reste lisible, simplement sans cette
                        # information, jusqu'à la prochaine redétection.
                        sens=int(v.get("sens", 0)),
                        chicane=bool(v.get("chicane", False)),
                    )
                    for v in sorted(brut["virages"], key=lambda v: float(v["debut"]))
                ),
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as erreur:
            detail = f"{type(erreur).__name__}: {erreur}"
            raise ErreurTelemetrie.de(
                "serveur.erreur.virages_illisible", chemin=str(chemin), detail=detail
            ) from erreur


def fichier_definition(dossier: Path, circuit: str) -> Path:
    """Chemin du fichier de définition d'un circuit."""
    propre = re.sub(r"[^\w\- ]", "", circuit).strip() or "circuit"
    return dossier / f"{propre}.json"


# ----------------------------------------------------------------------
# Détection
# ----------------------------------------------------------------------


def _lisser(valeurs: np.ndarray, fenetre: int) -> np.ndarray:
    fenetre = max(1, fenetre) | 1
    marge = fenetre // 2
    return np.convolve(
        np.pad(valeurs, marge, mode="edge"), np.ones(fenetre) / fenetre, mode="valid"
    )


def courbure_signee(axe: np.ndarray, pas: float = 1.0) -> np.ndarray:
    """Courbure de l'axe de piste, en 1/m, SIGNÉE.

    Positive à gauche, négative à droite. Les coordonnées ont x vers l'est et
    y vers le nord, et la distance croît dans le sens de marche : le cap tourne
    donc dans le sens trigonométrique quand la piste va à gauche.

    Vérifié sur deux virages de Monza dont le sens ne fait aucun doute : la
    Variante del Rettifilo sort en droite puis gauche, et la Curva Grande est
    une droite. C'est bien ce que donne cette convention.
    """
    fenetre = int(round(LISSAGE_COURBURE / pas))
    lisse = np.column_stack(
        [_lisser(axe[:, 0], fenetre), _lisser(axe[:, 1], fenetre)]
    )
    cap = np.unwrap(np.arctan2(np.gradient(lisse[:, 1]), np.gradient(lisse[:, 0])))
    return _lisser(np.gradient(cap) / pas, fenetre)


def courbure(axe: np.ndarray, pas: float = 1.0) -> np.ndarray:
    """Courbure de l'axe de piste, en 1/m. Son inverse est le rayon.

    C'est la valeur absolue : pour la détection des virages, seule l'intensité
    compte. Le sens sert ensuite à qualifier chaque virage.
    """
    return np.abs(courbure_signee(axe, pas))


def _sens_et_chicane(signee: np.ndarray) -> dict:
    """Sens d'un virage : celui dans lequel la piste tourne au total.

    C'est le signe de l'angle balayé sur toute la zone, et non celui du point
    le plus serré : un frémissement de l'axe peut être très courbé sans rien
    changer à la direction générale du virage.

    `chicane` vaut toujours False. Depuis le découpage par apex, les deux
    moitiés d'une chicane sont deux virages distincts : un virage ne change
    plus de sens. Le champ n'est gardé que pour relire les fichiers écrits
    avant. Constaté sur 138 virages de 9 tracés : un seul restait marqué
    chicane — le T1 de Portimão, un virage à droite traversé par un frémissement
    de l'axe, qui s'affichait sans flèche.
    """
    if signee.size == 0:
        return {"sens": 0, "chicane": False}
    total = float(signee.sum())
    return {"sens": 1 if total > 0 else -1 if total < 0 else 0, "chicane": False}


def _angle_balaye(signee: np.ndarray, a: int, b: int, pas: float) -> float:
    """Angle total (degrés) dont la piste tourne entre deux indices."""
    return abs(float(np.degrees(np.sum(signee[a:b]) * pas)))


def _apex(
    signee: np.ndarray, seuil: float, ecart: int, pas: float = 1.0
) -> list[tuple[int, int]]:
    """Découpe en virages au sens des circuits : un par changement de direction.

    C'est la numérotation qu'emploient les organisateurs et les cartes de
    circuit : à Monza, la Variante del Rettifilo compte pour DEUX virages (1 et
    2), la Variante Ascari pour TROIS (8, 9 et 10). Chaque apex a son numéro,
    parce que chacun se pilote à part — on freine pour l'un et on ressort de
    l'autre.

    On découpe d'abord la piste en plages de sens constant, puis on alterne
    deux opérations jusqu'à ce que plus rien ne bouge :

    * **recoller** deux plages voisines qui tournent dans le même sens, si
      elles sont séparées de moins de `ecart` ;
    * **jeter** les plages qui ne tournent pas assez pour être un virage.

    --- Pourquoi alterner, et pas faire l'un puis l'autre ---

    Les deux ordres simples ratent chacun un cas réel.

    *Trier d'abord* : un virage doux dont la courbure oscille autour du seuil
    se fragmente en morceaux de même sens, chacun sous `ANGLE_MINIMAL`. Tous
    sont jetés, et le virage disparaît alors que son angle total dépasse
    largement le seuil. Cas de Long Beach, à 62 m de la ligne : 21 à 23° de
    virage, détecté dans une session sur trois seulement.

    *Recoller d'abord* : un frémissement de l'axe dans un virage serré produit
    une bribe de sens OPPOSÉ, qui sépare le virage en deux morceaux non
    voisins, donc impossibles à recoller. La chicane de Monza donnait alors
    quatre virages au lieu de deux sur une session sur trois.

    En alternant, le recollage réunit les fragments d'un virage doux, et le tri
    fait disparaître la bribe parasite — ce qui rend voisins les deux morceaux
    qui l'encadraient, recollés au tour suivant. Mesuré sur trois sessions par
    tracé : quatre tracés instables sur six avec l'un ou l'autre ordre, un seul
    en alternant, sans qu'aucun ne change de nombre de virages.

    Le recollage ne joue QUE dans le même sens : deux moitiés de chicane
    restent toujours séparées, quelle que soit leur proximité. C'est tout
    l'objet de ce découpage.
    """
    actif = np.abs(signee) > seuil
    sens = np.where(actif, np.sign(signee), 0).astype(np.int8)

    changements = np.nonzero(np.diff(sens))[0] + 1
    plages = [
        [a, b]
        for a, b in zip([0, *changements], [*changements, len(sens)])
        if sens[a]
    ]

    def recoller(entree: list[list[int]]) -> list[list[int]]:
        sortie: list[list[int]] = []
        for a, b in entree:
            if sortie and sens[a] == sens[sortie[-1][0]] and a - sortie[-1][1] <= ecart:
                sortie[-1][1] = b
            else:
                sortie.append([a, b])
        return sortie

    # Chaque tour de boucle fait strictement diminuer le nombre de plages, ou
    # s'arrête : la boucle termine toujours.
    while True:
        avant = len(plages)
        plages = recoller(plages)
        plages = [p for p in plages if _angle_balaye(signee, *p, pas) >= ANGLE_MINIMAL]
        plages = recoller(plages)
        if len(plages) == avant:
            break

    return [(a, b) for a, b in plages]


def detecter(
    tours: list[DonneesTour],
    rayon_maximal: float = RAYON_MAXIMAL,
    pas: float = 1.0,
) -> DefinitionCircuit:
    """Découpe un circuit en virages à partir de la courbure de sa piste."""
    if not tours:
        raise ErreurTelemetrie.de("serveur.erreur.decoupage_sans_tour")

    fin = min(t.longueur for t in tours)
    if fin < LONGUEUR_TOUR_MINIMALE:
        raise ErreurTelemetrie.de("serveur.erreur.decoupage_tours_courts", longueur=f"{fin:.0f}")
    distance = np.arange(0.0, fin, pas)
    geometrie = construire(tours, distance)
    signee = courbure_signee(geometrie.axe, pas)
    k = np.abs(signee)

    seuil = 1.0 / rayon_maximal
    plages = _apex(signee, seuil=seuil, ecart=int(round(ECART_FUSION / pas)), pas=pas)
    virages = tuple(
        Virage(
            numero=i,
            debut=float(distance[a]),
            fin=float(distance[min(b, len(distance) - 1)]),
            rayon_min=float(1.0 / k[a:b].max()),
            **_sens_et_chicane(signee[a:b]),
        )
        for i, (a, b) in enumerate(plages, 1)
    )
    # Le TRACÉ, pas le circuit : LMU propose plusieurs variantes du même
    # circuit, et elles n'ont pas les mêmes virages. « Monza Curva Grande
    # Circuit » fait 5 745 m et compte 9 virages, contre 5 780 m et 11 pour
    # « Autodromo Nazionale Monza » — la Variante del Rettifilo n'y est pas.
    # Les deux portent pourtant le même `TrackName`, et partageaient donc le
    # même fichier de découpage.
    return DefinitionCircuit(
        circuit=tours[0].info.trace, longueur=float(fin), virages=virages
    )


# ----------------------------------------------------------------------
# Métriques par virage
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class MetriquesVirage:
    """Ce qu'on mesure d'un virage sur un tour donné.

    Toutes les distances sont en mètres depuis la ligne, les vitesses en km/h,
    les durées en secondes. Un champ vaut None quand l'événement n'a pas eu lieu
    — pas de freinage du tout dans le virage, par exemple.
    """

    virage: Virage

    debut_freinage: float | None
    """Distance à laquelle le frein est touché pour la première fois."""

    distance_freinage: float | None
    """Mètres entre le début du freinage et l'entrée du virage."""

    vitesse_entree: float | None
    """Vitesse au moment où le frein est touché."""

    duree_freinage: float
    """Temps cumulé pédale de frein enfoncée."""

    frein_max: float
    """Pic de pression de frein, en pourcentage de course."""

    vitesse_min: float
    position_vitesse_min: float

    remise_gaz: float | None
    """Distance à laquelle l'accélérateur repasse durablement au-dessus du seuil."""

    vitesse_remise_gaz: float | None
    vitesse_sortie: float
    temps_coasting: float
    """Temps sans frein ni gaz : la voiture roule sur son erre."""

    remarques: tuple[Message, ...] = field(default_factory=tuple)


def mesurer(
    tour: DonneesTour, definition: DefinitionCircuit, pas: float = 1.0
) -> list[MetriquesVirage]:
    """Mesure tous les virages d'un circuit sur un tour."""
    distance = np.arange(0.0, tour.longueur, pas)
    v = tour.sur_distance(distance)
    temps = tour.temps_a_distance(distance)
    return [
        _mesurer_un(tour, virage, definition, distance, v, temps, pas)
        for virage in definition.virages
        if virage.debut < tour.longueur
    ]


def secteurs(definition: DefinitionCircuit) -> list[tuple[float, float]]:
    """Découpe le tour ENTIER en une portion par virage, sans trou ni recouvrement.

    Sert à répartir le temps gagné ou perdu : chaque mètre du tour appartient à
    un virage et à un seul, si bien que la somme des écarts par virage redonne
    exactement l'écart du tour.

    La frontière entre deux virages est posée au milieu de la ligne droite qui
    les sépare. C'est un partage conventionnel, et il faut le savoir : sur une
    longue ligne droite, une bonne sortie continue de payer bien après le
    virage, et la seconde moitié de ce gain est portée au crédit du virage
    suivant. Aucun découpage ne peut faire mieux — l'effet d'une sortie ne
    s'arrête pas à un endroit précis.
    """
    bornes = [0.0]
    for precedent, suivant in zip(definition.virages, definition.virages[1:]):
        bornes.append((precedent.fin + suivant.debut) / 2)
    bornes.append(definition.longueur)
    return list(zip(bornes, bornes[1:]))


def zone_analyse(
    virage: Virage, definition: DefinitionCircuit
) -> tuple[float, float]:
    """Portion de piste observée pour un virage : son approche et sa sortie.

    On remonte jusqu'au freinage, sans empiéter sur le virage précédent — sinon
    le freinage d'un virage serait compté deux fois.
    """
    precedent = [v.fin for v in definition.virages if v.fin <= virage.debut]
    suivant = [v.debut for v in definition.virages if v.debut >= virage.fin]
    debut = max(
        virage.debut - REMONTEE_FREINAGE, max(precedent) if precedent else 0.0
    )
    fin = min(
        virage.fin + PROLONGEMENT_SORTIE,
        min(suivant) if suivant else definition.longueur,
    )
    return debut, max(fin, virage.fin)


def _mesurer_un(
    tour: DonneesTour,
    virage: Virage,
    definition: DefinitionCircuit,
    distance: np.ndarray,
    v: dict[str, np.ndarray],
    temps: np.ndarray,
    pas: float,
) -> MetriquesVirage:
    debut_zone, fin_zone = zone_analyse(virage, definition)
    zone = (distance >= debut_zone) & (distance <= fin_zone)
    dans = (distance >= virage.debut) & (distance <= virage.fin)
    if not zone.any() or not dans.any():
        raise ErreurTelemetrie.de(
            "serveur.erreur.virage_hors_tour",
            numero=virage.numero,
            debut=f"{virage.debut:.0f}",
            fin=f"{virage.fin:.0f}",
            longueur=f"{tour.longueur:.0f}",
        )

    d = distance[zone]
    t = temps[zone]
    frein = v["Brake Pos"][zone]
    gaz = v["Throttle Pos"][zone]
    vitesse = v["Ground Speed"][zone]
    remarques: list[Message] = []

    # --- freinage ----------------------------------------------------
    freine = frein > SEUIL_FREIN
    if freine.any():
        premier = int(np.argmax(freine))
        debut_freinage = float(d[premier])
        vitesse_entree = float(vitesse[premier])
        distance_freinage = virage.debut - debut_freinage
        if distance_freinage < 0:
            remarques.append(Message("serveur.virage.freinage_dans_virage"))
    else:
        debut_freinage = vitesse_entree = distance_freinage = None
        # Ce n'est pas une anomalie : à Monza, la sortie de la première chicane
        # et la Curva Grande se passent sans jamais toucher le frein.
        remarques.append(Message(SANS_FREINER))

    # Le temps se déduit de l'axe de distance : on somme la durée des tronçons
    # où la pédale est enfoncée, plutôt que de compter des échantillons.
    duree = np.diff(t, prepend=t[0])
    duree_freinage = float(duree[freine].sum())

    # --- point le plus lent ------------------------------------------
    vitesses_virage = v["Ground Speed"][dans]
    creux = int(np.argmin(vitesses_virage))
    vitesse_min = float(vitesses_virage[creux])
    position_min = float(distance[dans][creux])

    # --- remise des gaz ----------------------------------------------
    # On la cherche APRÈS le point le plus lent : avant, un coup d'accélérateur
    # en entrée de courbe n'est pas une remise des gaz.
    apres = d >= position_min
    gaz_apres = gaz[apres]
    ouvert = gaz_apres > SEUIL_GAZ
    if ouvert.any():
        indice = int(np.argmax(ouvert))
        remise_gaz = float(d[apres][indice])
        vitesse_remise = float(vitesse[apres][indice])
    else:
        remise_gaz = vitesse_remise = None
        remarques.append(Message("serveur.virage.pas_de_remise_gaz"))

    # --- sortie et coasting ------------------------------------------
    vitesse_sortie = float(v["Ground Speed"][dans][-1])
    sur_lerre = (frein <= SEUIL_COASTING_FREIN) & (gaz <= SEUIL_COASTING_GAZ)
    temps_coasting = float(duree[sur_lerre].sum())

    return MetriquesVirage(
        virage=virage,
        debut_freinage=debut_freinage,
        distance_freinage=distance_freinage,
        vitesse_entree=vitesse_entree,
        duree_freinage=duree_freinage,
        frein_max=float(frein.max()),
        vitesse_min=vitesse_min,
        position_vitesse_min=position_min,
        remise_gaz=remise_gaz,
        vitesse_remise_gaz=vitesse_remise,
        vitesse_sortie=vitesse_sortie,
        temps_coasting=temps_coasting,
        remarques=tuple(remarques),
    )
