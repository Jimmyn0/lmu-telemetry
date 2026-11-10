"""Les seuils réglables, et le fichier qui permet de les changer.

Les valeurs par défaut sont écrites ici. Le fichier
`%LOCALAPPDATA%\\GhostLine\\parametres.json` les remplace : il est créé au
premier lancement avec toutes les valeurs, pour qu'on voie ce qui se règle.

Une clé mal orthographiée ou une valeur qui n'est pas un nombre donne un message
qui désigne le fichier. L'ignorer laisserait croire qu'un réglage a été pris en
compte alors qu'il ne l'est pas.

Les sections qu'une version précédente de l'outil écrivait, et qui ne règlent plus
rien, sont une autre affaire : ce n'est pas une faute de l'utilisateur. Elles sont
ignorées à la lecture, et `creer_modele` les retire du fichier.

Les constantes de détection des virages (`virages.RAYON_MAXIMAL`...) ne sont pas
ici : elles décrivent la géométrie d'un circuit et ont été calées par mesure, ce
ne sont pas des préférences.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from . import emplacements
from .cache import CacheBorne
from .errors import ErreurTelemetrie
from .sources.reader import cle_fichier


@dataclass(frozen=True)
class SeuilsVirage:
    """Ce qui délimite les mesures faites sur un virage."""

    frein: float = 3.0
    """Course de pédale (%) à partir de laquelle on freine."""

    gaz: float = 15.0
    """Course de pédale (%) à partir de laquelle on accélère."""

    duree_remise_gaz: float = 0.3
    """Durée (s) à tenir au-dessus de `gaz` pour parler de remise des gaz."""

    coasting_frein: float = 3.0
    """Sous ce seuil de frein (%) et celui de gaz, la voiture roule sur son erre."""

    coasting_gaz: float = 5.0
    """Voir `coasting_frein`."""

    remontee_freinage: float = 350.0
    """Distance (m) remontée en amont d'un virage pour y chercher le freinage."""

    prolongement_sortie: float = 100.0
    """Distance (m) conservée en aval pour observer la sortie."""


@dataclass(frozen=True)
class Parametres:
    virages: SeuilsVirage = field(default_factory=SeuilsVirage)


#: Sections écrites par une version précédente, qui ne règlent plus rien : les conseils
#: de pilotage et leur overlay, retirés le 2026-11-09. Un fichier écrit à l'époque les
#: contient encore.
SECTIONS_RETIREES = frozenset({"coach", "overlay"})


#: Dernière lecture du fichier : il peut être retouché pendant que l'outil tourne.
_lus: CacheBorne[tuple, Parametres] = CacheBorne(2)


def _erreur(detail: str) -> ErreurTelemetrie:
    return ErreurTelemetrie.de(
        "serveur.erreur.parametres_illisible",
        chemin=str(emplacements.fichier_parametres()),
        detail=detail,
    )


def _section(classe: type, nom: str, brut: object):
    if not isinstance(brut, dict):
        raise _erreur(f"« {nom} » devrait contenir des réglages")
    connus = {f.name for f in fields(classe)}
    valeurs = {}
    for cle, valeur in brut.items():
        if cle not in connus:
            raise _erreur(f"réglage inconnu : « {nom}.{cle} »")
        if isinstance(valeur, bool) or not isinstance(valeur, int | float) or valeur < 0:
            raise _erreur(f"« {nom}.{cle} » devrait être un nombre positif")
        valeurs[cle] = float(valeur)
    return classe(**valeurs)


def _interpreter(brut: object) -> Parametres:
    if not isinstance(brut, dict):
        raise _erreur("le fichier devrait contenir des réglages")
    sections = {f.name: f for f in fields(Parametres)}
    valeurs = {}
    for nom, contenu in brut.items():
        if nom.startswith("_") or nom in SECTIONS_RETIREES:
            continue  # `_aide`, et ce qu'une version précédente a laissé
        if nom not in sections:
            raise _erreur(f"section inconnue : « {nom} »")
        valeurs[nom] = _section(sections[nom].default_factory, nom, contenu)
    return Parametres(**valeurs)


def lire() -> Parametres:
    """Les réglages en vigueur : ceux du fichier, ou les valeurs par défaut."""
    chemin = emplacements.fichier_parametres()
    cle = cle_fichier(chemin)
    if cle is None:
        return Parametres()

    def interpreter() -> Parametres:
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as erreur:
            raise _erreur(f"{type(erreur).__name__}: {erreur}") from erreur
        return _interpreter(brut)

    return _lus.obtenir(cle, interpreter)


def creer_modele() -> None:
    """Tient le fichier à jour : ce qu'on y lit est ce qui se règle.

    Il est créé s'il n'existe pas. S'il existe, les réglages apparus depuis y sont
    ajoutés, sans toucher à ceux qui y sont déjà, et les sections retirées en sont
    enlevées. Un fichier mal formé reste tel quel : c'est `lire` qui le signale.

    Un échec n'empêche rien : l'outil fonctionne avec ses valeurs par défaut.
    """
    chemin = emplacements.fichier_parametres()
    try:
        actuel = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        actuel = {}
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(actuel, dict):
        return
    contenu = {
        "_aide": (
            "Seuils de l'outil. Change une valeur, puis recharge la page. "
            "Supprime ce fichier pour retrouver les valeurs d'origine."
        ),
        **asdict(Parametres()),
    }
    for nom, reglages in actuel.items():
        if nom in SECTIONS_RETIREES:
            continue
        if isinstance(reglages, dict) and isinstance(contenu.get(nom), dict):
            contenu[nom].update(reglages)
        else:
            contenu[nom] = reglages
    if contenu == actuel:
        return
    provisoire = chemin.with_suffix(".tmp")
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        provisoire.write_text(
            json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(provisoire, chemin)
    except OSError:
        pass
