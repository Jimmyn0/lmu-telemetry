"""Le leaderboard d'un groupe : ses dernières courses, une page par circuit (ses pilotes, ses
voitures, ses courses) et une fiche par pilote (ses statistiques, ses records, ses courses).

Il se calcule à partir des performances de tous les membres (`performances.py`), et ne
compte que les **qualifications et les courses en ligne** : contre l'IA, on règle soi-même
le niveau des adversaires, ni les chronos ni les victoires ne s'y comparent ; en essais, on
roule pour régler, pas pour se classer. Les filtres sont le tracé, la catégorie, la voiture
et le pilote. Voir docs/19-leaderboard.md.

Les meilleurs tours ne se comparent que sur un même tracé et dans une même catégorie :
un pilote a une ligne par catégorie roulée sur le tracé, une voiture aussi.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace

from .performances import Performance, bilan_courses

#: Les familles de catégories, de la plus rapide à la plus lente. Le jeu écrit « Hyper »
#: ou « LMP2_ELMS » : comme à l'écran (`familleClasse` de format.js), on n'en garde que
#: la famille.
FAMILLES = ("HYPER", "LMP2", "LMP3", "GTE", "GT3")

#: Les dernières courses montrées d'un coup ; la page en redemande autant à chaque fois.
HISTORIQUE = 20
HISTORIQUE_MAX = 1000


def famille(classe: str) -> str:
    """La famille d'une catégorie du jeu ; une catégorie inconnue reste telle quelle."""
    texte = (classe or "").upper()
    return next((f for f in FAMILLES if texte.startswith(f)), classe)


def _ordre_familles(classe: str) -> tuple[int, str]:
    return (FAMILLES.index(classe) if classe in FAMILLES else len(FAMILLES), classe)


#: Les séances que compte le leaderboard : les qualifications et les courses. Les essais
#: n'y entrent pas (demandé le 2026-11-10) : on y roule pour régler, pas pour se classer.
TYPES_COMPTES = frozenset({"Q", "R"})


def comptee(p: Performance) -> bool:
    """La performance compte-t-elle au leaderboard ? En ligne, en qualifs ou en course."""
    return p.en_ligne and p.type in TYPES_COMPTES


def comptees(perfs: list[Performance]) -> list[Performance]:
    """Les seules performances que compte le leaderboard."""
    return [p for p in perfs if comptee(p)]


@dataclass(frozen=True)
class Filtres:
    trace: str | None = None
    """None : tous les circuits."""

    classe: str | None = None
    """Une famille (`FAMILLES`)."""

    voiture: str | None = None
    pilote: str | None = None


def retenues(
    perfs: list[Performance],
    f: Filtres,
    *,
    classe: bool = True,
    voiture: bool = True,
    pilote: bool = True,
) -> list[Performance]:
    """Les performances que les filtres retiennent ; `classe`, `voiture` et `pilote` à
    faux ignorent le filtre correspondant."""
    return [
        p
        for p in perfs
        if (f.trace is None or p.trace == f.trace)
        and (not classe or f.classe is None or famille(p.classe) == f.classe)
        and (not voiture or f.voiture is None or p.voiture == f.voiture)
        and (not pilote or f.pilote is None or p.pilote == f.pilote)
    ]


def _par(perfs: list[Performance], cle) -> dict:
    groupes: dict = defaultdict(list)
    for p in perfs:
        groupes[cle(p)].append(p)
    return groupes


def _par_pilote(perfs: list[Performance]) -> dict[str, list[Performance]]:
    return _par(perfs, lambda p: p.pilote)


def _record(liste: list[Performance]) -> Performance | None:
    """La séance du meilleur tour ; à égalité, la première."""
    chronometrees = [p for p in liste if p.meilleur_tour is not None]
    return min(chronometrees, key=lambda p: (p.meilleur_tour, p.date)) if chronometrees else None


def _temps_moyen(liste: list[Performance]) -> float | None:
    """Le temps moyen de plusieurs séances : celui de chacune pèse ses tours représentatifs."""
    ponderees = [p for p in liste if p.temps_moyen is not None and p.tours_moyenne]
    poids = sum(p.tours_moyenne for p in ponderees)
    return round(sum(p.temps_moyen * p.tours_moyenne for p in ponderees) / poids, 4) if poids else None


