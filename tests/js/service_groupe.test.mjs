// Le service du groupe (service/src/index.js), sur une base SQLite en mémoire qui répond
// comme D1 (service/d1_local.mjs). Lancé par tests/test_javascript.py.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { d1Local } from "../../service/d1_local.mjs";
import { LIMITES, normaliserCode, traiter } from "../../service/src/index.js";

function nouveauService() {
  const DB = d1Local();
  DB.exec(readFileSync(new URL("../../service/schema.sql", import.meta.url), "utf-8"));
  const env = { DB };
  return async (methode, chemin, { corps, membre, brut } = {}) => {
    const entetes = { "Content-Type": "application/json" };
    if (membre) entetes.Authorization = `Membre ${membre.membre}:${membre.cle}`;
    const reponse = await traiter(
      new Request(`https://groupe.test${chemin}`, {
        method: methode,
        headers: entetes,
        body: brut ?? (corps === undefined ? undefined : JSON.stringify(corps)),
      }),
      env
    );
    return { statut: reponse.status, json: await reponse.json() };
  };
}

const perf = (id, champs = {}) => ({
  id,
  date: "2026-11-02T12:00:00+00:00",
  circuit: "Autodromo Nazionale Monza",
  trace: "Autodromo Nazionale Monza",
  type: "R",
  en_ligne: true,
  pilote: "Moi",
  meilleur_tour: 100.5,
  ...champs,
});

const CONTOUR = [[0, 0], [1, 0], [0.5, 1]];

async function groupeDeDeux() {
  const service = nouveauService();
  const a = (await service("POST", "/v1/groupes", { corps: { nom: "Moi" } })).json;
  const b = (await service("POST", `/v1/groupes/${a.code}/membres`, { corps: { nom: "Ami" } })).json;
  return { service, a, b };
}

test("le service répond qu'il est là", async () => {
  const service = nouveauService();
  assert.deepEqual(await service("GET", "/v1/sante"), { statut: 200, json: { ok: true, version: 2 } });
  assert.equal((await service("GET", "/v1/inconnu")).statut, 404);
});

test("un code se recopie sans tiret ni majuscules", () => {
  assert.equal(normaliserCode("k7m2-qx9p"), "K7M2QX9P");
  assert.equal(normaliserCode(" K7M2 QX9P "), "K7M2QX9P");
  // Trop court, ou avec un I, un O, un 0 ou un 1 : ce n'est pas un code.
  for (const faux of ["K7M2QX9", "K7M2QX9PP", "K7M2QX0P", "K7M2QXIP", "", null]) assert.equal(normaliserCode(faux), null);
});

test("créer un groupe, puis le rejoindre avec son code", async () => {
  const { service, a, b } = await groupeDeDeux();
  assert.equal(a.code.length, 8);
  assert.notEqual(a.membre, b.membre);
  assert.equal(b.code, a.code);
  // Le code se saisit aussi avec un tiret et en minuscules.
  const tire = `${a.code.slice(0, 4)}-${a.code.slice(4)}`.toLowerCase();
  assert.equal((await service("POST", `/v1/groupes/${tire}/membres`, { corps: { nom: "Rival" } })).statut, 201);
  const { json } = await service("GET", `/v1/groupes/${a.code}`, { membre: a });
  assert.deepEqual(
    json.membres.map((m) => m.nom),
    ["Moi", "Ami", "Rival"]
  );
  assert.equal(json.moi, a.membre);
  // Lire le groupe note la dernière visite.
  assert.ok(json.membres[0].vu_le === null || typeof json.membres[0].vu_le === "string");
});

test("un code inconnu, un nom vide ou trop long", async () => {
  const service = nouveauService();
  assert.equal((await service("POST", "/v1/groupes/K7M2QX9P/membres", { corps: { nom: "Ami" } })).json.erreur, "groupe_introuvable");
  assert.equal((await service("POST", "/v1/groupes", { corps: { nom: "  " } })).json.erreur, "nom_invalide");
  assert.equal((await service("POST", "/v1/groupes", { corps: { nom: "x".repeat(LIMITES.nom + 1) } })).statut, 400);
  assert.equal((await service("POST", "/v1/groupes", { brut: "{pas du json" })).json.erreur, "json_invalide");
});

