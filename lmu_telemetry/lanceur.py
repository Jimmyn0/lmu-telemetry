"""Ce qui se passe quand on double-clique sur le .exe.

Pour quelqu'un qui n'a jamais ouvert un terminal, tout doit se régler seul :

* l'outil s'ouvre dans le navigateur, sans rien taper ;
* s'il est DÉJÀ ouvert (double-clic de trop, fenêtre cachée derrière le jeu),
  on rouvre simplement la page au lieu d'échouer sur un port occupé ;
* si le port est pris par un autre programme, on essaie les suivants ;
* en cas de problème, le message reste affiché jusqu'à ce qu'on appuie sur
  Entrée. Sans cette pause, la fenêtre se fermerait avant qu'on ait pu lire
  quoi que ce soit.

La fenêtre noire reste ouverte tant que l'outil tourne : c'est elle qui fait
tourner le serveur local, la fermer arrête l'outil. Elle le dit.

Elle parle la langue choisie dans l'interface (bouton FR | EN, enregistré dans
les réglages), et à défaut celle de Windows. Ses phrases sont les clés
`console.*` des mêmes fichiers de traduction que la page.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
import urllib.request
import webbrowser

from . import __version__
from .errors import ErreurTelemetrie
from .textes import Message, langue_preferee, traduire

#: Premier port essayé, puis les suivants s'il est pris par un autre programme.
PORT = 8770
PORTS_ESSAYES = 10


def outil_deja_ouvert(port: int) -> bool:
    """Ce port est-il tenu par l'outil lui-même (et non un autre programme) ?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=1) as r:
            return "version" in json.loads(r.read())
    except Exception:  # noqa: BLE001 — n'importe quel échec veut dire « non »
        return False


def _pause(langue: str) -> None:
    try:
        input("\n" + traduire("console.pause", langue))
    except (EOFError, KeyboardInterrupt):
        pass


def lancer(langue: str, ouvrir_navigateur: bool = True) -> int:
    from .web.serveur import PortOccupe, creer_serveur

    def dire(cle: str, **valeurs: object) -> None:
        print(traduire(cle, langue, valeurs))

    dire("console.titre", version=__version__)
    print("=" * 40)

    serveur = None
    for port in range(PORT, PORT + PORTS_ESSAYES):
        if outil_deja_ouvert(port):
            dire("console.deja_ouvert")
            if ouvrir_navigateur:
                webbrowser.open(f"http://127.0.0.1:{port}/")
            return 0
        try:
            serveur = creer_serveur(port)
            break
        except PortOccupe:
            continue
    if serveur is None:
        raise ErreurTelemetrie(
            Message("console.aucun_port", {"debut": PORT, "fin": PORT + PORTS_ESSAYES - 1})
        )

    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
    dire("console.ouvert", adresse=adresse)
    print()
    dire("console.laisser_ouvert")
    if ouvrir_navigateur:
        threading.Timer(0.5, lambda: webbrowser.open(adresse)).start()
    try:
        serveur.serve_forever()
    finally:
        serveur.server_close()
    return 0


def main() -> int:
    # La console Windows n'est pas en UTF-8 par défaut : sans ça, les accents
    # s'affichent en symboles incompréhensibles, voire font planter l'outil.
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    langue = langue_preferee()
    try:
        # `--sans-navigateur` : pour tester le .exe sans ouvrir de fenêtre.
        return lancer(langue, ouvrir_navigateur="--sans-navigateur" not in sys.argv)
    except KeyboardInterrupt:
        return 0
    except ErreurTelemetrie as erreur:
        print("\n" + (erreur.message.dans(langue) if erreur.message else str(erreur)))
        _pause(langue)
        return 1
    except Exception:  # noqa: BLE001
        print("\n" + traduire("console.inattendu", langue))
        traceback.print_exc()
        _pause(langue)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
