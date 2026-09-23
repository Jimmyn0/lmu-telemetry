"""Erreurs de l'outil, avec des messages qui disent quoi faire.

Le brief demande explicitement : « Message d'erreur explicite qui me dit quoi
faire, pas une stacktrace. » Toutes les erreurs prévisibles passent donc par
une de ces classes, et la ligne de commande les affiche telles quelles.

Chaque erreur porte un `Message` (voir `textes.py`) : une clé et des valeurs.
L'interface l'affiche dans la langue choisie ; `str(erreur)` donne la phrase
française, pour la ligne de commande et les journaux.
"""

from __future__ import annotations

from pathlib import Path

from .textes import Message


class ErreurTelemetrie(Exception):
    """Erreur attendue, avec un message destiné à être lu par l'utilisateur.

    Accepte un `Message` (traduisible) ou, pour ce qui ne sert qu'en ligne de
    commande, une simple phrase.
    """

    def __init__(self, message: str | Message) -> None:
        self.message = message if isinstance(message, Message) else None
        super().__init__(str(message))

    @classmethod
    def de(cls, cle: str, **valeurs: str | int | float) -> "ErreurTelemetrie":
        return cls(Message(cle, valeurs))


class FichierIntrouvable(ErreurTelemetrie):
    def __init__(self, chemin: Path) -> None:
        super().__init__(Message("serveur.erreur.fichier_introuvable", {"chemin": str(chemin)}))


class DossierIntrouvable(ErreurTelemetrie):
    """Le dossier de télémétrie (ou un dossier demandé) n'existe pas.

    Trois cas, trois messages : un chemin précis qui n'existe pas ; le jeu
    trouvé mais sans aucune session enregistrée ; le jeu introuvable.
    L'interface web reconnaît cette erreur et propose de choisir le dossier.
    """

    def __init__(self, chemin: Path | None, jeu_trouve: bool = False) -> None:
        self.chemin = chemin
        if jeu_trouve:
            message = Message("serveur.erreur.jeu_sans_session", {"chemin": str(chemin)})
        elif chemin is None:
            message = Message("serveur.erreur.jeu_introuvable")
        else:
            message = Message("serveur.erreur.dossier_inexistant", {"chemin": str(chemin)})
        super().__init__(message)


class SessionEnCours(ErreurTelemetrie):
    """Le jeu tient le fichier ouvert en écriture : il est illisible."""

    def __init__(self, chemin: Path, detail: str = "") -> None:
        if detail:
            message = Message(
                "serveur.erreur.session_en_cours_detail", {"fichier": chemin.name, "detail": detail}
            )
        else:
            message = Message("serveur.erreur.session_en_cours", {"fichier": chemin.name})
        super().__init__(message)


class SchemaInconnu(ErreurTelemetrie):
    """La structure du fichier n'est pas celle qu'on sait lire."""

    def __init__(self, chemin: Path, trouve: str | None, supportees: set[str]) -> None:
        super().__init__(
            Message(
                "serveur.erreur.schema_inconnu",
                {
                    "fichier": chemin.name,
                    "trouve": repr(trouve),
                    "supportees": ", ".join(sorted(supportees)),
                },
            )
        )


class DonneeManquante(ErreurTelemetrie):
    """On a demandé un canal ou un événement qui n'existe pas dans ce fichier."""

    def __init__(self, nom: str, disponibles: list[str]) -> None:
        proches = [d for d in disponibles if nom.lower() in d.lower()][:5]
        valeurs = {"nom": nom, "n": len(disponibles)}
        if proches:
            message = Message(
                "serveur.erreur.donnee_manquante_proches",
                {**valeurs, "proches": ", ".join(proches)},
            )
        else:
            message = Message("serveur.erreur.donnee_manquante", valeurs)
        super().__init__(message)
