// Le service du groupe : il garde les performances que les membres d'un groupe partagent.
//
// Un Worker Cloudflare et sa base D1 (voir docs/20-groupe.md et schema.sql). Il ne parle
// qu'à l'outil, jamais à une page web : du JSON, pas de CORS.
//
// Le code d'un groupe permet de le rejoindre. En rejoignant, chaque membre reçoit une clé
// secrète : elle seule permet de lire le groupe, et d'écrire ou d'effacer SES performances.
// La base n'en garde que l'empreinte. Tout le monde voit qui est dans le groupe.
//
// L'offre gratuite de Cloudflare compte 10 ms de calcul par requête : les performances
// reçues entrent dans la base en une seule requête (un tableau JSON que lit `json_each`),
// et celles qu'on renvoie y restent du texte, sans être relues.

// 2 : le classement des courses (`seances`), et le meilleur tour de chacune parmi les tours.
export const VERSION = 2;

// Ni I, O, 0 ni 1 : rien à confondre en recopiant un code.
const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const LONGUEUR_CODE = 8;
const LONGUEUR_MEMBRE = 12;

export const LIMITES = {
  membres: 50,
  nom: 40,
  corps: 2 * 1024 * 1024, // octets par requête
  performancesParEnvoi: 200,
  performancesParMembre: 20000,
  taillePerformance: 8 * 1024, // octets de JSON
  contoursParEnvoi: 40,
  pointsParContour: 400,
  // Ses records, et le meilleur tour de chacune de ses courses en ligne.
  toursParMembre: 1000,
  tailleTour: 1536 * 1024, // caractères de base64 : un tour du Mans en fait 140 000
  seancesParMembre: 2000,
  tailleSeance: 512 * 1024, // caractères de base64 : une course de 42 voitures en fait 40 000
};

// L'identifiant d'une performance de course ou de qualifs : son départ, et son type.
const ID_SEANCE = /^\d{1,12}-[QR]$/;

const TYPES = new Set(["P", "Q", "R"]);

class ErreurService extends Error {
  constructor(statut, code, message) {
    super(message);
    this.statut = statut;
    this.code = code;
  }
}

const ENTETES = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };

const repondre = (charge, statut = 200) => new Response(JSON.stringify(charge), { status: statut, headers: ENTETES });

const maintenant = () => new Date().toISOString();

// 256 est un multiple de 32 : chaque caractère a la même chance de sortir.
function aleatoire(longueur) {
  return Array.from(crypto.getRandomValues(new Uint8Array(longueur)), (o) => ALPHABET[o % ALPHABET.length]).join("");
}

function cleSecrete() {
  const octets = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...octets)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function empreinte(texte) {
  const octets = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texte));
  return Array.from(new Uint8Array(octets), (o) => o.toString(16).padStart(2, "0")).join("");
}

/** Un code tel qu'on le saisit (« k7m2-qx9p ») ramené à sa forme rangée ; null s'il n'en est pas un. */
export function normaliserCode(brut) {
  const code = String(brut ?? "").toUpperCase().replace(/[\s-]/g, "");
  if (code.length !== LONGUEUR_CODE || [...code].some((c) => !ALPHABET.includes(c))) return null;
  return code;
}

function nomValide(brut) {
  const nom = typeof brut === "string" ? brut.trim() : "";
  if (!nom || nom.length > LIMITES.nom) {
    throw new ErreurService(400, "nom_invalide", `un nom de 1 à ${LIMITES.nom} caractères est attendu`);
  }
  return nom;
}

async function lireCorps(requete) {
  const texte = await requete.text();
  if (texte.length > LIMITES.corps) throw new ErreurService(413, "trop_gros", "envoi trop gros");
  if (!texte) return {};
  let corps;
  try {
    corps = JSON.parse(texte);
  } catch {
    throw new ErreurService(400, "json_invalide", "JSON illisible");
  }
  if (!corps || typeof corps !== "object" || Array.isArray(corps)) {
    throw new ErreurService(400, "json_invalide", "un objet JSON est attendu");
  }
  return corps;
}