test("seuls les membres lisent le groupe, avec leur clé", async () => {
  const { service, a, b } = await groupeDeDeux();
  assert.equal((await service("GET", `/v1/groupes/${a.code}`)).statut, 401);
  assert.equal((await service("GET", `/v1/groupes/${a.code}`, { membre: { ...a, cle: "fausse" } })).statut, 403);
  // La clé d'un membre ne vaut que pour son groupe.
  const autre = (await service("POST", "/v1/groupes", { corps: { nom: "Ailleurs" } })).json;
  assert.equal((await service("GET", `/v1/groupes/${autre.code}`, { membre: b })).statut, 403);
});

test("les performances arrivent par version", async () => {
  const { service, a, b } = await groupeDeDeux();
  const envoi = await service("PUT", `/v1/groupes/${a.code}/performances`, {
    membre: a,
    corps: { performances: [perf("1-R"), perf("2-Q", { type: "Q" })], contours: { Monza: CONTOUR } },
  });
  assert.deepEqual(envoi.json, { version: 1, recues: 2 });

  const tout = (await service("GET", `/v1/groupes/${a.code}?depuis=0`, { membre: b })).json;
  assert.equal(tout.version, 1);
  assert.deepEqual(
    tout.performances.map((p) => [p.membre, p.performance.id]),
    [[a.membre, "1-R"], [a.membre, "2-Q"]]
  );
  assert.deepEqual(tout.performances[0].performance, perf("1-R"));
  assert.deepEqual(tout.contours, { Monza: CONTOUR });

  // Une performance qui change revient ; celles qu'on a déjà ne reviennent pas.
  await service("PUT", `/v1/groupes/${a.code}/performances`, {
    membre: a,
    corps: { performances: [perf("1-R", { meilleur_tour: 99.9 })] },
  });
  const neuf = (await service("GET", `/v1/groupes/${a.code}?depuis=1`, { membre: b })).json;
  assert.equal(neuf.version, 2);
  assert.deepEqual(
    neuf.performances.map((p) => [p.performance.id, p.performance.meilleur_tour]),
    [["1-R", 99.9]]
  );
  assert.deepEqual(neuf.contours, {});
  assert.deepEqual((await service("GET", `/v1/groupes/${a.code}?depuis=2`, { membre: b })).json.performances, []);
});

test("chacun écrit ses performances, jamais celles d'un autre", async () => {
  const { service, a, b } = await groupeDeDeux();
  await service("PUT", `/v1/groupes/${a.code}/performances`, { membre: a, corps: { performances: [perf("1-R")] } });
  // Le même numéro de séance chez l'ami : une autre performance, rangée sous son nom.
  await service("PUT", `/v1/groupes/${a.code}/performances`, {
    membre: b,
    corps: { performances: [perf("1-R", { pilote: "Ami", meilleur_tour: 98 })] },
  });
  const { json } = await service("GET", `/v1/groupes/${a.code}`, { membre: a });
  assert.deepEqual(
    json.performances.map((p) => [p.membre, p.performance.pilote, p.performance.meilleur_tour]).sort(),
    [[a.membre, "Moi", 100.5], [b.membre, "Ami", 98]].sort()
  );
  // Le premier contour d'un tracé reste.
  await service("PUT", `/v1/groupes/${a.code}/performances`, { membre: a, corps: { contours: { Monza: CONTOUR } } });
  await service("PUT", `/v1/groupes/${a.code}/performances`, {
    membre: b,
    corps: { contours: { Monza: [[0, 0], [1, 1], [0, 1]] } },
  });
  assert.deepEqual((await service("GET", `/v1/groupes/${a.code}`, { membre: a })).json.contours, { Monza: CONTOUR });
});

test("ce qui ne se garde pas", async () => {
  const { service, a } = await groupeDeDeux();
  const envoyer = (corps) => service("PUT", `/v1/groupes/${a.code}/performances`, { membre: a, corps });
  // Une séance contre l'IA, une performance sans tracé, un contour qui n'en est pas un.
  assert.equal((await envoyer({ performances: [perf("1-R", { en_ligne: false })] })).json.erreur, "performance_invalide");
  assert.equal((await envoyer({ performances: [perf("1-R", { trace: "" })] })).statut, 400);
  assert.equal((await envoyer({ contours: { Monza: [[0, 0], [5, 0], [0, 1]] } })).json.erreur, "contour_invalide");
  // Trop d'un coup, trop gros.
  const trop = Array.from({ length: LIMITES.performancesParEnvoi + 1 }, (_, i) => perf(`${i}-R`));
  assert.equal((await envoyer({ performances: trop })).statut, 413);
  assert.equal((await envoyer({ performances: [perf("1-R", { notes: "x".repeat(LIMITES.taillePerformance) })] })).statut, 413);
  // Rien n'a été écrit.
  const { json } = await service("GET", `/v1/groupes/${a.code}`, { membre: a });
  assert.deepEqual([json.version, json.performances], [0, []]);
  // Un envoi vide ne change pas la version.
  assert.deepEqual((await envoyer({})).json, { version: null, recues: 0 });
});

