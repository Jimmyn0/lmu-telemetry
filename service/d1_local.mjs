// Une base qui répond comme D1, servie par le SQLite intégré à Node (22.5 et plus) : le
// service tourne ainsi sur ce PC, pour les tests et pour l'essayer, sans Cloudflare.
//
// Seul ce dont le service se sert est imité : prepare, bind, first, all, run, batch, exec.

import { DatabaseSync } from "node:sqlite";

const ligneSimple = (ligne) => ({ ...ligne });

export function d1Local(chemin = ":memory:") {
  const base = new DatabaseSync(chemin);

  function prepare(sql) {
    let valeurs = [];
    const instruction = {
      bind(...v) {
        valeurs = v;
        return instruction;
      },
      async first(colonne) {
        const ligne = base.prepare(sql).get(...valeurs);
        if (ligne === undefined) return null;
        return colonne === undefined ? ligneSimple(ligne) : ligne[colonne];
      },
      async all() {
        return lire();
      },
      async run() {
        const resultat = base.prepare(sql).run(...valeurs);
        return { success: true, results: [], meta: { changes: Number(resultat.changes) } };
      },
      lire,
    };
    function lire() {
      return { success: true, results: base.prepare(sql).all(...valeurs).map(ligneSimple), meta: {} };
    }
    return instruction;
  }

  return {
    prepare,
    // Comme D1 : les instructions d'un lot passent ensemble, ou pas du tout.
    async batch(instructions) {
      base.exec("BEGIN");
      try {
        const resultats = instructions.map((instruction) => instruction.lire());
        base.exec("COMMIT");
        return resultats;
      } catch (erreur) {
        base.exec("ROLLBACK");
        throw erreur;
      }
    },
    exec(sql) {
      base.exec(sql);
    },
  };
}