def _vitesse_max(liste: list[Performance]) -> float | None:
    return max((p.vitesse_max for p in liste if p.vitesse_max is not None), default=None)


def _references(perfs: list[Performance], f: Filtres) -> dict[str, float]:
    """Le meilleur tour de chaque catégorie sur le tracé de `f`, quels que soient les
    filtres de catégorie, de voiture et de pilote : la référence des écarts."""
    references: dict[str, float] = {}
    for p in retenues(perfs, f, classe=False, voiture=False, pilote=False):
        if p.meilleur_tour is not None:
            c = famille(p.classe)
            references[c] = min(references.get(c, p.meilleur_tour), p.meilleur_tour)
    return references


def _par_categorie(lignes_par_classe: dict[str, list[dict]], references: dict[str, float]) -> list[dict]:
    """Les lignes de chaque catégorie, de la plus rapide à la plus lente, numérotées ; les
    catégories, de la plus rapide à la plus lente."""
    categories = []
    for classe, lignes in lignes_par_classe.items():
        if not lignes:
            continue
        lignes.sort(key=lambda l: (l["meilleur_tour"], l["date"]))
        for place, ligne in enumerate(lignes, start=1):
            ligne["place"] = place
        categories.append({"classe": classe, "reference": references[classe], "lignes": lignes})
    return sorted(categories, key=lambda c: c["reference"])


# ----------------------------------------------------------------------
# La page d'un circuit : ses pilotes, ses voitures
# ----------------------------------------------------------------------


def _ligne_tours(nom: str, liste: list[Performance], moi: set[str], reference: float) -> dict | None:
    """Ce qu'a fait un pilote dans une catégorie sur le tracé ; None sans tour chronométré."""
    record = _record(liste)
    if record is None:
        return None
    secteurs = [
        min((p.meilleurs_secteurs[i] for p in liste if p.meilleurs_secteurs[i] is not None), default=None)
        for i in range(3)
    ]
    gommes: Counter = Counter()
    for p in liste:
        gommes.update(p.gommes)
    return {
        "pilote": nom,
        "moi": nom in moi,
        "voiture": record.voiture,
        "marque": record.marque,
        "meilleur_tour": record.meilleur_tour,
        "ecart": round(record.meilleur_tour - reference, 4),
        "date": record.date,
        "type": record.type,
        "secteurs_meilleur": list(record.secteurs_meilleur),
        "gomme_meilleur": record.gomme_meilleur,
        "temps_moyen": _temps_moyen(liste),
        "meilleurs_secteurs": secteurs,
        "tour_ideal": round(sum(secteurs), 4) if None not in secteurs else None,
        "vitesse_max": _vitesse_max(liste),
        "gommes": dict(gommes.most_common()),
        "seances": len(liste),
        "tours": sum(p.tours for p in liste),
    }


def classement_tours(perfs: list[Performance], f: Filtres, moi: set[str] = frozenset()) -> list[dict]:
    """Les meilleurs tours sur le tracé choisi, catégorie par catégorie (la plus rapide
    d'abord) : une ligne par pilote, du plus rapide au plus lent, avec son meilleur tour,
    son temps moyen, ses meilleurs secteurs et le tour idéal qu'ils font, sa vitesse de
    pointe, ses gommes.

    L'écart se prend sur la référence de la catégorie : son meilleur tour sur le tracé,
    quels que soient les filtres de voiture et de pilote.
    """
    if f.trace is None:
        return []
    references = _references(perfs, f)
    lignes: dict[str, list[dict]] = {}
    for classe, liste in _par(retenues(perfs, f), lambda p: famille(p.classe)).items():
        if classe in references:
            lignes[classe] = [
                ligne
                for nom, du_pilote in _par_pilote(liste).items()
                if (ligne := _ligne_tours(nom, du_pilote, moi, references[classe])) is not None
            ]
    return _par_categorie(lignes, references)


