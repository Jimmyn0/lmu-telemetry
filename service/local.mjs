// Le service du groupe sur ce PC, pour les tests et pour l'essayer sans Cloudflare.
//
// Le même code que sur Cloudflare (src/index.js), servi par Node, avec le SQLite de Node à
// la place de D1 (d1_local.mjs). Il n'écoute que 127.0.0.1.
//
//   node service/local.mjs [--port 8787] [--base groupe.sqlite]
//
// Sans --base, la base vit en mémoire et disparaît avec lui. Il écrit « pret <port> » dès
// qu'il écoute : `--port 0` laisse le système choisir un port libre.

import { readFileSync } from "node:fs";
import { createServer } from "node:http";

import { d1Local } from "./d1_local.mjs";
import { traiter } from "./src/index.js";

const args = process.argv.slice(2);
const option = (nom, defaut) => {
  const i = args.indexOf(nom);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : defaut;
};

const DB = d1Local(option("--base", ":memory:"));
DB.exec(readFileSync(new URL("./schema.sql", import.meta.url), "utf-8"));
const env = { DB };

const serveur = createServer(async (req, res) => {
  const morceaux = [];
  for await (const morceau of req) morceaux.push(morceau);
  const entetes = new Headers();
  for (const [nom, valeur] of Object.entries(req.headers)) {
    if (typeof valeur === "string") entetes.set(nom, valeur);
  }
  const requete = new Request(`http://127.0.0.1${req.url}`, {
    method: req.method,
    headers: entetes,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : Buffer.concat(morceaux),
  });
  const reponse = await traiter(requete, env);
  res.writeHead(reponse.status, Object.fromEntries(reponse.headers));
  res.end(Buffer.from(await reponse.arrayBuffer()));
});

serveur.listen(Number(option("--port", "8787")), "127.0.0.1", () => {
  console.log(`pret ${serveur.address().port}`);
});
