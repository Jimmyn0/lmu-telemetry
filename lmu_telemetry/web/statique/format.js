// Mises en forme et calculs sans rapport avec la page : aucun accès au document,
// aucune traduction. C'est ce qui permet de les tester sans navigateur (voir
// tests/js/format.test.mjs).

export function chrono(secondes, decimales = 3) {
  if (secondes === null || secondes === undefined) return "—";
  const minutes = Math.floor(secondes / 60);
  const reste = secondes - minutes * 60;
  return `${minutes}:${reste.toFixed(decimales).padStart(decimales + 3, "0")}`;
}

/** Une heure de séance à la seconde : « 9:54 », ou « 1:05:12 » au-delà d'une heure. */
export function horloge(secondes) {
  if (secondes === null || secondes === undefined) return "—";
  const total = Math.round(secondes);
  const heures = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const reste = String(total % 60).padStart(2, "0");
  return heures ? `${heures}:${String(minutes).padStart(2, "0")}:${reste}` : `${minutes}:${reste}`;
}

/**
 * Le temps restant d'une séance : « 9:54 » ; une fois le temps écoulé (le dernier tour
 * d'une course au temps, les messages d'après l'arrivée), le temps passé depuis : « +1:23 ».
 */
export function tempsRestant(secondes) {
  if (secondes === null || secondes === undefined) return "—";
  return secondes < 0 ? `+${horloge(-secondes)}` : horloge(secondes);
}

/** Le temps d'une course : « 11:37.030 », ou « 1:05:12.345 » au-delà d'une heure. */
export function dureeCourse(secondes) {
  if (secondes === null || secondes === undefined) return "—";
  if (secondes < 3600) return chrono(secondes);
  const heures = Math.floor(secondes / 3600);
  return `${heures}:${chrono(secondes - heures * 3600).padStart(9, "0")}`;
}

/**
 * Les deux pilotes que le Rythme compare d'abord : un pilote (toi, sans autre
 * précision), et le rival de sa catégorie juste devant lui au classement, ou juste
 * derrière s'il est en tête. `engages` est dans l'ordre du classement.
 */
export function duelParDefaut(engages, a = engages.findIndex((e) => e.joueur)) {
  if (a < 0) a = 0;
  const memes = engages.map((_e, rang) => rang).filter((rang) => engages[rang].classe === engages[a].classe);
  const i = memes.indexOf(a);
  const autre = engages.findIndex((_e, rang) => rang !== a);
  const b = memes[i - 1] ?? memes[i + 1] ?? autre;
  return { a, b: b >= 0 ? b : a };
}

/**
 * Les places de chaque voiture, de la grille à l'arrivée, pour le graphique des
 * positions : au général, ou dans `categorie`. Un point est [x, place] : x vaut 0 sur
 * la grille, n au tour n, et `tours + 1` à l'arrivée, pour qui l'a vue. Les voitures
 * sont rendues dans l'ordre de l'arrivée.
 */
export function courbesPositions(engages, categorie = null) {
  const retenus = engages
    .map((e, rang) => ({ e, rang }))
    .filter(({ e }) => !categorie || e.classe === categorie);
  const tours = Math.max(0, ...retenus.flatMap(({ e }) => e.tours_detail.map((x) => x.numero)));
  const voitures = retenus.map(({ e, rang }) => {
    const grille = categorie ? e.grille_classe : e.grille;
    const finale = categorie ? e.place_classe : e.place;
    const points = grille ? [[0, grille]] : [];
    for (const x of e.tours_detail) {
      const place = categorie ? x.place_categorie : x.place;
      if (place) points.push([x.numero, place]);
    }
    if (finale && e.statut === "arrivee") points.push([tours + 1, finale]);
    const abandon = e.statut === "abandon" || e.statut === "disqualifie";
    return { rang, nom: e.nom, numero: e.numero, joueur: e.joueur, finale, abandon, points };
  });
  voitures.sort((a, b) => (a.finale ?? Infinity) - (b.finale ?? Infinity));
  const places = Math.max(0, ...voitures.flatMap((v) => v.points.map(([, place]) => place)));
  return { voitures, places, tours };
}

export function signe(v, decimales = 3) {
  if (v === null || v === undefined) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(decimales);
}

