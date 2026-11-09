"""Lecture en direct de la mémoire partagée de Le Mans Ultimate.

C'EST LE SEUL MODULE QUI CONNAÎT LA DISPOSITION DE CETTE MÉMOIRE.

Il joue pour le direct le rôle que `reader.py` joue pour les fichiers : si une
mise à jour de LMU déplace un champ, c'est ici, et ici seulement, qu'on corrige.

--------------------------------------------------------------------------
Quelle mémoire
--------------------------------------------------------------------------

Deux mémoires partagées existent sur une machine de joueur :

* `LMU_Data`, publiée par le jeu lui-même, documentée par les en-têtes livrés
  dans `<jeu>\\Support\\SharedMemoryInterface` ;
* celles du plugin tiers rFactor2SharedMemoryMapPlugin64, dont la version
  installée date de 2023.

On lit `LMU_Data` : c'est l'interface officielle, et elle seule porte les
champs ajoutés par LMU (`mLapInvalidated`, `mABSActive`, `mTCActive`,
`mVehicleModel`). Elle suit la structure de rFactor 2, étendue.

Les en-têtes interdisent la redistribution : ils ne sont pas copiés dans ce
dépôt. On ne garde ici que les décalages des champs utiles.

--------------------------------------------------------------------------
Comment les décalages ont été obtenus
--------------------------------------------------------------------------

Calculés le 2026-11-06 à partir des en-têtes, jeu en version 1.4200. Deux
règles d'alignement cohabitent, et c'est le piège :

* `InternalsPlugin.hpp` est compilé en `#pragma pack(4)` : les `double` n'y sont
  alignés que sur 4 octets ;
* `SharedMemoryInterface.hpp` est inclus APRÈS le `pack(pop)` : ses structures
  suivent l'alignement naturel. Le `size_t scoringStreamSize` qui suit
  `ScoringInfoV01` (548 octets) tombe donc à 552 et non à 548, et tout ce qui
  vient après est décalé de 4 octets.

`tools/sonde_live.py` confronte ces décalages à la mémoire réelle. Fait le
2026-11-06 sur deux sessions à Monza, en Mercedes-AMG LMGT3 et en Ferrari 499P :
le même circuit se lit dans les deux blocs, et vitesse, pédales et volant
coïncident avec le fichier que le jeu écrivait au même moment (corrélation
1,0000, même horloge). Voir docs/12-memoire-partagee.md.

--------------------------------------------------------------------------
Les champs à ne pas croire
--------------------------------------------------------------------------

Présents dans les en-têtes, mais que le jeu ne remplit pas. Ils restent dans les
tables pour que la sonde les surveille d'une version à l'autre :

* `tour_invalide` : resté faux sur des tours que le jeu n'a pas chronométrés.
  Se fier à `compte_tour`, qui passe de 2 à 1 à l'instant de l'infraction, lu à
  la ligne parce que le jeu peut pardonner en cours de tour, et à `dernier_tour`,
  qui vaut alors -1 ;
* `debattement_volant` : toujours 0. Le volant reste donc en pourcentage ;
* `charge` et `part_glissante` : remplis en Hypercar, à 0 en GT3.

--------------------------------------------------------------------------
Pourquoi on ne prend pas le verrou
--------------------------------------------------------------------------

Le SDK fournit un verrou, `SharedMemoryLock`, et le jeu le prend lui aussi pour
écrire : ses journaux contiennent `Failed to acquire SharedMemoryLock in
FlushTimeCritical` quand il ne l'obtient pas. Le prendre depuis Python ferait
courir le risque de gêner le jeu : le ramasse-miettes ou un changement de fil
peuvent suspendre le programme pendant qu'il le détient. Il faut de plus une
opération atomique, que `kernel32` n'exporte pas sur x64 (vérifié : ni
`InterlockedCompareExchange` ni ses voisines).

On lit donc sans verrou, avec une vue en lecture seule : rien de ce que fait ce
module ne peut retarder le jeu. La contrepartie est qu'une lecture peut tomber
pendant une écriture. On copie donc chaque bloc deux fois : deux copies
identiques font foi, sinon on recommence. Le bloc du joueur ne pèse que
1 888 octets ; la double copie reste négligeable.
"""

from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from dataclasses import dataclass

from ..errors import ErreurTelemetrie

