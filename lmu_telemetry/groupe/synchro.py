"""La synchronisation avec le groupe : envoyer ses performances, recevoir celles des autres,
et en garder une copie sur ce PC.

La copie (`groupe.json`, dans les données de l'outil) affiche le leaderboard tout de suite à
l'ouverture, et même sans connexion. Elle retient aussi ce qui a déjà été envoyé : chaque
synchronisation n'envoie que les performances nouvelles ou changées, et ne reçoit que ce
qui a changé depuis la dernière (le service numérote ses écritures).

Seules partent les performances du propriétaire qui comptent au leaderboard, ses
qualifications et ses courses en ligne : jamais ses essais, ni ce qu'il joue contre l'IA,
ni les autres pilotes de ses séances (voir `domaine/performances.py`). Avec elles, la
télémétrie de ses records des mêmes séances, un par tracé et par voiture (`tours.py`) : le
groupe n'en reçoit que la liste, et chacun télécharge un tour quand il veut le comparer.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import emplacements
from ..cache import CacheBorne
from ..domaine.donnees_tour import charger
from ..domaine.leaderboard import TYPES_COMPTES, comptee
from ..domaine.performances import Performance, _entier, _nombre, _texte, depuis_json
from ..errors import ErreurTelemetrie
from ..textes import Message
from . import reglages
from .reglages import Adhesion
from .service import ErreurGroupe, Service
from .tours import Record, TourPartage, analyser, decoder, designer, encoder

#: Le fichier de la copie, dans les données de l'outil.
FICHIER = "groupe.json"

#: Le dossier des tours d'amis déjà téléchargés, dans les données de l'outil.
DOSSIER_TOURS = "groupe_tours"

#: Performances par envoi : le service en accepte 200 et 1 Mo.
PAQUET = 100

#: Records envoyés au plus par synchronisation : lire un tour prend un quart de seconde,
#: le reste attend la suivante.
TOURS_PAR_SYNCHRO = 20


def fichier_copie() -> Path:
    return emplacements.donnees() / FICHIER


def dossier_tours() -> Path:
    return emplacements.donnees() / DOSSIER_TOURS


def exporter(record: Record) -> str:
    """La télémétrie d'un record de ce PC, prête à partir."""
    return encoder(charger(record.chemin, record.numero))


