"""Un cache à taille bornée, partagé entre les fils du serveur.

Le serveur tourne des heures et répond sur plusieurs fils : un simple `dict`
grossirait sans limite, et n'est pas protégé contre deux écritures simultanées.
On retire ce qui a servi le moins récemment : c'est ce qu'on a le moins de
chances de redemander.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

C = TypeVar("C", bound=Hashable)
V = TypeVar("V")


class CacheBorne(Generic[C, V]):
    def __init__(self, capacite: int) -> None:
        self._capacite = capacite
        self._valeurs: OrderedDict[C, V] = OrderedDict()
        self._verrou = threading.Lock()

    def get(self, cle: C, defaut: V | None = None) -> V | None:
        with self._verrou:
            if cle not in self._valeurs:
                return defaut
            self._valeurs.move_to_end(cle)
            return self._valeurs[cle]

    def __setitem__(self, cle: C, valeur: V) -> None:
        with self._verrou:
            self._valeurs[cle] = valeur
            self._valeurs.move_to_end(cle)
            while len(self._valeurs) > self._capacite:
                self._valeurs.popitem(last=False)

    def __contains__(self, cle: C) -> bool:
        with self._verrou:
            return cle in self._valeurs

    def __len__(self) -> int:
        with self._verrou:
            return len(self._valeurs)

    def obtenir(self, cle: C, calculer: Callable[[], V]) -> V:
        """La valeur en cache, calculée au besoin.

        Le calcul se fait hors du verrou : lire un fichier prend du temps, et les
        autres fils n'ont pas à attendre. Deux fils peuvent alors calculer la
        même valeur en même temps, ce qui coûte un calcul mais reste juste.
        """
        trouve = self.get(cle)
        if trouve is not None:
            return trouve
        valeur = calculer()
        self[cle] = valeur
        return valeur
