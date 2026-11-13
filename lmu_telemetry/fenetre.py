"""La fenêtre de l'application : l'interface web, sans bordure ni navigateur.

Les maquettes montrent un vrai programme, avec sa propre barre de titre. La page
reste la même : `pywebview` l'affiche dans une fenêtre Windows (WebView2, le
moteur d'Edge, déjà présent sur Windows 10 et 11).

--------------------------------------------------------------------------
Déplacer et redimensionner une fenêtre sans bordure
--------------------------------------------------------------------------

Sans bordure, Windows ne fournit plus ni barre à saisir ni côtés à tirer. La page
dessine donc les siens, et prévient Python au moment où le bouton s'enfonce.
Python suit ensuite la souris lui-même, jusqu'à ce que le bouton se relève.

Deux autres façons ont été écartées :

* suivre la souris dans la page : dès qu'elle sort de la fenêtre, plus aucun
  événement n'arrive, et un geste un peu vif décroche ;
* demander à Windows de prendre la main (`WM_NCLBUTTONDOWN`) : il refuse de
  redimensionner une fenêtre sans bord épais, et lui en donner un fait
  apparaître une bande blanche en haut de la fenêtre.

--------------------------------------------------------------------------
Agrandir
--------------------------------------------------------------------------

Une fenêtre sans bordure agrandie par Windows recouvre la barre des tâches. On
calcule donc soi-même la zone de travail de l'écran où elle se trouve.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
import traceback
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

TITRE = "GhostLine for LMU"

#: Pourquoi la fenêtre n'a pas pu s'ouvrir, la dernière fois : le lanceur le note dans
#: `journal.txt` avant de se rabattre sur le navigateur.
ERREUR: str | None = None

#: Taille d'ouverture, celle des maquettes, et taille en deçà de laquelle la page
#: n'a plus la place d'afficher ses colonnes.
LARGEUR, HAUTEUR = 1460, 880
LARGEUR_MINIMALE, HAUTEUR_MINIMALE = 1120, 680

#: Fréquence (Hz) du suivi de la souris pendant un déplacement.
FREQUENCE_SUIVI = 120

_VK_LBUTTON = 0x01
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_NOSIZE = 0x0001
_MONITOR_DEFAULTTONEAREST = 2
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_SW_RESTORE = 9


@dataclass(frozen=True)
class Rectangle:
    """Un rectangle d'écran, en pixels physiques."""

    gauche: int
    haut: int
    droite: int
    bas: int

    @property
    def largeur(self) -> int:
        return self.droite - self.gauche

    @property
    def hauteur(self) -> int:
        return self.bas - self.haut


def redimensionne(
    depart: Rectangle,
    bord: str,
    dx: int,
    dy: int,
    largeur_min: int = LARGEUR_MINIMALE,
    hauteur_min: int = HAUTEUR_MINIMALE,
) -> Rectangle:
    """Rectangle obtenu en tirant un bord de (dx, dy) depuis `depart`.

    `bord` combine « n », « s », « e » et « o ». Le côté opposé ne bouge jamais :
    arrivé à la taille minimale, le bord tiré s'arrête au lieu de pousser la
    fenêtre.
    """
    gauche, haut, droite, bas = depart.gauche, depart.haut, depart.droite, depart.bas
    if "o" in bord:
        gauche = min(depart.gauche + dx, depart.droite - largeur_min)
    if "e" in bord:
        droite = max(depart.droite + dx, depart.gauche + largeur_min)
    if "n" in bord:
        haut = min(depart.haut + dy, depart.bas - hauteur_min)
    if "s" in bord:
        bas = max(depart.bas + dy, depart.haut + hauteur_min)
    return Rectangle(gauche, haut, droite, bas)


class _Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _InfoMoniteur(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", wintypes.DWORD),
    ]


def _rectangle(r: _Rect) -> Rectangle:
    return Rectangle(r.left, r.top, r.right, r.bottom)


