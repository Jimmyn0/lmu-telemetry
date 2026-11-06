// Résultats : une session, ses tours et sa régularité.

import {
  $, $$, api, badgeClasse, badgeType, dateCourte, erreur, etat, etatVide, fleche, nomType,
} from "/commun.js";
import { COULEURS } from "/graphes.js";
import { dessinerChronos } from "/chronos.js";
import { drapeau, echapper, embleme } from "/emblemes.js";
import { chrono, codeType, dureeSession, signe, tourVoisin } from "/format.js";
import { ICONES } from "/icones.js";
import { t, traduire } from "/i18n.js";
import { barreSessions, derniereSessionUtile } from "/barre_sessions.js";
import { ouvrirTelemetrie } from "/ecran_telemetrie.js";

let vueCourante = "tours";
let choix = { ref: null, cmp: null };
let regularite = null;

const meilleurDe = (tours) => {
  const valides = tours.filter((x) => x.valide && x.chrono !== null);
  return valides.length ? valides.reduce((a, b) => (a.chrono <= b.chrono ? a : b)) : null;
};

/** Ouvre une session. `montrer` fait défiler la colonne de gauche jusqu'à elle. */
export async function ouvrirSession(chemin, { montrer = true } = {}) {
  barreSessions.marquer(chemin, { montrer });
  etat.session = null;
  $("#vue-session").innerHTML = etatVide({ chargement: true, titre: t("session.lecture") });
  $("#entete-session").innerHTML = "";
  $("#sous-onglets").hidden = true;
  let session;
  try {
    session = await api("/api/session", { chemin });
  } catch (e) {
    if (etat.sessionChoisie !== chemin) return;
    $("#vue-session").innerHTML = etatVide({
      icone: "avertissement", titre: t("session.indisponible"), texte: echapper(e.message),
    });
    return;
  }
  // Une autre a été choisie pendant la lecture : c'est elle que montre la colonne.
  if (etat.sessionChoisie !== chemin) return;
  etat.session = session;
  const meilleur = meilleurDe(etat.session.tours);
  const voisin = meilleur ? tourVoisin(etat.session.tours, meilleur) : null;
  choix = { ref: meilleur?.numero ?? null, cmp: voisin?.numero ?? null };
  regularite = null;
  vueCourante = "tours";
  afficherSession();
}

function afficherEntete() {
  const s = etat.session;
  const code = codeType(s.type) || "autre";
  $("#entete-session").innerHTML = `
    <div class="carte entete-session">
      <span class="grand-drapeau">${drapeau(s.pays)}</span>
      <div class="titres">
        <h1>${echapper(s.circuit)}</h1>
        <p>${dateCourte(s.date)} · ${echapper(s.meteo)}</p>
      </div>
      <span class="espace"></span>
      <button id="vers-telemetrie" type="button" class="bouton-carre vert"
        title="${t("session.ouvrir_telemetrie")}" ${choix.ref === null ? "disabled" : ""}>${ICONES.courbe}</button>
      <div class="tuile"><small>${t("session.duree")}</small><b>${dureeSession(s.duree)}</b></div>
      <div class="tuile"><small>${t("session.tours")}</small><b>${s.tours.length}</b></div>
      <div class="tuile"><small>${t("session.longueur")}</small><b>${
        s.longueur ? `${(s.longueur / 1000).toFixed(3)} km` : "—"
      }</b></div>
      <div class="tuile tuile-type type-${code}"><small>${t("session.type")}</small><b>${
        echapper(nomType(s.type))
      }</b></div>
    </div>
    ${s.journal ? `<div class="bandeau">${ICONES.avertissement}${t("session.non_refermee")}</div>` : ""}`;
  $("#vers-telemetrie").onclick = versTelemetrie;
}

function versTelemetrie() {
  const s = etat.session;
  if (choix.ref === null) return;
  ouvrirTelemetrie({
    ref: s.id, tourRef: choix.ref, cmp: choix.cmp === null ? null : s.id, tourCmp: choix.cmp,
  }).catch((e) => erreur(e.message));
}

function afficherSession() {
  afficherEntete();
  $("#sous-onglets").hidden = false;
  for (const bouton of $$("#sous-onglets button")) {
    bouton.classList.toggle("actif", bouton.dataset.vue === vueCourante);
    bouton.onclick = () => {
      vueCourante = bouton.dataset.vue;
      afficherSession();
    };
  }
  if (vueCourante === "tours") afficherTours();
  else ouvrirRegularite();
}

// ---------------------------------------------------------------------
// Les tours
// ---------------------------------------------------------------------

