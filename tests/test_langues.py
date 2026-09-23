"""Les deux langues de l'interface restent synchronisées.

Sans ces tests, un correctif qui ajoute une phrase en français et oublie
l'anglais passerait inaperçu : la version anglaise afficherait la clé brute
(« session.lecture ») ou le texte français. Comme `construire-exe.bat` passe les
tests avant de construire, un oubli bloque la construction du .exe.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from lmu_telemetry.web import serveur

STATIQUE = Path(serveur.STATIQUE)
LANGUES = ("fr", "en")


def _textes(langue: str) -> dict[str, str]:
    return json.loads((STATIQUE / "langues" / f"{langue}.json").read_text(encoding="utf-8"))


def _code_de_la_page() -> str:
    fichiers = sorted(STATIQUE.glob("*.js")) + [STATIQUE / "index.html"]
    return "\n".join(f.read_text(encoding="utf-8") for f in fichiers)


def _code_du_serveur() -> str:
    """Le code Python : c'est lui qui choisit les messages `serveur.*`."""
    paquet = STATIQUE.parent.parent
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted(paquet.rglob("*.py")))


def test_les_deux_langues_ont_les_memes_cles() -> None:
    fr, en = _textes("fr"), _textes("en")
    assert sorted(set(fr) - set(en)) == [], "clés sans traduction anglaise"
    assert sorted(set(en) - set(fr)) == [], "clés sans texte français"


@pytest.mark.parametrize("langue", LANGUES)
def test_aucun_texte_vide(langue: str) -> None:
    assert [cle for cle, texte in _textes(langue).items() if not texte.strip()] == []


def test_memes_emplacements_et_memes_balises() -> None:
    """Un `{n}` oublié dans une traduction laisserait « {n} » à l'écran ; une
    balise oubliée casserait la mise en page de toute la ligne."""
    fr, en = _textes("fr"), _textes("en")
    for cle in fr:
        assert set(re.findall(r"\{(\w+)\}", fr[cle])) == set(
            re.findall(r"\{(\w+)\}", en[cle])
        ), cle
        assert sorted(re.findall(r"</?\w+", fr[cle])) == sorted(
            re.findall(r"</?\w+", en[cle])
        ), cle


def test_chaque_cle_utilisee_existe() -> None:
    code = _code_de_la_page()
    textes = _textes("fr")
    utilisees = set(re.findall(r"\bt\(\s*\"([\w.]+)\"", code))
    utilisees |= set(re.findall(r'data-t(?:-html|-placeholder|-title)?="([\w.]+)"', code))
    pluriels = set(re.findall(r"\btp\(\s*\"([\w.]+)\"", code))
    manquantes = sorted(c for c in utilisees if c not in textes)
    manquantes += sorted(
        f"{c}.{forme}" for c in pluriels for forme in ("un", "plusieurs")
        if f"{c}.{forme}" not in textes
    )
    assert manquantes == []


def test_chaque_cle_definie_sert() -> None:
    """Une clé qui n'apparaît nulle part dans le code est un reste : elle
    embrouille la traduction sans rien afficher."""
    code = _code_de_la_page() + _code_du_serveur()
    inutiles = []
    for cle in _textes("fr"):
        base = re.sub(r"\.(un|plusieurs)$", "", cle)
        if f'"{cle}"' not in code and f'"{base}"' not in code:
            inutiles.append(cle)
    assert inutiles == []


def test_chaque_message_du_serveur_existe() -> None:
    """Toute clé `serveur.*` écrite dans le code Python a sa phrase."""
    textes = _textes("fr")
    utilisees = set(re.findall(r'"(serveur\.[\w.]+)"', _code_du_serveur()))
    assert utilisees, "aucune clé serveur trouvée : le test ne regarde plus au bon endroit"
    assert sorted(c for c in utilisees if c not in textes) == []


