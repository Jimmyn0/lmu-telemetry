"""Serveur local pour l'interface web.

Rien ne sort de la machine : le serveur n'écoute que sur 127.0.0.1, et la page
ne charge aucune ressource extérieure. L'outil fonctionne donc sans connexion.

Il s'appuie sur `http.server` de la bibliothèque standard plutôt que sur un
cadriciel : le besoin est de servir une page et quelques routes JSON, ce n'est
pas la peine d'ajouter une dépendance et un vocabulaire de plus à apprendre.

Trois protections, parce qu'un serveur local n'est pas pour autant à l'abri :

* seuls les fichiers `.duckdb` du dossier de télémétrie peuvent être ouverts,
  quel que soit le chemin que la page transmet ;
* seules les requêtes adressées à « 127.0.0.1 » ou « localhost » sont servies,
  ce qui ferme la porte à une page web qui ferait pointer son propre nom de
  domaine vers la machine (« DNS rebinding ») ;
* les routes qui modifient quelque chose — le choix du dossier de télémétrie,
  celui de la langue, le groupe — exigent une requête venue de la
  page de l'outil elle-même (en-tête Origin), en JSON : un autre site ouvert
  dans le navigateur ne peut pas les déclencher.
"""

from __future__ import annotations

import errno
import json
import socket
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import __version__, emplacements, parametres, textes
from ..errors import DossierIntrouvable, ErreurTelemetrie
from ..groupe.seances import est_seance
from ..groupe.synchro import Synchroniseur
from ..groupe.tours import est_partage
from ..sources import catalogue
from ..textes import Message
from . import reponses
from .reponses import Contexte

STATIQUE = Path(__file__).parent / "statique"

TYPES_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# ----------------------------------------------------------------------
# Serveur
# ----------------------------------------------------------------------


#: Paramètres qui désignent un fichier de session sur le disque.
PARAMETRES_CHEMIN = ("chemin", "ref", "cmp")

#: Noms d'hôte sous lesquels la page a le droit de joindre le serveur.
HOTES_ACCEPTES = frozenset({"127.0.0.1", "localhost"})


class CheminRefuse(ErreurTelemetrie):
    def __init__(self, brut: str) -> None:
        super().__init__(Message("serveur.erreur.chemin_refuse", {"chemin": brut}))


def _verifier_chemins(contexte: Contexte, params: dict[str, list[str]]) -> None:
    """Refuse tout chemin qui ne désigne pas une session du dossier de télémétrie.

    La page transmet le chemin des fichiers qu'elle veut ouvrir, et le serveur
    l'ouvrait tel quel : n'importe quel fichier du disque pouvait être demandé.
    Rien ne justifie d'en ouvrir d'autres que ceux du dossier — y compris le
    fichier d'un autre pilote, qu'on y dépose.
    """
    # Le record d'un ami (« groupe:<membre>/<numéro> ») ou une course (« seance:… ») n'est pas
    # un chemin : le serveur la cherche lui-même dans la copie du groupe ou les résultats du
    # jeu, d'après un motif strict (voir groupe/tours.py et groupe/seances.py), jamais sur le
    # disque à l'endroit qu'on lui donne.
    demandes = [
        brut
        for cle in PARAMETRES_CHEMIN
        for brut in params.get(cle, [])
        if not est_partage(brut) and not est_seance(brut)
    ]
    # Rien à vérifier : surtout, ne pas chercher le dossier. Sans lui, la page
    # elle-même refusait de s'afficher — et avec elle l'écran qui permet de
    # l'indiquer.
    if not demandes:
        return
    racine = catalogue.dossier_telemetrie(contexte.dossier).resolve()
    for brut in demandes:
        chemin = Path(brut).resolve()
        if chemin.suffix.lower() != ".duckdb" or racine not in chemin.parents:
            raise CheminRefuse(brut)


def _etat_dossier(contexte: Contexte) -> dict:
    """Dossier de télémétrie utilisé, ou pourquoi il n'y en a pas."""
    impose = contexte.dossier is not None
    try:
        dossier = catalogue.dossier_telemetrie(contexte.dossier)
    except DossierIntrouvable as erreur:
        return {
            "dossier": None,
            "erreur": str(erreur),
            "message": erreur.message.json() if erreur.message else None,
            "impose": impose,
        }
    return {"dossier": str(dossier), "erreur": None, "impose": impose}