function afficherTours() {
  const s = etat.session;
  const valides = s.tours.filter((x) => x.valide && x.chrono !== null);
  const meilleur = meilleurDe(s.tours);
  // Meilleur temps de chaque secteur parmi les tours valides, en violet comme
  // sur les écrans de chrono en course.
  const meilleursSecteurs = [0, 1, 2].map((i) =>
    Math.min(...valides.map((x) => x.secteurs[i] ?? Infinity))
  );
  const classe = s.voiture.classe || s.categorie;

  const lignes = s.tours
    .map((x) => {
      const record = meilleur && x.numero === meilleur.numero;
      const secteur = (i) => {
        if (x.secteurs[i] === null) return "—";
        const texte = x.secteurs[i].toFixed(3);
        return x.valide && x.secteurs[i] === meilleursSecteurs[i]
          ? `<span class="temps-record">${texte}</span>`
          : texte;
      };
      const choixTour = x.valide
        ? `<button type="button" class="pastille-choix ref ${choix.ref === x.numero ? "actif" : ""}"
             data-role="ref" data-tour="${x.numero}" title="${t("session.choisir_ref")}"></button>
           <button type="button" class="pastille-choix cmp ${choix.cmp === x.numero ? "actif" : ""}"
             data-role="cmp" data-tour="${x.numero}" title="${t("session.choisir_cmp")}"></button>`
        : "";
      return `<tr class="${x.valide ? "" : "invalide"}">
        <td class="centre"><span class="numero-tour">${x.numero}</span></td>
        <td class="nombre">${
          record ? `<span class="temps-record">${chrono(x.chrono)}</span>` : chrono(x.chrono)
        }</td>
        <td class="nombre">${secteur(0)}</td>
        <td class="nombre">${secteur(1)}</td>
        <td class="nombre">${secteur(2)}</td>
        <td class="nombre">${x.vitesse_min.toFixed(0)}</td>
        <td class="remarque">${echapper(x.remarques.map(traduire).join(" ; "))}</td>
        <td class="choix-tour-cellule">${choixTour}</td>
      </tr>`;
    })
    .join("");

  $("#vue-session").innerHTML = `
    <div class="groupe-classe classe-${classeCss(classe)}">
      <div class="groupe-entete">
        ${badgeClasse(classe)}
        <span class="groupe-voiture">${embleme(s.voiture.marque)}<strong>${
          echapper(s.voiture.modele || s.voiture.engagement)
        }</strong><small>${s.voiture.modele ? echapper(s.voiture.engagement) : ""}</small></span>
        <span class="espace"></span>
        <button id="comparer-tours" type="button" class="principal" ${choix.ref === null ? "disabled" : ""}>
          ${ICONES.courbe}${t("session.comparer")}</button>
        <span class="badge compteur classe-${classeCss(classe)}">${ICONES.chrono}${s.tours.length}</span>
      </div>
      <div class="defilement-table"><table class="table-tours">
        <thead><tr>
          <th class="centre">${t("session.col.tour")}</th>
          <th class="nombre">${t("session.col.chrono")}</th>
          <th class="nombre">S1</th><th class="nombre">S2</th><th class="nombre">S3</th>
          <th class="nombre">${t("session.col.vmin")}</th>
          <th>${t("session.col.remarques")}</th>
          <th class="centre">${t("session.col.choix")}</th>
        </tr></thead>
        <tbody>${lignes}</tbody>
      </table></div>
    </div>
    ${meilleur ? "" : `<p class="note">${t("session.rien_a_comparer")}</p>`}`;

  $("#comparer-tours").onclick = versTelemetrie;
  for (const bouton of $$(".pastille-choix")) {
    bouton.onclick = () => {
      const tour = +bouton.dataset.tour;
      const role = bouton.dataset.role;
      const autre = role === "ref" ? "cmp" : "ref";
      // Cliquer sur le tour déjà choisi en comparaison le retire.
      if (role === "cmp" && choix.cmp === tour) choix.cmp = null;
      else {
        if (choix[autre] === tour) choix[autre] = choix[role];
        choix[role] = tour;
      }
      afficherTours();
    };
  }
}

function classeCss(brut) {
  return String(badgeClasse(brut)).match(/classe-([\w]+)/)?.[1] || "autre";
}

// ---------------------------------------------------------------------
// La régularité
// ---------------------------------------------------------------------

async function ouvrirRegularite() {
  const chemin = etat.session.id;
  if (regularite && regularite.chemin === chemin) {
    afficherRegularite();
    return;
  }
  $("#vue-session").innerHTML = etatVide({ chargement: true, titre: t("regularite.analyse") });
  try {
    const donnees = await api("/api/regularite", { chemin });
    regularite = { chemin, donnees };
  } catch (e) {
    if (etat.session?.id !== chemin) return;
    $("#vue-session").innerHTML = etatVide({
      icone: "avertissement", titre: t("regularite.indisponible"), texte: echapper(e.message),
    });
    return;
  }
  if (etat.session?.id === chemin && vueCourante === "regularite") afficherRegularite();
}