@pytest.mark.parametrize("langue", LANGUES)
def test_messages_du_serveur_sans_balise(langue: str) -> None:
    """Les messages du serveur sont affichés en texte brut, et leurs valeurs
    (chemins, noms de voiture) viennent de fichiers : aucune balise n'y a sa
    place."""
    assert [
        cle for cle, texte in _textes(langue).items()
        if cle.startswith("serveur.") and re.search(r"</?\w+", texte)
    ] == []


def test_le_francais_du_serveur_vient_du_meme_fichier() -> None:
    """La ligne de commande écrit exactement la phrase de fr.json."""
    from lmu_telemetry.textes import Message

    message = Message("serveur.tour.quasi_arret", {"vitesse": "27", "duree": "1.6"})
    assert str(message) == "quasi-arrêt en piste (27 km/h pendant 1.6 s)"
    assert message.json() == {
        "cle": "serveur.tour.quasi_arret",
        "valeurs": {"vitesse": "27", "duree": "1.6"},
    }


class _TexteEnDur(HTMLParser):
    """Relève le texte visible de la page qui n'est pas confié à une traduction."""

    NEUTRES = {"Le Mans Ultimate"}

    def __init__(self) -> None:
        super().__init__()
        self.pile: list[bool] = []
        self.ignore = 0
        self.trouves: list[str] = []

    def handle_starttag(self, balise, attributs):
        if balise in ("script", "style", "title"):
            self.ignore += 1
        if balise in ("meta", "link", "input", "br", "img"):
            return
        traduit = any(nom.startswith("data-t") for nom, _ in attributs)
        self.pile.append(traduit or (bool(self.pile) and self.pile[-1]))

    def handle_endtag(self, balise):
        if balise in ("script", "style", "title"):
            self.ignore -= 1
        if balise not in ("meta", "link", "input", "br", "img") and self.pile:
            self.pile.pop()

    def handle_data(self, donnees):
        texte = donnees.strip()
        if (
            not self.ignore
            and re.search(r"[A-Za-zÀ-ÿ]{3,}", texte)
            and not (self.pile and self.pile[-1])
            and texte not in self.NEUTRES
        ):
            self.trouves.append(texte)


def test_aucun_texte_en_dur_dans_la_page() -> None:
    lecteur = _TexteEnDur()
    lecteur.feed((STATIQUE / "index.html").read_text(encoding="utf-8"))
    assert lecteur.trouves == []


# ----------------------------------------------------------------------
# Le choix de la langue
# ----------------------------------------------------------------------


def test_langue_retenue_dans_les_reglages() -> None:
    assert serveur._version()["langue"] is None
    assert serveur._choisir_langue({"langue": "en"}) == {"langue": "en"}
    assert serveur._version()["langue"] == "en"


def test_langue_inconnue_refusee() -> None:
    with pytest.raises(Exception, match="Langue inconnue"):
        serveur._choisir_langue({"langue": "de"})


# ----------------------------------------------------------------------
# La fenêtre du .exe
# ----------------------------------------------------------------------


def test_la_fenetre_suit_la_langue_choisie(monkeypatch) -> None:
    """La fenêtre s'affiche avant la page : elle lit la langue enregistrée par
    le bouton FR | EN, et à défaut prend celle de Windows."""
    from lmu_telemetry import emplacements, textes

    monkeypatch.setattr(textes, "langue_du_systeme", lambda: "fr")
    assert textes.langue_preferee() == "fr"
    emplacements.enregistrer_reglages({"langue": "en"})
    assert textes.langue_preferee() == "en"
    emplacements.enregistrer_reglages({"langue": "klingon"})
    assert textes.langue_preferee() == "fr"


def test_la_fenetre_parle_anglais(monkeypatch, capsys) -> None:
    import threading

    from lmu_telemetry import lanceur

    http_serveur = serveur.creer_serveur(0)
    threading.Thread(target=http_serveur.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(lanceur, "PORT", http_serveur.server_address[1])
        assert lanceur.lancer("en", ouvrir_navigateur=False) == 0
    finally:
        http_serveur.shutdown()
        http_serveur.server_close()
    sortie = capsys.readouterr().out
    assert "LMU Telemetry" in sortie
    assert "already open" in sortie
