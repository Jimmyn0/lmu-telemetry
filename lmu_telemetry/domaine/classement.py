"""Le classement d'une séance, tel que l'écran Résultats le montre.

Il part du fichier de résultats du jeu (`sources/resultats.py`) et y ajoute ce que le
fichier ne donne pas tout fait : l'écart de chacun sur le leader, au général et dans sa
catégorie ; sa place dans la catégorie à chaque tour ; son meilleur tour et les secteurs
de ce tour ; les catégories, de la plus rapide à la plus lente ; et les meilleures
performances de chaque catégorie.
"""

from __future__ import annotations

import statistics
from collections import Counter

from ..sources.resultats import Engage, ResultatsSession, TourResultat

#: Deux chronos plus proches (s) sont le même : le fichier les écrit au dix-millième.
MEME_CHRONO = 0.0005

#: Ce que devient le `FinishStatus` du jeu. Hors course, il vaut « None » : rien à dire.
STATUTS = {"Finished Normally": "arrivee", "DNF": "abandon", "DQ": "disqualifie"}

#: Un tour plus lent que le meilleur du pilote de plus de 7 % (une sortie, un drapeau, du
#: trafic) ne dit rien de sa régularité.
TOUR_REPRESENTATIF = 1.07

#: Tours représentatifs qu'il faut au moins pour mesurer une régularité.
TOURS_REGULARITE = 3

#: Force d'un contact, dans l'unité du jeu, à partir de laquelle il est moyen, puis violent.
#: Sur les 28 762 contacts des fichiers du disque, quatre sur dix restent sous 100, et un
#: sur six dépasse 1 000.
CONTACT_MOYEN = 100.0
CONTACT_VIOLENT = 1000.0


def ecart(engage: Engage, reference: Engage | None, course: bool) -> dict | None:
    """L'écart d'une voiture sur la référence (le leader du général ou de sa catégorie).

    En course : des tours de retard, sinon le temps à l'arrivée. En essais et en
    qualifications : l'écart de meilleur tour. None pour la référence elle-même, ou quand
    il ne se calcule pas (pas de temps).
    """
    if reference is None or engage is reference:
        return None
    if course:
        if reference.tours > engage.tours:
            return {"tours": reference.tours - engage.tours}
        if engage.temps_total is None or reference.temps_total is None:
            return None
        return {"temps": round(engage.temps_total - reference.temps_total, 4)}
    if engage.meilleur_tour is None or reference.meilleur_tour is None:
        return None
    return {"temps": round(engage.meilleur_tour - reference.meilleur_tour, 4)}


def tour_du_meilleur(engage: Engage) -> TourResultat | None:
    """Le tour du meilleur chrono : celui que le fichier annonce, sinon le plus rapide."""
    chronos = [t for t in engage.tours_detail if t.chrono is not None]
    if engage.meilleur_tour is not None:
        for tour in chronos:
            if abs(tour.chrono - engage.meilleur_tour) < MEME_CHRONO:
                return tour
    return min(chronos, key=lambda t: t.chrono, default=None)


def places_classe_par_tour(engages: tuple[Engage, ...]) -> dict[tuple[int, int], int]:
    """(rang de l'engagé dans `engages`, numéro du tour) -> sa place dans sa catégorie.

    À chaque tour, les voitures de la catégorie qui l'ont bouclé se classent par leur
    place au général à la fin de ce tour.
    """
    par_tour: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for rang, engage in enumerate(engages):
        for tour in engage.tours_detail:
            if tour.position is not None:
                par_tour.setdefault((engage.classe, tour.numero), []).append((tour.position, rang))
    places: dict[tuple[int, int], int] = {}
    for (_classe, numero), liste in par_tour.items():
        for place, (_position, rang) in enumerate(sorted(liste), start=1):
            places[(rang, numero)] = place
    return places


def ordre_des_categories(engages: tuple[Engage, ...]) -> list[str]:
    """Les catégories, de la plus rapide à la plus lente d'après leur meilleur tour."""
    meilleurs: dict[str, float] = {}
    for e in engages:
        if e.meilleur_tour is not None:
            meilleurs[e.classe] = min(meilleurs.get(e.classe, e.meilleur_tour), e.meilleur_tour)
    vues = list(dict.fromkeys(e.classe for e in engages))
    return sorted(vues, key=lambda c: (c not in meilleurs, meilleurs.get(c, 0.0), vues.index(c)))


def tours_representatifs(engage: Engage) -> list[float]:
    """Les chronos qui disent le rythme d'un pilote : ni le premier tour (le départ), ni
    les tours d'entrée et de sortie des stands, ni un tour à plus de 7 % de son meilleur."""
    stands = {t.numero for t in engage.tours_detail if t.stands}
    exclus = stands | {n + 1 for n in stands} | {1}
    chronos = [
        t.chrono for t in engage.tours_detail if t.chrono is not None and t.numero not in exclus
    ]
    if not chronos:
        return []
    meilleur = min(chronos)
    return [c for c in chronos if c <= meilleur * TOUR_REPRESENTATIF]


