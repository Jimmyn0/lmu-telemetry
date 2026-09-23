"""Point d'entrée du .exe.

PyInstaller exécute ce fichier comme un script isolé, hors de tout paquet : il
ne peut donc pas être `lmu_telemetry/lanceur.py` lui-même, dont les imports
relatifs (`from . import ...`) échoueraient. Il se contente de l'appeler.
"""

from lmu_telemetry.lanceur import main

raise SystemExit(main())