function afficherRegularite() {
  const r = regularite.donnees;
  const derive = r.tendance < 0 ? "regularite.derive_accelere" : "regularite.derive_ralentit";

  $("#vue-session").innerHTML = `
    <div class="grille-stats">
      <div class="carte carte-stat"><h4>${ICONES.chrono}${t("regularite.meilleur")}</h4>
        <div class="stat-valeur"><span class="pastille-temps record">${chrono(r.meilleur)}</span></div></div>
      <div class="carte carte-stat"><h4>${ICONES.chrono}${t("regularite.median")}</h4>
        <div class="stat-valeur"><span class="pastille-temps bleu">${chrono(r.median)}</span>
          <small>+${r.ecart_meilleur_median.toFixed(3)} s</small></div></div>
      <div class="carte carte-stat"><h4>${ICONES.courbe}${t("regularite.ecart_type")}</h4>
        <div class="stat-valeur"><span class="pastille-temps bleu">σ ${r.ecart_type.toFixed(3)} s</span></div></div>
      <div class="carte carte-stat"><h4>${ICONES.chrono}${t("regularite.tour_ideal")}</h4>
        <div class="stat-valeur"><span class="pastille-temps vert">${chrono(r.tour_ideal)}</span>
          <small>−${r.marge_de_regularite.toFixed(3)} s</small></div></div>
      <div class="carte carte-stat"><h4>${ICONES.chrono}${t("regularite.tours_valides")}</h4>
        <div class="stat-valeur grand">${r.tours.length}</div></div>
    </div>
    <p class="note">${t("regularite.note_ideal", { marge: r.marge_de_regularite.toFixed(3) })}${
      r.course ? ` <span class="moins">${t("regularite.note_course")}</span>` : ""
    }${r.fiable ? "" : ` <span class="moins">${t("regularite.note_peu_de_tours", { n: r.tours.length })}</span>`}</p>
    <div class="colonnes-regularite">
      <div class="carte bloc-chronos">
        <h3 class="titre-section">${t("regularite.titre_chronos")}</h3>
        <canvas id="graphe-chronos"></canvas>
      </div>
      <div class="carte aide">
        <strong>${t("regularite.au_fil")}</strong>
        <p>${Math.abs(r.tendance) < 0.01
          ? t("regularite.pas_de_derive")
          : t(derive, { valeur: signe(r.tendance) })}</p>
        <p>${t("regularite.moities", { debut: chrono(r.moitie_debut), fin: chrono(r.moitie_fin) })}</p>
        <p class="note">${t("regularite.description")}</p>
      </div>
    </div>
    <h3 class="titre-section">${t("regularite.titre_classement")}</h3>
    <div class="carte tableau" id="classement-virages"></div>`;

  dessinerChronos(
    $("#graphe-chronos"),
    { tours: r.tours, meilleur: r.meilleur, median: r.median, ideal: r.tour_ideal },
    COULEURS
  );
  afficherClassement(r);
}

function afficherClassement(r) {
  const maximum = Math.max(...r.virages.map((v) => v.dispersion), 0.001);
  const lignes = r.virages
    .map((v, i) => {
      const largeur = Math.round(60 * (v.dispersion / maximum));
      return `<tr>
        <td class="rang rang-${i + 1}"><span>${i + 1}</span></td>
        <td><span class="num-virage">${echapper(v.nom)}</span>${fleche(v.sens)}
          <span class="discret">${Math.round(v.debut)}–${Math.round(v.fin)} m</span></td>
        <td class="nombre">${v.temps_median.toFixed(3)} s</td>
        <td class="nombre">±${v.dispersion.toFixed(3)} s
          <span class="barre-dispersion" style="width:${largeur}px"></span></td>
        <td class="nombre">${v.potentiel.toFixed(3)} s</td>
        <td class="nombre">${
          v.dispersion_freinage === null ? "—" : `±${v.dispersion_freinage.toFixed(1)} m`
        }</td>
        <td class="nombre">±${v.dispersion_vitesse_min.toFixed(1)} km/h</td>
        <td class="remarque">${
          v.passage_aberrant ? t("regularite.passage_isole", { n: v.tour_le_plus_lent }) : ""
        }</td>
      </tr>`;
    })
    .join("");
  $("#classement-virages").innerHTML = `<table>
    <thead><tr>
      <th class="rang"></th><th>${t("regularite.col.virage")}</th>
      <th class="nombre">${t("regularite.col.passage")}</th>
      <th class="nombre">${t("regularite.col.dispersion")}</th>
      <th class="nombre">${t("regularite.col.a_gagner")}</th>
      <th class="nombre">${t("regularite.col.freinage")}</th>
      <th class="nombre">${t("regularite.col.vitesse_mini")}</th>
      <th></th>
    </tr></thead>
    <tbody>${lignes}</tbody></table>`;
}

// ---------------------------------------------------------------------

function afficherSansSession() {
  $("#entete-session").innerHTML = "";
  $("#sous-onglets").hidden = true;
  $("#vue-session").innerHTML = etat.sessions.length
    ? etatVide({ titre: t("resultats.choisir"), texte: t("resultats.choisir_texte") })
    : etatVide({
        icone: "calendrier", titre: t("resultats.aucune"), texte: t("resultats.aucune_texte"),
      });
}

/** L'onglet vient d'être affiché : si rien n'est choisi, on ouvre la dernière session utile. */
export function surResultats() {
  if (etat.sessionChoisie) return;
  const derniere = derniereSessionUtile();
  if (derniere) ouvrirSession(derniere.id).catch((e) => erreur(e.message));
  else afficherSansSession();
}

export const ecranResultats = {
  rafraichir() {
    if (etat.session) afficherSession();
    else if (etat.onglet === "resultats") afficherSansSession();
  },
};
