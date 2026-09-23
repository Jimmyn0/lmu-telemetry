"""Fabrique la session de test `synthetique.duckdb`.

Le fichier produit reproduit EXACTEMENT la structure d'un fichier LMU réel
(vérifiée dans docs/01-decouverte.md) mais avec des valeurs choisies, ce qui
permet d'écrire des tests aux résultats connus d'avance, sans avoir besoin du
jeu ni des enregistrements personnels de qui que ce soit.

Scénario, 552 secondes à partir de t0 = 100 s :

  tour 0  100 → 160 s   sortie des stands, aucun chrono
  tour 1  160 → 250 s   propre, chrono 90,000 s, secteurs 30 / 30 / 30
  tour 2  250 → 340 s   bouclé mais SANS chrono : invalidé par le jeu
  tour 3  340 → 432 s   chrono 92,000 s : même parcours que le tour 1, plus
                        2 s à l'arrêt, plus 1 s hors piste et 2 chocs
  tour 4  432 → 522 s   propre, chrono 90,000 s
  tour 5  522 → 612 s   propre, chrono 90,000 s
  tour 6  612 → 652 s   non bouclé, la session s'arrête

Quatre tours valides : de quoi calculer une dispersion, ce que la page
régularité exige (au moins trois).

Les tours 1, 2 et 3 couvrent EXACTEMENT la même distance : `Lap Dist` est
l'intégrale de la vitesse, comme dans la réalité. Sans cette cohérence, un
arrêt de deux secondes n'apparaîtrait pas dans le delta, puisque la distance
continuerait d'avancer pendant que la voiture est immobile.

Relancer :  python tests/fixtures/construire.py
"""

from __future__ import annotations

import math
from pathlib import Path

import duckdb
import numpy as np

SORTIE = Path(__file__).with_name("synthetique.duckdb")

T0 = 100.0
FIN = 652.0
DUREE = FIN - T0

#: Instants de franchissement de la ligne.
FRONTIERES = (100.0, 160.0, 250.0, 340.0, 432.0, 522.0, 612.0)

METADONNEES = {
    "Version": "1",
    "DriverName": "Pilote de test",
    "SteamID": "0",
    "RecordingTime": "2026-01-02T03_04_05Z",
    "SessionTime": "10:00:00",
    "SessionType": "Practice",
    "TrackName": "Circuit de test",
    "TrackLayout": "Circuit de test",
    "WeatherConditions": "Clear",
    "CarName": "Voiture de test #1",
    "CarClass": "GT3",
}

#: nom -> (fréquence Hz, unité)
CANAUX = {
    "Ground Speed": (100, "km/h"),
    "Lap Dist": (10, "m"),
    "Throttle Pos": (50, "%"),
    "Brake Pos": (50, "%"),
    "Steering Pos": (100, "%"),
    "SurfaceTypes": (5, ""),
    "GPS Latitude": (10, "deg"),
    "GPS Longitude": (10, "deg"),
    "Path Lateral": (10, "m"),
    "Track Edge": (10, "m"),
}

#: Mètres par degré de latitude, comme dans la projection du jeu. Répété ici
#: plutôt qu'importé : la fixture doit reproduire le format du jeu sans rien
#: devoir au code qu'elle sert à tester.
METRES_PAR_DEGRE = 111_320.0

#: Le circuit de test est un ANNEAU circulaire de 10 m de large. Un cercle est
#: fermé — donc le GPS reste continu au passage de la ligne, comme dans un vrai
#: fichier — et il est courbe, ce qui met réellement à l'épreuve le calcul des
#: normales. Une ligne droite ne testerait rien de tout cela.
DEMI_LARGEUR = 5.0

#: Longueur d'un tour de référence : 89 s à 150 km/h plus 1 s à 60 km/h.
LONGUEUR_TOUR = 150 / 3.6 * 89 + 60 / 3.6 * 1

