// Temps au tour : les records de chaque voiture, par circuit.
//
// Les variantes d'un même circuit ne se comparent pas : la colonne de gauche regroupe
// par circuit, mais les temps affichés sont toujours ceux d'un seul tracé.

import {
  $, api, badgeClasse, badgeType, dateJour, erreur, etat, etatVide, navigation,
} from "/commun.js";
import { drapeau, echapper, embleme } from "/emblemes.js";
import { chrono, familleClasse, meilleursParClasse } from "/format.js";
import { ICONES } from "/icones.js";
import { langue, t, tp } from "/i18n.js";
import { ouvrirSession } from "/ecran_resultats.js";
import { ouvrirTelemetrie } from "/ecran_telemetrie.js";

// Ordre des catégories, de la plus rapide à la plus lente.
const ORDRE_CLASSES = ["HYPER", "LMP2", "LMP3", "GTE", "GT3"];

const vue = { circuit: null, trace: null, classe: null, tri: "az", classesMasquees: new Set() };
let suivi = null;

async function charger() {
  const reponse = await api("/api/circuits");
  etat.circuits = reponse;
  clearTimeout(suivi);
  if (reponse.restant > 0) {
    suivi = setTimeout(() => {
      if (etat.onglet === "temps") charger().then(afficher).catch(() => {});
    }, 2000);
  }
}

const classeDe = (record) => familleClasse(record.classe) || record.classe;

function circuitsAffiches() {
  const liste = [...etat.circuits.circuits].filter((c) =>
    c.traces.some((x) => x.records.some((r) => !vue.classesMasquees.has(classeDe(r))))
  );
  if (vue.tri === "sessions") {
    const total = (c) => c.traces.reduce((n, x) => n + x.sessions, 0);
    return liste.sort((a, b) => total(b) - total(a));
  }
  return liste.sort((a, b) => a.circuit.localeCompare(b.circuit, langue()));
}

// Le tracé du circuit tient lieu d'image de fond : il ne doit rien à personne, et il
// dit mieux où l'on est.
function contourSvg(points) {
  if (!points) return "";
  const chemin = points.map(([x, y]) => `${(x * 100).toFixed(1)},${(y * 100).toFixed(1)}`).join(" ");
  return `<svg class="contour" viewBox="-4 -4 108 108" preserveAspectRatio="xMaxYMid meet" aria-hidden="true">
    <polygon points="${chemin}"/></svg>`;
}

function carteCircuit(c) {
  const principal = c.traces[0];
  const sessions = c.traces.reduce((n, x) => n + x.sessions, 0);
  const meilleurs = meilleursParClasse(principal.records)
    .filter((m) => !vue.classesMasquees.has(m.classe))
    .sort((a, b) => ORDRE_CLASSES.indexOf(b.classe) - ORDRE_CLASSES.indexOf(a.classe));
  return `<button type="button" class="carte-circuit ${vue.circuit === c.circuit ? "actif" : ""}"
      data-circuit="${echapper(c.circuit)}">
    ${contourSvg(principal.contour)}
    <span class="ligne-titre">${drapeau(c.pays)}<span class="nom">${echapper(c.circuit)}</span></span>
    <span class="sous">${tp("temps.sessions", sessions)}${
      c.traces.length > 1 ? `<i>${t("temps.traces", { n: c.traces.length })}</i>` : ""
    }</span>
    ${meilleurs
      .slice(0, 3)
      .map(
        (m) => `<span class="ligne-classe">${badgeClasse(m.classe)}<b>${chrono(m.chrono)}</b></span>`
      )
      .join("")}
  </button>`;
}

