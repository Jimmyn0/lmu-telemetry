"""Le client du service du groupe (`service/src/index.js`) : des requêtes HTTPS en JSON.

L'outil se présente sous un nom qui ne dit rien de qui l'utilise, et n'envoie que ce que
la route demande. Les erreurs deviennent des `ErreurGroupe`, avec une phrase qui dit quoi
faire, dans la langue de la page.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from ..errors import ErreurTelemetrie
from ..textes import Message
from .reglages import Adhesion

#: Délai (s) avant de renoncer à une réponse.
DELAI = 20.0

#: Comment l'outil se présente au service : rien qui dise qui l'utilise.
AGENT = "GhostLine-groupe/1"

#: Les lettres d'un code de groupe : ni I, O, 0 ni 1, comme le service.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGUEUR_CODE = 8

#: Les erreurs du service qu'on sait expliquer.
MESSAGES = {
    "groupe_introuvable": "serveur.erreur.groupe_introuvable",
    "groupe_complet": "serveur.erreur.groupe_complet",
    "non_membre": "serveur.erreur.groupe_non_membre",
    "nom_invalide": "serveur.erreur.groupe_nom",
    "trop_gros": "serveur.erreur.groupe_trop_gros",
    "tour_introuvable": "serveur.erreur.groupe_tour_introuvable",
    "seance_introuvable": "serveur.erreur.groupe_seance_introuvable",
}


class ErreurGroupe(ErreurTelemetrie):
    """Une erreur du groupe ; `code` est celui du service (« non_membre »), ou
    « hors_ligne » quand il ne répond pas."""

    def __init__(self, message: Message, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def normaliser_code(brut: object) -> str:
    """Un code tel qu'on le saisit (« k7m2-qx9p ») ramené à sa forme rangée (« K7M2QX9P »)."""
    code = "".join(c for c in str(brut or "").upper() if c not in " -")
    if len(code) != LONGUEUR_CODE or any(c not in ALPHABET for c in code):
        raise ErreurGroupe(Message("serveur.erreur.groupe_code"), "code_invalide")
    return code


class Service:
    def __init__(self, adresse: str, delai: float = DELAI) -> None:
        self.adresse = adresse.rstrip("/")
        self.delai = delai

    def sante(self) -> dict:
        return self._requete("GET", "/v1/sante")

    def creer(self, nom: str) -> Adhesion:
        """Crée un groupe, dont ce PC est le premier membre."""
        reponse = self._requete("POST", "/v1/groupes", {"nom": nom})
        return Adhesion(reponse["code"], reponse["membre"], reponse["cle"], nom)

    def rejoindre(self, code: str, nom: str) -> Adhesion:
        reponse = self._requete("POST", f"/v1/groupes/{normaliser_code(code)}/membres", {"nom": nom})
        return Adhesion(reponse["code"], reponse["membre"], reponse["cle"], nom)

    def lire(self, adhesion: Adhesion, depuis: int = 0) -> dict:
        """Ce que le groupe a de neuf depuis la version `depuis`."""
        return self._requete("GET", f"/v1/groupes/{adhesion.code}?depuis={int(depuis)}", adhesion=adhesion)

    def envoyer(self, adhesion: Adhesion, performances: list[dict], contours: dict | None = None) -> dict:
        return self._requete(
            "PUT",
            f"/v1/groupes/{adhesion.code}/performances",
            {"performances": performances, "contours": contours or {}},
            adhesion=adhesion,
        )

    def envoyer_tour(self, adhesion: Adhesion, tour: dict) -> dict:
        """Partage la télémétrie d'un record (voir `tours.py`)."""
        return self._requete("PUT", f"/v1/groupes/{adhesion.code}/tours", {"tour": tour}, adhesion=adhesion)

    def tour(self, adhesion: Adhesion, membre: str, identifiant: str) -> dict:
        """La télémétrie du record d'un membre : `donnees`, le tour compressé."""
        return self._requete(
            "GET",
            f"/v1/groupes/{adhesion.code}/tours/{membre}/{urllib.parse.quote(identifiant)}",
            adhesion=adhesion,
        )

    def envoyer_seance(self, adhesion: Adhesion, seance: dict) -> dict:
        """Partage le classement d'une course (voir `seances.py`) : `id`, `donnees`."""
        return self._requete("PUT", f"/v1/groupes/{adhesion.code}/seances", {"seance": seance}, adhesion=adhesion)

    def seance(self, adhesion: Adhesion, membre: str, identifiant: str) -> dict:
        """Le classement d'une course d'un membre : `donnees`, la séance compressée."""
        return self._requete(
            "GET",
            f"/v1/groupes/{adhesion.code}/seances/{membre}/{urllib.parse.quote(identifiant)}",
            adhesion=adhesion,
        )

    def quitter(self, adhesion: Adhesion) -> None:
        """Retire ce PC du groupe ; ses performances partent avec lui."""
        self._requete("DELETE", f"/v1/groupes/{adhesion.code}/membres/{adhesion.membre}", adhesion=adhesion)

    def _requete(
        self, methode: str, chemin: str, corps: dict | None = None, adhesion: Adhesion | None = None
    ) -> dict:
        entetes = {"Accept": "application/json", "User-Agent": AGENT}
        donnees = None
        if corps is not None:
            donnees = json.dumps(corps, ensure_ascii=False, allow_nan=False).encode("utf-8")
            entetes["Content-Type"] = "application/json"
        if adhesion is not None:
            entetes["Authorization"] = f"Membre {adhesion.membre}:{adhesion.cle}"
        requete = urllib.request.Request(self.adresse + chemin, data=donnees, headers=entetes, method=methode)
        try:
            with urllib.request.urlopen(requete, timeout=self.delai) as reponse:
                charge = json.loads(reponse.read() or b"{}")
        except urllib.error.HTTPError as erreur:
            code = None
            try:
                code = json.loads(erreur.read()).get("erreur")
            except (ValueError, AttributeError, OSError):
                pass
            if code in MESSAGES:
                raise ErreurGroupe(Message(MESSAGES[code]), code) from None
            detail = f"{erreur.code} {code or erreur.reason}"
            raise ErreurGroupe(Message("serveur.erreur.groupe_service", {"detail": detail}), code) from None
        except (urllib.error.URLError, OSError):
            raise ErreurGroupe(Message("serveur.erreur.groupe_hors_ligne"), "hors_ligne") from None
        except ValueError:
            raise ErreurGroupe(Message("serveur.erreur.groupe_service", {"detail": "JSON"})) from None
        if not isinstance(charge, dict):
            raise ErreurGroupe(Message("serveur.erreur.groupe_service", {"detail": "JSON"}))
        return charge