#: Rayon de l'anneau, déduit de sa circonférence.
RAYON = LONGUEUR_TOUR / (2 * math.pi)

#: Chronologie du virage de test, en secondes depuis le début de chaque tour.
#: Freinage à fond pendant une seconde, puis une seconde sur l'erre à vitesse
#: réduite, puis remise des gaz. De quoi vérifier chaque métrique du tableau
#: par virage sur des valeurs connues d'avance.
FREINAGE_S = (44.0, 45.0)
VIRAGE_LENT_S = (45.0, 46.0)
REPRISE_GAZ_S = 46.0
VITESSE_RAPIDE = 150.0
VITESSE_LENTE = 60.0
GAZ_EN_PISTE = 80.0

#: Écart latéral à l'axe, en mètres, pour chaque tour. Les tours 1 et 3, ceux
#: qu'utilisent les tests de géométrie, passent de part et d'autre de l'axe :
#: chacun renseigne donc un bord différent.
#:
#: Le tour 2 est le seul à TRAVERSER l'axe, en dérivant régulièrement d'un bord
#: à l'autre. Il sert à vérifier que `Track Edge`, qui saute d'un bord à l'autre
#: à cet instant, n'est jamais interpolé à travers ce saut.
ECART_LATERAL = {0: 0.0, 1: 2.0, 3: -3.0, 4: 2.0, 5: -3.0, 6: 0.0}
TOUR_TRAVERSANT = 2

#: nom -> (unité, lignes (ts, valeur))
EVENEMENTS = {
    # Le numéro de tour est écrit à l'instant où le tour COMMENCE.
    "Lap": (
        "",
        [
            (100.0, 0), (160.0, 1), (250.0, 2), (340.0, 3),
            (432.0, 4), (522.0, 5), (612.0, 6),
        ],
    ),
    # Le chrono est décalé d'un tour : celui écrit à 250 s est celui du tour 1.
    # Rien n'est écrit à 340 s : le tour 2 a été invalidé par le jeu.
    "Lap Time": (
        "s",
        [(100.0, 0.0), (250.0, 90.0), (432.0, 92.0), (522.0, 90.0), (612.0, 90.0)],
    ),
    "Last Sector1": (
        "s",
        [(100.0, 0.0), (250.0, 30.0), (432.0, 30.0), (522.0, 30.0), (612.0, 30.0)],
    ),
    "Last Sector2": (
        "s",
        [(100.0, 0.0), (250.0, 60.0), (432.0, 62.0), (522.0, 60.0), (612.0, 60.0)],
    ),
    "In Pits": ("", [(100.0, 1), (130.0, 0)]),
    "Speed Limiter": ("", [(100.0, True), (130.0, False)]),
    # La valeur présente à t0 est l'état initial, pas un choc : 2 chocs en tout.
    "LastImpactMagnitude": (
        "",
        [(100.0, False), (355.0, True), (355.1, False), (360.0, True), (360.1, False)],
    ),
    "Gear": ("", [(100.0, 0), (135.0, 3)]),
}


def _temps(frequence: int) -> np.ndarray:
    """Instants des échantillons d'un canal, comme le fera le lecteur."""
    return T0 + np.arange(int(DUREE * frequence)) / frequence


def _vitesse(frequence: int = 100) -> np.ndarray:
    """150 km/h en piste, 60 dans la voie des stands, 0 pendant l'arrêt.

    Un creux à 60 km/h une seconde par tour joue le rôle du virage le plus lent :
    sans lui, la vitesse minimale d'un tour propre vaudrait 150 km/h et ne
    testerait rien.

    Le tour 3 dure 2 s de plus que le tour 1 et passe 2 s à l'arrêt : les deux
    couvrent donc la même distance, comme deux vrais tours du même circuit.
    """
    t = _temps(frequence)
    v = np.full(t.shape, VITESSE_RAPIDE)
    v[_dans_chaque_tour(t, *VIRAGE_LENT_S)] = VITESSE_LENTE
    v[t < 130.0] = 60.0  # voie des stands
    v[(t >= 400.0) & (t < 402.0)] = 0.0  # arrêt au tour 3
    return v


