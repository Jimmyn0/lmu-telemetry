// Résultats : une session, son classement, ses tours et sa régularité.

import {
  $, $$, api, badgeClasse, badgeType, dateCourte, erreur, etat, etatVide, fleche, nomType,
} from "/commun.js";
import { COULEURS } from "/graphes.js";
import { dessinerChronos } from "/chronos.js";
import { drapeau, echapper, embleme } from "/emblemes.js";
import {
  chrono, codeType, courbesPositions, duelParDefaut, dureeCourse, dureeSession, familleClasse,
  horloge, signe, tempsRestant, tourVoisin,
} from "/format.js";
import { ICONES } from "/icones.js";
import { t, tp, traduire } from "/i18n.js";
import { barreSessions, derniereSessionUtile } from "/barre_sessions.js";
import { ouvrirTelemetrie } from "/ecran_telemetrie.js";
import { GraphePositions } from "/positions.js";
import { GrapheRythme } from "/rythme.js";

let vueCourante = "classement";
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
  fiche = null;
  duel = null;
  categoriePositions = undefined;
  filtresIncidents.pilote = null;
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
  vueCourante = "classement";
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
        <p>${[
          dateCourte(s.date),
          s.meteo ? echapper(s.meteo) : "",
          // La course d'un ami : elle n'est pas dans la colonne des sessions.
          s.proprietaire ? `${ICONES.groupe}${t("resultats.course_de", { pilote: echapper(s.proprietaire) })}` : "",
        ].filter(Boolean).join(" · ")}</p>
      </div>
      <span class="espace"></span>
      <button id="vers-telemetrie" type="button" class="bouton-carre vert"
        title="${t("session.ouvrir_telemetrie")}" ${choix.ref === null ? "disabled" : ""}>${ICONES.courbe}</button>
      <div class="tuile"><small>${t("session.duree")}</small><b>${dureeSession(s.duree)}</b></div>
      <div class="tuile"><small>${t("session.tours")}</small><b>${
        s.seance ? s.tours_seance : s.tours.length
      }</b></div>
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
  // L'évolution des positions et les statistiques n'ont de sens qu'en course.
  const course = codeType(etat.session.type) === "R";
  for (const vue of ["positions", "statistiques"]) {
    $(`#sous-onglets [data-vue="${vue}"]`).hidden = !course;
    if (!course && vueCourante === vue) vueCourante = "classement";
  }
  // Le chat n'existe qu'en ligne : la colonne des sessions le sait déjà, et une course dont
  // on n'a que le classement le dit elle-même.
  const seule = Boolean(etat.session.seance);
  const enLigne = seule
    ? Boolean(etat.session.en_ligne)
    : Boolean(etat.sessions?.find((s) => s.id === etat.session.id)?.en_ligne);
  $('#sous-onglets [data-vue="chat"]').hidden = !enLigne;
  if (!enLigne && vueCourante === "chat") vueCourante = "classement";
  // Sans télémétrie (la course d'un ami), ni tours ni régularité.
  for (const vue of ["tours", "regularite"]) {
    $(`#sous-onglets [data-vue="${vue}"]`).hidden = seule;
    if (seule && vueCourante === vue) vueCourante = "classement";
  }
  for (const bouton of $$("#sous-onglets button")) {
    bouton.classList.toggle("actif", bouton.dataset.vue === vueCourante);
    bouton.onclick = () => {
      vueCourante = bouton.dataset.vue;
      afficherSession();
    };
  }
  if (vueCourante === "classement") chargerClassement(afficherClassementSeance);
  else if (vueCourante === "rythme") chargerClassement(afficherRythmeSeance);
  else if (vueCourante === "positions") chargerClassement(afficherPositionsSeance);
  else if (vueCourante === "statistiques") chargerClassement(afficherStatistiquesSeance);
  else if (vueCourante === "incidents") chargerClassement(afficherIncidentsSeance);
  else if (vueCourante === "chat") chargerClassement(afficherChatSeance);
  else if (vueCourante === "tours") afficherTours();
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
// Le classement : le fichier de résultats que le jeu écrit pour chaque séance
// ---------------------------------------------------------------------

// Les gommes que le jeu nomme : leur lettre, et leur nom.
const GOMMES = {
  Soft: ["S", "classement.gomme.soft"],
  Medium: ["M", "classement.gomme.medium"],
  Hard: ["H", "classement.gomme.hard"],
  Wet: ["W", "classement.gomme.wet"],
};

let classement = null; // { chemin, r } : le classement de la session ouverte
let categorie = null; // la catégorie choisie ; null : le général
let fiche = null; // rang, dans r.engages, de la voiture dont la fiche est ouverte