NOM_MEMOIRE = "LMU_Data"

#: Le processus du jeu.
NOM_JEU = "Le Mans Ultimate.exe"

#: Taille de `SharedMemoryLayout`, alignement de fin compris.
TAILLE_MEMOIRE = 324_824

#: Décalages dans `SharedMemoryLayout`.
DEBUT_VERSION_JEU = 64
DEBUT_SCORING = 1_632
DEBUT_VEHICULES = 2_192
DEBUT_ENTETE_TELEMETRIE = 128_464
DEBUT_TELEMETRIE = 128_468

TAILLE_SCORING = 548
TAILLE_VEHICULE = 584
TAILLE_TELEMETRIE = 1_888

#: Nombre d'emplacements des tableaux de véhicules.
EMPLACEMENTS = 104

#: `mWheel`, à la fin de `TelemInfoV01` : AVG, AVD, ARG, ARD, comme dans les
#: fichiers de télémétrie.
DEBUT_ROUES = 848
TAILLE_ROUE = 260

#: Copies tentées avant de renoncer à un bloc. Le jeu écrit à 100 Hz et une
#: écriture dure quelques microsecondes : deux essais suffisent presque toujours.
ESSAIS_LECTURE = 4

#: Champs lus, par bloc : nom -> (décalage, format `struct`). Un format en
#: « s » désigne une chaîne de longueur fixe.
CHAMPS_TELEMETRIE = {
    "id": (0, "<i"),
    "pas_temps": (4, "<d"),
    "temps": (12, "<d"),
    "tour": (20, "<i"),
    "debut_tour": (24, "<d"),
    "voiture": (32, "64s"),
    "circuit": (96, "64s"),
    "position": (160, "<3d"),
    "vitesse_locale": (184, "<3d"),
    "acceleration_locale": (208, "<3d"),
    "rotation_locale": (304, "<3d"),
    "rapport": (352, "<i"),
    "regime": (356, "<d"),
    "gaz_brut": (388, "<d"),
    "frein_brut": (396, "<d"),
    "volant_brut": (404, "<d"),
    "gaz": (420, "<d"),
    "frein": (428, "<d"),
    "volant": (436, "<d"),
    "choc_temps": (552, "<d"),
    "choc_force": (560, "<d"),
    "secteur": (600, "<i"),
    "limiteur": (604, "<B"),
    "debattement_volant": (692, "<f"),
    "delta_meilleur": (696, "<d"),
    "tour_invalide": (745, "<?"),
    "abs_actif": (746, "<?"),
    "tc_actif": (747, "<?"),
    "niveau_tc": (750, "<B"),
    "niveau_abs": (756, "<B"),
    "limites_piste": (767, "<B"),
    "modele": (796, "30s"),
}

CHAMPS_ROUE = {
    "pression_frein": (32, "<d"),
    "rotation": (40, "<d"),
    "vitesse_patch_laterale": (48, "<d"),
    "vitesse_patch_longitudinale": (56, "<d"),
    "vitesse_sol_longitudinale": (72, "<d"),
    "charge": (104, "<d"),
    "part_glissante": (112, "<d"),
    "surface": (176, "<B"),
    "rayon_cm": (179, "<B"),
    "temperature_carcasse": (204, "<d"),
    "temperature_optimale": (236, "<f"),
}

#: Le scoring de chaque voiture, joueur compris. Ce qui sert à l'ingénieur de course :
#: place, écarts, secteurs, stands, pénalités, drapeaux. Les temps de secteur sont
#: cumulés depuis la ligne, comme dans les fichiers.
CHAMPS_VEHICULE = {
    "id": (0, "<i"),
    "pilote": (4, "32s"),
    "voiture": (36, "64s"),
    "tours_boucles": (100, "<h"),
    "secteur": (102, "<b"),
    "arrivee": (103, "<b"),
    "distance_tour": (104, "<d"),
    "ecart_lateral": (112, "<d"),
    "bord_piste": (120, "<d"),
    "meilleur_s1": (128, "<d"),
    "meilleur_s2": (136, "<d"),
    "meilleur_tour": (144, "<d"),
    "dernier_s1": (152, "<d"),
    "dernier_s2": (160, "<d"),
    "dernier_tour": (168, "<d"),
    "courant_s1": (176, "<d"),
    "courant_s2": (184, "<d"),
    "arrets": (192, "<h"),
    "penalites": (194, "<h"),
    "joueur": (196, "<?"),
    "controle": (197, "<b"),
    "aux_stands": (198, "<?"),
    "place": (199, "<B"),
    "classe": (200, "32s"),
    "ecart_devant": (232, "<d"),
    "tours_devant": (240, "<i"),
    "ecart_leader": (244, "<d"),
    "tours_leader": (252, "<i"),
    "debut_tour": (256, "<d"),
    "position": (264, "<3d"),
    "vitesse_locale": (288, "<3d"),
    "etat_stands": (457, "<B"),
    "temps_dans_tour": (464, "<d"),
    "tour_estime": (472, "<d"),
    "drapeau": (504, "<B"),
    "sous_jaune": (505, "<?"),
    "compte_tour": (506, "<B"),
    "au_garage": (507, "<?"),
}