def classement_voitures(perfs: list[Performance], f: Filtres, moi: set[str] = frozenset()) -> list[dict]:
    """Les voitures du tracé choisi, catégorie par catégorie (la plus rapide d'abord) : une
    ligne par voiture, de la plus rapide à la plus lente, avec le meilleur tour bouclé à son
    volant et qui l'a bouclé, l'écart avec la référence de la catégorie, combien de pilotes
    l'ont prise, et son temps moyen, tous pilotes confondus."""
    if f.trace is None:
        return []
    references = _references(perfs, f)
    lignes: dict[str, list[dict]] = defaultdict(list)
    for classe, liste in _par(retenues(perfs, f), lambda p: famille(p.classe)).items():
        for voiture, de_la_voiture in _par(liste, lambda p: p.voiture).items():
            record = _record(de_la_voiture)
            if record is None:
                continue
            lignes[classe].append(
                {
                    "voiture": voiture,
                    "marque": record.marque,
                    "meilleur_tour": record.meilleur_tour,
                    "ecart": round(record.meilleur_tour - references[classe], 4),
                    "gomme_meilleur": record.gomme_meilleur,
                    "pilote": record.pilote,
                    "moi": record.pilote in moi,
                    "date": record.date,
                    "type": record.type,
                    "pilotes": len({p.pilote for p in de_la_voiture}),
                    "seances": len(de_la_voiture),
                    "tours": sum(p.tours for p in de_la_voiture),
                    "temps_moyen": _temps_moyen(de_la_voiture),
                    "vitesse_max": _vitesse_max(de_la_voiture),
                }
            )
    return _par_categorie(lignes, references)


# ----------------------------------------------------------------------
# Les courses : le bilan, et les dernières
# ----------------------------------------------------------------------


def classement_courses(perfs: list[Performance], f: Filtres, moi: set[str] = frozenset()) -> list[dict]:
    """Le bilan des courses de chaque pilote selon les filtres (sur tous les circuits si
    aucun n'est choisi). Les plus victorieux d'abord, puis les plus souvent sur le podium,
    puis la meilleure place moyenne."""
    lignes = []
    for nom, liste in _par_pilote(retenues(perfs, f)).items():
        bilan = bilan_courses(liste)
        if bilan["courses"]:
            lignes.append({"pilote": nom, "moi": nom in moi, **bilan})
    return sorted(
        lignes,
        key=lambda l: (
            -l["victoires"],
            -l["podiums"],
            l["place_moyenne"] if l["place_moyenne"] is not None else float("inf"),
            l["pilote"],
        ),
    )


def historique(
    perfs: list[Performance], f: Filtres, moi: set[str] = frozenset(), limite: int = HISTORIQUE
) -> dict:
    """Les dernières courses selon les filtres, la plus récente d'abord : les `limite`
    premières, et combien il y en a en tout. Elles mêlent les circuits et les catégories :
    chacune dit les siens."""
    courses = sorted(
        (p for p in retenues(perfs, f) if p.type == "R"), key=lambda p: (p.date, p.pilote), reverse=True
    )
    return {
        "total": len(courses),
        "lignes": [
            {
                "id": p.id,
                "date": p.date,
                "circuit": p.circuit,
                "trace": p.trace,
                "classe": famille(p.classe),
                "pilote": p.pilote,
                "moi": p.pilote in moi,
                "voiture": p.voiture,
                "marque": p.marque,
                "grille": p.grille_classe,
                "place": p.place_classe,
                "engages": p.engages_classe,
                "statut": p.statut,
                "meilleur_tour": p.meilleur_tour,
                "tours": p.tours,
            }
            for p in courses[:limite]
        ],
    }


# ----------------------------------------------------------------------
# La fiche d'un pilote
# ----------------------------------------------------------------------


def records_personnels(perfs: list[Performance], f: Filtres) -> list[dict]:
    """Les records du pilote `f.pilote` : son meilleur tour sur chaque tracé, dans chaque
    catégorie, avec l'écart à la référence de la catégorie et sa place parmi les meilleurs
    tours des pilotes du groupe. Les filtres de catégorie et de voiture choisissent ses
    séances ; le groupe, lui, compte toutes les voitures."""
    groupe: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for p in perfs:
        if p.meilleur_tour is not None:
            meilleurs = groupe[(p.trace, famille(p.classe))]
            meilleurs[p.pilote] = min(meilleurs.get(p.pilote, p.meilleur_tour), p.meilleur_tour)
    records = []
    for (trace, classe), liste in _par(retenues(perfs, f), lambda p: (p.trace, famille(p.classe))).items():
        record = _record(liste)
        if record is None:
            continue
        meilleurs = groupe[(trace, classe)]
        reference = min(meilleurs.values())
        records.append(
            {
                "circuit": record.circuit,
                "trace": trace,
                "classe": classe,
                "voiture": record.voiture,
                "marque": record.marque,
                "meilleur_tour": record.meilleur_tour,
                "gomme_meilleur": record.gomme_meilleur,
                "date": record.date,
                "type": record.type,
                "reference": reference,
                "ecart": round(record.meilleur_tour - reference, 4),
                "rang": 1 + sum(t < record.meilleur_tour for nom, t in meilleurs.items() if nom != f.pilote),
                "pilotes": len(meilleurs),
                "seances": len(liste),
                "tours": sum(p.tours for p in liste),
            }
        )
    return sorted(records, key=lambda r: (r["circuit"], r["trace"], _ordre_familles(r["classe"])))