// Le classement de la session ouverte, lu une fois, puis montré par `afficher` :
// le Classement et le Rythme s'en servent tous les deux.
async function chargerClassement(afficher) {
  const chemin = etat.session.id;
  const vue = vueCourante;
  if (classement && classement.chemin === chemin) {
    afficher();
    return;
  }
  $("#vue-session").innerHTML = etatVide({ chargement: true, titre: t("classement.chargement") });
  let r;
  try {
    r = await api("/api/classement", { chemin });
  } catch (e) {
    if (etat.session?.id !== chemin || vueCourante !== vue) return;
    $("#vue-session").innerHTML = etatVide({
      icone: "avertissement", titre: t("classement.absent"), texte: echapper(e.message),
    });
    return;
  }
  classement = { chemin, r };
  // Une réponse arrivée après un changement de session ou de sous-onglet attendra.
  if (etat.session?.id === chemin && vueCourante === vue) afficher();
}

// Le jeu n'a pas écrit de résultats pour cette séance : on le dit, et c'est tout.
function sansClassement(r) {
  if (r.trouve) return false;
  $("#vue-session").innerHTML = etatVide({
    icone: "calendrier", titre: t("classement.absent"), texte: t("classement.absent_texte"),
  });
  return true;
}

function afficherClassementSeance() {
  const r = classement.r;
  if (sansClassement(r)) return;
  // La catégorie choisie dans une autre séance peut manquer dans celle-ci.
  if (!r.categories.includes(categorie)) categorie = null;
  if (fiche !== null && r.engages[fiche]) afficherFiche(r, fiche);
  else afficherTableClassement(r);
}

function numeroVoiture(e) {
  return `<span class="numero-voiture classe-${classeCss(e.classe)}">${echapper(e.numero)}</span>`;
}

function badgeToi(e) {
  return e.joueur ? `<span class="badge-toi">${t("classement.toi")}</span>` : "";
}

export function gomme(nom) {
  if (!nom) return "—";
  const [lettre, cle] = GOMMES[nom] || [nom[0].toUpperCase(), null];
  return `<span class="gomme gomme-${lettre}" title="${cle ? t(cle) : echapper(nom)}">${
    echapper(lettre)
  }</span>`;
}

function texteEcart(ecart) {
  if (!ecart) return "—";
  if (ecart.tours) return tp("classement.tours_retard", ecart.tours);
  return signe(ecart.temps);
}

function texteArrivee(e) {
  if (e.statut === "abandon") return `<span class="statut-course">${t("classement.abandon")}</span>`;
  if (e.statut === "disqualifie") {
    return `<span class="statut-course">${t("classement.disqualifie")}</span>`;
  }
  return dureeCourse(e.temps_total);
}

// Un temps, en violet s'il est le meilleur de ce qu'on montre.
export function tempsMarque(valeur, meilleur, texte) {
  if (valeur === null || valeur === undefined) return "—";
  return valeur === meilleur ? `<span class="temps-record">${texte}</span>` : texte;
}

const plusPetit = (valeurs) =>
  Math.min(...valeurs.filter((v) => v !== null && v !== undefined), Infinity);