#: Après `longueur_tour` vient un pointeur, de 8 octets : tout ce qui suit est décalé
#: d'autant par rapport à la version 32 bits de la structure.
CHAMPS_SCORING = {
    "circuit": (0, "64s"),
    "session": (64, "<i"),
    "temps": (68, "<d"),
    "fin": (76, "<d"),
    "tours_maximum": (84, "<i"),
    "longueur_tour": (88, "<d"),
    "vehicules": (104, "<i"),
    "phase": (108, "<B"),
    "drapeau_jaune": (109, "<b"),
    "drapeaux_secteurs": (110, "<3b"),
    "feux": (113, "<B"),
    "en_piste": (115, "<?"),
    "pluie": (220, "<d"),
    "temperature_air": (228, "<d"),
    "temperature_piste": (236, "<d"),
    "humidite_moyenne": (332, "<d"),
    "temps_restant": (340, "<f"),
}

#: Décalage de `mIsPlayer` dans un `VehicleScoringInfoV01`.
_DECALAGE_JOUEUR = CHAMPS_VEHICULE["joueur"][0]

_FILE_MAP_READ = 0x0004
_ERREUR_FICHIER_ABSENT = 2
_TH32CS_SNAPPROCESS = 0x00000002
_POIGNEE_INVALIDE = ctypes.c_void_p(-1).value


class MemoireAbsente(ErreurTelemetrie):
    """La mémoire n'existe pas : le jeu n'est pas lancé."""

    def __init__(self, nom: str) -> None:
        super().__init__(
            f"La mémoire partagée « {nom} » est introuvable : Le Mans Ultimate n'est "
            "pas lancé, ou l'option « Enable Plugins » n'est pas activée dans "
            "Paramètres > Gameplay. Après l'avoir activée, redémarre le jeu."
        )


class MemoireInattendue(ErreurTelemetrie):
    """La mémoire existe mais n'a pas la taille attendue."""

    def __init__(self, taille: int) -> None:
        super().__init__(
            f"La mémoire partagée fait {taille} octets, moins que les "
            f"{TAILLE_MEMOIRE} attendus : une mise à jour du jeu a sans doute "
            "changé sa structure, l'outil doit être adapté."
        )


class _Infos(ctypes.Structure):
    """`MEMORY_BASIC_INFORMATION`, pour connaître la taille réelle de la vue."""

    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class _Processus(ctypes.Structure):
    """`PROCESSENTRY32W`."""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _noyau() -> ctypes.WinDLL:
    noyau = ctypes.WinDLL("kernel32", use_last_error=True)
    noyau.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    noyau.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    noyau.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Processus)]
    noyau.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Processus)]
    noyau.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    noyau.OpenFileMappingW.restype = wintypes.HANDLE
    noyau.MapViewOfFile.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    noyau.MapViewOfFile.restype = ctypes.c_void_p
    noyau.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    noyau.UnmapViewOfFile.restype = wintypes.BOOL
    noyau.CloseHandle.argtypes = [wintypes.HANDLE]
    noyau.CloseHandle.restype = wintypes.BOOL
    noyau.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    noyau.VirtualQuery.restype = ctypes.c_size_t
    return noyau