def fiche_pilote(perfs: list[Performance], f: Filtres, moi: set[str] = frozenset()) -> dict:
    """La fiche du pilote `f.pilote` : ses statistiques générales, son circuit et sa voiture
    favoris, son bilan par catégorie et ses records personnels. Ses dernières courses sont
    celles de `historique`, avec les mêmes filtres."""
    siennes = retenues(perfs, f)
    circuits = Counter(p.circuit for p in siennes)
    voitures = Counter(p.voiture for p in siennes)
    marques = {p.voiture: p.marque for p in siennes}
    return {
        "pilote": f.pilote,
        "moi": f.pilote in moi,
        "depuis": min((p.date for p in siennes), default=None),
        "derniere": max((p.date for p in siennes), default=None),
        "seances": len(siennes),
        "bilan": bilan_courses(siennes),
        "circuit_favori": (
            {"circuit": circuits.most_common(1)[0][0], "seances": circuits.most_common(1)[0][1]}
            if circuits
            else None
        ),
        "voiture_favorite": (
            {
                "voiture": voitures.most_common(1)[0][0],
                "marque": marques[voitures.most_common(1)[0][0]],
                "seances": voitures.most_common(1)[0][1],
            }
            if voitures
            else None
        ),
        "categories": [
            {"classe": classe, "seances": len(liste), **bilan_courses(liste)}
            for classe, liste in sorted(
                _par(siennes, lambda p: famille(p.classe)).items(), key=lambda x: _ordre_familles(x[0])
            )
        ],
        "records": records_personnels(perfs, f),
    }


# ----------------------------------------------------------------------
# Les menus de l'écran, les filtres, la réponse entière
# ----------------------------------------------------------------------


def _meilleurs_par_famille(perfs: list[Performance]) -> list[dict]:
    meilleurs: dict[str, float] = {}
    for p in perfs:
        if p.meilleur_tour is not None:
            c = famille(p.classe)
            meilleurs[c] = min(meilleurs.get(c, p.meilleur_tour), p.meilleur_tour)
    return [{"classe": c, "chrono": meilleurs[c]} for c in sorted(meilleurs, key=_ordre_familles)]


def menu_circuits(perfs: list[Performance]) -> list[dict]:
    """Les circuits roulés : leurs séances, leurs courses, la date de la dernière, et leurs
    tracés (le plus roulé d'abord), chacun avec ses pilotes, ses voitures, ses tours et le
    meilleur tour de chaque catégorie."""
    resultat = []
    for nom, toutes in sorted(_par(perfs, lambda p: p.circuit).items()):
        traces = [
            {
                "nom": trace,
                "seances": len(liste),
                "courses": sum(p.type == "R" for p in liste),
                "derniere": max(p.date for p in liste),
                "pilotes": len({p.pilote for p in liste}),
                "voitures": len({p.voiture for p in liste}),
                "tours": sum(p.tours for p in liste),
                "meilleurs": _meilleurs_par_famille(liste),
            }
            for trace, liste in _par(toutes, lambda p: p.trace).items()
        ]
        resultat.append(
            {
                "circuit": nom,
                "seances": len(toutes),
                "courses": sum(p.type == "R" for p in toutes),
                "derniere": max(p.date for p in toutes),
                "traces": sorted(traces, key=lambda x: (-x["seances"], x["nom"])),
            }
        )
    return resultat