test("quitter efface ses performances ; le dernier parti efface le groupe", async () => {
  const { service, a, b } = await groupeDeDeux();
  await service("PUT", `/v1/groupes/${a.code}/performances`, { membre: b, corps: { performances: [perf("1-R")] } });
  // Un membre ne retire que lui-même.
  assert.equal((await service("DELETE", `/v1/groupes/${a.code}/membres/${a.membre}`, { membre: b })).statut, 403);
  assert.equal((await service("DELETE", `/v1/groupes/${a.code}/membres/${b.membre}`, { membre: b })).statut, 200);
  const { json } = await service("GET", `/v1/groupes/${a.code}`, { membre: a });
  assert.deepEqual(json.membres.map((m) => m.nom), ["Moi"]);
  assert.deepEqual(json.performances, []);
  // Parti, il ne lit plus rien.
  assert.equal((await service("GET", `/v1/groupes/${a.code}`, { membre: b })).statut, 403);
  await service("DELETE", `/v1/groupes/${a.code}/membres/${a.membre}`, { membre: a });
  assert.equal((await service("POST", `/v1/groupes/${a.code}/membres`, { corps: { nom: "Ami" } })).json.erreur, "groupe_introuvable");
});

const tourPartage = (id, champs = {}) => ({
  id,
  trace: "Autodromo Nazionale Monza",
  circuit: "Autodromo Nazionale Monza",
  voiture: "Porsche 911 GT3 R LMGT3",
  marque: "Porsche",
  classe: "GT3",
  pilote: "Moi",
  date: "2026-11-02T12:00:00+00:00",
  type: "Q",
  numero: 7,
  chrono: 99.5,
  donnees: "SGVsbG8=",
  ...champs,
});

test("les records : leur liste avec le groupe, leur télémétrie à la demande", async () => {
  const { service, a, b } = await groupeDeDeux();
  const envoyer = (tour) => service("PUT", `/v1/groupes/${a.code}/tours`, { membre: a, corps: { tour } });
  assert.deepEqual((await envoyer(tourPartage("abc"))).json, { version: 1 });

  const { json } = await service("GET", `/v1/groupes/${a.code}?depuis=0`, { membre: b });
  assert.deepEqual(
    json.tours.map((t) => [t.membre, t.id, t.maj, t.meta.chrono, t.meta.voiture, t.meta.taille]),
    [[a.membre, "abc", 1, 99.5, "Porsche 911 GT3 R LMGT3", 8]]
  );
  // La liste ne porte pas la télémétrie : elle se demande à part, quand on veut le tour.
  assert.equal(json.tours[0].meta.donnees, undefined);
  const tour = await service("GET", `/v1/groupes/${a.code}/tours/${a.membre}/abc`, { membre: b });
  assert.deepEqual(tour.json, { maj: 1, meta: json.tours[0].meta, donnees: "SGVsbG8=" });

  // Un meilleur tour sur le même tracé, dans la même voiture, remplace l'ancien.
  await envoyer(tourPartage("abc", { chrono: 99.1, donnees: "QQ==" }));
  const neuf = (await service("GET", `/v1/groupes/${a.code}?depuis=1`, { membre: b })).json;
  assert.deepEqual(neuf.tours.map((t) => [t.id, t.maj, t.meta.chrono]), [["abc", 2, 99.1]]);
  assert.equal((await service("GET", `/v1/groupes/${a.code}/tours/${a.membre}/abc`, { membre: b })).json.donnees, "QQ==");

  assert.equal(
    (await service("GET", `/v1/groupes/${a.code}/tours/${a.membre}/autre`, { membre: b })).json.erreur,
    "tour_introuvable"
  );
  assert.equal((await service("GET", `/v1/groupes/${a.code}/tours/${a.membre}/abc`)).statut, 401);

  // Parti, ses records partent avec lui.
  await service("DELETE", `/v1/groupes/${a.code}/membres/${a.membre}`, { membre: a });
  assert.deepEqual((await service("GET", `/v1/groupes/${a.code}`, { membre: b })).json.tours, []);
  assert.equal(
    (await service("GET", `/v1/groupes/${a.code}/tours/${a.membre}/abc`, { membre: b })).json.erreur,
    "tour_introuvable"
  );
});