def _choisir_dossier(contexte: Contexte, charge: dict) -> dict:
    """Retient le dossier de télémétrie indiqué dans l'interface.

    On refuse un dossier sans aucune session : c'est presque toujours une
    erreur de niveau (le dossier du jeu, ou `UserData`, au lieu de
    `UserData\\Telemetry`), et l'accepter donnerait une liste vide sans
    explication.
    """
    if contexte.dossier is not None:
        raise ErreurTelemetrie.de("serveur.erreur.dossier_impose")
    brut = str(charge.get("dossier") or "").strip().strip('"')
    if not brut:
        raise ErreurTelemetrie.de("serveur.erreur.dossier_vide")
    chemin = Path(brut)
    if not chemin.is_dir():
        raise DossierIntrouvable(chemin)
    if not any(chemin.glob("*.duckdb")):
        # L'erreur la plus probable est de s'arrêter un niveau trop haut : on
        # dit alors quel sous-dossier prendre.
        cle = "serveur.erreur.aucune_session_dossier"
        if (chemin / "UserData" / "Telemetry").is_dir():
            cle = "serveur.erreur.aucune_session_dossier_jeu"
        elif (chemin / "Telemetry").is_dir():
            cle = "serveur.erreur.aucune_session_dossier_userdata"
        raise ErreurTelemetrie.de(cle, chemin=str(chemin))
    reglages = emplacements.lire_reglages()
    reglages[catalogue.REGLAGE_DOSSIER] = str(chemin)
    emplacements.enregistrer_reglages(reglages)
    return _etat_dossier(contexte)


#: Langues de l'interface (textes dans statique/langues/), et la clé du fichier
#: de réglages qui retient celle choisie : les mêmes que la fenêtre du .exe.
LANGUES = textes.LANGUES_DISPONIBLES
REGLAGE_LANGUE = textes.REGLAGE_LANGUE


def _choisir_langue(charge: dict) -> dict:
    """Retient la langue de l'interface.

    C'est le serveur qui la garde, et non le navigateur : le .exe peut changer
    de port d'un lancement à l'autre (8770 pris, il passe à 8771), et le
    navigateur range ce qu'il mémorise par port — le choix serait perdu.
    """
    langue = str(charge.get("langue") or "")
    if langue not in LANGUES:
        raise ErreurTelemetrie.de("serveur.erreur.langue_inconnue", langue=repr(langue))
    reglages = emplacements.lire_reglages()
    reglages[REGLAGE_LANGUE] = langue
    emplacements.enregistrer_reglages(reglages)
    return {"langue": langue}


def _version() -> dict:
    langue = emplacements.lire_reglages().get(REGLAGE_LANGUE)
    return {
        "version": __version__,
        "donnees": str(emplacements.donnees()),
        "langue": langue if langue in LANGUES else None,
    }


def _origine_acceptee(origine: str | None, hote: str | None) -> bool:
    """La requête vient-elle de la page de l'outil lui-même ?

    Le navigateur joint l'en-tête Origin à toute requête POST, et un site tiers
    ne peut pas le falsifier : il ne vaut « http://127.0.0.1:8770 » que si
    c'est la page de l'outil qui écrit.
    """
    if not origine or not hote:
        return False
    return origine.lower() == f"http://{hote.lower()}" and _hote_accepte(hote)


def _hote_accepte(entete: str | None) -> bool:
    """La requête vise-t-elle bien le serveur local sous son nom local ?

    Le serveur n'écoute que sur 127.0.0.1, mais une page web quelconque peut
    faire résoudre son propre nom de domaine vers 127.0.0.1 (« DNS rebinding »)
    et lire alors les réponses comme si elles venaient de chez elle. Le
    navigateur envoie toujours le nom demandé dans l'en-tête Host : il suffit
    de refuser tout ce qui n'est pas un nom local.
    """
    if not entete:
        return False
    hote = entete.rsplit(":", 1)[0] if entete.count(":") == 1 else entete
    return hote.strip("[]").lower() in HOTES_ACCEPTES


