"""Tests de la lecture de la mémoire partagée, sans le jeu.

Une vraie mémoire nommée est créée par le test, remplie avec les décalages de
`memoire_lmu.py`. Ces tests prouvent donc que la lecture est cohérente avec ces
décalages, pas que ces décalages sont ceux du jeu : c'est le rôle de
`tools/sonde_live.py`, jeu lancé.
"""

from __future__ import annotations

import ctypes
import itertools
import json
import math
import struct
import threading
import time
from ctypes import wintypes

import pytest

from lmu_telemetry.sources import memoire_lmu as m
from lmu_telemetry.sources import flux_memoire
from tools import sonde_live as sonde

_noms = itertools.count()


class FausseMemoire:
    """Une mémoire partagée nommée, tenue par le test à la place du jeu."""

    def __init__(self, taille: int = m.TAILLE_MEMOIRE) -> None:
        self.nom = f"LMU_Test_{id(self)}_{next(_noms)}"
        self.noyau = ctypes.WinDLL("kernel32", use_last_error=True)
        self.noyau.CreateFileMappingW.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        ]
        self.noyau.CreateFileMappingW.restype = wintypes.HANDLE
        self.noyau.MapViewOfFile.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_size_t,
        ]
        self.noyau.MapViewOfFile.restype = ctypes.c_void_p
        self.noyau.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self.noyau.CloseHandle.argtypes = [wintypes.HANDLE]
        self.poignee = self.noyau.CreateFileMappingW(
            wintypes.HANDLE(-1), None, 0x04, 0, taille, self.nom
        )
        assert self.poignee
        self.adresse = self.noyau.MapViewOfFile(self.poignee, 0xF001F, 0, 0, 0)
        assert self.adresse

    def ecrire(self, decalage: int, brut: bytes) -> None:
        ctypes.memmove(self.adresse + decalage, brut, len(brut))

    def champ(self, base: int, champs: dict, nom: str, *valeurs) -> None:
        decalage, format_ = champs[nom]
        self.ecrire(base + decalage, struct.pack(format_, *valeurs))

    def fermer(self) -> None:
        self.noyau.UnmapViewOfFile(self.adresse)
        self.noyau.CloseHandle(self.poignee)

    # ------------------------------------------------------------------

    def preparer(self, indice_telemetrie: int = 1, indice_scoring: int = 2) -> None:
        """Une session à deux voitures de plus, le joueur à des places différentes."""
        self.ecrire(m.DEBUT_ENTETE_TELEMETRIE, bytes([3, indice_telemetrie, 1]))
        self.champ(m.DEBUT_SCORING, m.CHAMPS_SCORING, "vehicules", 3)
        self.champ(m.DEBUT_SCORING, m.CHAMPS_SCORING, "circuit", b"Monza")
        self.champ(m.DEBUT_SCORING, m.CHAMPS_SCORING, "en_piste", True)
        self.base_telemetrie = m.DEBUT_TELEMETRIE + indice_telemetrie * m.TAILLE_TELEMETRIE
        self.base_vehicule = m.DEBUT_VEHICULES + indice_scoring * m.TAILLE_VEHICULE
        self.champ(self.base_telemetrie, m.CHAMPS_TELEMETRIE, "circuit", b"Monza")
        self.champ(self.base_telemetrie, m.CHAMPS_TELEMETRIE, "modele", b"BMW M4 GT3")
        self.champ(self.base_vehicule, m.CHAMPS_VEHICULE, "joueur", True)


@pytest.fixture
def jeu():
    memoire = FausseMemoire()
    memoire.preparer()
    yield memoire
    memoire.fermer()


# ----------------------------------------------------------------------
# Disposition
# ----------------------------------------------------------------------


def test_les_blocs_se_suivent_sans_se_chevaucher():
    assert m.DEBUT_SCORING + m.TAILLE_SCORING <= m.DEBUT_VEHICULES
    fin_vehicules = m.DEBUT_VEHICULES + m.EMPLACEMENTS * m.TAILLE_VEHICULE
    assert fin_vehicules + 65_536 == m.DEBUT_ENTETE_TELEMETRIE
    fin_telemetrie = m.DEBUT_TELEMETRIE + m.EMPLACEMENTS * m.TAILLE_TELEMETRIE
    assert fin_telemetrie <= m.TAILLE_MEMOIRE