// « Authorization: Membre <numéro>:<clé> »
async function membreAuthentifie(requete, env, code) {
  const trouve = /^Membre ([A-Z0-9]+):(\S+)$/.exec(requete.headers.get("Authorization") || "");
  if (!trouve) throw new ErreurService(401, "non_membre", "la clé d'un membre est attendue");
  const membre = await env.DB.prepare("SELECT id, nom FROM membres WHERE id = ? AND groupe = ? AND cle = ?")
    .bind(trouve[1], code, await empreinte(trouve[2]))
    .first();
  if (!membre) throw new ErreurService(403, "non_membre", "ce membre ne fait pas partie de ce groupe");
  return membre;
}

const texteCourt = (v, max) => typeof v === "string" && v.length > 0 && v.length <= max;

// Le service ne garde que des performances de séances en ligne, qui disent qui, où et
// quand. Le reste, c'est l'outil qui le vérifie en les recevant.
function validerPerformance(p) {
  const valide =
    p &&
    typeof p === "object" &&
    !Array.isArray(p) &&
    texteCourt(p.id, 64) &&
    texteCourt(p.pilote, 64) &&
    texteCourt(p.circuit, 160) &&
    texteCourt(p.trace, 160) &&
    texteCourt(p.date, 40) &&
    TYPES.has(p.type) &&
    p.en_ligne === true;
  if (!valide) throw new ErreurService(400, "performance_invalide", "une performance ne se lit pas");
  if (JSON.stringify(p).length > LIMITES.taillePerformance) {
    throw new ErreurService(413, "trop_gros", "une performance est trop grosse");
  }
  return p;
}

const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;

// Ce que la liste des tours en montre ; le tour lui-même reste dans `donnees`, que le
// service range sans le lire : c'est l'outil qui le vérifie en le recevant.
function validerTour(t) {
  const valide =
    t &&
    typeof t === "object" &&
    !Array.isArray(t) &&
    texteCourt(t.id, 64) &&
    texteCourt(t.trace, 160) &&
    texteCourt(t.circuit, 160) &&
    texteCourt(t.voiture, 160) &&
    (t.marque === null || t.marque === undefined || (typeof t.marque === "string" && t.marque.length <= 80)) &&
    (t.classe === null || t.classe === undefined || (typeof t.classe === "string" && t.classe.length <= 40)) &&
    texteCourt(t.pilote, 64) &&
    texteCourt(t.date, 40) &&
    TYPES.has(t.type) &&
    Number.isInteger(t.numero) &&
    t.numero >= 0 &&
    typeof t.chrono === "number" &&
    t.chrono > 0 &&
    t.chrono < 3600 &&
    typeof t.donnees === "string";
  if (!valide) throw new ErreurService(400, "tour_invalide", "un tour ne se lit pas");
  if (t.donnees.length > LIMITES.tailleTour) throw new ErreurService(413, "trop_gros", "un tour est trop gros");
  if (!BASE64.test(t.donnees)) throw new ErreurService(400, "tour_invalide", "un tour ne se lit pas");
  const meta = {
    trace: t.trace,
    circuit: t.circuit,
    voiture: t.voiture,
    marque: t.marque ?? null,
    classe: t.classe ?? null,
    pilote: t.pilote,
    date: t.date,
    type: t.type,
    numero: t.numero,
    chrono: t.chrono,
    taille: t.donnees.length,
  };
  return { id: t.id, meta: JSON.stringify(meta), donnees: t.donnees };
}