def _dans_chaque_tour(t: np.ndarray, debut_s: float, fin_s: float) -> np.ndarray:
    """Masque des instants situés dans une fenêtre, à chaque tour."""
    masque = np.zeros(t.shape, dtype=bool)
    for depart in FRONTIERES:
        masque |= (t >= depart + debut_s) & (t < depart + fin_s)
    return masque


def _frein() -> np.ndarray:
    """Freinage à fond juste avant le virage lent, rien ailleurs."""
    t = _temps(50)
    return np.where(_dans_chaque_tour(t, *FREINAGE_S), 100.0, 0.0)


def _gaz() -> np.ndarray:
    """Pied levé du début du freinage jusqu'à la remise des gaz.

    Entre la fin du freinage et la remise des gaz, ni frein ni accélérateur :
    c'est le « coasting » que le tableau par virage doit mesurer.
    """
    t = _temps(50)
    leve = _dans_chaque_tour(t, FREINAGE_S[0], REPRISE_GAZ_S)
    return np.where(leve, 0.0, GAZ_EN_PISTE)


def _distance() -> np.ndarray:
    """`Lap Dist` : intégrale de la vitesse, remise à zéro à chaque ligne.

    C'est ce que fait le jeu, à ceci près que son `Lap Dist` suit l'axe de la
    piste alors qu'ici la voiture roule pile dessus. Pour un fichier de test,
    l'important est que distance et vitesse racontent la même histoire.
    """
    t = _temps(10)
    v = _vitesse(10) / 3.6  # km/h -> m/s
    distance = np.zeros(t.shape)
    parcouru = 0.0
    for i in range(1, len(t)):
        if any(abs(t[i] - f) < 1e-9 for f in FRONTIERES):
            parcouru = 0.0  # franchissement de la ligne
        else:
            parcouru += (v[i] + v[i - 1]) / 2 * (t[i] - t[i - 1])
        distance[i] = parcouru
    return distance


def _surfaces() -> dict[str, np.ndarray]:
    """Tout en piste, sauf une seconde sur l'herbe (valeur 2) au tour 3."""
    t = _temps(5)
    roue_avant_gauche = np.where((t >= 380.0) & (t < 381.0), 2, 0)
    autres = np.zeros(t.shape, dtype=int)
    return {
        "value1": roue_avant_gauche.astype("uint8"),
        "value2": autres.astype("uint8"),
        "value3": autres.astype("uint8"),
        "value4": autres.astype("uint8"),
    }


def _lateral() -> np.ndarray:
    """Écart à l'axe de la piste.

    Constant sur chaque tour, sauf sur le tour traversant, qui dérive de +3 m
    à -3 m et franchit donc l'axe en son milieu.
    """
    t = _temps(10)
    numero = np.searchsorted(np.array(FRONTIERES), t, side="right") - 1
    valeurs = np.array([ECART_LATERAL.get(int(k), 0.0) for k in numero])

    dans_le_tour = numero == TOUR_TRAVERSANT
    if dans_le_tour.any():
        debut = FRONTIERES[TOUR_TRAVERSANT]
        fin = FRONTIERES[TOUR_TRAVERSANT + 1]
        avance = (t[dans_le_tour] - debut) / (fin - debut)
        valeurs[dans_le_tour] = 3.0 - 6.0 * avance
    return valeurs


def _bord() -> np.ndarray:
    """Bord de piste DU CÔTÉ DE LA VOITURE, comme le fait le jeu.

    C'est la sémantique établie par la mesure sur de vrais fichiers : la valeur
    change de signe selon le côté où roule la voiture.
    """
    lateral = _lateral()
    signe = np.where(lateral < 0, -1.0, 1.0)
    return signe * DEMI_LARGEUR


