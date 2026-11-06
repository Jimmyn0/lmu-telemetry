"""Diagnostic de la mémoire partagée, à lancer pendant que tu roules.

La structure de `LMU_Data` a été déduite des en-têtes du jeu, jeu fermé. Cet
outil vérifie sur le jeu en marche ce que la v2 tient pour acquis, et mesure ce
que les en-têtes ne disent pas :

* les décalages de `memoire_lmu.py` sont-ils les bons ?
* à quelle fréquence la télémétrie et le scoring sont-ils mis à jour ?
* combien de lectures tombent pendant une écriture du jeu ?
* que vaut la distance estimée entre deux mises à jour de `mLapDist` ?
* la rotation des roues montre-t-elle le blocage et le patinage ? Le canal
  `Wheel Speed` des fichiers ne les montre pas ;
* quels champs le jeu laisse-t-il à zéro ?

Il ne fait que lire : voir `memoire_lmu.py`. Il s'arrête tout seul après
`--roulage` secondes passées à rouler, ou sur Ctrl+C.

Il dépose dans `%LOCALAPPDATA%\\Telemetrie LMU\\diagnostics\\<date>` :

* `rapport.json` : les mesures ;
* `capture.bin` : tout ce qui a été lu, pour rejouer et réanalyser sans le jeu ;
* `image-N.bin` : quelques copies intégrales de la mémoire. En ligne, elles
  contiennent aussi les noms des autres pilotes. Rien ne quitte la machine.

Usage, depuis la racine du projet :

    .venv\\Scripts\\python.exe -m tools.sonde_live
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import numpy as np

from lmu_telemetry import emplacements
from lmu_telemetry.textes import console_utf8
from lmu_telemetry.sources.memoire_lmu import (
    CHAMPS_ROUE,
    CHAMPS_SCORING,
    CHAMPS_TELEMETRIE,
    CHAMPS_VEHICULE,
    NOM_MEMOIRE,
    TAILLE_MEMOIRE,
    LecteurMemoire,
    Lecture,
    MemoireAbsente,
    decoder,
    decoder_roues,
)

#: Fréquence de sondage, en Hz. Le double du débit annoncé par le jeu (100 Hz) :
#: en dessous, on ne pourrait pas le mesurer. L'overlay lira, lui, à 50 Hz.
FREQUENCE_SONDAGE = 200

#: Temps passé à rouler (s) après lequel la sonde s'arrête d'elle-même.
ROULAGE_PAR_DEFAUT = 300.0

#: Vitesse (m/s) au-dessus de laquelle on considère que la voiture roule.
VITESSE_ROULAGE = 5.0

#: Écart (s) entre deux copies intégrales de la mémoire, et leur nombre maximal.
ECART_IMAGES = 60.0
IMAGES_MAXIMUM = 5

#: Bornes des mesures de roues : pédale et vitesse (m/s) au-dessus desquelles un
#: glissement a un sens. À faible vitesse, le rapport ne veut plus rien dire.
SEUIL_PEDALE = 0.2
VITESSE_MINIMALE_ROUES = 15.0

ENTETE_CAPTURE = b"LMUCAP1\n"
ENREGISTREMENT = struct.Struct("<BdI")
TYPE_TELEMETRIE, TYPE_VEHICULE, TYPE_SCORING = 1, 2, 3


# ----------------------------------------------------------------------
# Capture
# ----------------------------------------------------------------------


def ecrire_enregistrement(flux: BinaryIO, type_: int, instant: float, brut: bytes) -> None:
    flux.write(ENREGISTREMENT.pack(type_, instant, len(brut)))
    flux.write(brut)


def relire_capture(chemin: Path) -> Iterator[tuple[int, float, bytes]]:
    """Enregistrements d'une capture : (type, instant, bloc brut)."""
    with chemin.open("rb") as flux:
        if flux.read(len(ENTETE_CAPTURE)) != ENTETE_CAPTURE:
            raise ValueError(f"{chemin} n'est pas une capture de la sonde")
        while entete := flux.read(ENREGISTREMENT.size):
            if len(entete) < ENREGISTREMENT.size:
                return  # capture coupée en pleine écriture
            type_, instant, longueur = ENREGISTREMENT.unpack(entete)
            brut = flux.read(longueur)
            if len(brut) < longueur:
                return
            yield type_, instant, brut