function afficherLaterale() {
  const lateral = $("#laterale");
  const circuits = circuitsAffiches();
  const haut = lateral.querySelector(".liste-laterale")?.scrollTop || 0;
  const classes = [
    ...new Set(
      etat.circuits.circuits.flatMap((c) => c.traces.flatMap((x) => x.records.map(classeDe)))
    ),
  ].sort((a, b) => ORDRE_CLASSES.indexOf(a) - ORDRE_CLASSES.indexOf(b));

  lateral.innerHTML = `
    <div class="entete-laterale">
      <h2>${t("temps.circuits")}</h2>
      <span class="badge compteur-blanc">${circuits.length}</span>
      <span class="espace"></span>
      <button id="tri-circuits" type="button" class="pilule claire">${
        t(vue.tri === "az" ? "temps.tri_az" : "temps.tri_sessions")
      }</button>
      <button id="filtres-circuits" type="button" class="pilule">${t("sessions.filtres")}</button>
    </div>
    <div id="panneau-classes" class="filtres" hidden>
      ${classes
        .map(
          (c) => `<label class="case"><input type="checkbox" data-classe="${echapper(c)}"
            ${vue.classesMasquees.has(c) ? "" : "checked"}> ${badgeClasse(c)}</label>`
        )
        .join("")}
    </div>
    ${etat.circuits.restant
      ? `<div class="note avancement"><span class="roue"></span>${tp("sessions.lecture", etat.circuits.restant)}</div>`
      : ""}
    <div class="liste-laterale" id="liste-circuits">${circuits.map(carteCircuit).join("")}</div>`;

  const liste = $("#liste-circuits");
  liste.scrollTop = haut;
  liste.onclick = (e) => {
    const carte = e.target.closest(".carte-circuit");
    if (!carte) return;
    vue.circuit = carte.dataset.circuit;
    vue.trace = null;
    vue.classe = null;
    afficher();
  };
  $("#tri-circuits").onclick = () => {
    vue.tri = vue.tri === "az" ? "sessions" : "az";
    afficherLaterale();
  };
  $("#filtres-circuits").onclick = () => {
    $("#panneau-classes").hidden = !$("#panneau-classes").hidden;
  };
  for (const c of lateral.querySelectorAll("[data-classe]")) {
    c.onchange = () => {
      if (c.checked) vue.classesMasquees.delete(c.dataset.classe);
      else vue.classesMasquees.add(c.dataset.classe);
      afficherLaterale();
      $("#panneau-classes").hidden = false;
    };
  }
}

function classesDe(trace) {
  return [...new Set(trace.records.map(classeDe))].sort(
    (a, b) => ORDRE_CLASSES.indexOf(b) - ORDRE_CLASSES.indexOf(a)
  );
}

function carteMeilleur(trace, classe, type) {
  const record = trace.meilleurs.find((m) => classeDe(m) === classe && m.type === type);
  if (!record) return "";
  return `<div class="carte-record">
    <div class="ligne">${embleme(record.voiture.marque)}
      <span>${echapper(record.voiture.modele || record.voiture.engagement)}</span>
      <span class="espace"></span>${badgeType(type)}</div>
    <div class="ligne bas">${badgeClasse(classe)}<span class="espace"></span>
      <b class="temps-violet">${chrono(record.chrono)}</b></div>
  </div>`;
}

function afficherContenu() {
  const cible = $("#ecran-temps");
  const circuits = circuitsAffiches();
  const circuit = circuits.find((c) => c.circuit === vue.circuit) || circuits[0];
  if (!circuit) {
    cible.innerHTML = etatVide({
      icone: "chrono",
      titre: t("temps.vide_titre"),
      texte: t(etat.circuits.restant ? "temps.vide_lecture" : "temps.vide_texte"),
      chargement: etat.circuits.restant > 0,
    });
    return;
  }
  vue.circuit = circuit.circuit;
  const trace = circuit.traces.find((x) => x.trace === vue.trace) || circuit.traces[0];
  vue.trace = trace.trace;
  const classes = classesDe(trace);
  if (!classes.includes(vue.classe)) vue.classe = classes[0] ?? null;
  const records = trace.records.filter((r) => !vue.classesMasquees.has(classeDe(r)));

  const groupes = ORDRE_CLASSES.concat(classes.filter((c) => !ORDRE_CLASSES.includes(c)))
    .filter((classe) => records.some((r) => classeDe(r) === classe))
    .sort((a, b) => {
      const meilleur = (c) => Math.min(...records.filter((r) => classeDe(r) === c).map((r) => r.chrono));
      return meilleur(a) - meilleur(b);
    });

  cible.innerHTML = `
    <div class="carte entete-temps">
      <div class="entete-temps-haut">
        <span class="grand-drapeau">${drapeau(circuit.pays)}</span>
        <div class="titres">
          <h1>${echapper(circuit.circuit)}</h1>
          <p>${t("temps.meilleurs_de", { pilote: echapper(etat.circuits.pilote || "") })}</p>
        </div>
        <span class="espace"></span>
        ${circuit.traces.length > 1
          ? `<label class="choix-trace"><small>${t("temps.trace")}</small>
              <select id="choix-trace">${circuit.traces
                .map(
                  (x) => `<option value="${echapper(x.trace)}" ${x === trace ? "selected" : ""}>
                    ${echapper(x.trace)}</option>`
                )
                .join("")}</select></label>`
          : ""}
        ${classes.length
          ? `<div class="comparer-classe"><small>${t("temps.comparer_classe")}</small>
              <div>${classes
                .map(
                  (c) => `<button type="button" data-choix-classe="${echapper(c)}"
                    class="${c === vue.classe ? "actif" : ""}">${badgeClasse(c)}</button>`
                )
                .join("")}</div></div>`
          : ""}
      </div>
      <div class="tuiles-temps">
        ${carteMeilleur(trace, vue.classe, "Q")}
        ${carteMeilleur(trace, vue.classe, "R")}
        <div class="tuile-totale"><small>${t("temps.total_tours")}</small><b>${trace.tours.toLocaleString(langue())}</b></div>
        <div class="tuile-totale"><small>${t("temps.voitures")}</small><b>${trace.voitures}</b></div>
        <div class="tuile-totale"><small>${t("temps.sessions_titre")}</small><b>${trace.sessions}</b></div>
      </div>
    </div>
    <div class="entete-records">
      <h3>${t("temps.records")}</h3>
      <span class="espace"></span>
      <small>${tp("temps.records_voiture", records.length)}</small>
    </div>
    ${groupes.map((g) => groupeRecords(g, records)).join("") ||
      etatVide({ icone: "chrono", titre: t("temps.aucun_record"), texte: t("temps.aucun_record_texte") })}`;

  const choixTrace = $("#choix-trace");
  if (choixTrace) {
    choixTrace.onchange = (e) => {
      vue.trace = e.target.value;
      afficher();
    };
  }
  for (const bouton of cible.querySelectorAll("[data-choix-classe]")) {
    bouton.onclick = () => {
      vue.classe = bouton.dataset.choixClasse;
      afficherContenu();
    };
  }
  for (const bouton of cible.querySelectorAll("[data-ouvrir]")) {
    bouton.onclick = () => {
      const { session, tour } = bouton.dataset;
      if (bouton.dataset.ouvrir === "telemetrie") {
        ouvrirTelemetrie({ ref: session, tourRef: +tour, cmp: null, tourCmp: null }).catch((e) =>
          erreur(e.message)
        );
      } else {
        // Connue avant de changer d'onglet, qui ouvrirait sinon la dernière session.
        etat.sessionChoisie = session;
        navigation.aller("resultats");
        ouvrirSession(session).catch((e) => erreur(e.message));
      }
    };
  }
}