// Le classement d'une course, rangé sans être lu, comme la télémétrie d'un tour : c'est
// l'outil qui le vérifie en le recevant.
function validerSeance(s) {
  const valide = s && typeof s === "object" && !Array.isArray(s) && typeof s.id === "string" && ID_SEANCE.test(s.id) &&
    typeof s.donnees === "string";
  if (!valide) throw new ErreurService(400, "seance_invalide", "une séance ne se lit pas");
  if (s.donnees.length > LIMITES.tailleSeance) throw new ErreurService(413, "trop_gros", "une séance est trop grosse");
  if (!BASE64.test(s.donnees)) throw new ErreurService(400, "seance_invalide", "une séance ne se lit pas");
  return { id: s.id, donnees: s.donnees };
}

function validerContour([trace, points]) {
  const valide =
    texteCourt(trace, 160) &&
    Array.isArray(points) &&
    points.length >= 3 &&
    points.length <= LIMITES.pointsParContour &&
    points.every(
      (point) =>
        Array.isArray(point) &&
        point.length === 2 &&
        point.every((v) => typeof v === "number" && Number.isFinite(v) && v >= -0.1 && v <= 1.1)
    );
  if (!valide) throw new ErreurService(400, "contour_invalide", "un contour ne se lit pas");
  return [trace, points];
}

// ---------------------------------------------------------------------
// Les routes
// ---------------------------------------------------------------------

async function nouveauMembre(env, code, nom) {
  const membre = aleatoire(LONGUEUR_MEMBRE);
  const cle = cleSecrete();
  await env.DB.prepare("INSERT INTO membres (id, groupe, cle, nom, rejoint_le) VALUES (?, ?, ?, ?, ?)")
    .bind(membre, code, await empreinte(cle), nom, maintenant())
    .run();
  return { code, membre, cle };
}

async function creerGroupe(requete, env) {
  const nom = nomValide((await lireCorps(requete)).nom);
  // Un code déjà pris (une chance sur mille milliards) : on en tire un autre.
  for (let essai = 0; essai < 5; essai++) {
    const code = aleatoire(LONGUEUR_CODE);
    const cree = await env.DB.prepare("INSERT OR IGNORE INTO groupes (code, cree_le, version) VALUES (?, ?, 0)")
      .bind(code, maintenant())
      .run();
    if (cree.meta.changes === 1) return repondre(await nouveauMembre(env, code, nom), 201);
  }
  throw new ErreurService(503, "indisponible", "aucun code libre, réessaie");
}

async function rejoindre(requete, env, code) {
  const nom = nomValide((await lireCorps(requete)).nom);
  const groupe = await env.DB.prepare(
    "SELECT (SELECT count(*) FROM membres WHERE groupe = ?) AS membres FROM groupes WHERE code = ?"
  )
    .bind(code, code)
    .first();
  if (!groupe) throw new ErreurService(404, "groupe_introuvable", "aucun groupe n'a ce code");
  if (groupe.membres >= LIMITES.membres) throw new ErreurService(403, "groupe_complet", "ce groupe est complet");
  return repondre(await nouveauMembre(env, code, nom), 201);
}