# ----------------------------------------------------------------------
# Mesures
# ----------------------------------------------------------------------


def _vitesse(telemetrie: dict) -> float:
    """Vitesse de la voiture, en m/s, à partir de sa vitesse locale."""
    return math.hypot(*telemetrie["vitesse_locale"])


def _centiles(valeurs: list[float] | np.ndarray) -> dict | None:
    if len(valeurs) == 0:
        return None
    tableau = np.asarray(valeurs, dtype=float)
    return {
        "mediane": round(float(np.median(tableau)), 4),
        "p99": round(float(np.percentile(tableau, 99)), 4),
        "max": round(float(tableau.max()), 4),
    }


def _frequence(instants: list[float]) -> float | None:
    """Fréquence de mise à jour, d'après l'écart médian entre deux instants."""
    if len(instants) < 3:
        return None
    ecart = float(np.median(np.diff(instants)))
    return round(1.0 / ecart, 2) if ecart > 0 else None


class Bilan:
    """Accumule ce qui a été lu, et en tire le rapport."""

    def __init__(self) -> None:
        self.telemetrie: list[dict] = []
        self.roues: list[list[dict]] = []
        self.vehicules: list[tuple[float, dict]] = []
        self.durees_lecture: list[float] = []
        self.instants_sondage: list[float] = []
        self.identite: dict = {}
        self.circuits_concordent: bool | None = None
        self.roulage = 0.0

    def ajouter_telemetrie(self, lecture: Lecture) -> None:
        telemetrie = decoder(lecture.telemetrie, CHAMPS_TELEMETRIE)
        scoring = decoder(lecture.scoring, CHAMPS_SCORING)
        # L'horloge du jeu repart de zéro à chaque session, et la mémoire garde
        # l'ancienne voiture jusqu'au chargement de la nouvelle. Constaté : la
        # capture Hypercar commençait par une image de la GT3 d'avant. Mêler les
        # deux fausserait toutes les mesures, on ne garde que la session en cours.
        if self.telemetrie and telemetrie["temps"] < self.telemetrie[-1]["temps"]:
            self.telemetrie.clear()
            self.roues.clear()
            self.vehicules.clear()
        if self.telemetrie:
            pas = telemetrie["temps"] - self.telemetrie[-1]["temps"]
            if 0 < pas < 1 and _vitesse(telemetrie) > VITESSE_ROULAGE:
                self.roulage += pas
        self.telemetrie.append(telemetrie)
        self.roues.append(decoder_roues(lecture.telemetrie))
        self.identite = {
            "circuit_telemetrie": telemetrie["circuit"],
            "circuit_scoring": scoring["circuit"],
            "voiture": telemetrie["voiture"],
            "modele": telemetrie["modele"],
            "session": scoring["session"],
        }
        # Deux blocs éloignés de 127 ko qui nomment le même circuit : c'est la
        # preuve la plus simple que les deux décalages sont justes.
        self.circuits_concordent = (
            bool(telemetrie["circuit"]) and telemetrie["circuit"] == scoring["circuit"]
        )

    def ajouter_vehicule(self, lecture: Lecture) -> None:
        temps = decoder(lecture.scoring, CHAMPS_SCORING)["temps"]
        self.vehicules.append((temps, decoder(lecture.vehicule, CHAMPS_VEHICULE)))

    # ------------------------------------------------------------------

    def _estimation_distance(self) -> dict | None:
        """Erreur de la distance estimée entre deux mises à jour de `mLapDist`.

        C'est la méthode retenue pour le direct : repartir de la dernière valeur
        du jeu et y ajouter l'intégrale de la vitesse. Chaque mise à jour est
        comparée à ce que la précédente aurait prédit.
        """
        if len(self.telemetrie) < 3 or len(self.vehicules) < 3:
            return None
        temps = np.array([t["temps"] for t in self.telemetrie])
        vitesse = np.array([_vitesse(t) for t in self.telemetrie])
        ordre = np.argsort(temps)
        temps, vitesse = temps[ordre], vitesse[ordre]
        parcouru = np.concatenate(
            [[0.0], np.cumsum((vitesse[1:] + vitesse[:-1]) / 2 * np.diff(temps))]
        )
        erreurs = []
        for (t0, v0), (t1, v1) in zip(self.vehicules, self.vehicules[1:]):
            d0, d1 = v0["distance_tour"], v1["distance_tour"]
            # Le passage de la ligne remet la distance à zéro : ce couple-là ne
            # compare rien.
            if d1 <= d0 or t1 <= t0 or t1 - t0 > 1.0:
                continue
            estime = np.interp(t1, temps, parcouru) - np.interp(t0, temps, parcouru)
            erreurs.append(abs(estime - (d1 - d0)))
        return _centiles(erreurs)

    def _glissements(self) -> dict | None:
        """Ce que chaque source donne comme glissement au freinage et à l'accélération.

        Le rayon statique n'étant qu'approché, on le recale roue par roue sur les
        moments où aucune pédale n'agit.
        """
        if len(self.telemetrie) < 10:
            return None
        vitesse = np.array([_vitesse(t) for t in self.telemetrie])
        frein = np.array([t["frein"] for t in self.telemetrie])
        gaz = np.array([t["gaz"] for t in self.telemetrie])
        abs_actif = np.array([t["abs_actif"] for t in self.telemetrie])
        tc_actif = np.array([t["tc_actif"] for t in self.telemetrie])

        def par_roue(nom: str) -> np.ndarray:
            return np.array([[abs(r[nom]) for r in roues] for roues in self.roues])

        rayon = par_roue("rayon_cm") / 100.0
        roues_vitesse = par_roue("rotation") * rayon
        roulant = vitesse > VITESSE_MINIMALE_ROUES
        libre = roulant & (frein < 0.02) & (gaz < 0.5)
        if libre.sum() < 10:
            libre = roulant
        if not libre.any():
            return None
        echelle = np.median(roues_vitesse[libre] / vitesse[libre, None], axis=0)
        echelle = np.where(echelle > 0, echelle, 1.0)

        with np.errstate(divide="ignore", invalid="ignore"):
            rotation = 1.0 - roues_vitesse / echelle / vitesse[:, None]
            patch = par_roue("vitesse_patch_longitudinale") / vitesse[:, None]
            sol = 1.0 - par_roue("vitesse_sol_longitudinale") / vitesse[:, None]

        freinage = roulant & (frein > SEUIL_PEDALE)
        traction = roulant & (gaz > SEUIL_PEDALE) & (frein < 0.02)
        return {
            "echelle_rayon": [round(float(e), 3) for e in echelle],
            "freinage": {
                "echantillons": int(freinage.sum()),
                "part_abs_actif": round(float(abs_actif[freinage].mean()), 3)
                if freinage.any()
                else None,
                "rotation": _centiles(rotation[freinage].max(axis=1)),
                "patch": _centiles(patch[freinage].max(axis=1)),
                "sol": _centiles(sol[freinage].max(axis=1)),
            },
            "acceleration": {
                "echantillons": int(traction.sum()),
                "part_tc_actif": round(float(tc_actif[traction].mean()), 3)
                if traction.any()
                else None,
                "rotation_arriere": _centiles(-rotation[traction, 2:].min(axis=1)),
                "patch_arriere": _centiles(patch[traction, 2:].max(axis=1)),
            },
        }

    def _champs_nuls(self) -> dict[str, list[str]]:
        """Champs restés à zéro pendant toute la capture : le jeu ne les remplit
        peut-être pas. Un décalage faux se voit aussi ici."""

        def nuls(lignes: list[dict], noms) -> list[str]:
            return [n for n in noms if lignes and not any(ligne[n] for ligne in lignes)]

        return {
            "telemetrie": nuls(self.telemetrie, CHAMPS_TELEMETRIE),
            "roue_avant_gauche": nuls([r[0] for r in self.roues], CHAMPS_ROUE),
            "vehicule": nuls([v for _, v in self.vehicules], CHAMPS_VEHICULE),
        }

    def rapport(self, memoire: LecteurMemoire | None, fin: str) -> dict:
        tours = sorted({t["tour"] for t in self.telemetrie})
        gaz = np.array([t["gaz"] for t in self.telemetrie])
        gaz_brut = np.array([t["gaz_brut"] for t in self.telemetrie])
        return {
            "fin": fin,
            "memoire": {
                "nom": memoire.nom if memoire else NOM_MEMOIRE,
                "taille_attendue": TAILLE_MEMOIRE,
                "taille_reelle": memoire.taille if memoire else None,
                "version_jeu": memoire.version_jeu() if memoire else None,
                "lecture_seule": memoire.protection == 2 if memoire else None,
                "circuits_concordent": self.circuits_concordent,
                **self.identite,
            },
            "debits_hz": {
                "sondage": _frequence(self.instants_sondage),
                "telemetrie": _frequence([t["temps"] for t in self.telemetrie]),
                "distance_tour": _frequence([t for t, _ in self.vehicules]),
            },
            "lecture": {
                "duree_us": _centiles(self.durees_lecture),
                "lectures": len(self.durees_lecture),
                "dechirures": memoire.dechirures if memoire else None,
                "abandons": memoire.abandons if memoire else None,
            },
            "roulage_s": round(self.roulage, 1),
            "echantillons": {
                "telemetrie": len(self.telemetrie),
                "vehicule": len(self.vehicules),
            },
            "tours_vus": tours,
            "tour_invalide_vu": any(t["tour_invalide"] for t in self.telemetrie),
            "gaz_different_du_brut": round(
                float(np.mean(np.abs(gaz - gaz_brut) > 0.01)), 3
            )
            if gaz.size
            else None,
            "erreur_distance_m": self._estimation_distance(),
            "glissements": self._glissements(),
            "champs_nuls": self._champs_nuls(),
        }


