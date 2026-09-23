"""Les textes que l'outil produit lui-même : remarques, avertissements, erreurs.

Le serveur n'envoie pas de phrases à la page, mais des `Message` : une clé et
des valeurs. C'est la page qui écrit la phrase, dans la langue choisie, à partir
de `web/statique/langues/<langue>.json`.

Le français reste nécessaire côté Python — pour la ligne de commande, et pour
que `str(erreur)` garde un sens dans les journaux et les tests. Il est lu dans
le MÊME fichier `fr.json` que la page : une seule version de chaque phrase, à
un seul endroit. Les clés du serveur commencent toutes par `serveur.`.

Les valeurs sont insérées telles quelles : les nombres y sont donc déjà mis en
forme (« 1.8 », pas 1.8123), pour que les deux langues affichent la même chose.
Elles finissent dans du texte brut, jamais dans du HTML : un chemin ou un nom de
voiture venu d'un fichier ne peut rien injecter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

LANGUES = Path(__file__).parent / "web" / "statique" / "langues"


#: Langues disponibles, la première servant de repli.
LANGUES_DISPONIBLES = ("fr", "en")

#: Clé du fichier de réglages qui retient la langue choisie dans l'interface.
REGLAGE_LANGUE = "langue"


@lru_cache(maxsize=None)
def _textes(langue: str) -> dict[str, str]:
    return json.loads((LANGUES / f"{langue}.json").read_text(encoding="utf-8"))


def traduire(cle: str, langue: str, valeurs: dict | None = None) -> str:
    """La phrase d'une clé dans une langue, avec ses `{emplacements}` remplis.

    Une clé absente de la langue retombe sur le français, puis sur la clé
    elle-même, comme dans la page.
    """
    valeurs = valeurs or {}
    modele = _textes(langue).get(cle) or _textes("fr").get(cle, cle)
    return re.sub(
        r"\{(\w+)\}",
        lambda m: str(valeurs[m.group(1)]) if m.group(1) in valeurs else m.group(0),
        modele,
    )


def texte(cle: str, **valeurs: object) -> str:
    """La phrase française d'une clé, avec ses `{emplacements}` remplis."""
    return traduire(cle, "fr", valeurs)


def langue_du_systeme() -> str:
    """Français si Windows est en français, anglais sinon."""
    try:
        import ctypes

        identifiant = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "fr" if identifiant & 0x3FF == 0x0C else "en"  # 0x0C : français
    except (AttributeError, OSError):
        import locale

        code = (locale.getlocale()[0] or "").lower()
        return "fr" if code.startswith(("fr", "french")) else "en"


def langue_preferee() -> str:
    """La langue choisie dans l'interface, sinon celle du système.

    Sert à la fenêtre du .exe, qui s'affiche avant la page : elle ne peut pas
    lire le bouton FR | EN, mais elle lit ce qu'il a enregistré.
    """
    from . import emplacements

    choisie = emplacements.lire_reglages().get(REGLAGE_LANGUE)
    return choisie if choisie in LANGUES_DISPONIBLES else langue_du_systeme()


@dataclass(frozen=True)
class Message:
    """Une phrase à afficher, désignée par sa clé plutôt qu'écrite."""

    cle: str
    valeurs: dict[str, str | int | float] = field(default_factory=dict)

    def __str__(self) -> str:
        return texte(self.cle, **self.valeurs)

    def dans(self, langue: str) -> str:
        return traduire(self.cle, langue, self.valeurs)

    def __hash__(self) -> int:  # les valeurs sont un dict : on hache leur contenu
        return hash((self.cle, tuple(sorted(self.valeurs.items()))))

    def json(self) -> dict:
        return {"cle": self.cle, "valeurs": self.valeurs}