def identifiant_jeu() -> int | None:
    """L'identifiant du processus du jeu, s'il tourne.

    Que la mémoire existe ne prouve rien : elle survit au jeu tant qu'un autre programme
    la tient ouverte, et SimHub le fait. On y lit alors, sans fin, la dernière image de
    la dernière session, comme si la voiture était encore en piste.

    Rien n'ouvre le processus : un jeu sous anti-triche pourrait le refuser.
    """
    noyau = _noyau()
    instantane = noyau.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if instantane == _POIGNEE_INVALIDE:
        return None
    try:
        processus = _Processus()
        processus.dwSize = ctypes.sizeof(_Processus)
        suite = noyau.Process32FirstW(instantane, ctypes.byref(processus))
        while suite:
            if processus.szExeFile.lower() == NOM_JEU.lower():
                return processus.th32ProcessID
            suite = noyau.Process32NextW(instantane, ctypes.byref(processus))
        return None
    finally:
        noyau.CloseHandle(instantane)


def decoder(brut: bytes, champs: dict[str, tuple[int, str]], base: int = 0) -> dict:
    """Extrait des champs d'un bloc brut.

    Les chaînes sont coupées au premier octet nul. Un format à plusieurs valeurs
    (`<3d`) donne un tuple, les autres une valeur simple.
    """
    valeurs = {}
    for nom, (decalage, format_) in champs.items():
        lu = struct.unpack_from(format_, brut, base + decalage)
        if format_.endswith("s"):
            valeurs[nom] = lu[0].split(b"\0", 1)[0].decode("utf-8", "replace")
        else:
            valeurs[nom] = lu[0] if len(lu) == 1 else lu
    return valeurs


