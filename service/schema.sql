-- La base du service du groupe (Cloudflare D1, c'est-à-dire SQLite). Voir docs/20-groupe.md.
--
-- Chaque écriture dans un groupe augmente sa version ; les lignes écrites la portent. Un PC
-- qui a déjà reçu la version N ne demande que les lignes plus récentes.

CREATE TABLE IF NOT EXISTS groupes (
  code TEXT PRIMARY KEY,
  cree_le TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0
);

-- La clé secrète d'un membre n'est jamais gardée : seulement son empreinte SHA-256.
CREATE TABLE IF NOT EXISTS membres (
  id TEXT PRIMARY KEY,
  groupe TEXT NOT NULL,
  cle TEXT NOT NULL,
  nom TEXT NOT NULL,
  rejoint_le TEXT NOT NULL,
  vu_le TEXT
);
CREATE INDEX IF NOT EXISTS membres_par_groupe ON membres (groupe);

-- Une performance (une séance d'un pilote), telle que l'outil l'envoie, en JSON.
CREATE TABLE IF NOT EXISTS performances (
  groupe TEXT NOT NULL,
  membre TEXT NOT NULL,
  id TEXT NOT NULL,
  donnees TEXT NOT NULL,
  maj INTEGER NOT NULL,
  PRIMARY KEY (groupe, membre, id)
);
CREATE INDEX IF NOT EXISTS performances_par_version ON performances (groupe, maj);

-- La télémétrie d'un record (le meilleur tour d'un membre sur un tracé, dans une voiture),
-- pour la comparer dans l'onglet Télémétrie. `meta` : ce que montre la liste des tours ;
-- `donnees` : le tour lui-même, en JSON compressé (gzip) puis en base64, lu à la demande.
CREATE TABLE IF NOT EXISTS tours (
  groupe TEXT NOT NULL,
  membre TEXT NOT NULL,
  id TEXT NOT NULL,
  meta TEXT NOT NULL,
  donnees TEXT NOT NULL,
  maj INTEGER NOT NULL,
  PRIMARY KEY (groupe, membre, id)
);
CREATE INDEX IF NOT EXISTS tours_par_version ON tours (groupe, maj);

-- Le classement complet d'une course en ligne d'un membre (son fichier de résultats, mis en
-- forme par l'outil), pour l'ouvrir dans l'onglet Résultats d'un autre PC. `id` : celui de la
-- performance (« 1794245179-R ») ; `donnees` : du JSON compressé (gzip) puis en base64, lu à
-- la demande, comme la télémétrie d'un tour.
CREATE TABLE IF NOT EXISTS seances (
  groupe TEXT NOT NULL,
  membre TEXT NOT NULL,
  id TEXT NOT NULL,
  donnees TEXT NOT NULL,
  maj INTEGER NOT NULL,
  PRIMARY KEY (groupe, membre, id)
);
CREATE INDEX IF NOT EXISTS seances_par_version ON seances (groupe, maj);

-- Le contour d'un tracé, pour le fond des cartes : le premier envoyé reste.
CREATE TABLE IF NOT EXISTS contours (
  groupe TEXT NOT NULL,
  trace TEXT NOT NULL,
  points TEXT NOT NULL,
  maj INTEGER NOT NULL,
  PRIMARY KEY (groupe, trace)
);