def test_le_size_t_du_scoring_est_aligne_sur_huit_octets():
    # 548 octets de ScoringInfoV01, puis 4 de remplissage : c'est le piège du
    # changement de règle d'alignement entre les deux en-têtes.
    assert m.DEBUT_VEHICULES - m.DEBUT_SCORING == 552 + 8


@pytest.mark.parametrize(
    "champs, taille",
    [
        (m.CHAMPS_TELEMETRIE, m.DEBUT_ROUES),
        (m.CHAMPS_ROUE, m.TAILLE_ROUE),
        (m.CHAMPS_VEHICULE, m.TAILLE_VEHICULE),
        (m.CHAMPS_SCORING, m.TAILLE_SCORING),
    ],
)
def test_aucun_champ_ne_deborde_de_son_bloc(champs, taille):
    for decalage, format_ in champs.values():
        assert decalage + struct.calcsize(format_) <= taille


# ----------------------------------------------------------------------
# Lecture
# ----------------------------------------------------------------------


def test_lit_le_joueur_meme_a_des_places_differentes(jeu):
    jeu.champ(jeu.base_telemetrie, m.CHAMPS_TELEMETRIE, "temps", 123.5)
    jeu.champ(jeu.base_telemetrie, m.CHAMPS_TELEMETRIE, "gaz_brut", 0.75)
    jeu.champ(jeu.base_vehicule, m.CHAMPS_VEHICULE, "distance_tour", 1500.25)
    with m.LecteurMemoire(jeu.nom) as memoire:
        lecture = memoire.lire()
    telemetrie = m.decoder(lecture.telemetrie, m.CHAMPS_TELEMETRIE)
    assert telemetrie["temps"] == 123.5
    assert telemetrie["gaz_brut"] == 0.75
    assert telemetrie["circuit"] == "Monza"
    assert telemetrie["modele"] == "BMW M4 GT3"
    assert m.decoder(lecture.vehicule, m.CHAMPS_VEHICULE)["distance_tour"] == 1500.25


def test_lit_les_quatre_roues(jeu):
    for i in range(4):
        base = jeu.base_telemetrie + m.DEBUT_ROUES + i * m.TAILLE_ROUE
        jeu.champ(base, m.CHAMPS_ROUE, "rotation", -100.0 - i)
        jeu.champ(base, m.CHAMPS_ROUE, "rayon_cm", 33 + i)
    with m.LecteurMemoire(jeu.nom) as memoire:
        roues = m.decoder_roues(memoire.lire().telemetrie)
    assert [r["rotation"] for r in roues] == [-100.0, -101.0, -102.0, -103.0]
    assert [r["rayon_cm"] for r in roues] == [33, 34, 35, 36]


def test_retrouve_le_joueur_quand_il_change_de_place(jeu):
    with m.LecteurMemoire(jeu.nom) as memoire:
        assert memoire.lire().vehicule is not None
        jeu.champ(jeu.base_vehicule, m.CHAMPS_VEHICULE, "joueur", False)
        jeu.base_vehicule = m.DEBUT_VEHICULES
        jeu.champ(jeu.base_vehicule, m.CHAMPS_VEHICULE, "joueur", True)
        jeu.champ(jeu.base_vehicule, m.CHAMPS_VEHICULE, "distance_tour", 42.0)
        vehicule = memoire.lire().vehicule
    assert m.decoder(vehicule, m.CHAMPS_VEHICULE)["distance_tour"] == 42.0


def test_sans_voiture_il_n_y_a_rien_a_lire(jeu):
    jeu.ecrire(m.DEBUT_ENTETE_TELEMETRIE, bytes([0, 0, 0]))
    with m.LecteurMemoire(jeu.nom) as memoire:
        assert memoire.lire() is None


def test_la_vue_est_en_lecture_seule(jeu):
    with m.LecteurMemoire(jeu.nom) as memoire:
        assert memoire.protection == 2  # PAGE_READONLY


def test_jeu_absent_donne_un_message_qui_dit_quoi_faire():
    with pytest.raises(m.MemoireAbsente, match="Enable Plugins"):
        m.LecteurMemoire("LMU_Test_memoire_qui_n_existe_pas")