function afficherTableClassement(r) {
  const course = r.type === "R";
  const rangs = r.engages
    .map((_e, rang) => rang)
    .filter((rang) => !categorie || r.engages[rang].classe === categorie);
  const visibles = rangs.map((rang) => r.engages[rang]);
  const meilleurTour = plusPetit(visibles.map((e) => e.meilleur_tour));
  const meilleursSecteurs = [0, 1, 2].map((i) =>
    plusPetit(visibles.map((e) => e.secteurs_meilleur[i]))
  );

  const lignes = rangs
    .map((rang) => {
      const e = r.engages[rang];
      const ecart = categorie ? e.ecart_categorie : e.ecart;
      const meilleur = `<td class="nombre">${
        tempsMarque(e.meilleur_tour, meilleurTour, chrono(e.meilleur_tour))
      }</td>`;
      const colonnes = course
        ? `${meilleur}
          <td class="nombre">${texteEcart(ecart)}</td>
          <td class="nombre">${e.arrets}</td>
          <td class="nombre">${e.tours}</td>
          <td class="nombre">${texteArrivee(e)}</td>`
        : `${[0, 1, 2]
            .map((i) => {
              const v = e.secteurs_meilleur[i];
              return `<td class="nombre">${
                tempsMarque(v, meilleursSecteurs[i], v === null ? "" : v.toFixed(3))
              }</td>`;
            })
            .join("")}
          ${meilleur}
          <td class="nombre">${texteEcart(ecart)}</td>
          <td class="nombre">${e.tours}</td>`;
      return `<tr class="${e.joueur ? "joueur" : ""}" data-engage="${rang}" title="${t("classement.voir_fiche")}">
        <td class="centre">${(categorie ? e.place_classe : e.place) ?? "—"}</td>
        <td class="centre">${numeroVoiture(e)}</td>
        <td><span class="nom-pilote">${echapper(e.nom)}</span>${badgeToi(e)}</td>
        <td><span class="voiture-cellule">${embleme(e.marque)}<span>${
          echapper(e.modele || e.engagement)
        }</span></span></td>
        <td class="centre">${gomme(e.gomme)}</td>
        ${colonnes}
      </tr>`;
    })
    .join("");

  const entetes = course
    ? `<th class="nombre">${t("classement.col.meilleur")}</th>
      <th class="nombre">${t("classement.col.ecart")}</th>
      <th class="nombre">${t("classement.col.arrets")}</th>
      <th class="nombre">${t("classement.col.tours")}</th>
      <th class="nombre">${t("classement.col.temps")}</th>`
    : `<th class="nombre">S1</th><th class="nombre">S2</th><th class="nombre">S3</th>
      <th class="nombre">${t("classement.col.meilleur")}</th>
      <th class="nombre">${t("classement.col.ecart")}</th>
      <th class="nombre">${t("classement.col.tours")}</th>`;

  const filtre =
    r.categories.length > 1
      ? `<div class="filtre-categories" role="group">
        <button type="button" data-categorie="" class="${categorie ? "" : "actif"}">${
          t("classement.general")
        }</button>
        ${r.categories
          .map(
            (c) => `<button type="button" data-categorie="${echapper(c)}"
              class="classe-${classeCss(c)}${c === categorie ? " actif" : ""}">${
              echapper(familleClasse(c) || c)
            }</button>`
          )
          .join("")}
      </div>`
      : "";

  $("#vue-session").innerHTML = `
    <div class="groupe-classe classe-${categorie ? classeCss(categorie) : "autre"}">
      <div class="groupe-entete">
        ${categorie ? badgeClasse(categorie) : `<span class="badge compteur-blanc">${t("classement.general")}</span>`}
        <span class="espace"></span>
        ${filtre}
        <span class="badge compteur">${rangs.length}</span>
      </div>
      <div class="defilement-table"><table class="table-tours table-classement">
        <thead><tr>
          <th class="centre">${t("classement.col.place")}</th>
          <th class="centre">${t("classement.col.numero")}</th>
          <th>${t("classement.col.pilote")}</th>
          <th>${t("classement.col.voiture")}</th>
          <th class="centre">${t("classement.col.gomme")}</th>
          ${entetes}
        </tr></thead>
        <tbody>${lignes}</tbody>
      </table></div>
    </div>`;

  for (const bouton of $$("[data-categorie]")) {
    bouton.onclick = () => {
      categorie = bouton.dataset.categorie || null;
      afficherTableClassement(r);
    };
  }
  for (const ligne of $$(".table-classement tbody tr")) {
    ligne.onclick = () => {
      fiche = +ligne.dataset.engage;
      afficherFiche(r, fiche);
    };
  }
}

