"""Ce qui se passe quand on double-clique sur le .exe.

Pour quelqu'un qui n'a jamais ouvert un terminal, tout doit se régler seul :

* l'outil s'ouvre dans sa propre fenêtre, sans rien taper ;
* s'il est DÉJÀ ouvert (double-clic de trop, fenêtre cachée derrière le jeu),
  on ramène simplement sa fenêtre au lieu d'échouer sur un port occupé ;
* si le port est pris par un autre programme, on essaie les suivants ;
* sans WebView2, le moteur de la fenêtre, on se rabat sur le navigateur ;
* en cas de problème, un message reste affiché jusqu'à ce qu'on le ferme. Il n'y
  a plus de console pour le lire : c'est une boîte de dialogue, et une copie va
  dans `journal.txt`.

Fermer la fenêtre arrête l'outil.

Les messages parlent la langue choisie dans l'interface (bouton FR | EN,
enregistré dans les réglages), et à défaut celle de Windows. Ce sont les clés
`console.*` des mêmes fichiers de traduction que la page.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import traceback
import urllib.request
import webbrowser

from . import __version__, emplacements, fenetre
from .errors import ErreurTelemetrie
from .textes import Message, console_utf8, langue_preferee, traduire

#: Premier port essayé, puis les suivants s'il est pris par un autre programme.
PORT = 8770
PORTS_ESSAYES = 10
#: Un autre premier port, pour essayer un .exe pendant que l'outil tourne déjà.
VARIABLE_PORT = "LMU_PORT"


def premier_port() -> int:
    return int(os.environ.get(VARIABLE_PORT) or PORT)


def outil_deja_ouvert(port: int) -> bool:
    """Ce port est-il tenu par l'outil lui-même (et non un autre programme) ?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=1) as r:
            return "version" in json.loads(r.read())
    except Exception:  # noqa: BLE001 — n'importe quel échec veut dire « non »
        return False


def _boite(texte: str, titre: str = fenetre.TITRE) -> None:
    """Un message à lire, qui reste affiché jusqu'à ce qu'on le ferme."""
    ctypes.windll.user32.MessageBoxW(None, texte, titre, 0x40)


def _journaliser(texte: str) -> None:
    """Sans console, une erreur ne laisserait aucune trace."""
    try:
        chemin = emplacements.donnees() / "journal.txt"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a", encoding="utf-8") as journal:
            journal.write(texte + "\n")
    except OSError:
        pass


def _ramener(port: int) -> None:
    """Demande à l'outil déjà ouvert d'afficher sa fenêtre.

    Windows n'autorise un programme à passer devant que si celui qui est au
    premier plan l'y autorise : c'est nous, puisqu'on vient d'être lancé.
    """
    ctypes.windll.user32.AllowSetForegroundWindow(-1)
    requete = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/premier-plan",
        data=b"{}",
        headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=2) as reponse:
            if json.loads(reponse.read()).get("fenetre"):
                return
    except OSError:
        pass
    webbrowser.open(f"http://127.0.0.1:{port}/")


def lancer(langue: str, ouvrir_fenetre: bool = True) -> int:
    from .web.serveur import Gestionnaire, PortOccupe, creer_serveur, servir

    serveur = None
    debut = premier_port()
    for port in range(debut, debut + PORTS_ESSAYES):
        if outil_deja_ouvert(port):
            if ouvrir_fenetre:
                _ramener(port)
            return 0
        try:
            serveur = creer_serveur(port)
            break
        except PortOccupe:
            continue
    if serveur is None:
        raise ErreurTelemetrie(
            Message("console.aucun_port", {"debut": debut, "fin": debut + PORTS_ESSAYES - 1})
        )

    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
    print(traduire("console.titre", langue, {"version": __version__}), adresse)
    if not ouvrir_fenetre:
        servir(serveur, ouvrir=False)
        return 0

    threading.Thread(target=servir, args=(serveur, False), daemon=True).start()

    def retenir(ouverte: fenetre.Fenetre) -> None:
        Gestionnaire.fenetre = ouverte

    if not fenetre.ouvrir(adresse, retenir):
        if fenetre.ERREUR:
            _journaliser("La fenêtre n'a pas pu s'ouvrir :\n" + fenetre.ERREUR)
        webbrowser.open(adresse)
        journal = emplacements.donnees() / "journal.txt"
        _boite(traduire("console.sans_fenetre", langue, {"adresse": adresse, "journal": journal}))
    return 0


def reprendre_ancien_dossier() -> None:
    """L'outil s'appelait « Télémétrie LMU » : son dossier de données prend le nouveau
    nom, avant que quoi que ce soit ne l'ouvre. Pas si l'outil tourne déjà : il s'en
    sert encore, et c'est sa fenêtre qu'on va ramener."""
    if not outil_deja_ouvert(premier_port()):
        emplacements.migrer_ancien_dossier()


def main() -> int:
    reprendre_ancien_dossier()
    console_utf8()
    langue = langue_preferee()
    try:
        # `--sans-fenetre` : pour tester le .exe sans rien ouvrir.
        return lancer(langue, ouvrir_fenetre="--sans-fenetre" not in sys.argv)
    except KeyboardInterrupt:
        return 0
    except ErreurTelemetrie as erreur:
        texte = erreur.message.dans(langue) if erreur.message else str(erreur)
        _journaliser(texte)
        _boite(texte)
        return 1
    except Exception:  # noqa: BLE001
        _journaliser(traceback.format_exc())
        _boite(traduire("console.inattendu", langue) + traceback.format_exc(limit=3))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