def _gps() -> dict[str, np.ndarray]:
    """Position sur l'anneau, repassée en degrés comme le fait le jeu.

    L'angle se déduit de la distance parcourue dans le tour : à la ligne, la
    distance repasse à zéro et l'angle à 2π, c'est-à-dire au même point. Le
    tracé est donc continu d'un tour à l'autre, comme un vrai relevé GPS.
    """
    angle = 2 * math.pi * _distance() / LONGUEUR_TOUR
    rayon = RAYON + _lateral()
    x = rayon * np.sin(angle)
    y = rayon * np.cos(angle)
    latitude = y / METRES_PAR_DEGRE
    k = math.cos(math.radians(float(np.mean(latitude))))
    return {
        "GPS Latitude": latitude.astype("float32"),
        "GPS Longitude": (x / (METRES_PAR_DEGRE * k)).astype("float32"),
    }


def _creer_table(con, table: str, colonnes: dict[str, np.ndarray]) -> None:
    """Crée une table à partir de tableaux numpy, en une seule passe.

    DuckDB sait lire directement un dictionnaire de tableaux numpy présent dans
    les variables locales : la table est écrite d'un bloc. Insérer ligne par
    ligne prendrait plusieurs minutes pour 37 000 échantillons.
    """
    scan = colonnes  # le nom `scan` est celui que DuckDB retrouve ci-dessous
    champs = ", ".join(f'"{nom}"' for nom in colonnes)
    con.execute(f'CREATE TABLE "{table}" AS SELECT {champs} FROM scan')


def construire(sortie: Path = SORTIE) -> Path:
    sortie.unlink(missing_ok=True)
    Path(str(sortie) + ".wal").unlink(missing_ok=True)
    con = duckdb.connect(str(sortie))

    _creer_table(
        con,
        "metadata",
        {
            "key": np.array(list(METADONNEES), dtype=object),
            "value": np.array(list(METADONNEES.values()), dtype=object),
        },
    )
    _creer_table(
        con,
        "channelsList",
        {
            "channelName": np.array(list(CANAUX), dtype=object),
            "frequency": np.array([f for f, _ in CANAUX.values()], dtype="int32"),
            "unit": np.array([u for _, u in CANAUX.values()], dtype=object),
        },
    )
    _creer_table(
        con,
        "eventsList",
        {
            "eventName": np.array(list(EVENEMENTS), dtype=object),
            "unit": np.array([u for u, _ in EVENEMENTS.values()], dtype=object),
        },
    )

    valeurs = {
        "Ground Speed": {"value": _vitesse(100).astype("float32")},
        "Lap Dist": {"value": _distance().astype("float32")},
        "Throttle Pos": {"value": _gaz().astype("float32")},
        "Brake Pos": {"value": _frein().astype("float32")},
        "Steering Pos": {"value": np.zeros(int(DUREE * 100), dtype="float32")},
        "SurfaceTypes": _surfaces(),
        "Path Lateral": {"value": _lateral().astype("float32")},
        "Track Edge": {"value": _bord().astype("float32")},
    }
    gps = _gps()
    valeurs["GPS Latitude"] = {"value": gps["GPS Latitude"]}
    valeurs["GPS Longitude"] = {"value": gps["GPS Longitude"]}
    for nom, colonnes in valeurs.items():
        _creer_table(con, nom, colonnes)

    for nom, (_unite, lignes) in EVENEMENTS.items():
        exemple = lignes[0][1]
        typ = {bool: bool, int: "uint16", float: "float32"}[type(exemple)]
        _creer_table(
            con,
            nom,
            {
                "ts": np.array([t for t, _ in lignes], dtype="float64"),
                "value": np.array([v for _, v in lignes], dtype=typ),
            },
        )

    con.close()
    return sortie


if __name__ == "__main__":
    chemin = construire()
    print(f"Écrit : {chemin}  ({chemin.stat().st_size / 1024:.0f} Ko)")