test("un record qui ne se garde pas", async () => {
  const { service, a } = await groupeDeDeux();
  const envoyer = (tour) => service("PUT", `/v1/groupes/${a.code}/tours`, { membre: a, corps: { tour } });
  assert.equal((await envoyer(tourPartage("x", { donnees: "pas du base64 !" }))).json.erreur, "tour_invalide");
  assert.equal((await envoyer(tourPartage("x", { chrono: 0 }))).json.erreur, "tour_invalide");
  assert.equal((await envoyer(tourPartage("x", { type: "X" }))).json.erreur, "tour_invalide");
  assert.equal((await envoyer(tourPartage("x", { numero: 1.5 }))).json.erreur, "tour_invalide");
  assert.equal((await envoyer(tourPartage("x", { donnees: "A".repeat(LIMITES.tailleTour + 4) }))).statut, 413);
  assert.equal((await envoyer(undefined)).json.erreur, "tour_invalide");
  // Rien n'a été écrit.
  const { json } = await service("GET", `/v1/groupes/${a.code}`, { membre: a });
  assert.deepEqual([json.version, json.tours], [0, []]);
});

test("le classement d'une course : la liste avec le groupe, le classement à la demande", async () => {
  const { service, a, b } = await groupeDeDeux();
  const envoyer = (seance, membre = a) => service("PUT", `/v1/groupes/${a.code}/seances`, { membre, corps: { seance } });
  assert.deepEqual((await envoyer({ id: "1794245179-R", donnees: "SGVsbG8=" })).json, { version: 1 });

  const { json } = await service("GET", `/v1/groupes/${a.code}?depuis=0`, { membre: b });
  assert.deepEqual(json.seances, [{ membre: a.membre, id: "1794245179-R", maj: 1 }]);
  const lue = await service("GET", `/v1/groupes/${a.code}/seances/${a.membre}/1794245179-R`, { membre: b });
  assert.deepEqual(lue.json, { maj: 1, donnees: "SGVsbG8=" });

  // Renvoyée (le fichier du jeu réécrit), elle remplace l'ancienne et revient dans la liste.
  await envoyer({ id: "1794245179-R", donnees: "QQ==" });
  const neuf = (await service("GET", `/v1/groupes/${a.code}?depuis=1`, { membre: b })).json;
  assert.deepEqual(neuf.seances, [{ membre: a.membre, id: "1794245179-R", maj: 2 }]);

  // Ce qui ne se garde pas : un autre identifiant, des essais, autre chose que du base64, trop gros.
  for (const id of ["abc", "1794245179-P", "1-R; DROP TABLE seances"]) {
    assert.equal((await envoyer({ id, donnees: "QQ==" })).json.erreur, "seance_invalide");
  }
  assert.equal((await envoyer({ id: "2-R", donnees: "pas du base64 !" })).json.erreur, "seance_invalide");
  assert.equal((await envoyer({ id: "2-R", donnees: "A".repeat(LIMITES.tailleSeance + 4) })).statut, 413);
  assert.equal((await envoyer(undefined)).json.erreur, "seance_invalide");

  // Sans clé, rien ; une séance absente, introuvable.
  assert.equal((await service("GET", `/v1/groupes/${a.code}/seances/${a.membre}/1794245179-R`)).statut, 401);
  assert.equal(
    (await service("GET", `/v1/groupes/${a.code}/seances/${a.membre}/1-R`, { membre: b })).json.erreur,
    "seance_introuvable"
  );

  // Parti, ses séances partent avec lui.
  await service("DELETE", `/v1/groupes/${a.code}/membres/${a.membre}`, { membre: a });
  assert.deepEqual((await service("GET", `/v1/groupes/${a.code}`, { membre: b })).json.seances, []);
});

test("un groupe complet refuse un membre de plus", async () => {
  const service = nouveauService();
  const a = (await service("POST", "/v1/groupes", { corps: { nom: "Moi" } })).json;
  for (let i = 1; i < LIMITES.membres; i++) {
    assert.equal((await service("POST", `/v1/groupes/${a.code}/membres`, { corps: { nom: `Pilote ${i}` } })).statut, 201);
  }
  assert.equal((await service("POST", `/v1/groupes/${a.code}/membres`, { corps: { nom: "De trop" } })).json.erreur, "groupe_complet");
});