// La fiche d'une voiture : d'où elle est partie, où elle a fini, et chacun de ses tours.
function afficherFiche(r, rang) {
  const e = r.engages[rang];
  const moi = r.engages.findIndex((x) => x.joueur);
  const course = r.type === "R";
  // En multiclasse, les places sont celles de sa catégorie, le général en dessous.
  const multi = r.categories.length > 1;
  const p = (place) => (place ? `P${place}` : "—");
  const record = plusPetit(e.tours_detail.map((x) => x.chrono));
  const meilleursSecteurs = [0, 1, 2].map((i) => plusPetit(e.tours_detail.map((x) => x.secteurs[i])));
  const tuile = (titre, valeur, detail = "") =>
    `<div class="tuile"><small>${titre}</small><b>${valeur}</b>${detail ? `<small>${detail}</small>` : ""}</div>`;

  const tuiles = [
    course
      ? tuile(
          t("fiche.grille_arrivee"),
          `${p(multi ? e.grille_classe : e.grille)} → ${p(multi ? e.place_classe : e.place)}`,
          multi ? t("fiche.au_general", { depart: p(e.grille), arrivee: p(e.place) }) : ""
        )
      : tuile(
          t("fiche.place"),
          p(multi ? e.place_classe : e.place),
          multi ? t("fiche.au_general_seul", { place: p(e.place) }) : ""
        ),
    tuile(
      t("classement.col.meilleur"),
      chrono(e.meilleur_tour),
      e.tour_meilleur ? t("fiche.tour_n", { n: e.tour_meilleur }) : ""
    ),
    tuile(t("fiche.vitesse_max"), e.vitesse_max ? `${e.vitesse_max.toFixed(0)} km/h` : "—"),
    tuile(t("classement.col.tours"), e.tours),
    course ? tuile(t("classement.col.arrets"), e.arrets) : "",
    course ? tuile(t("fiche.arrivee"), texteArrivee(e), e.ecart_categorie ? texteEcart(e.ecart_categorie) : "") : "",
  ].join("");

  const lignes = e.tours_detail
    .map((x) => {
      const secteur = (i) =>
        tempsMarque(x.secteurs[i], meilleursSecteurs[i], x.secteurs[i]?.toFixed(3));
      return `<tr class="${x.chrono === null ? "invalide" : ""}">
        <td class="centre"><span class="numero-tour">${x.numero}</span></td>
        <td class="centre">${p(multi ? x.place_categorie : x.place)}</td>
        <td class="nombre">${tempsMarque(x.chrono, record, chrono(x.chrono))}</td>
        <td class="nombre">${secteur(0)}</td>
        <td class="nombre">${secteur(1)}</td>
        <td class="nombre">${secteur(2)}</td>
        <td class="nombre">${x.vitesse_max === null ? "—" : x.vitesse_max.toFixed(0)}</td>
        <td class="centre">${gomme(x.gomme)}</td>
        <td class="remarque">${x.stands ? `<span class="badge alerte">${t("fiche.stands")}</span>` : ""}</td>
      </tr>`;
    })
    .join("");

  $("#vue-session").innerHTML = `
    <div class="groupe-classe classe-${classeCss(e.classe)}">
      <div class="groupe-entete">
        <button id="retour-classement" type="button" class="pilule">← ${t("fiche.retour")}</button>
        ${badgeClasse(e.classe)}
        ${numeroVoiture(e)}
        <span class="groupe-voiture">${embleme(e.marque)}<strong>${echapper(e.nom)}</strong>${badgeToi(e)}
          <small>${echapper([e.equipe, e.modele].filter(Boolean).join(" · "))}</small></span>
        <span class="espace"></span>
        <button id="comparer-pilote" type="button" class="principal">${ICONES.courbe}${
          t(moi >= 0 && moi !== rang ? "fiche.comparer_moi" : "fiche.comparer")
        }</button>
      </div>
      <div class="tuiles-fiche">${tuiles}</div>
      <div class="defilement-table"><table class="table-tours">
        <thead><tr>
          <th class="centre">${t("session.col.tour")}</th>
          <th class="centre">${t("classement.col.place")}</th>
          <th class="nombre">${t("session.col.chrono")}</th>
          <th class="nombre">S1</th><th class="nombre">S2</th><th class="nombre">S3</th>
          <th class="nombre">${t("fiche.col.vitesse_max")}</th>
          <th class="centre">${t("classement.col.gomme")}</th>
          <th></th>
        </tr></thead>
        <tbody>${lignes}</tbody>
      </table></div>
    </div>`;
  $("#retour-classement").onclick = () => {
    fiche = null;
    afficherTableClassement(r);
  };
  $("#comparer-pilote").onclick = () => {
    duel = moi >= 0 && moi !== rang ? { a: moi, b: rang } : duelParDefaut(r.engages, rang);
    vueCourante = "rythme";
    afficherSession();
  };
}

// ---------------------------------------------------------------------
// Le rythme : deux pilotes, tour par tour (maquette 03)
// ---------------------------------------------------------------------

let duel = null; // { a, b } : rangs, dans r.engages, des deux pilotes comparés

function afficherRythmeSeance() {
  const r = classement.r;
  if (sansClassement(r)) return;
  if (!duel || !r.engages[duel.a] || !r.engages[duel.b]) duel = duelParDefaut(r.engages);
  afficherRythme(r);
}