def resume(rapport: dict) -> str:
    """Ce qu'il faut lire du rapport, en quelques lignes."""
    memoire, debits, lecture = rapport["memoire"], rapport["debits_hz"], rapport["lecture"]
    verdict = "OK" if memoire["circuits_concordent"] else "À VÉRIFIER"
    lignes = [
        f"Structure de la mémoire : {verdict}",
        f"  circuit : {memoire.get('circuit_telemetrie', '?')}"
        f"   voiture : {memoire.get('modele') or memoire.get('voiture', '?')}",
        f"  taille : {memoire['taille_reelle']} octets (attendu {memoire['taille_attendue']})",
        f"Débits : télémétrie {debits['telemetrie']} Hz, "
        f"distance {debits['distance_tour']} Hz",
        f"Lectures : {lecture['lectures']}, dont {lecture['dechirures']} déchirées "
        f"et {lecture['abandons']} abandonnées",
        f"Roulage : {rapport['roulage_s']} s, tours vus : {rapport['tours_vus']}",
    ]
    if rapport["erreur_distance_m"]:
        lignes.append(f"Erreur de distance estimée (m) : {rapport['erreur_distance_m']}")
    return "\n".join(lignes)


# ----------------------------------------------------------------------
# Boucle de lecture
# ----------------------------------------------------------------------


