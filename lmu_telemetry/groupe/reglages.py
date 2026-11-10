"""Les réglages du groupe : l'adresse du service, et la place de ce PC dans un groupe — le
code du groupe, son numéro de membre, sa clé secrète et le nom qu'il y porte.

Rangés avec les autres réglages, dans `reglages.json` (voir `emplacements.py`), sous la clé
« groupe ». La clé secrète ne quitte ce fichier que vers le service, à chaque échange.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from .. import emplacements

#: Clé des réglages du groupe dans `reglages.json`.
CLE = "groupe"

#: Pour parler à un autre service : celui des tests (`service/local.mjs`), ou celui qu'un
#: autre groupe d'amis aurait mis en ligne.
VARIABLE_SERVICE = "LMU_SERVICE_GROUPE"

#: L'adresse du service en ligne, mis en ligne le 2026-11-10 : voir docs/20-groupe.md,
#: « Mettre le service en ligne ». Les tests la remplacent toujours (tests/conftest.py).
SERVICE = "https://lmu-groupe.lmu-groupe.workers.dev"


@dataclass(frozen=True)
class Adhesion:
    """La place de ce PC dans un groupe."""

    code: str
    """Le code du groupe, tel que le service le range : « K7M2QX9P »."""

    membre: str
    cle: str
    nom: str
    """Le nom que ce PC porte dans le groupe."""

    @property
    def code_affiche(self) -> str:
        """Le code tel qu'on le recopie : « K7M2-QX9P »."""
        return f"{self.code[:4]}-{self.code[4:]}"


def _section(tout: dict | None = None) -> dict:
    section = (emplacements.lire_reglages() if tout is None else tout).get(CLE)
    return section if isinstance(section, dict) else {}


def adresse_service() -> str | None:
    """L'adresse du service : la variable d'environnement, sinon celle des réglages, sinon
    celle livrée avec l'outil. None tant qu'aucun service n'est en ligne."""
    adresse = os.environ.get(VARIABLE_SERVICE) or _section().get("service") or SERVICE
    if not isinstance(adresse, str) or not adresse.strip():
        return None
    return adresse.strip().rstrip("/")


def adhesion() -> Adhesion | None:
    """La place de ce PC dans un groupe ; None s'il n'est dans aucun."""
    section = _section()
    valeurs = {champ: section.get(champ) for champ in ("code", "membre", "cle", "nom")}
    if not all(isinstance(v, str) and v for v in valeurs.values()):
        return None
    return Adhesion(**valeurs)


def enregistrer(nouvelle: Adhesion | None) -> None:
    """Range l'adhésion de ce PC (None : il quitte son groupe), sans toucher aux autres
    réglages ni à une adresse de service choisie à la main."""
    tout = emplacements.lire_reglages()
    section = {cle: valeur for cle, valeur in _section(tout).items() if cle == "service"}
    if nouvelle is not None:
        section.update(asdict(nouvelle))
    if section:
        tout[CLE] = section
    else:
        tout.pop(CLE, None)
    emplacements.enregistrer_reglages(tout)