// Ce que le groupe a de neuf depuis la version `depuis` : ses membres, les performances et
// les contours écrits depuis. Les performances restent le texte rangé dans la base.
async function lireGroupe(requete, env, code, url) {
  const moi = await membreAuthentifie(requete, env, code);
  const depuis = Math.max(0, Number.parseInt(url.searchParams.get("depuis") || "0", 10) || 0);
  const [groupe, membres, performances, contours, tours, seances] = await env.DB.batch([
    env.DB.prepare("SELECT version FROM groupes WHERE code = ?").bind(code),
    // Dans l'ordre d'arrivée : deux membres arrivés dans la même milliseconde gardent le leur.
    env.DB.prepare("SELECT id, nom, rejoint_le, vu_le FROM membres WHERE groupe = ? ORDER BY rowid").bind(code),
    env.DB.prepare("SELECT membre, donnees FROM performances WHERE groupe = ? AND maj > ? ORDER BY maj").bind(code, depuis),
    env.DB.prepare("SELECT trace, points FROM contours WHERE groupe = ? AND maj > ?").bind(code, depuis),
    // Des tours, seulement ce qu'en montre la liste : la télémétrie se demande à part.
    env.DB.prepare("SELECT membre, id, meta, maj FROM tours WHERE groupe = ? AND maj > ? ORDER BY maj").bind(code, depuis),
    // Des séances, seulement lesquelles sont là : leur classement se demande à part.
    env.DB.prepare("SELECT membre, id, maj FROM seances WHERE groupe = ? AND maj > ? ORDER BY maj").bind(code, depuis),
    env.DB.prepare("UPDATE membres SET vu_le = ? WHERE id = ?").bind(maintenant(), moi.id),
  ]);
  // Les numéros de membre et les contours viennent de la base, déjà vérifiés : ils se
  // recopient tels quels.
  const corps =
    `{"code":${JSON.stringify(code)},"version":${groupe.results[0].version},"moi":${JSON.stringify(moi.id)},` +
    `"membres":${JSON.stringify(membres.results)},` +
    `"performances":[${performances.results.map((p) => `{"membre":"${p.membre}","performance":${p.donnees}}`).join(",")}],` +
    `"contours":{${contours.results.map((c) => `${JSON.stringify(c.trace)}:${c.points}`).join(",")}},` +
    `"tours":[${tours.results
      .map((t) => `{"membre":"${t.membre}","id":${JSON.stringify(t.id)},"maj":${t.maj},"meta":${t.meta}}`)
      .join(",")}],` +
    `"seances":${JSON.stringify(seances.results)}}`;
  return new Response(corps, { status: 200, headers: ENTETES });
}

// Le classement d'une course : un membre en envoie un à la fois ; renvoyé, il remplace l'ancien.
async function envoyerSeance(requete, env, code) {
  const moi = await membreAuthentifie(requete, env, code);
  const seance = validerSeance((await lireCorps(requete)).seance);
  const deja = await env.DB.prepare(
    "SELECT count(*) AS n, sum(id = ?) AS meme FROM seances WHERE groupe = ? AND membre = ?"
  )
    .bind(seance.id, code, moi.id)
    .first();
  if (!deja.meme && deja.n >= LIMITES.seancesParMembre) {
    throw new ErreurService(413, "trop_gros", "trop de séances pour un seul membre");
  }
  const [version] = await env.DB.batch([
    env.DB.prepare("UPDATE groupes SET version = version + 1 WHERE code = ? RETURNING version").bind(code),
    env.DB.prepare(
      `INSERT INTO seances (groupe, membre, id, donnees, maj)
       VALUES (?, ?, ?, ?, (SELECT version FROM groupes WHERE code = ?))
       ON CONFLICT (groupe, membre, id) DO UPDATE SET donnees = excluded.donnees, maj = excluded.maj`
    ).bind(code, moi.id, seance.id, seance.donnees, code),
  ]);
  return repondre({ version: version.results[0].version });
}

async function lireSeance(requete, env, code, membre, id) {
  await membreAuthentifie(requete, env, code);
  const seance = await env.DB.prepare("SELECT donnees, maj FROM seances WHERE groupe = ? AND membre = ? AND id = ?")
    .bind(code, membre, id)
    .first();
  if (!seance) throw new ErreurService(404, "seance_introuvable", "cette séance n'est plus dans le groupe");
  return new Response(`{"maj":${seance.maj},"donnees":"${seance.donnees}"}`, { status: 200, headers: ENTETES });
}