class Fenetre:
    """Les gestes que la page demande à la fenêtre.

    Ses méthodes publiques sont appelées depuis la page par pywebview, chacune
    dans un fil à part : c'est ce qui permet à `deplacer` de durer tant que le
    bouton reste enfoncé.

    Les attributs sont privés pour une bonne raison : pywebview parcourt tout ce
    qui est public pour le proposer à la page.
    """

    def __init__(self) -> None:
        self._vue = None
        self._poignee = None
        self._echelle = 1.0
        self._agrandie: Rectangle | None = None
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
        self._user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self._user32.GetCursorPos.argtypes = [ctypes.POINTER(_Point)]
        self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self._user32.GetAsyncKeyState.restype = ctypes.c_short
        self._user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self._user32.MonitorFromWindow.restype = wintypes.HMONITOR
        self._user32.GetMonitorInfoW.argtypes = [
            wintypes.HMONITOR,
            ctypes.POINTER(_InfoMoniteur),
        ]
        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self._user32.GetDpiForWindow.argtypes = [wintypes.HWND]

    def _attacher(self, vue) -> None:
        """Retient la fenêtre pywebview, une fois qu'elle existe."""
        self._vue = vue
        self._poignee = int(vue.native.Handle.ToInt64())
        self._echelle = self._user32.GetDpiForWindow(self._poignee) / 96 or 1.0
        self._arrondir()
        self._centrer()

    def _arrondir(self) -> None:
        """Coins arrondis, comme sur les maquettes. Windows 11 seulement : ailleurs,
        l'appel échoue sans conséquence et les coins restent droits."""
        try:
            preference = ctypes.c_int(_DWMWCP_ROUND)
            ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
                wintypes.HWND(self._poignee),
                _DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )
        except OSError:
            pass

    def _centrer(self) -> None:
        """Taille d'ouverture, centrée dans la zone de travail de l'écran.

        pywebview retire le cadre de la taille qu'on lui donne, et ne tient pas
        compte de la mise à l'échelle de l'écran : la page, elle, se compte en
        pixels mis à l'échelle.
        """
        zone = self._zone_de_travail()
        largeur = min(int(LARGEUR * self._echelle), zone.largeur)
        hauteur = min(int(HAUTEUR * self._echelle), zone.hauteur)
        gauche = zone.gauche + (zone.largeur - largeur) // 2
        haut = zone.haut + (zone.hauteur - hauteur) // 2
        self._placer(Rectangle(gauche, haut, gauche + largeur, haut + hauteur))

    # ------------------------------------------------------------------

    def _rect(self) -> Rectangle:
        r = _Rect()
        self._user32.GetWindowRect(self._poignee, ctypes.byref(r))
        return _rectangle(r)

    def _curseur(self) -> tuple[int, int]:
        p = _Point()
        self._user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def _bouton_enfonce(self) -> bool:
        return bool(self._user32.GetAsyncKeyState(_VK_LBUTTON) & 0x8000)

    def _placer(self, r: Rectangle) -> None:
        self._user32.SetWindowPos(
            self._poignee,
            None,
            r.gauche,
            r.haut,
            r.largeur,
            r.hauteur,
            _SWP_NOZORDER | _SWP_NOACTIVATE,
        )

    def _suivre(self, geste) -> None:
        """Applique `geste(dx, dy)` tant que le bouton de la souris reste enfoncé."""
        x0, y0 = self._curseur()
        derniere = (x0, y0)
        while self._bouton_enfonce():
            x, y = self._curseur()
            if (x, y) != derniere:
                geste(x - x0, y - y0)
                derniere = (x, y)
            time.sleep(1 / FREQUENCE_SUIVI)

    def _zone_de_travail(self) -> Rectangle:
        moniteur = self._user32.MonitorFromWindow(self._poignee, _MONITOR_DEFAULTTONEAREST)
        info = _InfoMoniteur()
        info.cbSize = ctypes.sizeof(info)
        self._user32.GetMonitorInfoW(moniteur, ctypes.byref(info))
        return _rectangle(info.rcWork)

    # ------------------------------------------------------------------
    # Appelé depuis la page
    # ------------------------------------------------------------------

    def deplacer(self) -> None:
        """Suit la souris pour déplacer la fenêtre, tant que le bouton est enfoncé."""
        depart = self._rect()
        if self._agrandie is not None:
            # Saisie agrandie, la fenêtre reprend sa taille sous la souris, à la
            # même proportion de sa largeur : sinon elle sauterait hors de portée.
            x, y = self._curseur()
            proportion = (x - depart.gauche) / max(1, depart.largeur)
            normale = self._agrandie
            self._agrandie = None
            gauche = x - int(proportion * normale.largeur)
            depart = Rectangle(
                gauche, depart.haut, gauche + normale.largeur, depart.haut + normale.hauteur
            )
            self._placer(depart)

        def geste(dx: int, dy: int) -> None:
            self._user32.SetWindowPos(
                self._poignee,
                None,
                depart.gauche + dx,
                depart.haut + dy,
                0,
                0,
                _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_NOSIZE,
            )

        self._suivre(geste)

    def redimensionner(self, bord: str) -> None:
        """Suit la souris pour tirer un bord, tant que le bouton est enfoncé."""
        if self._agrandie is not None:
            return
        depart = self._rect()
        minimum = (
            int(LARGEUR_MINIMALE * self._echelle),
            int(HAUTEUR_MINIMALE * self._echelle),
        )
        self._suivre(
            lambda dx, dy: self._placer(redimensionne(depart, bord, dx, dy, *minimum))
        )

    def reduire(self) -> None:
        self._vue.minimize()

    def agrandir(self) -> bool:
        """Agrandit la fenêtre ou lui rend sa taille. Rend True si elle est agrandie."""
        if self._agrandie is not None:
            self._placer(self._agrandie)
            self._agrandie = None
            return False
        self._agrandie = self._rect()
        self._placer(self._zone_de_travail())
        return True

    def agrandie(self) -> bool:
        return self._agrandie is not None

    def fermer(self) -> None:
        self._vue.destroy()

    def premier_plan(self) -> None:
        """Ramène la fenêtre devant : un second lancement de l'outil le demande."""
        self._user32.ShowWindow(self._poignee, _SW_RESTORE)
        self._user32.SetForegroundWindow(self._poignee)


