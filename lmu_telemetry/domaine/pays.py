"""Pays de chaque circuit, pour afficher un drapeau à côté du nom.

Contrairement au modèle de voiture, cette information n'existe NULLE PART dans
les fichiers du jeu. Trois pistes ont été essayées avant d'écrire cette table à
la main :

* `TrackVenue` et `TrackEvent` des résultats ne donnent que des noms ;
* `TrackData` donne un chemin de fichier (`...\\Locations\\Spa_2023\\...`),
  sans pays ;
* les canaux `GPS Latitude` / `GPS Longitude` de la télémétrie sont FACTICES.
  Vérifié sur les neuf circuits enregistrés : tous ont pour centre 60,00° N et
  0,00° E, à quelques millièmes de degré près. Ce ne sont pas des coordonnées
  terrestres mais un repère local, centré sur un point arbitraire au nord de
  l'Écosse. Ils restent parfaitement utilisables pour reconstruire la géométrie
  de la piste — c'est ce que fait `piste.py` — mais ils ne disent pas où elle
  se trouve.

La table ci-dessous couvre les circuits installés avec le jeu. Elle est
donc écrite de mémoire, ce qui est acceptable ici et seulement ici : se tromper
de drapeau n'a aucun effet sur une analyse. Un circuit inconnu n'affiche
simplement pas de drapeau, et le fichier `circuits/pays.json` permet d'en
ajouter un sans toucher au code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Nom du fichier qui permet d'ajouter ou de corriger un pays sans recompiler.
#: Format : { "fragment de nom de circuit": "code ISO" }.
FICHIER_SUPPLEMENT = "pays.json"

#: Fragment de nom de circuit (en minuscules) -> code ISO 3166-1 alpha-2.
#: Les fragments sont testés du plus long au plus court : un nom qui en
#: contiendrait deux retient donc le plus spécifique.
CIRCUITS = {
    "algarve": "PT",
    "portimao": "PT",
    "portimão": "PT",
    "bahrain": "BH",
    "barcelona": "ES",
    "catalunya": "ES",
    "circuit of the americas": "US",
    "daytona": "US",
    "laguna seca": "US",
    "long beach": "US",
    "sebring": "US",
    "fuji": "JP",
    "imola": "IT",
    "enzo e dino ferrari": "IT",
    "monza": "IT",
    "interlagos": "BR",
    "carlos pace": "BR",
    "la sarthe": "FR",
    "le mans": "FR",
    "paul ricard": "FR",
    "lusail": "QA",
    "losail": "QA",
    "silverstone": "GB",
    "spa-francorchamps": "BE",
}

#: Noms français des pays utilisés ci-dessus, pour l'infobulle du drapeau.
NOMS = {
    "BE": "Belgique",
    "BH": "Bahreïn",
    "BR": "Brésil",
    "ES": "Espagne",
    "FR": "France",
    "GB": "Royaume-Uni",
    "IT": "Italie",
    "JP": "Japon",
    "PT": "Portugal",
    "QA": "Qatar",
    "US": "États-Unis",
}


@dataclass(frozen=True)
class Pays:
    code: str  # ISO 3166-1 alpha-2, en majuscules
    nom: str


def pays_du_circuit(circuit: str, dossier: Path | str | None = None) -> Pays | None:
    """Pays d'un circuit d'après son nom, ou None si on ne le connaît pas.

    La reconnaissance se fait par fragment de nom plutôt que par égalité : le
    jeu écrit « Autodromo Nazionale Monza » côté télémétrie et pourrait écrire
    autre chose demain, mais « monza » restera dedans.
    """
    table = dict(CIRCUITS)
    table.update(_supplement(dossier))

    reduit = (circuit or "").lower()
    for fragment in sorted(table, key=len, reverse=True):
        if fragment in reduit:
            code = table[fragment].upper()
            return Pays(code=code, nom=NOMS.get(code, code))
    return None


def _supplement(dossier: Path | str | None) -> dict[str, str]:
    """Table complémentaire écrite par l'utilisateur, si elle existe.

    Un fichier illisible est ignoré : un drapeau manquant vaut mieux qu'une
    page qui refuse de s'afficher.
    """
    if dossier is None:
        return {}
    chemin = Path(dossier) / FICHIER_SUPPLEMENT
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(brut, dict):
        return {}
    return {
        str(k).lower(): str(v)
        for k, v in brut.items()
        if isinstance(v, str) and len(v) == 2
    }
