"""Les performances d'un pilote, séance par séance, tirées des fichiers de résultats du jeu.

C'est la matière du leaderboard (docs/19-leaderboard.md). Chaque PC n'en tire que
celles de son propriétaire, et ce sont elles que le groupe partagera : jamais les autres
pilotes de ses fichiers, les inconnus d'une séance en ligne n'ont rien à y faire.

Une performance résume une séance : meilleur tour et ses secteurs, meilleurs secteurs,
temps moyen, vitesse de pointe, gommes, tours ; en course, la grille, la place et le
statut à l'arrivée. Elle se calcule depuis le fichier de résultats, sans la télémétrie :
toutes les séances comptent, même celles roulées sans enregistrer.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from ..sources.resultats import Engage, SeanceIndexee
from .classement import STATUTS, tour_du_meilleur, tours_representatifs


@dataclass(frozen=True)
class Performance:
    id: str
    """Le départ de la séance et son type, « 1794245179-R » : unique pour un pilote."""

    date: str
    """Début de la séance, en ISO 8601 (UTC)."""

    circuit: str
    trace: str
    """Le tracé (`TrackCourse`) : seuls les chronos d'un même tracé se comparent."""

    type: str
    """« P », « Q » ou « R »."""

    en_ligne: bool
    pilote: str
    voiture: str
    marque: str
    classe: str
    tours: int
    tours_chronometres: int
    meilleur_tour: float | None
    tour_meilleur: int | None
    secteurs_meilleur: tuple[float | None, float | None, float | None]
    meilleurs_secteurs: tuple[float | None, float | None, float | None]
    temps_moyen: float | None
    """Moyenne des tours représentatifs : ni le départ, ni les arrêts, ni les tours à plus
    de 7 % du meilleur (voir `classement.tours_representatifs`)."""

    tours_moyenne: int
    vitesse_max: float | None
    gommes: dict[str, int] = field(default_factory=dict)
    """Composé -> nombre de tours."""

    gomme_meilleur: str | None = None
    """Le composé du meilleur tour."""

    # En course
    grille_classe: int | None = None
    place: int | None = None
    place_classe: int | None = None
    engages: int = 0
    engages_classe: int = 0
    statut: str | None = None
    """« arrivee », « abandon » ou « disqualifie » ; None hors course."""

    def json(self) -> dict:
        return asdict(self)


def _plus_petit(valeurs) -> float | None:
    valeurs = [v for v in valeurs if v is not None]
    return min(valeurs) if valeurs else None


def performance(seance: SeanceIndexee, engage: Engage) -> Performance:
    """La performance d'un pilote dans une séance."""
    chronometres = [t for t in engage.tours_detail if t.chrono is not None]
    meilleur = tour_du_meilleur(engage)
    representatifs = tours_representatifs(engage)
    vitesses = [t.vitesse_max for t in engage.tours_detail if t.vitesse_max is not None]
    course = seance.type == "R"
    return Performance(
        id=f"{int(seance.debut)}-{seance.type}",
        date=datetime.fromtimestamp(seance.debut, timezone.utc).isoformat(),
        circuit=seance.circuit,
        trace=seance.parcours or seance.circuit,
        type=seance.type,
        en_ligne=seance.en_ligne,
        pilote=engage.nom,
        voiture=engage.modele,
        marque=engage.marque,
        classe=engage.classe,
        tours=engage.tours,
        tours_chronometres=len(chronometres),
        meilleur_tour=meilleur.chrono if meilleur else None,
        tour_meilleur=meilleur.numero if meilleur else None,
        secteurs_meilleur=meilleur.secteurs if meilleur else (None, None, None),
        meilleurs_secteurs=tuple(_plus_petit(t.secteurs[i] for t in chronometres) for i in range(3)),
        temps_moyen=round(statistics.fmean(representatifs), 4) if representatifs else None,
        tours_moyenne=len(representatifs),
        vitesse_max=max(vitesses, default=None),
        gommes=dict(Counter(t.gomme for t in engage.tours_detail if t.gomme)),
        gomme_meilleur=meilleur.gomme if meilleur else None,
        grille_classe=engage.grille_classe if course else None,
        place=engage.place if course else None,
        place_classe=engage.place_classe if course else None,
        engages=seance.engages,
        engages_classe=seance.par_classe.get(engage.classe, 0),
        statut=STATUTS.get(engage.statut) if course else None,
    )


def noms_du_proprietaire(
    seances: list[SeanceIndexee], pilotes_telemetrie: set[str] | frozenset[str] = frozenset()
) -> set[str]:
    """Les noms sous lesquels roule le propriétaire du PC : ceux de sa télémétrie, et le
    joueur de ses séances jouées seul. Là, le jeu ne marque que lui ; en ligne, il marque
    tous les humains, et seul le nom permet de le retrouver."""
    noms = {nom for nom in pilotes_telemetrie if nom and nom != "?"}
    for s in seances:
        if not s.en_ligne and len(s.joueurs) == 1:
            noms.add(s.joueurs[0].nom)
    return noms