def decoder_plateau(brut: bytes) -> list[dict]:
    """Le scoring de toutes les voitures d'une copie faite par `LecteurMemoire.plateau`."""
    return [
        decoder(brut, CHAMPS_VEHICULE, i * TAILLE_VEHICULE)
        for i in range(len(brut) // TAILLE_VEHICULE)
    ]


def decoder_roues(brut: bytes) -> list[dict]:
    """Les quatre roues d'un bloc de télémétrie, dans l'ordre AVG, AVD, ARG, ARD."""
    return [
        decoder(brut, CHAMPS_ROUE, DEBUT_ROUES + i * TAILLE_ROUE) for i in range(4)
    ]


@dataclass(frozen=True)
class Lecture:
    """Une photo cohérente de ce qui concerne le joueur."""

    telemetrie: bytes
    """`TelemInfoV01` du joueur, tel quel."""

    vehicule: bytes | None
    """`VehicleScoringInfoV01` du joueur, ou None si le jeu ne l'a pas encore publié."""

    scoring: bytes
    """`ScoringInfoV01`, tel quel."""


class LecteurMemoire:
    """Accès en lecture seule à la mémoire partagée de LMU.

    À utiliser comme gestionnaire de contexte :

        with LecteurMemoire() as memoire:
            lecture = memoire.lire()

    La vue est ouverte avec FILE_MAP_READ : ce module ne peut rien écrire dans
    la mémoire du jeu, et n'y prend aucun verrou (voir en tête de module).
    """

    def __init__(self, nom: str = NOM_MEMOIRE) -> None:
        self.nom = nom
        self.dechirures = 0
        """Copies qui différaient : la lecture est tombée pendant une écriture."""

        self.abandons = 0
        """Blocs auxquels on a renoncé après `ESSAIS_LECTURE` copies différentes."""

        self._noyau = _noyau()
        self._indice_joueur: int | None = None

        self._poignee = self._noyau.OpenFileMappingW(_FILE_MAP_READ, False, nom)
        if not self._poignee:
            erreur = ctypes.get_last_error()
            if erreur == _ERREUR_FICHIER_ABSENT:
                raise MemoireAbsente(nom)
            raise ctypes.WinError(erreur)

        self._adresse = self._noyau.MapViewOfFile(self._poignee, _FILE_MAP_READ, 0, 0, 0)
        if not self._adresse:
            erreur = ctypes.get_last_error()
            self._noyau.CloseHandle(self._poignee)
            raise ctypes.WinError(erreur)

        self.taille = self._infos_vue().RegionSize
        if self.taille < TAILLE_MEMOIRE:
            taille = self.taille
            self.fermer()
            raise MemoireInattendue(taille)

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def __enter__(self) -> "LecteurMemoire":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.fermer()

    def fermer(self) -> None:
        if self._adresse:
            self._noyau.UnmapViewOfFile(self._adresse)
            self._adresse = None
        if self._poignee:
            self._noyau.CloseHandle(self._poignee)
            self._poignee = None

    def _infos_vue(self) -> _Infos:
        infos = _Infos()
        self._noyau.VirtualQuery(self._adresse, ctypes.byref(infos), ctypes.sizeof(infos))
        return infos

    @property
    def protection(self) -> int:
        """Protection de la vue, au sens de Windows : PAGE_READONLY vaut 2."""
        return self._infos_vue().Protect

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def _copier(self, decalage: int, taille: int) -> bytes | None:
        """Copie un bloc, deux fois, jusqu'à obtenir deux copies identiques."""
        adresse = self._adresse + decalage
        for _ in range(ESSAIS_LECTURE):
            premiere = ctypes.string_at(adresse, taille)
            if premiere == ctypes.string_at(adresse, taille):
                return premiere
            self.dechirures += 1
        self.abandons += 1
        return None

    def _vehicule_joueur(self, nombre: int) -> bytes | None:
        """Bloc de scoring du joueur.

        Les tableaux de scoring et de télémétrie n'ont pas de raison d'être dans
        le même ordre : on cherche `mIsPlayer`, et on retient la place trouvée
        pour ne pas tout reparcourir à chaque lecture.
        """

        def est_joueur(indice: int) -> bool:
            adresse = DEBUT_VEHICULES + indice * TAILLE_VEHICULE + _DECALAGE_JOUEUR
            return ctypes.string_at(self._adresse + adresse, 1) != b"\0"

        if self._indice_joueur is None or not est_joueur(self._indice_joueur):
            self._indice_joueur = next(
                (i for i in range(min(nombre, EMPLACEMENTS)) if est_joueur(i)), None
            )
        if self._indice_joueur is None:
            return None
        return self._copier(
            DEBUT_VEHICULES + self._indice_joueur * TAILLE_VEHICULE, TAILLE_VEHICULE
        )

    def lire(self) -> Lecture | None:
        """Photo du joueur, ou None s'il n'a pas de voiture en piste.

        None vaut aussi quand une copie n'a pas pu aboutir : pour l'appelant,
        c'est simplement un échantillon de moins.
        """
        entete = ctypes.string_at(self._adresse + DEBUT_ENTETE_TELEMETRIE, 3)
        actifs, indice, present = entete[0], entete[1], entete[2]
        if not present or indice >= max(actifs, 1):
            return None

        scoring = self._copier(DEBUT_SCORING, TAILLE_SCORING)
        telemetrie = self._copier(
            DEBUT_TELEMETRIE + indice * TAILLE_TELEMETRIE, TAILLE_TELEMETRIE
        )
        if scoring is None or telemetrie is None:
            return None
        nombre = decoder(scoring, {"n": CHAMPS_SCORING["vehicules"]})["n"]
        return Lecture(telemetrie, self._vehicule_joueur(nombre), scoring)

    def plateau(self, nombre: int) -> bytes | None:
        """Le scoring des `nombre` premières voitures, d'une seule copie cohérente.

        Le tableau fait 584 octets par voiture : 23 ko pour 40 voitures, de quoi le
        copier deux fois à chaque mise à jour du scoring sans gêner personne.
        """
        nombre = max(0, min(nombre, EMPLACEMENTS))
        return self._copier(DEBUT_VEHICULES, nombre * TAILLE_VEHICULE) if nombre else None

    def voitures_telemetrie(self) -> int:
        """Nombre de voitures dont la télémétrie complète est publiée."""
        return ctypes.string_at(self._adresse + DEBUT_ENTETE_TELEMETRIE, 1)[0]

    def version_jeu(self) -> int:
        """`gameVersion`, tel que le jeu le publie."""
        brut = ctypes.string_at(self._adresse + DEBUT_VERSION_JEU, 4)
        return struct.unpack("<i", brut)[0]

    def image(self) -> bytes:
        """Copie de toute la mémoire, pour l'examiner à tête reposée.

        Elle sert au diagnostic : elle permet de retrouver un champ déplacé sans
        avoir à relancer le jeu.
        """
        return ctypes.string_at(self._adresse, TAILLE_MEMOIRE)