def _attendre_memoire(nom: str, delai: float | None) -> LecteurMemoire | None:
    """Attend que le jeu publie sa mémoire. None si `delai` est dépassé."""
    debut = time.perf_counter()
    prevenu = False
    while True:
        try:
            return LecteurMemoire(nom)
        except MemoireAbsente:
            if not prevenu:
                print("En attente de Le Mans Ultimate… Lance le jeu, puis va en piste.")
                prevenu = True
            if delai is not None and time.perf_counter() - debut > delai:
                return None
            time.sleep(1.0)


def sonder(
    dossier: Path,
    nom: str = NOM_MEMOIRE,
    roulage: float = ROULAGE_PAR_DEFAUT,
    frequence: int = FREQUENCE_SONDAGE,
    attente: float | None = None,
    duree_maximale: float | None = None,
) -> dict:
    """Lit la mémoire jusqu'à `roulage` secondes de roulage, et écrit le rapport."""
    dossier.mkdir(parents=True, exist_ok=True)
    bilan = Bilan()
    memoire = _attendre_memoire(nom, attente)
    if memoire is None:
        rapport = bilan.rapport(None, "jeu non détecté")
        (dossier / "rapport.json").write_text(
            json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return rapport

    fin = "roulage atteint"
    periode = 1.0 / frequence
    debut = time.perf_counter()
    dernier_message = debut
    derniere_image = -ECART_IMAGES
    images = 0
    dernier_temps = None
    derniere_distance = None
    dernier_scoring = None
    try:
        with memoire, (dossier / "capture.bin").open("wb") as capture:
            capture.write(ENTETE_CAPTURE)
            print(f"Mémoire trouvée. Roule {roulage:.0f} s ; Ctrl+C pour arrêter avant.")
            while bilan.roulage < roulage:
                instant = time.perf_counter()
                if duree_maximale is not None and instant - debut > duree_maximale:
                    fin = "durée maximale"
                    break
                bilan.instants_sondage.append(instant)
                lecture = memoire.lire()
                bilan.durees_lecture.append((time.perf_counter() - instant) * 1e6)

                if lecture is not None:
                    temps = struct.unpack_from("<d", lecture.telemetrie, 12)[0]
                    if temps != dernier_temps:
                        dernier_temps = temps
                        bilan.ajouter_telemetrie(lecture)
                        ecrire_enregistrement(
                            capture, TYPE_TELEMETRIE, instant, lecture.telemetrie
                        )
                    if lecture.scoring != dernier_scoring:
                        dernier_scoring = lecture.scoring
                        ecrire_enregistrement(capture, TYPE_SCORING, instant, lecture.scoring)
                    if lecture.vehicule is not None:
                        distance = struct.unpack_from("<d", lecture.vehicule, 104)[0]
                        if distance != derniere_distance:
                            derniere_distance = distance
                            bilan.ajouter_vehicule(lecture)
                            ecrire_enregistrement(
                                capture, TYPE_VEHICULE, instant, lecture.vehicule
                            )
                    if (
                        images < IMAGES_MAXIMUM
                        and bilan.roulage - derniere_image >= ECART_IMAGES
                        and bilan.roulage > 0
                    ):
                        derniere_image = bilan.roulage
                        images += 1
                        (dossier / f"image-{images}.bin").write_bytes(memoire.image())

                if instant - dernier_message >= 10.0:
                    dernier_message = instant
                    print(f"  {bilan.roulage:.0f} s de roulage sur {roulage:.0f} s")
                time.sleep(max(0.0, periode - (time.perf_counter() - instant)))
            rapport = bilan.rapport(memoire, fin)
    except KeyboardInterrupt:
        rapport = bilan.rapport(None, "arrêt manuel")
        rapport["lecture"]["dechirures"] = memoire.dechirures
        rapport["lecture"]["abandons"] = memoire.abandons

    (dossier / "rapport.json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return rapport


def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="python -m tools.sonde_live",
        description="Diagnostic de la mémoire partagée de Le Mans Ultimate.",
    )
    parseur.add_argument("--roulage", type=float, default=ROULAGE_PAR_DEFAUT)
    parseur.add_argument("--frequence", type=int, default=FREQUENCE_SONDAGE)
    parseur.add_argument("--dossier", type=Path, help="où déposer le rapport")
    return parseur


def main(argv: list[str] | None = None) -> int:
    console_utf8()
    args = construire_parseur().parse_args(argv)
    dossier = args.dossier or (
        emplacements.donnees() / "diagnostics" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    )
    rapport = sonder(dossier, roulage=args.roulage, frequence=args.frequence)
    print()
    print(resume(rapport))
    print(f"\nRapport complet : {dossier / 'rapport.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