def performances(seances: list[SeanceIndexee], noms: set[str]) -> list[Performance]:
    """Les performances du propriétaire, de la plus ancienne à la plus récente."""
    return [
        performance(s, e)
        for s in sorted(seances, key=lambda s: s.debut)
        for e in s.joueurs
        if e.nom in noms
    ]


# ----------------------------------------------------------------------
# Une performance reçue du groupe
# ----------------------------------------------------------------------


def _texte(valeur: object, maximum: int = 160, vide: bool = False) -> str:
    if not isinstance(valeur, str) or len(valeur) > maximum or (not valeur and not vide):
        raise ValueError(valeur)
    return valeur


def _entier(valeur: object) -> int | None:
    if valeur is None:
        return None
    if isinstance(valeur, bool) or not isinstance(valeur, int) or not -1 <= valeur <= 10**7:
        raise ValueError(valeur)
    return valeur


def _nombre(valeur: object) -> float | None:
    if valeur is None:
        return None
    if isinstance(valeur, bool) or not isinstance(valeur, int | float) or not math.isfinite(valeur):
        raise ValueError(valeur)
    return float(valeur)


def _trois(valeur: object) -> tuple[float | None, float | None, float | None]:
    if valeur is None:
        return (None, None, None)
    if not isinstance(valeur, list | tuple) or len(valeur) != 3:
        raise ValueError(valeur)
    return tuple(_nombre(v) for v in valeur)


def depuis_json(brut: object) -> Performance | None:
    """Une performance reçue du groupe (`Performance.json` d'un autre PC), ou None si elle
    ne se lit pas. Ce qui vient du réseau est vérifié champ par champ : rien n'est cru sur
    parole, et un champ inconnu (d'une version plus récente de l'outil) est ignoré."""
    if not isinstance(brut, dict):
        return None
    try:
        gommes = brut.get("gommes") or {}
        if not isinstance(gommes, dict):
            raise ValueError(gommes)
        statut = brut.get("statut")
        if statut is not None and statut not in STATUTS.values():
            raise ValueError(statut)
        if brut.get("type") not in ("P", "Q", "R") or not isinstance(brut.get("en_ligne"), bool):
            raise ValueError(brut.get("type"))
        return Performance(
            id=_texte(brut["id"], 64),
            date=_texte(brut["date"], 40),
            circuit=_texte(brut["circuit"]),
            trace=_texte(brut["trace"]),
            type=brut["type"],
            en_ligne=brut["en_ligne"],
            pilote=_texte(brut["pilote"], 64),
            voiture=_texte(brut.get("voiture", ""), vide=True),
            marque=_texte(brut.get("marque", ""), vide=True),
            classe=_texte(brut.get("classe", ""), 40, vide=True),
            tours=_entier(brut.get("tours")) or 0,
            tours_chronometres=_entier(brut.get("tours_chronometres")) or 0,
            meilleur_tour=_nombre(brut.get("meilleur_tour")),
            tour_meilleur=_entier(brut.get("tour_meilleur")),
            secteurs_meilleur=_trois(brut.get("secteurs_meilleur")),
            meilleurs_secteurs=_trois(brut.get("meilleurs_secteurs")),
            temps_moyen=_nombre(brut.get("temps_moyen")),
            tours_moyenne=_entier(brut.get("tours_moyenne")) or 0,
            vitesse_max=_nombre(brut.get("vitesse_max")),
            gommes={_texte(g, 20): _entier(n) or 0 for g, n in list(gommes.items())[:10]},
            gomme_meilleur=None if brut.get("gomme_meilleur") is None else _texte(brut["gomme_meilleur"], 20),
            grille_classe=_entier(brut.get("grille_classe")),
            place=_entier(brut.get("place")),
            place_classe=_entier(brut.get("place_classe")),
            engages=_entier(brut.get("engages")) or 0,
            engages_classe=_entier(brut.get("engages_classe")) or 0,
            statut=statut,
        )
    except (KeyError, TypeError, ValueError):
        return None


def bilan_courses(perfs: list[Performance]) -> dict:
    """Les statistiques de course d'un pilote. Les places sont celles de sa catégorie ;
    la place moyenne ne compte que les arrivées."""
    courses = [p for p in perfs if p.type == "R"]
    arrivees = [p for p in courses if p.statut == "arrivee" and p.place_classe]
    places = [p.place_classe for p in arrivees]
    return {
        "courses": len(courses),
        "victoires": sum(p == 1 for p in places),
        "podiums": sum(p <= 3 for p in places),
        "top10": sum(p <= 10 for p in places),
        "abandons": sum(p.statut in ("abandon", "disqualifie") for p in courses),
        "place_moyenne": round(statistics.fmean(places), 2) if places else None,
        "tours_en_course": sum(p.tours for p in courses),
        "tours": sum(p.tours for p in perfs),
    }