def _record(trouve: tuple[float, int, int] | None) -> dict | None:
    """(temps, rang de l'engagé, numéro du tour) -> ce que l'écran en montre."""
    if trouve is None:
        return None
    temps, rang, tour = trouve
    return {"temps": temps, "rang": rang, "tour": tour}


def statistiques(seance: ResultatsSession) -> list[dict]:
    """Les meilleures performances de chaque catégorie (maquette 05) : meilleur tour et
    meilleurs secteurs, pilote le plus régulier, plus de places gagnées et perdues entre la
    grille et l'arrivée, gomme la plus utilisée. À égalité, le mieux classé l'emporte.

    Les secteurs ne viennent que des tours chronométrés : le premier secteur d'un tour
    invalidé plus loin ne compte pas. Les rangs renvoient à `seance.engages`.
    """
    resultat = []
    for categorie in ordre_des_categories(seance.engages):
        membres = [(rang, e) for rang, e in enumerate(seance.engages) if e.classe == categorie]
        chronometres = [(rang, t) for rang, e in membres for t in e.tours_detail if t.chrono is not None]
        meilleur = min(((t.chrono, rang, t.numero) for rang, t in chronometres), default=None)
        secteurs = [
            _record(
                min(
                    (
                        (t.secteurs[i], rang, t.numero)
                        for rang, t in chronometres
                        if t.secteurs[i] is not None
                    ),
                    default=None,
                )
            )
            for i in range(3)
        ]
        regularites = []
        for rang, e in membres:
            chronos = tours_representatifs(e)
            if len(chronos) >= TOURS_REGULARITE:
                regularites.append((statistics.pstdev(chronos), rang, len(chronos)))
        regulier = min(regularites, default=None)
        # Places gagnées (positives) ou perdues (négatives) dans la catégorie.
        bilans = [
            (e.grille_classe - e.place_classe, rang)
            for rang, e in membres
            if e.grille_classe and e.place_classe
        ]
        gagne = max(bilans, key=lambda b: (b[0], -b[1]), default=None)
        perdu = min(bilans, default=None)
        gommes = Counter(t.gomme for _rang, e in membres for t in e.tours_detail if t.gomme)
        gomme = gommes.most_common(1)
        resultat.append(
            {
                "categorie": categorie,
                "voitures": len(membres),
                "meilleur_tour": _record(meilleur),
                "secteurs": secteurs,
                "regularite": {
                    "rang": regulier[1], "ecart_type": round(regulier[0], 4), "tours": regulier[2],
                }
                if regulier
                else None,
                "gagnees": {"rang": gagne[1], "places": gagne[0]} if gagne and gagne[0] > 0 else None,
                "perdues": {"rang": perdu[1], "places": -perdu[0]} if perdu and perdu[0] < 0 else None,
                "gomme": {"nom": gomme[0][0], "tours": gomme[0][1]} if gomme else None,
            }
        )
    return resultat


def gravite(intensite: float | None) -> str | None:
    """« leger », « moyen » ou « violent » : la force d'un contact, telle qu'on la dit."""
    if intensite is None:
        return None
    if intensite >= CONTACT_VIOLENT:
        return "violent"
    return "moyen" if intensite >= CONTACT_MOYEN else "leger"


def depart_de_seance(seance: ResultatsSession) -> float:
    """L'heure de séance du départ : le drapeau vert en course, où tous les premiers tours
    partent ensemble ; le début de la séance ailleurs."""
    if seance.type != "R":
        return 0.0
    debuts = [
        e.tours_detail[0].debut
        for e in seance.engages
        if e.tours_detail and e.tours_detail[0].debut is not None
    ]
    return min(debuts, default=0.0)


def tour_a(engage: Engage, instant: float) -> int | None:
    """Le tour que la voiture courait à cet instant : le dernier parti avant lui. None avant
    son premier tour (le tour de formation, le garage)."""
    tour = None
    for t in engage.tours_detail:
        if t.debut is not None and t.debut <= instant:
            tour = t.numero
    return tour


def incidents(seance: ResultatsSession) -> list[dict]:
    """Les incidents de la séance (maquette 06), dans l'ordre où ils sont arrivés : quand
    (temps écoulé depuis le départ, et temps restant si la séance a une durée, négatif une
    fois le temps écoulé), qui, à quel tour, et ce qui s'est passé. Les pilotes sont
    désignés par leur rang dans `engages`."""
    rangs = {e.nom: rang for rang, e in enumerate(seance.engages)}
    depart = depart_de_seance(seance)
    fin = depart + seance.minutes * 60 if seance.minutes else None
    resultat = []
    for ev in seance.evenements:
        rang = rangs.get(ev.pilote)
        resultat.append(
            {
                "genre": ev.genre,
                "ecoule": round(max(0.0, ev.instant - depart), 1),
                # Négatif après la fin du temps : le dernier tour d'une course au temps.
                "restant": round(fin - ev.instant, 1) if fin is not None else None,
                "tour": tour_a(seance.engages[rang], ev.instant) if rang is not None else None,
                "rang": rang,
                "pilote": ev.pilote,
                "autre": ev.autre,
                "objet": ev.objet,
                "gravite": gravite(ev.intensite),
                "suite": ev.suite,
                "penalite": ev.penalite,
                "motif": ev.motif,
                "secondes": ev.secondes,
            }
        )
    return resultat