def test_memoire_trop_petite_est_refusee():
    petite = FausseMemoire(taille=64 * 1024)
    try:
        with pytest.raises(m.MemoireInattendue, match="mise à jour"):
            m.LecteurMemoire(petite.nom)
    finally:
        petite.fermer()


def test_une_lecture_dechiree_est_recommencee(jeu, monkeypatch):
    with m.LecteurMemoire(jeu.nom) as memoire:
        copies = iter([b"a", b"b", b"c", b"c"])
        monkeypatch.setattr(m.ctypes, "string_at", lambda *_: next(copies))
        assert memoire._copier(0, 1) == b"c"
        monkeypatch.undo()
        assert memoire.dechirures == 1
        assert memoire.abandons == 0


def test_une_ecriture_permanente_fait_abandonner_le_bloc(jeu, monkeypatch):
    with m.LecteurMemoire(jeu.nom) as memoire:
        copies = (bytes([i % 256]) for i in itertools.count())
        monkeypatch.setattr(m.ctypes, "string_at", lambda *_: next(copies))
        assert memoire._copier(0, 1) is None
        monkeypatch.undo()
        assert memoire.dechirures == m.ESSAIS_LECTURE
        assert memoire.abandons == 1


# ----------------------------------------------------------------------
# Sonde
# ----------------------------------------------------------------------


def test_une_capture_se_relit_a_l_identique(tmp_path):
    chemin = tmp_path / "capture.bin"
    with chemin.open("wb") as flux:
        flux.write(flux_memoire.ENTETE_CAPTURE)
        flux_memoire.ecrire_enregistrement(flux, flux_memoire.TYPE_TELEMETRIE, 1.5, b"abc")
        flux_memoire.ecrire_enregistrement(flux, flux_memoire.TYPE_SCORING, 2.5, b"de")
    assert list(flux_memoire.relire_capture(chemin)) == [
        (flux_memoire.TYPE_TELEMETRIE, 1.5, b"abc"),
        (flux_memoire.TYPE_SCORING, 2.5, b"de"),
    ]


def test_une_capture_coupee_rend_ce_qu_elle_contient(tmp_path):
    chemin = tmp_path / "capture.bin"
    with chemin.open("wb") as flux:
        flux.write(flux_memoire.ENTETE_CAPTURE)
        flux_memoire.ecrire_enregistrement(flux, flux_memoire.TYPE_TELEMETRIE, 1.5, b"abc")
        flux.write(flux_memoire.ENREGISTREMENT.pack(flux_memoire.TYPE_SCORING, 2.5, 100))
        flux.write(b"tronque")
    assert len(list(flux_memoire.relire_capture(chemin))) == 1


def test_sans_jeu_la_sonde_le_dit_et_s_arrete(tmp_path):
    rapport = sonde.sonder(tmp_path, nom="LMU_Test_absente", attente=0.0)
    assert rapport["fin"] == "jeu non détecté"
    assert (tmp_path / "rapport.json").exists()


def _simuler_tour(jeu: FausseMemoire, arret: threading.Event, vitesse: float) -> None:
    """Le jeu : télémétrie à 100 Hz, distance à 5 Hz, un blocage de roue au milieu."""
    temps = 100.0
    distance = 0.0
    rayon_cm = 33
    pas = 0.01
    tic = 0
    while not arret.is_set():
        temps += pas
        tic += 1
        distance += vitesse * pas
        bloque = 30 <= tic % 100 < 50
        base = jeu.base_telemetrie
        jeu.champ(base, m.CHAMPS_TELEMETRIE, "temps", temps)
        jeu.champ(base, m.CHAMPS_TELEMETRIE, "vitesse_locale", 0.0, 0.0, -vitesse)
        jeu.champ(base, m.CHAMPS_TELEMETRIE, "frein", 0.9 if bloque else 0.0)
        jeu.champ(base, m.CHAMPS_TELEMETRIE, "gaz", 0.0 if bloque else 0.3)
        for i in range(4):
            roue = base + m.DEBUT_ROUES + i * m.TAILLE_ROUE
            jeu.champ(roue, m.CHAMPS_ROUE, "rayon_cm", rayon_cm)
            rotation = 0.0 if bloque and i == 0 else vitesse / (rayon_cm / 100)
            jeu.champ(roue, m.CHAMPS_ROUE, "rotation", -rotation)
        if tic % 20 == 0:
            jeu.champ(m.DEBUT_SCORING, m.CHAMPS_SCORING, "temps", temps)
            jeu.champ(jeu.base_vehicule, m.CHAMPS_VEHICULE, "distance_tour", distance)
        time.sleep(pas)


