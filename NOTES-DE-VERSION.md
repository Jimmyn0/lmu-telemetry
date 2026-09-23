# Notes de version

Une entrée par version distribuée, la plus récente en haut. Le numéro est
celui de `lmu_telemetry/__init__.py` : le dernier chiffre augmente pour une
correction, celui du milieu pour un ajout.

---

## 1.0.0 — 23/09/2026

Première version distribuée, en `.exe` autonome.

* **Liste des sessions** : tri par date ou par meilleur chrono, filtre par
  circuit, variantes de tracé séparées (Monza et Monza Curva Grande).
* **Tours d'une session** : chronos, secteurs, validité ; meilleur tour et
  meilleurs secteurs en violet.
* **Comparaison de deux tours**, y compris de deux sessions différentes :
  delta cumulé, vitesse, pédales, angle volant en degrés, rapport, carte du
  circuit et vue rapprochée de la route.
* **Virage par virage** : virages numérotés T1, T2… comme sur les cartes
  officielles, temps perdu ou gagné sur chacun, freinage, vitesses, remise des
  gaz, temps sur l'erre.
* **Régularité** : dispersion des chronos, tour idéal, virages où tu es le moins
  constant.
* **Modèle de la voiture**, logo de la marque et drapeau du circuit.
* Le jeu est trouvé tout seul dans les bibliothèques Steam ; sinon, l'outil
  demande le dossier et retient la réponse.
