"""Erreurs de l'outil, avec des messages qui disent quoi faire.

Le brief demande explicitement : « Message d'erreur explicite qui me dit quoi
faire, pas une stacktrace. » Toutes les erreurs prévisibles passent donc par
une de ces classes, et la ligne de commande les affiche telles quelles.
"""

from __future__ import annotations

from pathlib import Path


class ErreurTelemetrie(Exception):
    """Erreur attendue, avec un message destiné à être lu par l'utilisateur."""


class FichierIntrouvable(ErreurTelemetrie):
    def __init__(self, chemin: Path) -> None:
        super().__init__(
            f"Fichier introuvable : {chemin}\n"
            "Vérifie le chemin. Les sessions de LMU se trouvent normalement dans :\n"
            r"  <dossier Steam>\steamapps\common\Le Mans Ultimate\UserData\Telemetry"
        )


class DossierIntrouvable(ErreurTelemetrie):
    """Le dossier de télémétrie (ou un dossier demandé) n'existe pas.

    Trois cas, trois messages : un chemin précis qui n'existe pas ; le jeu
    trouvé mais sans aucune session enregistrée ; le jeu introuvable.
    L'interface web reconnaît cette erreur et propose de choisir le dossier.
    """

    def __init__(self, chemin: Path | None, jeu_trouve: bool = False) -> None:
        self.chemin = chemin
        if jeu_trouve:
            message = (
                "Le Mans Ultimate est bien installé, mais n'a encore enregistré "
                "aucune session : le dossier\n"
                f"  {chemin}\n"
                "n'existe pas encore. Roule une session (même quelques tours en "
                "essais), quitte-la, puis relance l'outil."
            )
        elif chemin is None:
            message = (
                "Impossible de trouver Le Mans Ultimate sur cet ordinateur.\n"
                "Indique le dossier où le jeu enregistre ta télémétrie. Il se "
                "trouve dans le dossier d'installation du jeu :\n"
                r"  ...\steamapps\common\Le Mans Ultimate\UserData\Telemetry"
            )
        else:
            message = (
                f"Ce dossier n'existe pas :\n  {chemin}\n"
                "Indique le dossier où Le Mans Ultimate enregistre ta télémétrie :\n"
                r"  ...\steamapps\common\Le Mans Ultimate\UserData\Telemetry"
            )
        super().__init__(message)


class SessionEnCours(ErreurTelemetrie):
    """Le jeu tient le fichier ouvert en écriture : il est illisible."""

    def __init__(self, chemin: Path, detail: str = "") -> None:
        message = (
            f"Cette session est en cours d'enregistrement par le jeu :\n"
            f"  {chemin.name}\n\n"
            "Le Mans Ultimate garde le fichier ouvert tant que la session tourne.\n"
            "Quitte le jeu (ou au moins reviens au menu principal et attends quelques\n"
            "secondes), puis réessaie."
        )
        if detail:
            message += f"\n\nDétail technique : {detail}"
        super().__init__(message)


class SchemaInconnu(ErreurTelemetrie):
    """La structure du fichier n'est pas celle qu'on sait lire."""

    def __init__(self, chemin: Path, trouve: str | None, supportees: set[str]) -> None:
        super().__init__(
            f"Version de format non reconnue dans : {chemin.name}\n"
            f"  trouvée   : {trouve!r}\n"
            f"  supportée : {', '.join(sorted(supportees))}\n\n"
            "Le format des fichiers de télémétrie a probablement changé avec une mise\n"
            "à jour de Le Mans Ultimate. Procure-toi la dernière version de l'outil.\n\n"
            "Pour qui maintient l'outil : seul le module lmu_telemetry/reader.py est\n"
            "concerné ; `python -m lmu_telemetry info <fichier>` montre la structure réelle."
        )


class DonneeManquante(ErreurTelemetrie):
    """On a demandé un canal ou un événement qui n'existe pas dans ce fichier."""

    def __init__(self, nom: str, disponibles: list[str]) -> None:
        proches = [d for d in disponibles if nom.lower() in d.lower()][:5]
        message = f"« {nom} » n'existe pas dans ce fichier."
        if proches:
            message += "\nPeut-être cherchais-tu : " + ", ".join(proches)
        message += f"\n({len(disponibles)} noms disponibles ; `info <fichier>` les liste tous.)"
        super().__init__(message)