function choixPilote(r, role, choisi) {
  const groupes = r.categories.map((c) => {
    const options = r.engages
      .map((e, rang) => ({ e, rang }))
      .filter(({ e }) => e.classe === c)
      .map(
        ({ e, rang }) => `<option value="${rang}"${rang === choisi ? " selected" : ""}>${
          echapper(`${e.place_classe ?? "—"}. ${e.nom} · #${e.numero}`)
        }</option>`
      )
      .join("");
    return r.categories.length > 1
      ? `<optgroup label="${echapper(familleClasse(c) || c)}">${options}</optgroup>`
      : options;
  });
  const e = r.engages[choisi];
  return `<div class="pilote-duel duel-${role}">
    <span class="trait-duel"></span>
    <select data-duel="${role}" aria-label="${t(role === "a" ? "rythme.pilote_a" : "rythme.pilote_b")}">${
      groupes.join("")
    }</select>
    ${e.meilleur_tour ? `<span class="chrono-duel">${chrono(e.meilleur_tour)}</span>` : ""}
    ${badgeToi(e)}
  </div>`;
}

// Les tours d'un pilote, et l'écart de chacun sur le même tour de l'autre.
function tableauDuel(role, e, autre) {
  const autreParTour = new Map(autre.tours_detail.map((x) => [x.numero, x]));
  const record = plusPetit(e.tours_detail.map((x) => x.chrono));
  const lignes = e.tours_detail
    .map((x) => {
      const y = autreParTour.get(x.numero);
      const ecart = x.chrono !== null && y && y.chrono !== null ? x.chrono - y.chrono : null;
      const sens = !ecart ? "" : ecart < 0 ? "ecart-gain" : "ecart-perte";
      const secteur = (i) => (x.secteurs[i] === null ? "—" : x.secteurs[i].toFixed(3));
      return `<tr class="${x.chrono === null ? "invalide" : ""}">
        <td class="centre"><span class="numero-tour">${x.numero}</span></td>
        <td class="nombre">${tempsMarque(x.chrono, record, chrono(x.chrono))}</td>
        <td class="nombre">${secteur(0)}</td>
        <td class="nombre">${secteur(1)}</td>
        <td class="nombre">${secteur(2)}</td>
        <td class="nombre ${sens}">${ecart === null ? "—" : signe(ecart)}</td>
        <td class="remarque">${x.stands ? `<span class="badge alerte">${t("fiche.stands")}</span>` : ""}</td>
      </tr>`;
    })
    .join("");
  return `<div class="tableau-duel duel-${role}"><div class="defilement-table"><table class="table-tours">
    <thead><tr>
      <th class="centre">${t("session.col.tour")}</th>
      <th class="nombre">${t("session.col.chrono")}</th>
      <th class="nombre">S1</th><th class="nombre">S2</th><th class="nombre">S3</th>
      <th class="nombre">${t("rythme.col.ecart")}</th>
      <th></th>
    </tr></thead>
    <tbody>${lignes}</tbody>
  </table></div></div>`;
}

function afficherRythme(r) {
  const a = r.engages[duel.a];
  const b = r.engages[duel.b];
  $("#vue-session").innerHTML = `
    <div class="duel">${choixPilote(r, "a", duel.a)}${choixPilote(r, "b", duel.b)}</div>
    <div class="carte bloc-rythme"><canvas id="graphe-rythme"></canvas></div>
    <div class="tableaux-duel">${tableauDuel("a", a, b)}${tableauDuel("b", b, a)}</div>`;
  new GrapheRythme($("#graphe-rythme")).afficher({
    series: [
      { couleur: COULEURS.reference, tours: a.tours_detail },
      { couleur: COULEURS.compare, tours: b.tours_detail },
    ],
    couleurs: COULEURS,
  });
  for (const liste of $$("[data-duel]")) {
    liste.onchange = () => {
      duel[liste.dataset.duel] = +liste.value;
      afficherRythme(r);
    };
  }
}

// ---------------------------------------------------------------------
// Les positions : de la grille à l'arrivée (maquette 04)
// ---------------------------------------------------------------------

// Les couleurs des voitures, dans l'ordre de l'arrivée. Le violet est réservé à toi.
const TEINTES = [
  "#ee8a35", "#28c8f0", "#22c55e", "#e7be16", "#ef4465", "#2c8ed6", "#f472b6",
  "#a3e635", "#fb923c", "#38bdf8", "#facc15", "#34d399", "#f87171", "#94a3b8",
];

let categoriePositions; // undefined : pas encore choisie ; null : le général
let moiEnAvant = false;

function afficherPositionsSeance() {
  const r = classement.r;
  if (sansClassement(r)) return;
  if (
    categoriePositions === undefined ||
    (categoriePositions && !r.categories.includes(categoriePositions))
  ) {
    // En multiclasse, la catégorie du pilote d'abord : c'est elle qui l'intéresse.
    const moi = r.engages.find((e) => e.joueur);
    categoriePositions = r.categories.length > 1 ? moi?.classe ?? r.categories[0] : null;
  }
  afficherPositions(r);
}

function afficherPositions(r) {
  const { voitures, places, tours } = courbesPositions(r.engages, categoriePositions);
  let teinte = 0;
  for (const v of voitures) {
    v.couleur = v.joueur ? COULEURS.reference : TEINTES[teinte++ % TEINTES.length];
  }
  const filtre =
    r.categories.length > 1
      ? `<div class="filtre-categories" role="group">
        <button type="button" data-positions="" class="${categoriePositions ? "" : "actif"}">${
          t("classement.general")
        }</button>
        ${r.categories
          .map(
            (c) => `<button type="button" data-positions="${echapper(c)}"
              class="classe-${classeCss(c)}${c === categoriePositions ? " actif" : ""}">${
              echapper(familleClasse(c) || c)
            }</button>`
          )
          .join("")}
      </div>`
      : "";
  const lignes = voitures
    .map(
      (v) => `<li data-rang="${v.rang}">
        <span class="pastille-pilote" style="background:${v.couleur}"></span>
        <span class="nom">${echapper(v.nom)}</span>${
          v.joueur ? `<span class="badge-toi">${t("classement.toi")}</span>` : ""
        }
        <b>${v.abandon ? t("positions.abandon") : v.finale ? `P${v.finale}` : "—"}</b>
      </li>`
    )
    .join("");
  const moi = voitures.find((v) => v.joueur);
  // Une ligne par place, assez haute pour suivre chaque voiture.
  const hauteur = Math.min(760, Math.max(300, places * 22 + 46));
  $("#vue-session").innerHTML = `
    <div class="positions">
      <div class="carte liste-positions">
        <div class="entete-positions"><h3 class="titre-section">${t("positions.pilotes")}</h3>${filtre}</div>
        <ol>${lignes}</ol>
      </div>
      <div class="carte bloc-positions">
        ${
          moi
            ? `<div class="outils-positions"><button id="moi-en-avant" type="button"
                class="pilule${moiEnAvant ? " actif" : ""}">${t("positions.moi")}</button></div>`
            : ""
        }
        <canvas id="graphe-positions" style="height:${hauteur}px"></canvas>
      </div>
    </div>`;

  const items = $$(".liste-positions li");
  const graphe = new GraphePositions($("#graphe-positions"), {
    surSurvol: (rang) => {
      for (const li of items) li.classList.toggle("survol", +li.dataset.rang === rang);
    },
  });
  graphe.afficher({ voitures, places, tours, couleurs: COULEURS });
  graphe.mettreEnAvant(moiEnAvant && moi ? moi.rang : null);
  for (const li of items) {
    li.onmouseenter = () => graphe.designer(+li.dataset.rang);
    li.onmouseleave = () => graphe.designer(null);
  }
  for (const bouton of $$("[data-positions]")) {
    bouton.onclick = () => {
      categoriePositions = bouton.dataset.positions || null;
      afficherPositions(r);
    };
  }
  if (moi) {
    $("#moi-en-avant").onclick = () => {
      moiEnAvant = !moiEnAvant;
      afficherPositions(r);
    };
  }
}

// ---------------------------------------------------------------------
// Les statistiques : les meilleures performances de chaque catégorie (maquette 05)
// ---------------------------------------------------------------------

function afficherStatistiquesSeance() {
  const r = classement.r;
  if (sansClassement(r)) return;
  const pilote = (rang) =>
    `<div class="pilote-stat"><span class="nom-pilote">${echapper(r.engages[rang].nom)}</span>${
      badgeToi(r.engages[rang])
    }</div>`;
  // `genre` colore le titre : record, regularite, gain, perte, usage.
  const carte = (genre, titre, corps, icone = "") =>
    `<div class="carte-stat ${genre}"><small>${icone}${titre}</small>${corps}</div>`;
  const record = (titre, x, texte) =>
    x
      ? carte(
          "record",
          titre,
          `${pilote(x.rang)}<div class="valeur-stat"><span class="temps-record">${texte}</span>
            <small>${t("fiche.tour_n", { n: x.tour })}</small></div>`,
          ICONES.chrono
        )
      : "";

  const groupes = r.statistiques
    .map((s) => {
      const cartes = [
        record(t("stats.meilleur_tour"), s.meilleur_tour, chrono(s.meilleur_tour?.temps)),
        ...s.secteurs.map((x, i) =>
          record(t("stats.meilleur_secteur", { n: i + 1 }), x, x?.temps.toFixed(3))
        ),
        s.regularite
          ? carte(
              "regularite",
              t("stats.regularite"),
              `${pilote(s.regularite.rang)}<div class="valeur-stat">
                <span class="chip-stat bleu">σ ${s.regularite.ecart_type.toFixed(3)} s</span>
                <small>${tp("stats.sur_tours", s.regularite.tours)}</small></div>`,
              ICONES.delta
            )
          : "",
        s.gagnees
          ? carte(
              "gain",
              t("stats.gagnees"),
              `${pilote(s.gagnees.rang)}<div class="valeur-stat">
                <span class="chip-stat vert">▲ ${tp("stats.places", s.gagnees.places)}</span></div>`,
              "<span>▲</span>"
            )
          : "",
        s.perdues
          ? carte(
              "perte",
              t("stats.perdues"),
              `${pilote(s.perdues.rang)}<div class="valeur-stat">
                <span class="chip-stat rouge">▼ ${tp("stats.places", s.perdues.places)}</span></div>`,
              "<span>▼</span>"
            )
          : "",
        s.gomme
          ? carte(
              "usage",
              t("stats.gomme"),
              `<div class="valeur-gomme">${gomme(s.gomme.nom)}<span>${tp("stats.tours", s.gomme.tours)}</span></div>`
            )
          : "",
      ].join("");
      return `<div class="groupe-classe classe-${classeCss(s.categorie)}">
        <div class="groupe-entete">
          ${badgeClasse(s.categorie)}
          <span class="espace"></span>
          <span class="badge compteur">${s.voitures}</span>
        </div>
        <div class="cartes-stats">${cartes}</div>
      </div>`;
    })
    .join("");
  $("#vue-session").innerHTML = `<div class="statistiques">${groupes}</div>`;
}

// ---------------------------------------------------------------------
// Les incidents : contacts, limites de piste, pénalités (maquette 06)
// ---------------------------------------------------------------------

// Ce que le jeu écrit en anglais, et ce qu'on en dit. Ce qui n'y est pas s'affiche tel quel.
const OBJETS = {
  Immovable: "incidents.objet.decor",
  Post: "incidents.objet.poteau",
  Sign: "incidents.objet.panneau",
  Wheel: "incidents.objet.roue",
  Wing: "incidents.objet.aileron",
  Cone: "incidents.objet.cone",
};
const SUITES = {
  "No Further Action": "incidents.suite.rien",
  Warning: "incidents.suite.avertissement",
  "Invalid Lap Cut Track": "incidents.suite.tour_invalide",
  "Drive Through Penalty": "incidents.penalite.drive",
  "Stop Go Penalty": "incidents.penalite.stop",
  "Time Penalty": "incidents.penalite.temps",
  Disqualify: "incidents.penalite.disqualification",
};
const PENALITES = {
  "Stop/Go": "incidents.penalite.stop",
  "Drive Thru": "incidents.penalite.drive",
  Time: "incidents.penalite.temps",
  Disqualify: "incidents.penalite.disqualification",
};
const MOTIFS = {
  "Speeding In Pitlane": "incidents.motif.vitesse_stands",
  "Exiting Pits Under Red": "incidents.motif.feu_rouge",
  Speeding: "incidents.motif.vitesse",
  "Exceeded energy allowance limit.": "incidents.motif.energie",
  "Track Limits": "incidents.motif.limites",
  "Erratic driving": "incidents.motif.conduite",
  "Out of position": "incidents.motif.position",
  "Driving Too Slow": "incidents.motif.lent",
  "Jumped the start": "incidents.motif.depart",
};
const GRAVITES = {
  leger: "incidents.gravite.leger",
  moyen: "incidents.gravite.moyen",
  violent: "incidents.gravite.violent",
};
// Les genres que l'on filtre : une pénalité purgée va avec les pénalités.
const GENRES = {
  contact: "incidents.genre.contact",
  limites: "incidents.genre.limites",
  penalite: "incidents.genre.penalite",
};

const traduit = (table, brut) => (brut && table[brut] ? t(table[brut]) : echapper(brut || "—"));

const filtresIncidents = { categorie: null, genres: new Set(Object.keys(GENRES)), pilote: null };

function detailIncident(i) {
  if (i.genre === "contact") {
    const qui = i.autre ? echapper(i.autre) : traduit(OBJETS, i.objet);
    const gravite = i.gravite ? ` · ${t(GRAVITES[i.gravite])}` : "";
    return `${t("incidents.contact_avec", { qui })}${gravite}`;
  }
  if (i.genre === "limites") return traduit(SUITES, i.suite);
  if (i.genre === "purge") return t("incidents.purgee", { penalite: traduit(PENALITES, i.penalite) });
  const duree = i.secondes ? ` ${i.secondes} s` : "";
  return `${traduit(PENALITES, i.penalite)}${duree}${i.motif ? ` · ${traduit(MOTIFS, i.motif)}` : ""}`;
}

function afficherIncidentsSeance() {
  const r = classement.r;
  if (sansClassement(r)) return;
  if (filtresIncidents.categorie && !r.categories.includes(filtresIncidents.categorie)) {
    filtresIncidents.categorie = null;
  }
  afficherIncidents(r);
}

function afficherIncidents(r) {
  const f = filtresIncidents;
  const genreDe = (i) => (i.genre === "purge" ? "penalite" : i.genre);
  const visibles = r.incidents.filter((i) => {
    const e = i.rang === null ? null : r.engages[i.rang];
    return (
      f.genres.has(genreDe(i)) &&
      (!f.categorie || e?.classe === f.categorie) &&
      (f.pilote === null || i.rang === f.pilote)
    );
  });
  // Temps restant quand la séance a une durée ; sinon, le temps écoulé depuis le départ.
  const avecRestant = r.incidents.length > 0 && r.incidents.every((i) => i.restant !== null);
  const lignes = visibles
    .map((i) => {
      const e = i.rang === null ? null : r.engages[i.rang];
      return `<tr class="${e?.joueur ? "joueur" : ""}">
        <td class="nombre">${avecRestant ? tempsRestant(i.restant) : horloge(i.ecoule)}</td>
        <td class="centre"><span class="genre-incident ${i.genre}">${
          t(i.genre === "purge" ? "incidents.genre.purge" : GENRES[i.genre])
        }</span></td>
        <td><span class="nom-pilote">${echapper(i.pilote)}</span>${e ? badgeToi(e) : ""}</td>
        <td class="centre">${e ? badgeClasse(e.classe) : ""}</td>
        <td class="centre">${i.tour ?? "—"}</td>
        <td>${detailIncident(i)}</td>
      </tr>`;
    })
    .join("");

  // Les pilotes qu'on peut choisir : ceux qui ont au moins un incident.
  const concernes = [...new Set(r.incidents.map((i) => i.rang).filter((rang) => rang !== null))].sort(
    (a, b) => a - b
  );
  const pilotes = `<select id="pilote-incidents" aria-label="${t("incidents.tous")}">
      <option value="">${t("incidents.tous")}</option>
      ${concernes
        .map(
          (rang) => `<option value="${rang}"${rang === f.pilote ? " selected" : ""}>${
            echapper(r.engages[rang].nom)
          }</option>`
        )
        .join("")}
    </select>`;
  const categories =
    r.categories.length > 1
      ? `<div class="filtre-categories" role="group">
        <button type="button" data-incidents-categorie="" class="${f.categorie ? "" : "actif"}">${
          t("classement.general")
        }</button>
        ${r.categories
          .map(
            (c) => `<button type="button" data-incidents-categorie="${echapper(c)}"
              class="classe-${classeCss(c)}${c === f.categorie ? " actif" : ""}">${
              echapper(familleClasse(c) || c)
            }</button>`
          )
          .join("")}
      </div>`
      : "";
  const genres = `<div class="filtre-categories filtre-genres" role="group">${Object.entries(GENRES)
    .map(
      ([genre, cle]) => `<button type="button" data-incidents-genre="${genre}"
        class="genre-${genre}${f.genres.has(genre) ? " actif" : ""}" aria-pressed="${f.genres.has(genre)}">${
        t(cle)
      }</button>`
    )
    .join("")}</div>`;

  const tableau = !r.incidents.length
    ? etatVide({ titre: t("incidents.aucun"), texte: t("incidents.aucun_texte") })
    : !visibles.length
      ? etatVide({ titre: t("incidents.aucun_filtre") })
      : `<div class="defilement-table"><table class="table-tours table-incidents">
        <thead><tr>
          <th class="nombre">${t(avecRestant ? "incidents.col.restant" : "incidents.col.ecoule")}</th>
          <th class="centre">${t("incidents.col.genre")}</th>
          <th>${t("classement.col.pilote")}</th>
          <th class="centre">${t("incidents.col.categorie")}</th>
          <th class="centre">${t("session.col.tour")}</th>
          <th>${t("incidents.col.detail")}</th>
        </tr></thead>
        <tbody>${lignes}</tbody>
      </table></div>`;

  $("#vue-session").innerHTML = `
    <div class="groupe-classe classe-autre">
      <div class="groupe-entete filtres-incidents">
        ${categories}${genres}${pilotes}
        <span class="espace"></span>
        <span class="badge compteur">${visibles.length}</span>
      </div>
      ${tableau}
    </div>`;

  for (const bouton of $$("[data-incidents-categorie]")) {
    bouton.onclick = () => {
      f.categorie = bouton.dataset.incidentsCategorie || null;
      afficherIncidents(r);
    };
  }
  for (const bouton of $$("[data-incidents-genre]")) {
    bouton.onclick = () => {
      const genre = bouton.dataset.incidentsGenre;
      if (f.genres.has(genre)) f.genres.delete(genre);
      else f.genres.add(genre);
      afficherIncidents(r);
    };
  }
  $("#pilote-incidents").onchange = (e) => {
    f.pilote = e.target.value === "" ? null : +e.target.value;
    afficherIncidents(r);
  };
}

// ---------------------------------------------------------------------
// Le chat des séances en ligne
// ---------------------------------------------------------------------

function afficherChatSeance() {
  const r = classement.r;
  if (sansClassement(r)) return;
  if (!r.chat.length) {
    $("#vue-session").innerHTML = etatVide({ titre: t("chat.aucun"), texte: t("chat.aucun_texte") });
    return;
  }
  const avecRestant = r.chat.every((m) => m.restant !== null);
  const lignes = r.chat
    .map(
      (m) => `<tr>
        <td class="nombre">${avecRestant ? tempsRestant(m.restant) : horloge(m.ecoule)}</td>
        <td><span class="nom-pilote">${echapper(m.auteur || "—")}</span></td>
        <td class="message-chat">${echapper(m.texte)}</td>
      </tr>`
    )
    .join("");
  $("#vue-session").innerHTML = `
    <div class="groupe-classe classe-autre">
      <div class="defilement-table"><table class="table-tours table-chat">
        <thead><tr>
          <th class="nombre">${t(avecRestant ? "incidents.col.restant" : "incidents.col.ecoule")}</th>
          <th>${t("chat.col.auteur")}</th>
          <th>${t("chat.col.message")}</th>
        </tr></thead>
        <tbody>${lignes}</tbody>
      </table></div>
    </div>`;
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
