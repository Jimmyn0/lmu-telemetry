# Notes de version

Une entrée par version distribuée, la plus récente en haut. Le numéro est
celui de `lmu_telemetry/__init__.py` : le dernier chiffre augmente pour une
correction, celui du milieu pour un ajout.

---

## 1.1.0 — 23/09/2026

**L'outil existe en anglais.**

* Bouton **FR | EN** en haut à droite : toute l'interface change de langue,
  sans perdre l'écran en cours ni le zoom. Le choix est retenu d'un lancement à
  l'autre. Au premier lancement, l'outil prend la langue du navigateur.
* Tout est traduit : écrans, graphiques, remarques sur les tours, remarques par
  virage, avertissements, messages d'erreur, noms de pays, et la fenêtre noire
  du `.exe`, qui suit la langue choisie (ou celle de Windows).
* Mode d'emploi en anglais, `README.txt`, à côté de `LISEZ-MOI.txt`.
* Un test vérifie que les deux langues ont exactement les mêmes phrases : un
  oubli empêche de construire le `.exe`.

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