def empreinte(donnees: dict) -> str:
    """De quoi savoir si une performance a changé depuis qu'on l'a envoyée."""
    return hashlib.sha1(json.dumps(donnees, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _contour_valide(points: object) -> bool:
    return (
        isinstance(points, list)
        and 3 <= len(points) <= 400
        and all(
            isinstance(p, list)
            and len(p) == 2
            and all(isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) for v in p)
            for p in points
        )
    )


@dataclass
class Copie:
    """Ce que ce PC sait du groupe."""

    code: str
    membre: str
    version: int = 0
    """La dernière version du groupe reçue."""

    membres: list[dict] = field(default_factory=list)
    performances: dict[str, dict[str, dict]] = field(default_factory=dict)
    """Membre -> numéro de performance -> performance, telle que reçue (les autres membres)."""

    contours: dict[str, list] = field(default_factory=dict)
    envoyees: dict[str, str] = field(default_factory=dict)
    """Numéro de performance -> empreinte de ce qui a été envoyé."""

    contours_envoyes: list[str] = field(default_factory=list)
    tours: dict[str, dict[str, dict]] = field(default_factory=dict)
    """Membre -> numéro de record -> ce qu'en montre la liste (sa télémétrie se télécharge
    à la demande)."""

    tours_envoyes: dict[str, str] = field(default_factory=dict)
    """Numéro de record -> signature du tour envoyé (`Record.signature`)."""

    derniere: str | None = None
    """La dernière synchronisation réussie (ISO 8601)."""

    @classmethod
    def lire(cls, adhesion: Adhesion, chemin: Path | None = None) -> Copie:
        """La copie de ce groupe ; une copie neuve si elle manque, ne se lit pas, ou est celle
        d'un autre groupe."""
        try:
            brut = json.loads((chemin or fichier_copie()).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            brut = None
        copie = cls(code=adhesion.code, membre=adhesion.membre)
        if isinstance(brut, dict) and brut.get("code") == adhesion.code and brut.get("membre") == adhesion.membre:
            for nom, attendu in _TYPES.items():
                if isinstance(brut.get(nom), attendu) and not isinstance(brut.get(nom), bool):
                    setattr(copie, nom, brut[nom])
        # Là où elle se réenregistrera (les tests simulent plusieurs PC).
        copie._chemin = chemin
        return copie

    def enregistrer(self, chemin: Path | None = None) -> None:
        """Écrite d'un coup : jamais de copie à moitié écrite."""
        chemin = chemin or getattr(self, "_chemin", None) or fichier_copie()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        provisoire = chemin.with_suffix(".tmp")
        provisoire.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")
        os.replace(provisoire, chemin)

    def vider(self) -> None:
        """Repartir de zéro, comme si rien n'avait été reçu ni envoyé."""
        neuve = Copie(code=self.code, membre=self.membre)
        for nom in _TYPES:
            setattr(self, nom, getattr(neuve, nom))

    def performances_des_autres(self) -> list[Performance]:
        """Les performances des autres membres, celles qui se lisent."""
        return [
            perf
            for membre, liste in self.performances.items()
            if membre != self.membre
            for brut in liste.values()
            if (perf := depuis_json(brut)) is not None
        ]


#: Ce que la copie relit de son fichier, et le type attendu de chaque champ.
_TYPES = {
    "version": int,
    "membres": list,
    "performances": dict,
    "contours": dict,
    "envoyees": dict,
    "contours_envoyes": list,
    "tours": dict,
    "tours_envoyes": dict,
    "derniere": str,
}


def a_envoyer(copie: Copie, miennes: list[Performance]) -> list[dict]:
    """Les performances du propriétaire qui comptent au leaderboard (qualifs et courses en
    ligne : `leaderboard.comptee`) et ont changé depuis leur dernier envoi. Le reste ne
    part pas : le groupe n'en ferait rien."""
    return [
        donnees
        for p in miennes
        if comptee(p) and copie.envoyees.get((donnees := p.json())["id"]) != empreinte(donnees)
    ]


def records_a_envoyer(copie: Copie, records: list[Record]) -> list[Record]:
    """Les records du propriétaire nouveaux ou battus depuis leur dernier envoi."""
    return [r for r in records if copie.tours_envoyes.get(r.id) != r.signature]


def _meta_valide(brut: object) -> dict | None:
    """Ce que la liste montre du record d'un ami, vérifié ; None s'il ne se lit pas, ou s'il
    ne compte pas : un record d'essai (la première version de l'outil en partageait)."""
    if not isinstance(brut, dict):
        return None
    try:
        meta = {
            "trace": _texte(brut["trace"]),
            "circuit": _texte(brut["circuit"]),
            "voiture": _texte(brut["voiture"]),
            "marque": None if brut.get("marque") is None else _texte(brut["marque"], 80),
            "classe": None if brut.get("classe") is None else _texte(brut["classe"], 40),
            "pilote": _texte(brut["pilote"], 64),
            "date": _texte(brut["date"], 40),
            "type": brut["type"] if brut.get("type") in TYPES_COMPTES else None,
            "numero": _entier(brut.get("numero")),
            "chrono": _nombre(brut.get("chrono")),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if meta["type"] is None or meta["chrono"] is None or meta["numero"] is None:
        return None
    return meta


@dataclass(frozen=True)
class Bilan:
    envoyees: int
    recues: int
    version: int
    tours_envoyes: int = 0
    tours_recus: int = 0


def synchroniser(
    service: Service,
    adhesion: Adhesion,
    copie: Copie,
    miennes: list[Performance],
    contours: dict,
    records: list[Record] = (),
    exporteur=exporter,
) -> Bilan:
    """Envoie au groupe ce qui a changé chez soi, puis reçoit ce que le groupe a de neuf, et
    enregistre la copie. `contours` : ceux des tracés connus de la télémétrie de ce PC ;
    `records` : ses records à partager, que `exporteur` met en forme."""
    envoi = a_envoyer(copie, miennes)
    traces = sorted({p.trace for p in miennes if comptee(p)} - set(copie.contours_envoyes))
    nouveaux = {t: contours[t] for t in traces if t in contours}
    paquets = [envoi[i : i + PAQUET] for i in range(0, len(envoi), PAQUET)]
    if nouveaux and not paquets:
        paquets = [[]]
    for rang, paquet in enumerate(paquets):
        service.envoyer(adhesion, paquet, nouveaux if rang == 0 else None)
        for donnees in paquet:
            copie.envoyees[donnees["id"]] = empreinte(donnees)
        if rang == 0:
            copie.contours_envoyes.extend(nouveaux)

    tours_envoyes = 0
    for record in records_a_envoyer(copie, list(records))[:TOURS_PAR_SYNCHRO]:
        try:
            donnees = exporteur(record)
        except (ErreurTelemetrie, ValueError, OSError):
            # Un fichier illisible ne se relira pas mieux à la prochaine : on n'y revient pas.
            copie.tours_envoyes[record.id] = record.signature
            continue
        service.envoyer_tour(adhesion, {**record.meta(), "donnees": donnees})
        copie.tours_envoyes[record.id] = record.signature
        tours_envoyes += 1

    reponse = service.lire(adhesion, copie.version)
    version = reponse.get("version")
    if not isinstance(version, int):
        version = 0
    if version < copie.version:
        # Le service a oublié le groupe (une base refaite) : tout repart, une fois.
        copie.vider()
        return synchroniser(service, adhesion, copie, miennes, contours, records, exporteur)

    recues = 0
    for element in reponse.get("performances") or []:
        if not isinstance(element, dict):
            continue
        membre, brut = element.get("membre"), element.get("performance")
        # Les siennes viennent des fichiers de ce PC, pas du service.
        if not isinstance(membre, str) or membre == adhesion.membre or depuis_json(brut) is None:
            continue
        copie.performances.setdefault(membre, {})[brut["id"]] = brut
        recues += 1
    for trace, points in (reponse.get("contours") or {}).items():
        if isinstance(trace, str) and _contour_valide(points):
            copie.contours[trace] = points
    tours_recus = 0
    for element in reponse.get("tours") or []:
        if not isinstance(element, dict):
            continue
        membre, identifiant, maj = element.get("membre"), element.get("id"), element.get("maj")
        meta = _meta_valide(element.get("meta"))
        if (
            meta is None
            or not isinstance(membre, str)
            or membre == adhesion.membre
            or not isinstance(identifiant, str)
            or isinstance(maj, bool)
            or not isinstance(maj, int)
        ):
            continue
        try:
            analyser(designer(membre, identifiant))
        except ErreurGroupe:
            continue
        copie.tours.setdefault(membre, {})[identifiant] = {**meta, "maj": maj}
        tours_recus += 1
    copie.membres = [
        {
            "id": m["id"],
            "nom": str(m.get("nom") or "?")[:40],
            "rejoint_le": m.get("rejoint_le") if isinstance(m.get("rejoint_le"), str) else None,
            "vu_le": m.get("vu_le") if isinstance(m.get("vu_le"), str) else None,
        }
        for m in reponse.get("membres") or []
        if isinstance(m, dict) and isinstance(m.get("id"), str)
    ]
    # Un membre parti : ses performances et ses records partent avec lui.
    presents = {m["id"] for m in copie.membres}
    for table in (copie.performances, copie.tours):
        for membre in list(table):
            if membre not in presents:
                del table[membre]
    copie.version = version
    copie.derniere = maintenant()
    copie.enregistrer()
    return Bilan(len(envoi), recues, version, tours_envoyes, tours_recus)


_lue: tuple[tuple, Copie] | None = None


def copie_courante() -> Copie | None:
    """La copie du groupe de ce PC telle qu'enregistrée, relue seulement quand elle change ;
    None s'il n'est dans aucun groupe."""
    global _lue
    adhesion = reglages.adhesion()
    if adhesion is None:
        return None
    chemin = fichier_copie()
    try:
        etat = chemin.stat()
        cle = (str(chemin), etat.st_mtime_ns, etat.st_size, adhesion.code, adhesion.membre)
    except OSError:
        return Copie(code=adhesion.code, membre=adhesion.membre)
    if _lue is None or _lue[0] != cle:
        _lue = (cle, Copie.lire(adhesion, chemin))
    return _lue[1]


def tours_des_amis(trace: str | None = None) -> list[dict]:
    """Les records des autres membres que ce PC connaît, sur un tracé ou sur tous : ce
    que la page propose comme tour à comparer."""
    copie = copie_courante()
    if copie is None:
        return []
    return sorted(
        (
            {"id": designer(membre, identifiant), "membre": membre, **meta}
            for membre, liste in copie.tours.items()
            if membre != copie.membre
            for identifiant, meta in liste.items()
            if trace is None or meta.get("trace") == trace
        ),
        key=lambda t: (t["trace"], t["chrono"], t["pilote"]),
    )


#: Les tours d'amis déjà relus : une comparaison, ses virages et sa page les demandent
#: tous les trois.
_charges: CacheBorne[tuple, TourPartage] = CacheBorne(8)

#: Un verrou par record. Ouverte depuis le leaderboard, la page Télémétrie demande le même
#: par plusieurs routes à la fois : il ne se télécharge qu'une fois, et personne n'efface le
#: fichier qu'un autre écrit (Windows refuse). Deux records différents se chargent ensemble.
_verrous: dict[tuple[str, str], threading.Lock] = {}
_verrou_des_verrous = threading.Lock()


def _verrou_du_record(membre: str, identifiant: str) -> threading.Lock:
    with _verrou_des_verrous:
        return _verrous.setdefault((membre, identifiant), threading.Lock())


def charger_partage(designation: str) -> TourPartage:
    """Le record d'un ami (« groupe:<membre>/<numéro> »), prêt à être comparé : relu du
    disque s'il a déjà été téléchargé dans cette version, demandé au service sinon."""
    membre, identifiant = analyser(designation)
    copie = copie_courante()
    meta = (copie.tours.get(membre) or {}).get(identifiant) if copie else None
    if meta is None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_tour_introuvable"), "tour_introuvable")
    cle = (membre, identifiant, meta["maj"])
    with _verrou_du_record(membre, identifiant):
        if (deja := _charges.get(cle)) is not None:
            return deja
        donnees = _lire_ou_telecharger(membre, identifiant, meta["maj"])
        voiture = {"engagement": meta["voiture"], "modele": meta["voiture"], "marque": meta["marque"], "classe": meta["classe"]}
        tour = decoder(donnees, designation, voiture)
        _charges[cle] = tour
        return tour


def _lire_ou_telecharger(membre: str, identifiant: str, maj: object) -> str:
    """La télémétrie d'un record : du disque si elle y est dans cette version, du service
    sinon. À appeler sous le verrou du record."""
    dossier = dossier_tours()
    fichier = dossier / f"{membre}-{identifiant}-{maj}.txt"
    try:
        return fichier.read_text(encoding="ascii")
    except OSError:
        pass
    adresse, adhesion = reglages.adresse_service(), reglages.adhesion()
    if adresse is None or adhesion is None:
        raise ErreurGroupe(Message("serveur.erreur.groupe_sans_service"), "sans_service")
    donnees = Service(adresse).tour(adhesion, membre, identifiant).get("donnees")
    if not isinstance(donnees, str):
        raise ErreurGroupe(Message("serveur.erreur.groupe_tour_illisible"), "tour_illisible")
    dossier.mkdir(parents=True, exist_ok=True)
    # Une version plus ancienne de ce record n'a plus lieu d'être gardée. Celle qu'un autre
    # programme tiendrait ouverte s'effacera une prochaine fois.
    for ancien in dossier.glob(f"{membre}-{identifiant}-*.txt"):
        try:
            ancien.unlink(missing_ok=True)
        except OSError:
            pass
    # Écrit à côté, puis mis en place : un arrêt en pleine écriture ne laisse pas un fichier
    # tronqué, que la relecture refuserait jusqu'au record suivant.
    provisoire = fichier.with_suffix(".tmp")
    provisoire.write_text(donnees, encoding="ascii")
    os.replace(provisoire, fichier)
    return donnees


class Synchroniseur:
    """Tient la copie du groupe à jour en tâche de fond : à l'ouverture de l'outil, dès
    qu'une séance en ligne s'ajoute aux résultats du jeu, et toutes les cinq minutes pour
    recevoir celles des autres. Hors d'un groupe, ou sans service, il ne fait rien.

    `sources` donne les performances du propriétaire, les contours connus de ce PC et,
    s'il y en a, ses records à partager ; `exporteur` met un record en forme.
    """

    #: Secondes entre deux regards sur les résultats du jeu.
    VERIFICATION = 60.0
    #: Secondes entre deux réceptions, quand ce PC n'a rien à envoyer.
    RECEPTION = 300.0

    def __init__(self, sources: Callable[[], tuple], exporteur: Callable[[Record], str] = exporter) -> None:
        self._sources = sources
        self._exporteur = exporteur
        self._verrou = threading.Lock()
        self._reveil = threading.Event()
        self._fil: threading.Thread | None = None
        self.etat: dict = {"etat": "inactif", "derniere": None, "erreur": None, "envoyees": 0, "recues": 0}

    def demarrer(self) -> None:
        if self._fil is None or not self._fil.is_alive():
            self._fil = threading.Thread(target=self._boucle, name="groupe", daemon=True)
            self._fil.start()

    def reveiller(self) -> None:
        """Une synchronisation complète au prochain tour de la boucle, tout de suite."""
        self._reveil.set()

    def maintenant(self) -> dict:
        """Synchronise tout de suite, ici, et rend l'état."""
        self._une_fois(recevoir=True)
        return self.etat

    def oublier(self) -> None:
        """Ce PC vient de quitter son groupe."""
        with self._verrou:
            self.etat = {"etat": "inactif", "derniere": None, "erreur": None, "envoyees": 0, "recues": 0}

    def _boucle(self) -> None:
        derniere = None
        while True:
            force = self._reveil.is_set()
            self._reveil.clear()
            recevoir = force or derniere is None or time.monotonic() - derniere >= self.RECEPTION
            try:
                if self._une_fois(recevoir) and recevoir:
                    derniere = time.monotonic()
            except Exception:  # noqa: BLE001  (la tâche de fond ne doit jamais mourir)
                traceback.print_exc()
            self._reveil.wait(self.VERIFICATION)

    def _une_fois(self, recevoir: bool) -> bool:
        """Une synchronisation, s'il y a lieu : recevoir, ou envoyer des performances
        nouvelles. Vrai si elle a été tentée."""
        adresse, adhesion = reglages.adresse_service(), reglages.adhesion()
        if adresse is None or adhesion is None:
            return False
        with self._verrou:
            copie = Copie.lire(adhesion)
            miennes, contours, *reste = self._sources()
            records = reste[0] if reste else []
            if not recevoir and not a_envoyer(copie, miennes) and not records_a_envoyer(copie, records):
                return False
            self.etat = {**self.etat, "etat": "en_cours"}
            try:
                bilan = synchroniser(
                    Service(adresse), adhesion, copie, miennes, contours, records, self._exporteur
                )
            except ErreurGroupe as erreur:
                self.etat = {
                    **self.etat,
                    "etat": "erreur",
                    "erreur": erreur.message.json() if erreur.message else str(erreur),
                    "code": erreur.code,
                }
                return True
            self.etat = {
                "etat": "ok",
                "derniere": copie.derniere,
                "erreur": None,
                "envoyees": bilan.envoyees,
                "recues": bilan.recues,
            }
            return True