def chat(seance: ResultatsSession) -> list[dict]:
    """Les messages du chat d'une séance en ligne, avec leur heure comme les incidents."""
    depart = depart_de_seance(seance)
    fin = depart + seance.minutes * 60 if seance.minutes else None
    return [
        {
            "ecoule": round(max(0.0, m.instant - depart), 1),
            "restant": round(fin - m.instant, 1) if fin is not None else None,
            "auteur": m.auteur,
            "texte": m.texte,
        }
        for m in seance.messages
    ]


def rang_du_pilote(engages: tuple[Engage, ...], pilote: str | None) -> int | None:
    """Le pilote de la session de télémétrie, parmi les voitures de la séance.

    Son nom est écrit de la même façon dans les deux fichiers : vérifié sur 586 sessions,
    il désigne chaque fois une seule voiture. Le fichier marque bien la voiture du joueur
    (`isPlayer`), mais en multijoueur il marque tous les humains (36 sur 36 dans une
    qualification en ligne), et plusieurs peuvent rouler sous le même engagement. Ce
    marquage ne sert donc que s'il ne désigne qu'une voiture.
    """
    par_nom = [rang for rang, e in enumerate(engages) if pilote and e.nom == pilote]
    if len(par_nom) == 1:
        return par_nom[0]
    marques = [rang for rang, e in enumerate(engages) if e.joueur]
    return marques[0] if len(marques) == 1 else None


def classement_json(seance: ResultatsSession, pilote: str | None = None) -> dict:
    """La séance pour l'écran Résultats : ses voitures dans l'ordre du classement.
    `pilote` : le nom du pilote de la session de télémétrie, désigné comme « toi »."""
    course = seance.type == "R"
    engages = seance.engages
    moi = rang_du_pilote(engages, pilote)
    # Les voitures sont dans l'ordre du classement : la première de chaque catégorie
    # en est le leader.
    leader = engages[0] if engages and engages[0].place is not None else None
    leaders: dict[str, Engage] = {}
    for e in engages:
        if e.place is not None:
            leaders.setdefault(e.classe, e)
    places = places_classe_par_tour(engages)
    return {
        "type": seance.type,
        "circuit": seance.circuit,
        "parcours": seance.parcours,
        "longueur": seance.longueur,
        "debut": seance.debut.isoformat() if seance.debut else None,
        "minutes": seance.minutes,
        "tours_prevus": seance.tours_prevus,
        "categories": ordre_des_categories(engages),
        "statistiques": statistiques(seance),
        "incidents": incidents(seance),
        "en_ligne": seance.en_ligne,
        "chat": chat(seance),
        "engages": [
            {
                **_engage_json(rang, e, course, leader, leaders.get(e.classe), places),
                "joueur": rang == moi,
            }
            for rang, e in enumerate(engages)
        ],
    }


def _engage_json(
    rang: int,
    e: Engage,
    course: bool,
    leader: Engage | None,
    leader_categorie: Engage | None,
    places: dict[tuple[int, int], int],
) -> dict:
    meilleur = tour_du_meilleur(e)
    derniere_gomme = next((t.gomme for t in reversed(e.tours_detail) if t.gomme), None)
    # En course, la gomme de l'arrivée ; ailleurs, celle du meilleur tour.
    gomme = derniere_gomme if course or meilleur is None else (meilleur.gomme or derniere_gomme)
    vitesses = [t.vitesse_max for t in e.tours_detail if t.vitesse_max is not None]
    return {
        "nom": e.nom,
        "equipe": e.equipe,
        "numero": e.numero,
        "engagement": e.engagement,
        "modele": e.modele,
        "marque": e.marque,
        "classe": e.classe,
        "grille": e.grille,
        "place": e.place,
        "grille_classe": e.grille_classe,
        "place_classe": e.place_classe,
        "meilleur_tour": e.meilleur_tour,
        "tour_meilleur": meilleur.numero if meilleur else None,
        "secteurs_meilleur": list(meilleur.secteurs) if meilleur else [None, None, None],
        "temps_total": e.temps_total,
        "tours": e.tours,
        "arrets": e.arrets,
        "statut": STATUTS.get(e.statut),
        "gomme": gomme,
        "vitesse_max": max(vitesses, default=None),
        "ecart": ecart(e, leader, course),
        "ecart_categorie": ecart(e, leader_categorie, course),
        "tours_detail": [
            {
                "numero": t.numero,
                "place": t.position,
                "place_categorie": places.get((rang, t.numero)),
                "chrono": t.chrono,
                "secteurs": list(t.secteurs),
                "vitesse_max": t.vitesse_max,
                "stands": t.stands,
                "gomme": t.gomme,
            }
            for t in e.tours_detail
        ],
    }