def retirer_marque_internet(dossier: Path | None = None) -> int:
    """Retire la marque « venu d'Internet » des bibliothèques de l'outil.

    Windows marque ainsi chaque fichier d'un zip téléchargé (le flux NTFS
    `Zone.Identifier`), et .NET refuse alors de charger les bibliothèques de la fenêtre
    (pythonnet, WebView2) : chez qui avait téléchargé l'outil, la fenêtre ne s'ouvrait pas
    et l'outil se rabattait sur le navigateur. Seuls les fichiers de l'outil lui-même sont
    touchés, et seulement dans le .exe (`dossier` sert aux tests). Rend le nombre de
    fichiers débloqués.
    """
    if dossier is None:
        if not getattr(sys, "frozen", False):
            return 0
        dossier = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    debloques = 0
    for fichier in dossier.rglob("*"):
        if fichier.suffix.lower() in (".dll", ".pyd", ".exe"):
            try:
                os.remove(f"{fichier}:Zone.Identifier")
            except OSError:
                continue
            debloques += 1
    return debloques


def ouvrir(adresse: str, avant_ouverture=None) -> bool:
    """Affiche la page dans sa fenêtre, jusqu'à ce qu'on la ferme.

    Rend False si la fenêtre n'a pas pu s'ouvrir, par exemple sans WebView2 :
    l'appelant se rabat alors sur le navigateur. La cause reste dans `ERREUR`.
    """
    global ERREUR
    ERREUR = None
    retirer_marque_internet()
    try:
        import webview
    except ImportError:
        ERREUR = traceback.format_exc(limit=4)
        return False

    fenetre = Fenetre()
    vue = webview.create_window(
        TITRE,
        adresse,
        js_api=fenetre,
        width=LARGEUR,
        height=HAUTEUR,
        min_size=(LARGEUR_MINIMALE, HAUTEUR_MINIMALE),
        frameless=True,
        easy_drag=False,
        background_color="#192633",
    )

    def demarrer() -> None:
        # pywebview appelle cette fonction sans attendre que la fenêtre existe.
        vue.events.shown.wait()
        fenetre._attacher(vue)
        if avant_ouverture is not None:
            avant_ouverture(fenetre)

    try:
        webview.start(demarrer, private_mode=True)
    except Exception:  # noqa: BLE001 — sans WebView2, l'erreur dépend de la machine
        ERREUR = traceback.format_exc(limit=6)
        return False
    return True


if __name__ == "__main__" and sys.platform == "win32":  # pragma: no cover
    threading.current_thread().name = "fenetre"
    ouvrir(sys.argv[1] if len(sys.argv) > 1 else "about:blank")
