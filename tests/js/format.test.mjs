// Tests de ce qui, dans la page, ne dépend pas du navigateur.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  chrono,
  circuitDe,
  codeType,
  dureeSession,
  familleClasse,
  filtrerSessions,
  indiceAuTemps,
  meilleursParClasse,
  partsSecteurs,
  signe,
  statistiques,
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
  { id: "c", circuit: "Spa", date: "2026-01-04" },
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