function groupeRecords(classe, records) {
  const lignes = records.filter((r) => classeDe(r) === classe);
  const meilleur = lignes[0].chrono;
  const secteur = (r, i) => (r.secteurs[i] === null ? "—" : r.secteurs[i].toFixed(3));
  return `<div class="groupe-records classe-${familleClasse(classe) || "autre"}">
    <div class="groupe-records-entete">
      <div>${badgeClasse(classe)}<small>${tp("temps.records_voiture", lignes.length)}</small></div>
      <span class="espace"></span>
      <b>${chrono(meilleur)}</b>
    </div>
    <table>
      <thead><tr>
        <th>${t("temps.col.session")}</th><th>${t("temps.col.voiture")}</th>
        <th class="nombre">S1</th><th class="nombre">S2</th><th class="nombre">S3</th>
        <th class="centre">${t("temps.col.temps")}</th>
        <th class="centre">${t("temps.col.ouvrir")}</th>
      </tr></thead>
      <tbody>${lignes
        .map(
          (r) => `<tr>
            <td>${badgeType(r.type)}</td>
            <td class="voiture-date">${embleme(r.voiture.marque)}<span>
              <strong>${echapper(r.voiture.modele || r.voiture.engagement)}</strong>
              <small>${dateJour(r.date)}</small></span></td>
            <td class="nombre">${secteur(r, 0)}</td>
            <td class="nombre">${secteur(r, 1)}</td>
            <td class="nombre">${secteur(r, 2)}</td>
            <td class="centre"><span class="pastille-temps record">${chrono(r.chrono)}</span>${
              r.chrono > meilleur ? `<small class="ecart-record">+${(r.chrono - meilleur).toFixed(3)}</small>` : ""
            }</td>
            <td class="centre actions-record">
              <button type="button" class="bouton-carre petit vert" data-ouvrir="telemetrie"
                data-session="${echapper(r.session)}" data-tour="${r.tour}"
                title="${t("temps.ouvrir_telemetrie")}">${ICONES.courbe}</button>
              <button type="button" class="bouton-carre petit bleu" data-ouvrir="session"
                data-session="${echapper(r.session)}" data-tour="${r.tour}"
                title="${t("temps.ouvrir_session")}">${ICONES.lien}</button>
            </td>
          </tr>`
        )
        .join("")}</tbody>
    </table>
  </div>`;
}

function afficher() {
  if (etat.onglet !== "temps" || !etat.circuits) return;
  afficherLaterale();
  afficherContenu();
}

/** L'onglet vient d'être affiché. */
export async function surTemps() {
  if (!etat.circuits) {
    $("#laterale").innerHTML = "";
    $("#ecran-temps").innerHTML = etatVide({ chargement: true, titre: t("temps.chargement") });
  } else {
    afficher();
  }
  try {
    await charger();
    afficher();
  } catch (e) {
    $("#ecran-temps").innerHTML = etatVide({
      icone: "avertissement", titre: t("temps.impossible"), texte: echapper(e.message),
    });
  }
}

export const ecranTemps = {
  rafraichir: afficher,
};