// La télémétrie d'un record : un membre en envoie un à la fois, le même tracé et la
// même voiture remplaçant l'ancien.
async function envoyerTour(requete, env, code) {
  const moi = await membreAuthentifie(requete, env, code);
  const tour = validerTour((await lireCorps(requete)).tour);
  const deja = await env.DB.prepare(
    "SELECT count(*) AS n, sum(id = ?) AS meme FROM tours WHERE groupe = ? AND membre = ?"
  )
    .bind(tour.id, code, moi.id)
    .first();
  if (!deja.meme && deja.n >= LIMITES.toursParMembre) {
    throw new ErreurService(413, "trop_gros", "trop de tours pour un seul membre");
  }
  const [version] = await env.DB.batch([
    env.DB.prepare("UPDATE groupes SET version = version + 1 WHERE code = ? RETURNING version").bind(code),
    env.DB.prepare(
      `INSERT INTO tours (groupe, membre, id, meta, donnees, maj)
       VALUES (?, ?, ?, ?, ?, (SELECT version FROM groupes WHERE code = ?))
       ON CONFLICT (groupe, membre, id) DO UPDATE SET meta = excluded.meta, donnees = excluded.donnees, maj = excluded.maj`
    ).bind(code, moi.id, tour.id, tour.meta, tour.donnees, code),
  ]);
  return repondre({ version: version.results[0].version });
}

async function lireTour(requete, env, code, membre, id) {
  await membreAuthentifie(requete, env, code);
  const tour = await env.DB.prepare("SELECT meta, donnees, maj FROM tours WHERE groupe = ? AND membre = ? AND id = ?")
    .bind(code, membre, id)
    .first();
  if (!tour) throw new ErreurService(404, "tour_introuvable", "ce tour n'est plus dans le groupe");
  return new Response(`{"maj":${tour.maj},"meta":${tour.meta},"donnees":"${tour.donnees}"}`, {
    status: 200,
    headers: ENTETES,
  });
}

async function envoyer(requete, env, code) {
  const moi = await membreAuthentifie(requete, env, code);
  const corps = await lireCorps(requete);
  const performances = (Array.isArray(corps.performances) ? corps.performances : []).map(validerPerformance);
  const contours =
    corps.contours && typeof corps.contours === "object" && !Array.isArray(corps.contours)
      ? Object.entries(corps.contours).map(validerContour)
      : [];
  if (performances.length > LIMITES.performancesParEnvoi || contours.length > LIMITES.contoursParEnvoi) {
    throw new ErreurService(413, "trop_gros", "trop de performances ou de contours d'un coup");
  }
  if (!performances.length && !contours.length) return repondre({ version: null, recues: 0 });
  const deja = await env.DB.prepare("SELECT count(*) AS n FROM performances WHERE groupe = ? AND membre = ?")
    .bind(code, moi.id)
    .first();
  if (deja.n + performances.length > LIMITES.performancesParMembre) {
    throw new ErreurService(413, "trop_gros", "trop de performances pour un seul membre");
  }
  // Tout d'un bloc : la nouvelle version, et les lignes qui la portent.
  const instructions = [
    env.DB.prepare("UPDATE groupes SET version = version + 1 WHERE code = ? RETURNING version").bind(code),
  ];
  if (performances.length) {
    instructions.push(
      env.DB.prepare(
        `INSERT INTO performances (groupe, membre, id, donnees, maj)
         SELECT ?, ?, json_extract(value, '$.id'), value, (SELECT version FROM groupes WHERE code = ?)
         FROM json_each(?) WHERE true
         ON CONFLICT (groupe, membre, id) DO UPDATE SET donnees = excluded.donnees, maj = excluded.maj`
      ).bind(code, moi.id, code, JSON.stringify(performances))
    );
  }
  if (contours.length) {
    instructions.push(
      env.DB.prepare(
        `INSERT INTO contours (groupe, trace, points, maj)
         SELECT ?, json_extract(value, '$[0]'), json_extract(value, '$[1]'), (SELECT version FROM groupes WHERE code = ?)
         FROM json_each(?) WHERE true
         ON CONFLICT (groupe, trace) DO NOTHING`
      ).bind(code, code, JSON.stringify(contours))
    );
  }
  const [version] = await env.DB.batch(instructions);
  return repondre({ version: version.results[0].version, recues: performances.length });
}