class Gestionnaire(BaseHTTPRequestHandler):
    contexte = Contexte()

    #: La fenêtre de l'application, quand l'outil en a une.
    fenetre = None

    #: La synchronisation avec le groupe, en tâche de fond (lancée par `servir`).
    groupe = Synchroniseur(lambda: reponses.sources_du_groupe(Gestionnaire.contexte))

    # Les journaux ligne par ligne d'http.server polluent le terminal sans rien
    # apprendre : on ne garde que les erreurs.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802  (nom imposé par http.server)
        url = urlparse(self.path)
        params = parse_qs(url.query)
        if not _hote_accepte(self.headers.get("Host")):
            self.send_error(403, "Hote non autorise")
            return
        try:
            _verifier_chemins(self.contexte, params)
            if url.path == "/api/sessions":
                self._json(reponses.sessions(self.contexte))
            elif url.path == "/api/circuits":
                self._json(reponses.circuits(self.contexte))
            elif url.path == "/api/session":
                self._json(reponses.session(self.contexte, params["chemin"][0]))
            elif url.path == "/api/classement":
                self._json(reponses.classement(self.contexte, params["chemin"][0]))
            elif url.path == "/api/leaderboard":
                self._json(reponses.leaderboard(self.contexte, params))
            elif url.path == "/api/groupe":
                self._json(reponses.groupe(self.contexte, self.groupe))
            elif url.path == "/api/groupe/tours":
                self._json(reponses.tours_du_groupe(params))
            elif url.path == "/api/comparaison":
                self._json(reponses.comparaison(self.contexte, params))
            elif url.path == "/api/virages":
                self._json(reponses.virages(self.contexte, params))
            elif url.path == "/api/regularite":
                self._json(reponses.regularite(self.contexte, params))
            elif url.path == "/api/logos":
                self._json(sorted(reponses.logos(self.contexte)))
            elif url.path == "/api/version":
                self._json(_version())
            elif url.path == "/api/dossier":
                self._json(_etat_dossier(self.contexte))
            elif url.path == "/logo":
                self._logo(params)
            else:
                self._fichier(url.path)
        except Exception as erreur:  # noqa: BLE001
            self._erreur(erreur)

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        hote = self.headers.get("Host")
        if not _hote_accepte(hote) or not _origine_acceptee(self.headers.get("Origin"), hote):
            self.send_error(403, "Origine non autorisee")
            return
        # Exiger du JSON oblige un site tiers à une requête « préalable » que
        # le serveur ne sait pas traiter : le navigateur n'envoie alors rien.
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self.send_error(415, "JSON attendu")
            return
        try:
            longueur = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
            charge = json.loads(self.rfile.read(longueur) or b"{}")
            if not isinstance(charge, dict):
                raise ValueError("objet JSON attendu")
            if url.path == "/api/dossier":
                self._json(_choisir_dossier(self.contexte, charge))
            elif url.path == "/api/langue":
                self._json(_choisir_langue(charge))
            elif url.path == "/api/premier-plan":
                # Un second lancement de l'outil : il ramène cette fenêtre-ci.
                if self.fenetre is not None:
                    self.fenetre.premier_plan()
                self._json({"fenetre": self.fenetre is not None})
            elif url.path == "/api/groupe/creer":
                self._json(reponses.creer_groupe(self.contexte, self.groupe, charge))
            elif url.path == "/api/groupe/rejoindre":
                self._json(reponses.rejoindre_groupe(self.contexte, self.groupe, charge))
            elif url.path == "/api/groupe/quitter":
                self._json(reponses.quitter_groupe(self.contexte, self.groupe))
            elif url.path == "/api/groupe/synchroniser":
                self._json(reponses.synchroniser_groupe(self.contexte, self.groupe))
            else:
                self.send_error(404, "Route inconnue")
        except Exception as erreur:  # noqa: BLE001
            self._erreur(erreur)

    def _erreur(self, erreur: Exception) -> None:
        """Répond par un message lisible, jamais par une trace de pile."""
        if isinstance(erreur, BrokenPipeError | ConnectionResetError):
            return  # le navigateur a fermé l'onglet en cours de route
        # `erreur` : la phrase française ; `message` : de quoi l'écrire dans la
        # langue de la page (voir textes.py).
        if isinstance(erreur, ErreurTelemetrie):
            message = erreur.message or Message("serveur.erreur.brute", {"texte": str(erreur)})
            code = 400
            charge = {}
            if isinstance(erreur, DossierIntrouvable):
                charge["code"] = "dossier_introuvable"
        elif isinstance(erreur, KeyError | ValueError):
            message = Message("serveur.erreur.requete_incomplete", {"detail": str(erreur)})
            code = 400
            charge = {}
        else:
            # Un défaut de l'outil, pas une erreur de l'utilisateur : on le dit,
            # avec de quoi le signaler, et la trace complète va dans la console.
            traceback.print_exception(erreur)
            message = Message(
                "serveur.erreur.inattendue", {"detail": f"{type(erreur).__name__}: {erreur}"}
            )
            code = 500
            charge = {}
        self._json({"erreur": str(message), "message": message.json(), **charge}, code=code)

    # ------------------------------------------------------------------

    def _json(self, charge: object, code: int = 200) -> None:
        corps = json.dumps(charge, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _logo(self, params: dict[str, list[str]]) -> None:
        """Sert le logo d'une marque, s'il a été déposé dans `logos/`."""
        marque = (params.get("marque") or [""])[0]
        cible = reponses.logos(self.contexte).get(marque)
        if cible is None:
            self.send_error(404, "Pas de logo pour cette marque")
            return
        self._envoyer(cible.read_bytes(), TYPES_MIME.get(cible.suffix.lower(), "image/png"))

    def _fichier(self, chemin: str) -> None:
        nom = "index.html" if chemin in ("/", "") else chemin.lstrip("/")
        cible = (STATIQUE / nom).resolve()
        # Un chemin comme /../../secret.txt ne doit pas sortir du dossier servi.
        if not cible.is_file() or STATIQUE.resolve() not in cible.parents:
            self.send_error(404, "Page introuvable")
            return
        self._envoyer(
            cible.read_bytes(),
            TYPES_MIME.get(cible.suffix, "application/octet-stream"),
        )

    def _envoyer(self, corps: bytes, type_mime: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", type_mime)
        self.send_header("Content-Length", str(len(corps)))
        # Rien n'est mis en cache : les fichiers sont lus sur le disque local,
        # donc gratuits à recharger, et une page servie depuis le cache après
        # une mise à jour de l'outil donne un mélange incohérent d'ancien et de
        # nouveau code — constaté en développement.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)


class PortOccupe(ErreurTelemetrie):
    def __init__(self, port: int) -> None:
        self.port = port
        super().__init__(
            Message("serveur.erreur.port_occupe", {"port": port, "suivant": port + 1})
        )


class ServeurLocal(ThreadingHTTPServer):
    """Serveur HTTP qui refuse de partager son port.

    `http.server` active SO_REUSEADDR, qui sous Windows ne veut pas dire la même
    chose qu'ailleurs : il laisse un SECOND programme s'installer sur un port
    déjà pris. Constaté : deux lancements de l'outil tournaient côte à côte sur
    le port 8770, et le navigateur tombait sur l'un ou l'autre au hasard. On
    demande au contraire l'usage exclusif du port.
    """

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def creer_serveur(port: int, dossier: Path | None = None) -> ThreadingHTTPServer:
    """Prépare le serveur sur 127.0.0.1 — rien n'est exposé sur le réseau local."""
    Gestionnaire.contexte = Contexte(dossier=dossier)
    try:
        return ServeurLocal(("127.0.0.1", port), Gestionnaire)
    except OSError as erreur:
        if erreur.errno in (errno.EADDRINUSE, 10048) or getattr(erreur, "winerror", None) in (
            10013,
            10048,
        ):
            raise PortOccupe(port) from None
        raise


def servir(serveur: ThreadingHTTPServer, ouvrir: bool) -> None:
    """Fait tourner le serveur jusqu'à son arrêt, en ouvrant la page au besoin."""
    parametres.creer_modele()
    # Hors d'un groupe, la synchronisation ne fait rien ; les tests, qui ne passent pas
    # par ici, ne la lancent pas.
    Gestionnaire.groupe.demarrer()
    if ouvrir:
        adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
        threading.Timer(0.5, lambda: webbrowser.open(adresse)).start()
    try:
        serveur.serve_forever()
    finally:
        serveur.server_close()


def demarrer(port: int = 8770, dossier: Path | None = None, ouvrir: bool = True) -> None:
    """Lance le serveur et ouvre le navigateur."""
    serveur = creer_serveur(port, dossier)
    print(f"Interface disponible sur http://127.0.0.1:{port}/")
    print("Ctrl+C pour arrêter.")
    try:
        servir(serveur, ouvrir)
    except KeyboardInterrupt:
        print("\nArrêt.")
