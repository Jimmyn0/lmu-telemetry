// Tests de ce qui, dans la page, ne dépend pas du navigateur.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  chrono,
  circuitDe,
  codeType,
  courbesPositions,
  duelParDefaut,
  dureeCourse,
  dureeSession,
  familleClasse,
  filtrerSessions,
  horloge,
  indiceAuTemps,
  meilleursParClasse,
  partsSecteurs,
  signe,
  statistiques,
  tempsRestant,
  tourVoisin,
  trierSessions,
} from "../../lmu_telemetry/web/statique/format.js";

test("un chrono s'écrit comme à l'écran du jeu", () => {
  assert.equal(chrono(113.208), "1:53.208");
  assert.equal(chrono(59.5), "0:59.500");
  assert.equal(chrono(60), "1:00.000");
  assert.equal(chrono(null), "—");
  assert.equal(chrono(undefined), "—");
});

test("le temps d'une course passe aux heures au-delà d'une heure", () => {
  assert.equal(dureeCourse(697.0297), "11:37.030");
  assert.equal(dureeCourse(3599.5), "59:59.500");
  assert.equal(dureeCourse(3912.345), "1:05:12.345");
  assert.equal(dureeCourse(null), "—");
});

test("le rythme compare d'abord le pilote au rival de sa catégorie juste devant", () => {
  const engages = [
    { classe: "Hyper" }, { classe: "GT3" }, { classe: "Hyper" }, { classe: "GT3", joueur: true },
  ];
  assert.deepEqual(duelParDefaut(engages), { a: 3, b: 1 });
  // En tête de sa catégorie : le rival juste derrière.
  assert.deepEqual(duelParDefaut(engages, 1), { a: 1, b: 3 });
  // Seul de sa catégorie : la voiture suivante, quelle qu'elle soit.
  assert.deepEqual(duelParDefaut([{ classe: "LMP2", joueur: true }, { classe: "GT3" }]), { a: 0, b: 1 });
  // Personne de marqué : le leader.
  assert.deepEqual(duelParDefaut([{ classe: "GT3" }, { classe: "GT3" }]), { a: 0, b: 1 });
  assert.deepEqual(duelParDefaut([{ classe: "GT3" }]), { a: 0, b: 0 });
});

test("les positions vont de la grille à l'arrivée, au général ou dans la catégorie", () => {
  const tour = (numero, place, placeCategorie) => ({ numero, place, place_categorie: placeCategorie });
  const engages = [
    { nom: "A", classe: "Hyper", grille: 1, grille_classe: 1, place: 1, place_classe: 1, statut: "arrivee",
      tours_detail: [tour(1, 1, 1), tour(2, 1, 1)] },
    { nom: "B", classe: "GT3", grille: 3, grille_classe: 2, place: 2, place_classe: 1, statut: "arrivee",
      tours_detail: [tour(1, 3, 2), tour(2, 2, 1)] },
    { nom: "C", classe: "GT3", grille: 2, grille_classe: 1, place: 3, place_classe: 2, statut: "abandon",
      tours_detail: [tour(1, 2, 1)] },
  ];
  const general = courbesPositions(engages);
  assert.equal(general.tours, 2);
  assert.equal(general.places, 3);
  // L'arrivée vient après le dernier tour ; une voiture qui abandonne s'arrête à son dernier tour.
  assert.deepEqual(general.voitures[1].points, [[0, 3], [1, 3], [2, 2], [3, 2]]);
  assert.deepEqual(general.voitures[2].points, [[0, 2], [1, 2]]);
  assert.equal(general.voitures[2].abandon, true);
  const gt3 = courbesPositions(engages, "GT3");
  assert.deepEqual(gt3.voitures.map((v) => v.nom), ["B", "C"]);
  assert.deepEqual(gt3.voitures[0].points, [[0, 2], [1, 2], [2, 1], [3, 1]]);
  assert.equal(gt3.places, 2);
});

test("une heure de séance se lit à la seconde", () => {
  assert.equal(horloge(593.7), "9:54");
  assert.equal(horloge(5), "0:05");
  assert.equal(horloge(3912.4), "1:05:12");
  assert.equal(horloge(null), "—");
});

test("après la fin du temps, le temps restant devient le temps passé depuis", () => {
  assert.equal(tempsRestant(593.7), "9:54");
  assert.equal(tempsRestant(0), "0:00");
  assert.equal(tempsRestant(-83), "+1:23");
  assert.equal(tempsRestant(null), "—");
});