// Un membre ne peut retirer que lui-même, et ses performances partent avec lui. Le dernier
// parti, le groupe disparaît.
async function quitter(requete, env, code, membre) {
  const moi = await membreAuthentifie(requete, env, code);
  if (membre !== moi.id) throw new ErreurService(403, "non_membre", "un membre ne peut retirer que lui-même");
  await env.DB.batch([
    env.DB.prepare("UPDATE groupes SET version = version + 1 WHERE code = ?").bind(code),
    env.DB.prepare("DELETE FROM performances WHERE groupe = ? AND membre = ?").bind(code, moi.id),
    env.DB.prepare("DELETE FROM tours WHERE groupe = ? AND membre = ?").bind(code, moi.id),
    env.DB.prepare("DELETE FROM seances WHERE groupe = ? AND membre = ?").bind(code, moi.id),
    env.DB.prepare("DELETE FROM membres WHERE id = ?").bind(moi.id),
    env.DB.prepare("DELETE FROM contours WHERE groupe = ? AND NOT EXISTS (SELECT 1 FROM membres WHERE groupe = ?)").bind(
      code,
      code
    ),
    env.DB.prepare("DELETE FROM groupes WHERE code = ? AND NOT EXISTS (SELECT 1 FROM membres WHERE groupe = ?)").bind(
      code,
      code
    ),
  ]);
  return repondre({ quitte: true });
}

/** Répond à une requête : `env.DB` est la base (D1 sur Cloudflare, SQLite en local). */
export async function traiter(requete, env) {
  const url = new URL(requete.url);
  const morceaux = url.pathname.split("/").filter(Boolean);
  const methode = requete.method;
  try {
    if (morceaux[0] !== "v1") throw new ErreurService(404, "route_inconnue", "route inconnue");
    const [, ressource, brut, sous, membre] = morceaux;
    if (ressource === "sante" && morceaux.length === 2 && methode === "GET") {
      return repondre({ ok: true, version: VERSION });
    }
    if (ressource !== "groupes") throw new ErreurService(404, "route_inconnue", "route inconnue");
    if (morceaux.length === 2 && methode === "POST") return await creerGroupe(requete, env);
    const code = normaliserCode(brut);
    if (!code) throw new ErreurService(404, "groupe_introuvable", "aucun groupe n'a ce code");
    if (morceaux.length === 3 && methode === "GET") return await lireGroupe(requete, env, code, url);
    if (morceaux.length === 4 && sous === "membres" && methode === "POST") return await rejoindre(requete, env, code);
    if (morceaux.length === 4 && sous === "performances" && methode === "PUT") return await envoyer(requete, env, code);
    if (morceaux.length === 4 && sous === "tours" && methode === "PUT") return await envoyerTour(requete, env, code);
    if (morceaux.length === 6 && sous === "tours" && methode === "GET") {
      return await lireTour(requete, env, code, membre, decodeURIComponent(morceaux[5]));
    }
    if (morceaux.length === 4 && sous === "seances" && methode === "PUT") return await envoyerSeance(requete, env, code);
    if (morceaux.length === 6 && sous === "seances" && methode === "GET") {
      return await lireSeance(requete, env, code, membre, decodeURIComponent(morceaux[5]));
    }
    if (morceaux.length === 5 && sous === "membres" && methode === "DELETE") {
      return await quitter(requete, env, code, membre);
    }
    throw new ErreurService(404, "route_inconnue", "route inconnue");
  } catch (erreur) {
    if (erreur instanceof ErreurService) {
      return repondre({ erreur: erreur.code, message: erreur.message }, erreur.statut);
    }
    console.error(erreur);
    return repondre({ erreur: "interne", message: "le service a rencontré un problème" }, 500);
  }
}

export default {
  fetch: (requete, env) => traiter(requete, env),
};