def menu_pilotes(perfs: list[Performance], moi: set[str] = frozenset()) -> list[dict]:
    """Les pilotes du groupe : leurs séances, leurs courses, victoires et podiums, la date
    de leur dernière séance, et les catégories qu'ils roulent (la plus roulée d'abord)."""
    resultat = []
    for nom, liste in sorted(_par_pilote(perfs).items()):
        bilan = bilan_courses(liste)
        familles = Counter(famille(p.classe) for p in liste)
        resultat.append(
            {
                "pilote": nom,
                "moi": nom in moi,
                "seances": len(liste),
                "courses": bilan["courses"],
                "victoires": bilan["victoires"],
                "podiums": bilan["podiums"],
                "derniere": max(p.date for p in liste),
                "classes": [c for c, _ in sorted(familles.items(), key=lambda x: (-x[1], _ordre_familles(x[0])))],
            }
        )
    return resultat


def options(perfs: list[Performance], f: Filtres) -> dict:
    """Ce que proposent les listes de filtres : les catégories du tracé choisi (de tous
    les circuits sans tracé), ses voitures dans la catégorie choisie, et les pilotes."""
    sur_trace = [p for p in perfs if f.trace is None or p.trace == f.trace]
    return {
        "classes": sorted({famille(p.classe) for p in sur_trace}, key=_ordre_familles),
        "voitures": sorted(
            {p.voiture for p in sur_trace if f.classe is None or famille(p.classe) == f.classe}
        ),
        "pilotes": sorted({p.pilote for p in perfs}),
    }


def filtres_demandes(
    perfs: list[Performance], demande: Mapping[str, str | None], profil: str | None = None
) -> Filtres:
    """Les filtres d'une demande de l'écran, sans ceux qui n'ont pas de sens : un tracé
    inconnu (on revient aux dernières courses), une catégorie absente du tracé, une
    voiture absente de la catégorie, un pilote inconnu. Sur la fiche d'un pilote
    (`profil`), le filtre de pilote est le sien, et les catégories et voitures proposées
    sont celles qu'il a roulées."""
    if profil is not None:
        f = Filtres(pilote=profil)
        base = retenues(perfs, f)
    else:
        trace = demande.get("trace")
        f = Filtres(trace=trace if trace in {p.trace for p in perfs} else None)
        base = perfs
    if demande.get("classe") in options(base, f)["classes"]:
        f = replace(f, classe=demande["classe"])
    proposees = options(base, f)
    if demande.get("voiture") in proposees["voitures"]:
        f = replace(f, voiture=demande["voiture"])
    if profil is None and demande.get("pilote") in proposees["pilotes"]:
        f = replace(f, pilote=demande["pilote"])
    return f


def _limite(demande: Mapping[str, str | None]) -> int:
    try:
        return min(max(int(demande.get("historique") or HISTORIQUE), 1), HISTORIQUE_MAX)
    except ValueError:
        return HISTORIQUE


def leaderboard_json(
    perfs: list[Performance], demande: Mapping[str, str | None], moi: set[str] = frozenset()
) -> dict:
    """Tout ce que montre l'onglet Leaderboard, d'après les seules qualifications et courses
    en ligne (`comptees`).

    La page (`vue`) dépend de la demande : un tracé (`trace`) donne la page de son circuit,
    un pilote (`profil`) sa fiche, et sans l'un ni l'autre, les dernières courses. Viennent
    avec elle les menus des circuits et des pilotes, les filtres retenus et ce que
    proposent leurs listes.
    """
    perfs = comptees(perfs)
    profil = demande.get("profil")
    if demande.get("trace") in {p.trace for p in perfs} or profil not in {p.pilote for p in perfs}:
        profil = None
    f = filtres_demandes(perfs, demande, profil)
    base = retenues(perfs, Filtres(pilote=profil)) if profil else perfs
    return {
        "vue": "circuit" if f.trace else ("pilote" if profil else "historique"),
        "filtres": asdict(f),
        "options": options(base, f),
        "circuits": menu_circuits(perfs),
        "pilotes": menu_pilotes(perfs, moi),
        "historique": historique(perfs, f, moi, _limite(demande)),
        "tours": classement_tours(perfs, f, moi),
        "voitures": classement_voitures(perfs, f, moi),
        "courses": classement_courses(perfs, f, moi),
        "profil": fiche_pilote(perfs, f, moi) if profil else None,
    }