/** Durée d'une session : « 40 min », ou « 1 h 05 » au-delà d'une heure. */
export function dureeSession(secondes) {
  if (!secondes) return "—";
  const minutes = Math.round(secondes / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}`;
}

// La liste des sessions donne le code (P, Q, R), un fichier ouvert le nom anglais.
const CODES_TYPE = { practice: "P", qualifying: "Q", qualify: "Q", race: "R" };

export function codeType(type) {
  const brut = String(type || "");
  return ["P", "Q", "R"].includes(brut) ? brut : CODES_TYPE[brut.toLowerCase()] || null;
}

// Le jeu écrit la catégorie de plusieurs façons : « LMP2_ELMS », « LMP2 »,
// « Hyper ». L'affichage n'en garde que la famille, qui porte la couleur.
const FAMILLES = ["GT3", "GTE", "LMP2", "LMP3", "HYPER"];

export function familleClasse(brut) {
  const texte = String(brut || "").toUpperCase();
  return FAMILLES.find((f) => texte.startsWith(f)) || null;
}

/** Ce qu'on affiche et sur quoi on filtre : le tracé dès qu'on le connaît. */
export function circuitDe(session) {
  return session.trace || session.circuit;
}

/** Sessions retenues par les filtres. */
export function filtrerSessions(sessions, { circuit = "", masquerVides = false, enLigne = false } = {}) {
  return sessions.filter(
    (s) =>
      (!circuit || circuitDe(s) === circuit) &&
      // Une session pas encore lue est gardée : on ne peut pas savoir.
      (!masquerVides || s.valides === undefined || s.valides > 0) &&
      (!enLigne || s.en_ligne)
  );
}

/**
 * Classe les sessions. Une session dont on ignore encore le chrono passe à la fin,
 * plutôt que de sauter en tête et de faire danser la liste pendant la lecture.
 */
export function trierSessions(sessions, tri) {
  if (tri !== "chrono") return sessions;
  return [...sessions].sort((a, b) => {
    const ca = a.meilleur ?? Infinity;
    const cb = b.meilleur ?? Infinity;
    if (ca !== cb) return ca - cb;
    return (b.date || "").localeCompare(a.date || "");
  });
}

/** Indice du dernier instant ≤ t dans un tableau croissant. */
export function indiceAuTemps(temps, t) {
  let bas = 0;
  let haut = temps.length - 1;
  while (bas < haut) {
    const milieu = Math.ceil((bas + haut) / 2);
    if (temps[milieu] <= t) bas = milieu;
    else haut = milieu - 1;
  }
  return bas;
}

/** Minimum, maximum et moyenne d'une portion, valeurs manquantes écartées. */
export function statistiques(valeurs, i0, i1) {
  let min = Infinity;
  let max = -Infinity;
  let somme = 0;
  let nombre = 0;
  for (let i = i0; i <= i1; i++) {
    const v = valeurs[i];
    if (v === null || v === undefined || Number.isNaN(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
    somme += v;
    nombre++;
  }
  return nombre ? { min, max, moyenne: somme / nombre } : null;
}

/** Part du tour occupée par chaque secteur, en pour cent. */
export function partsSecteurs(finS1, finS2, longueur) {
  if (!finS1 || !finS2 || !longueur) return null;
  const a = (finS1 / longueur) * 100;
  const b = (finS2 / longueur) * 100;
  return [a, b - a, 100 - b];
}

/** Meilleur chrono de chaque catégorie, dans l'ordre où elles arrivent. */
export function meilleursParClasse(records) {
  const meilleurs = new Map();
  for (const r of records) {
    const famille = familleClasse(r.classe) || r.classe;
    if (!meilleurs.has(famille) || r.chrono < meilleurs.get(famille)) {
      meilleurs.set(famille, r.chrono);
    }
  }
  return [...meilleurs.entries()].map(([classe, chrono]) => ({ classe, chrono }));
}

/**
 * Tour de comparaison proposé par défaut : le tour valide le plus proche du
 * meilleur, parce que c'est celui dont l'écart se lit le mieux.
 */
export function tourVoisin(tours, reference) {
  const valides = tours.filter(
    (t) => t.valide && t.chrono !== null && t.numero !== reference.numero
  );
  if (!valides.length) return null;
  return valides.reduce((a, b) =>
    Math.abs(a.chrono - reference.chrono) <= Math.abs(b.chrono - reference.chrono) ? a : b
  );
}