test("un écart porte toujours son signe", () => {
  assert.equal(signe(0.825), "+0.825");
  assert.equal(signe(-0.136), "-0.136");
  assert.equal(signe(0), "+0.000");
  assert.equal(signe(1.5, 1), "+1.5");
  assert.equal(signe(null), "—");
});

test("la durée d'une session passe aux heures au-delà de 60 minutes", () => {
  assert.equal(dureeSession(2400), "40 min");
  assert.equal(dureeSession(3900), "1 h 05");
  assert.equal(dureeSession(0), "—");
});

test("le type de session se reconnaît sous ses deux écritures", () => {
  assert.equal(codeType("R"), "R");
  assert.equal(codeType("Race"), "R");
  assert.equal(codeType("Qualify"), "Q");
  assert.equal(codeType("qualifying"), "Q");
  assert.equal(codeType("Practice"), "P");
  assert.equal(codeType("Warmup"), null);
});

test("la catégorie se ramène à sa famille", () => {
  assert.equal(familleClasse("LMP2_ELMS"), "LMP2");
  assert.equal(familleClasse("Hyper"), "HYPER");
  assert.equal(familleClasse("GT3"), "GT3");
  assert.equal(familleClasse("Inconnue"), null);
  assert.equal(familleClasse(undefined), null);
});

const sessions = [
  { id: "a", circuit: "Monza", trace: "Monza GP", valides: 3, meilleur: 110, date: "2026-01-02" },
  { id: "b", circuit: "Monza", valides: 0, date: "2026-01-03" },
  { id: "c", circuit: "Spa", date: "2026-01-04", en_ligne: true },
  { id: "d", circuit: "Spa", valides: 1, meilleur: 100, date: "2026-01-01" },
];

test("le tracé prime sur le nom du fichier", () => {
  assert.equal(circuitDe(sessions[0]), "Monza GP");
  assert.equal(circuitDe(sessions[1]), "Monza");
});

test("les filtres gardent ce qu'on ne connaît pas encore", () => {
  const noms = (l) => l.map((s) => s.id).join("");
  assert.equal(noms(filtrerSessions(sessions)), "abcd");
  assert.equal(noms(filtrerSessions(sessions, { masquerVides: true })), "acd");
  assert.equal(noms(filtrerSessions(sessions, { circuit: "Spa" })), "cd");
  assert.equal(noms(filtrerSessions(sessions, { enLigne: true })), "c");
});

test("le tri par chrono met les inconnues à la fin, sans toucher à l'original", () => {
  const avant = [...sessions];
  const tries = trierSessions(sessions, "chrono");
  assert.deepEqual(tries.map((s) => s.id), ["d", "a", "c", "b"]);
  assert.deepEqual(sessions, avant);
  assert.equal(trierSessions(sessions, "date"), sessions);
});

test("la lecture du tour retrouve le bon instant", () => {
  const temps = [0, 1, 2, 2, 3];
  assert.equal(indiceAuTemps(temps, -1), 0);
  assert.equal(indiceAuTemps(temps, 0.5), 0);
  assert.equal(indiceAuTemps(temps, 2), 3);
  assert.equal(indiceAuTemps(temps, 99), 4);
});

test("les statistiques ignorent les valeurs manquantes et respectent la portion", () => {
  const valeurs = [1, null, 3, Number.NaN, 5, 100];
  assert.deepEqual(statistiques(valeurs, 0, 4), { min: 1, max: 5, moyenne: 3 });
  assert.equal(statistiques([null, null], 0, 1), null);
});

test("les secteurs se partagent tout le tour", () => {
  const parts = partsSecteurs(1000, 3000, 5000);
  assert.deepEqual(parts, [20, 40, 40]);
  assert.equal(parts.reduce((a, b) => a + b), 100);
  assert.equal(partsSecteurs(null, 3000, 5000), null);
});

test("chaque catégorie garde son meilleur chrono", () => {
  const records = [
    { classe: "GT3", chrono: 112 },
    { classe: "LMP2_ELMS", chrono: 100 },
    { classe: "GT3", chrono: 110 },
  ];
  assert.deepEqual(meilleursParClasse(records), [
    { classe: "GT3", chrono: 110 },
    { classe: "LMP2", chrono: 100 },
  ]);
});

test("le tour proposé en comparaison est le plus proche de la référence", () => {
  const tours = [
    { numero: 1, chrono: 115, valide: true },
    { numero: 2, chrono: 113.5, valide: true },
    { numero: 3, chrono: 113.1, valide: false },
    { numero: 4, chrono: null, valide: true },
    { numero: 5, chrono: 113, valide: true },
  ];
  assert.equal(tourVoisin(tours, tours[4]).numero, 2);
  assert.equal(tourVoisin([tours[4]], tours[4]), null);
});