def test_la_sonde_mesure_une_session_simulee(jeu, tmp_path):
    arret = threading.Event()
    simulation = threading.Thread(target=_simuler_tour, args=(jeu, arret, 50.0), daemon=True)
    simulation.start()
    try:
        rapport = sonde.sonder(tmp_path, nom=jeu.nom, roulage=1.5, duree_maximale=20.0)
    finally:
        arret.set()
        simulation.join()

    assert rapport["fin"] == "roulage atteint"
    assert rapport["memoire"]["circuits_concordent"] is True
    assert rapport["memoire"]["lecture_seule"] is True
    assert rapport["memoire"]["modele"] == "BMW M4 GT3"
    assert rapport["debits_hz"]["telemetrie"] == pytest.approx(100, rel=0.05)
    assert rapport["debits_hz"]["distance_tour"] == pytest.approx(5, rel=0.1)
    assert rapport["erreur_distance_m"]["max"] < 1.0
    # La roue avant gauche se bloque à chaque freinage simulé.
    assert rapport["glissements"]["freinage"]["rotation"]["max"] == pytest.approx(1.0)
    assert "gaz_brut" in rapport["champs_nuls"]["telemetrie"]

    enregistre = json.loads((tmp_path / "rapport.json").read_text(encoding="utf-8"))
    assert enregistre["roulage_s"] >= 1.5
    types = {t for t, _, _ in flux_memoire.relire_capture(tmp_path / "capture.bin")}
    assert types == {flux_memoire.TYPE_TELEMETRIE, flux_memoire.TYPE_VEHICULE, flux_memoire.TYPE_SCORING}
    assert (tmp_path / "image-1.bin").stat().st_size == m.TAILLE_MEMOIRE


def _lecture(temps: float, modele: bytes) -> m.Lecture:
    telemetrie = bytearray(m.TAILLE_TELEMETRIE)
    struct.pack_into("<d", telemetrie, m.CHAMPS_TELEMETRIE["temps"][0], temps)
    struct.pack_into("30s", telemetrie, m.CHAMPS_TELEMETRIE["modele"][0], modele)
    return m.Lecture(bytes(telemetrie), None, bytes(m.TAILLE_SCORING))


def test_une_nouvelle_session_efface_les_images_de_la_precedente():
    bilan = sonde.Bilan()
    bilan.ajouter_telemetrie(_lecture(379.1, b"Mercedes-AMG LMGT3"))
    bilan.ajouter_telemetrie(_lecture(0.0, b"Ferrari 499P"))
    bilan.ajouter_telemetrie(_lecture(0.01, b"Ferrari 499P"))
    assert [t["modele"] for t in bilan.telemetrie] == ["Ferrari 499P", "Ferrari 499P"]
    assert len(bilan.roues) == 2


def test_le_resume_signale_une_structure_douteuse():
    bilan = sonde.Bilan()
    texte = sonde.resume(bilan.rapport(None, "arrêt manuel"))
    assert "À VÉRIFIER" in texte


def test_la_vitesse_vient_de_la_vitesse_locale():
    assert sonde._vitesse({"vitesse_locale": (3.0, 100.0, -4.0)}) == pytest.approx(
        math.hypot(3.0, 100.0, -4.0)
    )


# ----------------------------------------------------------------------
# Le jeu lui-même
# ----------------------------------------------------------------------


def test_identifiant_jeu_ne_trouve_pas_un_jeu_absent(monkeypatch):
    monkeypatch.setattr(m, "NOM_JEU", "Programme inexistant.exe")
    assert m.identifiant_jeu() is None


def test_identifiant_jeu_reconnait_un_processus(monkeypatch):
    """La mémoire ne suffit pas : SimHub la garde ouverte une fois le jeu fermé."""
    import sys
    from pathlib import Path

    monkeypatch.setattr(m, "NOM_JEU", Path(sys.executable).name)
    assert m.identifiant_jeu() is not None
