// Leaderboard : les dernières courses du groupe, une page par circuit (ses pilotes, ses
// voitures, ses courses) et une fiche par pilote (ses statistiques, ses records, ses
// courses).
//
// Tout vient des fichiers de résultats que le jeu écrit après chaque séance, et seules
// les séances en ligne comptent (voir docs/19-leaderboard.md). La colonne de gauche
// choisit un circuit ou un pilote, comme dans l'onglet Temps au tour ; sa première carte
// ramène aux dernières courses. Le serveur applique les filtres et renvoie ceux qu'il a
// retenus : la page n'a qu'à les montrer. Tant que le groupe n'existe pas, il n'y a que
// les séances de ce PC.

import {
  $, api, badgeClasse, contourSvg, dateCourte, dateJour, envoyer, erreur, etat, etatVide, navigation, nomType,
} from "/commun.js";
import { drapeau, echapper, embleme } from "/emblemes.js";
import { gomme, ouvrirSession, tempsMarque } from "/ecran_resultats.js";
import { ouvrirTelemetrie } from "/ecran_telemetrie.js";
import { chrono, familleClasse, signe } from "/format.js";
import { ICONES } from "/icones.js";
import { langue, locale, t, tp, traduire } from "/i18n.js";

// Ordre des catégories, de la plus rapide à la plus lente (comme l'onglet Temps au tour).
const ORDRE_CLASSES = ["HYPER", "LMP2", "LMP3", "GTE", "GT3"];

// Les dernières courses demandées d'un coup, puis à chaque « voir plus » (voir
// leaderboard.HISTORIQUE).
const PAR_PAGE = 20;

// Les mêmes largeurs pour chaque tableau : les colonnes s'alignent d'une catégorie à
// l'autre. La colonne sans largeur prend le reste. Tout tient à côté de la colonne de
// gauche : le pilote et sa voiture partagent une cellule, la gomme suit le chrono.
const LARGEURS_TOURS = [46, null, 86, 74, 74, 74, 106, 66, 86, 98, 76, 58, 100];
const LARGEURS_VOITURES = [52, null, 116, 66, 210, 76, 80, 104, 84, 64];
const LARGEURS_COURSES = [null, 84, 88, 86, 70, 92, 96, 128, 125];
const LARGEURS_HISTORIQUE = [103, null, 88, 220, 66, 108, 104, 63];
// Sur la page d'un circuit, la colonne Réf. / Comp. en plus.
const LARGEURS_HISTORIQUE_CHOIX = [...LARGEURS_HISTORIQUE, 100];
const LARGEURS_RECORDS = [null, 88, 230, 116, 66, 78, 74, 64];
const LARGEURS_CATEGORIES = [null, 84, 84, 88, 86, 70, 92, 96, 125];

// Les deux menus de la colonne de gauche, et les sous-onglets de la page d'un circuit.
const MENUS = { circuits: "temps.circuits", pilotes: "leaderboard.pilotes" };
const ONGLETS_CIRCUIT = {
  pilotes: "leaderboard.pilotes",
  voitures: "leaderboard.voitures",
  courses: "leaderboard.col.courses",
};

// Ce que la page demande ; la réponse donne ce que le serveur a retenu. Sans tracé ni
// pilote (`profil`), la page des dernières courses.
const demande = {
  trace: null, profil: null, classe: null, voiture: null, pilote: null, historique: PAR_PAGE,
};
// `page` : « groupe » quand l'écran du groupe est ouvert, à la place de la page demandée.
const vue = { tri: "az", menu: "circuits", onglet: "pilotes", page: null };
let donnees = null;
let numero = 0; // la dernière demande partie : une réponse plus ancienne est ignorée
let remonter = false; // une autre page : on la montre depuis le haut

// L'écran du groupe : ce que le serveur en dit, la dernière erreur, une action en cours,
// et le bouton « Quitter » armé (un second clic confirme).
const groupe = { etat: null, erreur: null, occupe: false, quitter: false };
let suiviGroupe = null;

// Toutes les 30 s, onglet ouvert, on regarde si la synchronisation a apporté du neuf.
const SUIVI_GROUPE = 30000;

// Le tour de référence et le tour comparé, choisis comme dans Résultats (colonne Réf. / Comp.)
// parmi les tours enregistrés du tracé de la page. `tours` retrouve ce qu'une pastille désigne.
const choixTours = { trace: null, ref: null, cmp: null, tours: new Map() };

async function charger() {
  const n = ++numero;
  const r = await api("/api/leaderboard", demande);
  if (n !== numero) return false;
  donnees = r;
  // Ce que le serveur a retenu devient la demande : un filtre sans objet disparaît. Sur
  // une fiche, le filtre de pilote est le pilote lui-même : il ne lui survit pas.
  Object.assign(demande, r.filtres);
  demande.profil = r.vue === "pilote" ? r.filtres.pilote : null;
  if (r.vue === "pilote") demande.pilote = null;
  // Le menu de gauche suit la page : les pilotes pour une fiche, les circuits pour un circuit.
  if (r.vue === "pilote") vue.menu = "pilotes";
  if (r.vue === "circuit") vue.menu = "circuits";
  // Des tours choisis sur un autre tracé ne se comparent pas à ceux de celui-ci.
  if (r.filtres.trace !== choixTours.trace) {
    choixTours.trace = r.filtres.trace;
    choixTours.ref = null;
    choixTours.cmp = null;
  }
  choixTours.tours.clear();
  return true;
}

// ---------------------------------------------------------------------
// Petites mises en forme
// ---------------------------------------------------------------------

const colonnes = (largeurs) =>
  `<colgroup>${largeurs.map((l) => `<col${l ? ` style="width:${l}px"` : ""}>`).join("")}</colgroup>`;

const plusPetit = (valeurs) =>
  Math.min(...valeurs.filter((v) => v !== null && v !== undefined), Infinity);

const nombre = (v, decimales = 0) =>
  v === null || v === undefined
    ? "—"
    : v.toLocaleString(langue(), { minimumFractionDigits: decimales, maximumFractionDigits: decimales });

const ecart = (v) => (v > 0 ? signe(v) : "—");
const vitesse = (v) => (v === null ? "—" : `${nombre(v)} km/h`);
const vide = (texte) => `<p class="note vide-leaderboard">${texte}</p>`;
const titreSection = (texte, droite = "") =>
  `<div class="entete-records"><h3>${texte}</h3>${droite ? `<span class="espace"></span>${droite}` : ""}</div>`;

const circuitDuTrace = (r, trace) => r.circuits.find((c) => c.traces.some((x) => x.nom === trace)) || null;
const paysDesCircuits = (r) => new Map(r.circuits.map((c) => [c.circuit, c.pays]));

const heure = (iso) =>
  new Date(iso).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });

const deuxLignes = (haut, bas) => `<span class="deux-lignes"><span>${haut}</span><small>${bas}</small></span>`;

function initiales(nom) {
  return String(nom)
    .split(/[\s_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((mot) => mot[0])
    .join("")
    .toUpperCase();
}

function badgeToi(ligne) {
  return ligne.moi ? `<span class="badge-toi">${t("classement.toi")}</span>` : "";
}

// Le nom d'un pilote ouvre sa fiche, d'où qu'on le voie.
function lienPilote(l) {
  return `<button type="button" class="nom-pilote lien-pilote" data-profil="${echapper(l.pilote)}"
    title="${t("leaderboard.voir_profil")}">${echapper(l.pilote)}</button>${badgeToi(l)}`;
}

// Le pilote sur une ligne, sa voiture en dessous.
function piloteVoiture(l) {
  return `<span class="pilote-voiture">
    <span class="ligne-pilote">${lienPilote(l)}</span>
    <small class="cellule-icone">${embleme(l.marque)}<span>${echapper(l.voiture)}</span></small>
  </span>`;
}

// La voiture sur une ligne, la date et le type de séance en dessous.
function voitureDate(l) {
  return `<span class="pilote-voiture">
    <span class="cellule-icone">${embleme(l.marque)}<span class="nom-voiture">${echapper(l.voiture)}</span></span>
    <small>${dateJour(l.date)} · ${echapper(nomType(l.type))}</small>
  </span>`;
}

const tourGomme = (l, meilleur) =>
  `<span class="tour-gomme">${gomme(l.gomme_meilleur)}<b>${
    tempsMarque(l.meilleur_tour, meilleur, chrono(l.meilleur_tour))
  }</b></span>`;

// ---------------------------------------------------------------------
// La colonne de gauche : les dernières courses, puis les circuits ou les pilotes
// ---------------------------------------------------------------------

function tries(liste, nom, seances) {
  const parNom = (a, b) => nom(a).localeCompare(nom(b), langue());
  return [...liste].sort(vue.tri === "sessions" ? (a, b) => seances(b) - seances(a) || parNom(a, b) : parNom);
}

function carteGroupe(r) {
  const g = r.groupe;
  return `<button type="button" class="carte-circuit carte-historique ${vue.page === "groupe" ? "actif" : ""}"
      data-groupe="1">
    <span class="ligne-titre"><span class="icone-historique">${ICONES.groupe}</span>
      <span class="nom">${t("groupe.titre")}</span>${g ? `<span class="code-groupe">${echapper(g.code)}</span>` : ""}</span>
    <span class="sous">${g ? tp("groupe.membres", g.membres) : t("groupe.sans")}</span>
  </button>`;
}

function carteHistorique(r) {
  const courses = r.circuits.reduce((n, c) => n + c.courses, 0);
  const actif = r.vue === "historique" && vue.page !== "groupe";
  return `<button type="button" class="carte-circuit carte-historique ${actif ? "actif" : ""}"
      data-historique="1">
    <span class="ligne-titre"><span class="icone-historique">${ICONES.calendrier}</span>
      <span class="nom">${t("leaderboard.historique")}</span></span>
    <span class="sous">${tp("leaderboard.nb_en_ligne", courses)}</span>
  </button>`;
}

function carteCircuit(c, actif) {
  const meilleurs = [...c.traces[0].meilleurs]
    .sort((a, b) => ORDRE_CLASSES.indexOf(b.classe) - ORDRE_CLASSES.indexOf(a.classe))
    .slice(0, 3);
  return `<button type="button" class="carte-circuit ${actif ? "actif" : ""}" data-circuit="${echapper(c.circuit)}">
    ${contourSvg(c.contour)}
    <span class="ligne-titre">${drapeau(c.pays)}<span class="nom">${echapper(c.circuit)}</span></span>
    <span class="sous">${tp("leaderboard.nb_courses", c.courses)}<i>${tp("leaderboard.nb_seances", c.seances)}</i>${
      c.traces.length > 1 ? `<i>${t("temps.traces", { n: c.traces.length })}</i>` : ""
    }</span>
    ${meilleurs
      .map((m) => `<span class="ligne-classe">${badgeClasse(m.classe)}<b>${chrono(m.chrono)}</b></span>`)
      .join("")}
  </button>`;
}

function cartePilote(p, actif) {
  return `<button type="button" class="carte-circuit carte-pilote ${actif ? "actif" : ""}"
      data-profil="${echapper(p.pilote)}">
    <span class="ligne-titre"><span class="avatar">${echapper(initiales(p.pilote))}</span>
      <span class="nom">${echapper(p.pilote)}</span>${badgeToi(p)}</span>
    <span class="sous">${tp("leaderboard.nb_courses", p.courses)}<i>${
      tp("leaderboard.nb_victoires", p.victoires)
    }</i><i>${tp("leaderboard.nb_podiums", p.podiums)}</i></span>
    <span class="ligne-badges">${p.classes.slice(0, 3).map(badgeClasse).join("")}<span class="espace"></span>
      <small>${dateJour(p.derniere)}</small></span>
  </button>`;
}

function afficherLaterale(r) {
  const lateral = $("#laterale");
  const ancienne = lateral.querySelector("#lb-menu");
  const haut = ancienne?.dataset.menu === vue.menu ? ancienne.scrollTop : 0;
  const page = vue.page === "groupe" ? null : r.vue;
  const choisi = page === "circuit" ? circuitDuTrace(r, r.filtres.trace) : null;
  const cartes =
    vue.menu === "pilotes"
      ? tries(r.pilotes, (p) => p.pilote, (p) => p.seances).map((p) =>
          cartePilote(p, page === "pilote" && p.pilote === r.filtres.pilote)
        )
      : tries(r.circuits, (c) => c.circuit, (c) => c.seances).map((c) => carteCircuit(c, c === choisi));
  lateral.innerHTML = `
    <div class="entete-laterale">
      <div class="choix-menu" role="group">${Object.entries(MENUS)
        .map(
          ([menu, cle]) => `<button type="button" data-menu="${menu}" class="${menu === vue.menu ? "actif" : ""}">
            ${t(cle)}<span class="badge compteur-blanc">${r[menu].length}</span></button>`
        )
        .join("")}</div>
      <span class="espace"></span>
      <button id="lb-tri" type="button" class="pilule claire">${
        t(vue.tri === "az" ? "temps.tri_az" : "temps.tri_sessions")
      }</button>
    </div>
    <div class="liste-laterale" id="lb-menu" data-menu="${vue.menu}">
      ${carteGroupe(r)}
      ${carteHistorique(r)}
      ${cartes.join("")}
    </div>`;

  const liste = $("#lb-menu");
  liste.scrollTop = haut;
  liste.onclick = (e) => {
    const carte = e.target.closest(".carte-circuit");
    if (!carte) return;
    if (carte.dataset.groupe) {
      ouvrirGroupe();
      return;
    }
    vue.page = null;
    if (carte.dataset.profil) {
      ouvrirFiche(carte.dataset.profil);
      return;
    }
    const circuit = r.circuits.find((c) => c.circuit === carte.dataset.circuit);
    // Un circuit s'ouvre sur son tracé le plus roulé ; la première carte, sur les dernières courses.
    changer({ trace: circuit ? circuit.traces[0].nom : null, profil: null });
  };
  for (const bouton of lateral.querySelectorAll("[data-menu]")) {
    if (bouton.tagName !== "BUTTON") continue;
    bouton.onclick = () => {
      vue.menu = bouton.dataset.menu;
      afficherLaterale(r);
    };
  }
  $("#lb-tri").onclick = () => {
    vue.tri = vue.tri === "az" ? "sessions" : "az";
    afficherLaterale(r);
  };
}

// ---------------------------------------------------------------------
// L'en-tête d'une page et ses filtres
// ---------------------------------------------------------------------

function liste(id, libelle, valeur, choix, tous) {
  return `<label class="filtre-leaderboard"><small>${libelle}</small>
    <select id="${id}">
      <option value="">${tous}</option>
      ${choix
        .map(
          (c) => `<option value="${echapper(c.valeur)}" ${c.valeur === valeur ? "selected" : ""}>${
            echapper(c.texte)
          }</option>`
        )
        .join("")}
    </select></label>`;
}

// La note tant que ce PC n'est dans aucun groupe : un seul pilote, ce PC.
const noteGroupe = (r) => (r.groupe || r.pilotes.length > 1 ? "" : t("leaderboard.seul"));

function entete(r, { visuel, titre, sous, droite = "", fond = "", tuiles = "", avecPilote = true }) {
  const f = r.filtres;
  const o = r.options;
  return `<div class="carte entete-leaderboard">
    ${fond}
    <div class="entete-temps-haut">
      ${visuel}
      <div class="titres"><h1>${titre}</h1><p>${sous}</p></div>
      <span class="espace"></span>
      ${droite}
    </div>
    ${tuiles}
    <div class="filtres-leaderboard">
      ${liste(
        "lb-classe",
        t("leaderboard.filtre.categorie"),
        f.classe,
        o.classes.map((c) => ({ valeur: c, texte: familleClasse(c) || c })),
        t("leaderboard.toutes")
      )}
      ${liste(
        "lb-voiture",
        t("leaderboard.filtre.voiture"),
        f.voiture,
        o.voitures.map((v) => ({ valeur: v, texte: v })),
        t("leaderboard.toutes")
      )}
      ${avecPilote
        ? liste(
            "lb-pilote",
            t("leaderboard.filtre.pilote"),
            f.pilote,
            o.pilotes.map((p) => ({ valeur: p, texte: p })),
            t("leaderboard.tous")
          )
        : ""}
    </div>
  </div>`;
}

// ---------------------------------------------------------------------
// Les tableaux
// ---------------------------------------------------------------------

function arrivee(c) {
  if (c.statut === "abandon") return `<span class="statut-course">${t("classement.abandon")}</span>`;
  if (c.statut === "disqualifie") return `<span class="statut-course">${t("classement.disqualifie")}</span>`;
  if (!c.place) return "—";
  const gain = c.grille ? c.grille - c.place : 0;
  const place = c.place === 1 ? `<span class="badge victoire">P1</span>` : `<b>P${c.place}</b>`;
  return `${place}<small class="sur">/${c.engages}</small>${
    gain ? `<small class="${gain > 0 ? "gagne" : "perd"}">${gain > 0 ? "▲" : "▼"}${Math.abs(gain)}</small>` : ""
  }`;
}

// Les dernières courses. Une ligne ouvre le classement de sa course dans Résultats, même
// celle d'un ami (ce qu'il en a partagé) ; sur la page d'un circuit (`choix`), la colonne
// Réf. / Comp. choisit son meilleur tour enregistré, à comparer dans Télémétrie.
function tableHistorique(r, { choix = false } = {}) {
  const h = r.historique;
  if (!h.lignes.length) return vide(t("leaderboard.aucune_course"));
  const pays = paysDesCircuits(r);
  const restant = h.total - h.lignes.length;
  return `<div class="groupe-records classe-autre">
    <div class="defilement-table"><table class="table-leaderboard table-cliquable">
      ${colonnes(choix ? LARGEURS_HISTORIQUE_CHOIX : LARGEURS_HISTORIQUE)}
      <thead><tr>
        <th>${t("leaderboard.col.date")}</th>
        <th>${t("leaderboard.col.circuit")}</th>
        <th class="centre">${t("leaderboard.filtre.categorie")}</th>
        <th>${t("leaderboard.col.pilote_voiture")}</th>
        <th class="nombre">${t("leaderboard.col.depart")}</th>
        <th class="nombre">${t("leaderboard.col.arrivee")}</th>
        <th class="nombre">${t("classement.col.meilleur")}</th>
        <th class="nombre">${t("classement.col.tours")}</th>
        ${choix ? `<th class="centre">${t("session.col.choix")}</th>` : ""}
      </tr></thead>
      <tbody>${h.lignes
        .map(
          (c) => `<tr class="${c.moi ? "joueur" : ""}" ${
              c.seance
                ? `data-seance="${echapper(c.seance)}" title="${t("leaderboard.voir_course")}"`
                : `title="${t("leaderboard.course_non_partagee")}"`
            }>
            <td>${deuxLignes(dateJour(c.date), heure(c.date))}</td>
            <td><span class="cellule-icone">${drapeau(pays.get(c.circuit))}<span>${echapper(c.trace)}</span></span></td>
            <td class="centre">${badgeClasse(c.classe)}</td>
            <td>${piloteVoiture(c)}</td>
            <td class="nombre">${c.grille ? `P${c.grille}` : "—"}</td>
            <td class="nombre arrivee">${arrivee(c)}</td>
            <td class="nombre">${chrono(c.meilleur_tour)}</td>
            <td class="nombre">${nombre(c.tours)}</td>
            ${choix ? `<td class="choix-tour-cellule">${pastillesChoix(c)}</td>` : ""}
          </tr>`
        )
        .join("")}</tbody>
    </table></div>
    ${restant > 0
      ? `<div class="pied-historique">
          <small>${t("leaderboard.affichees", { n: h.lignes.length, total: h.total })}</small>
          <button type="button" id="lb-plus" class="pilule">${
            t("leaderboard.voir_plus", { n: Math.min(PAR_PAGE, restant) })
          }</button>
        </div>`
      : ""}
  </div>`;
}

function enteteCategorie(c, compte) {
  return `<div class="groupe-records-entete">
    <div>${badgeClasse(c.classe)}<small>${compte}</small></div>
    <span class="espace"></span>
    <b title="${t("leaderboard.reference")}">${chrono(c.reference)}</b>
  </div>`;
}

// Les deux pastilles d'une ligne dont le tour est enregistré : le record de ce PC, ou celui
// qu'un ami a partagé. Ce n'est pas toujours le tour du classement : leur bulle dit lequel.
function pastillesChoix(l) {
  const e = l.enregistre;
  if (!e) return "";
  const cle = `${e.chemin}#${e.numero}`;
  choixTours.tours.set(cle, { ...e, cle, pilote: l.pilote });
  const quoi = { chrono: chrono(e.chrono), voiture: echapper(e.voiture) };
  const pastille = (role, titre) => `<button type="button" class="pastille-choix ${role} ${
    choixTours[role]?.cle === cle ? "actif" : ""
  }" data-role="${role}" data-cle="${echapper(cle)}" title="${titre}"></button>`;
  return pastille("ref", t("leaderboard.choisir_ref", quoi)) + pastille("cmp", t("leaderboard.choisir_cmp", quoi));
}

// `lignes` : celles du tableau dont on choisit les tours (meilleurs tours, ou courses).
function barreComparer(lignes) {
  if (!lignes.some((l) => l.enregistre)) return "";
  const { ref, cmp } = choixTours;
  const role = (cle, nom, x) => `<span class="role-choix ${cle}">${nom}</span>${
    x ? `<b>${echapper(x.pilote)}</b><span>${chrono(x.chrono)}</span>` : "<span>—</span>"
  }`;
  const texte = ref || cmp
    ? `${role("ref", t("tele.reference"), ref)}<span class="separateur-choix"></span>${
        role("cmp", t("tele.comparaison"), cmp)
      }`
    : t("leaderboard.comparer_aide");
  // Une référence suffit : sans tour comparé, la page Télémétrie la montre seule.
  return `<div class="carte barre-comparer">
    <span class="icone-comparer">${ICONES.courbe}</span>
    <span class="texte-comparer">${texte}</span>
    <span class="espace"></span>
    <button type="button" class="principal" id="lb-comparer" ${ref ? "" : "disabled"}>${
      t("leaderboard.comparer")
    }</button>
  </div>`;
}

function groupeTours(c) {
  // Le meilleur de chaque colonne, en violet. Seul dans sa catégorie, un pilote aurait
  // toute sa ligne en violet : on ne marque rien.
  const comparer = c.lignes.length > 1;
  const meilleur = (valeurs) => (comparer ? plusPetit(valeurs) : null);
  const meilleursSecteurs = [0, 1, 2].map((i) => meilleur(c.lignes.map((l) => l.secteurs_meilleur[i])));
  const meilleurIdeal = meilleur(c.lignes.map((l) => l.tour_ideal));
  const meilleurMoyen = meilleur(c.lignes.map((l) => l.temps_moyen));
  const lignes = c.lignes
    .map(
      (l) => `<tr class="${l.moi ? "joueur" : ""}">
        <td class="centre">${l.place}</td>
        <td>${piloteVoiture(l)}</td>
        <td>${deuxLignes(dateJour(l.date), echapper(nomType(l.type)))}</td>
        ${[0, 1, 2]
          .map((i) => {
            const v = l.secteurs_meilleur[i];
            return `<td class="nombre">${tempsMarque(v, meilleursSecteurs[i], v === null ? "" : v.toFixed(3))}</td>`;
          })
          .join("")}
        <td class="nombre">${tourGomme(l, comparer ? c.reference : null)}</td>
        <td class="nombre">${ecart(l.ecart)}</td>
        <td class="nombre">${tempsMarque(l.tour_ideal, meilleurIdeal, chrono(l.tour_ideal))}</td>
        <td class="nombre">${tempsMarque(l.temps_moyen, meilleurMoyen, chrono(l.temps_moyen))}</td>
        <td class="nombre">${vitesse(l.vitesse_max)}</td>
        <td class="nombre">${nombre(l.tours)}</td>
        <td class="choix-tour-cellule">${pastillesChoix(l)}</td>
      </tr>`
    )
    .join("");
  return `<div class="groupe-records classe-${familleClasse(c.classe) || "autre"}">
    ${enteteCategorie(c, tp("leaderboard.membres", c.lignes.length))}
    <div class="defilement-table"><table class="table-leaderboard">
      ${colonnes(LARGEURS_TOURS)}
      <thead><tr>
        <th class="centre">${t("classement.col.place")}</th>
        <th>${t("leaderboard.col.pilote_voiture")}</th>
        <th>${t("leaderboard.col.date")}</th>
        <th class="nombre">S1</th><th class="nombre">S2</th><th class="nombre">S3</th>
        <th class="nombre">${t("classement.col.meilleur")}</th>
        <th class="nombre" title="${t("leaderboard.col.ecart_titre")}">${t("classement.col.ecart")}</th>
        <th class="nombre" title="${t("leaderboard.col.ideal_titre")}">${t("leaderboard.col.ideal")}</th>
        <th class="nombre" title="${t("leaderboard.col.moyen_titre")}">${t("leaderboard.col.moyen")}</th>
        <th class="nombre">${t("leaderboard.col.vitesse")}</th>
        <th class="nombre">${t("classement.col.tours")}</th>
        <th class="centre">${t("session.col.choix")}</th>
      </tr></thead>
      <tbody>${lignes}</tbody>
    </table></div>
  </div>`;
}

function groupeVoitures(c) {
  const comparer = c.lignes.length > 1;
  const meilleurMoyen = comparer ? plusPetit(c.lignes.map((l) => l.temps_moyen)) : null;
  const lignes = c.lignes
    .map(
      (l) => `<tr class="${l.moi ? "joueur" : ""}">
        <td class="centre">${l.place}</td>
        <td><span class="cellule-icone">${embleme(l.marque)}<span class="nom-voiture">${echapper(l.voiture)}</span></span></td>
        <td class="nombre">${tourGomme(l, comparer ? c.reference : null)}</td>
        <td class="nombre">${ecart(l.ecart)}</td>
        <td>${deuxLignes(lienPilote(l), `${dateJour(l.date)} · ${echapper(nomType(l.type))}`)}</td>
        <td class="nombre">${nombre(l.pilotes)}</td>
        <td class="nombre">${nombre(l.seances)}</td>
        <td class="nombre">${tempsMarque(l.temps_moyen, meilleurMoyen, chrono(l.temps_moyen))}</td>
        <td class="nombre">${vitesse(l.vitesse_max)}</td>
        <td class="nombre">${nombre(l.tours)}</td>
      </tr>`
    )
    .join("");
  return `<div class="groupe-records classe-${familleClasse(c.classe) || "autre"}">
    ${enteteCategorie(c, tp("leaderboard.nb_voitures", c.lignes.length))}
    <div class="defilement-table"><table class="table-leaderboard">
      ${colonnes(LARGEURS_VOITURES)}
      <thead><tr>
        <th class="centre">${t("classement.col.place")}</th>
        <th>${t("classement.col.voiture")}</th>
        <th class="nombre">${t("classement.col.meilleur")}</th>
        <th class="nombre" title="${t("leaderboard.col.ecart_titre")}">${t("classement.col.ecart")}</th>
        <th>${t("leaderboard.col.par")}</th>
        <th class="nombre">${t("leaderboard.pilotes")}</th>
        <th class="nombre">${t("leaderboard.col.seances")}</th>
        <th class="nombre" title="${t("leaderboard.col.moyen_voiture_titre")}">${t("leaderboard.col.moyen")}</th>
        <th class="nombre">${t("leaderboard.col.vitesse")}</th>
        <th class="nombre">${t("classement.col.tours")}</th>
      </tr></thead>
      <tbody>${lignes}</tbody>
    </table></div>
  </div>`;
}

function tableCourses(lignes) {
  if (!lignes.length) return vide(t("leaderboard.aucune_course"));
  return `<div class="groupe-records classe-autre">
    <div class="defilement-table"><table class="table-leaderboard">
      ${colonnes(LARGEURS_COURSES)}
      <thead><tr>
        <th>${t("classement.col.pilote")}</th>
        <th class="nombre">${t("leaderboard.col.courses")}</th>
        <th class="nombre">${t("leaderboard.col.victoires")}</th>
        <th class="nombre">${t("leaderboard.col.podiums")}</th>
        <th class="nombre">${t("leaderboard.col.top10")}</th>
        <th class="nombre">${t("leaderboard.col.abandons")}</th>
        <th class="nombre" title="${t("leaderboard.col.place_moyenne_titre")}">${t("leaderboard.col.place_moyenne")}</th>
        <th class="nombre">${t("leaderboard.col.tours_course")}</th>
        <th class="nombre" title="${t("leaderboard.col.tours_total_titre")}">${t("leaderboard.col.tours_total")}</th>
      </tr></thead>
      <tbody>${lignes
        .map(
          (l) => `<tr class="${l.moi ? "joueur" : ""}">
            <td>${lienPilote(l)}</td>
            ${cellulesBilan(l)}
          </tr>`
        )
        .join("")}</tbody>
    </table></div>
  </div>`;
}

// Les cellules d'un bilan de courses, de « Courses » à « Tours au total ».
function cellulesBilan(l) {
  return `<td class="nombre">${nombre(l.courses)}</td>
    <td class="nombre">${l.victoires ? `<b class="victoires">${nombre(l.victoires)}</b>` : "0"}</td>
    <td class="nombre">${nombre(l.podiums)}</td>
    <td class="nombre">${nombre(l.top10)}</td>
    <td class="nombre">${nombre(l.abandons)}</td>
    <td class="nombre">${l.place_moyenne === null ? "—" : nombre(l.place_moyenne, 1)}</td>
    <td class="nombre">${nombre(l.tours_en_course)}</td>
    <td class="nombre">${nombre(l.tours)}</td>`;
}

function tableRecords(r, records) {
  if (!records.length) return vide(t("leaderboard.aucun_tour"));
  const pays = paysDesCircuits(r);
  return `<div class="groupe-records classe-autre">
    <div class="defilement-table"><table class="table-leaderboard table-cliquable">
      ${colonnes(LARGEURS_RECORDS)}
      <thead><tr>
        <th>${t("leaderboard.col.circuit")}</th>
        <th class="centre">${t("leaderboard.filtre.categorie")}</th>
        <th>${t("leaderboard.col.voiture_date")}</th>
        <th class="nombre">${t("classement.col.meilleur")}</th>
        <th class="nombre" title="${t("leaderboard.col.ecart_titre")}">${t("classement.col.ecart")}</th>
        <th class="nombre" title="${t("leaderboard.col.rang_titre")}">${t("leaderboard.col.rang")}</th>
        <th class="nombre">${t("leaderboard.col.seances")}</th>
        <th class="nombre">${t("classement.col.tours")}</th>
      </tr></thead>
      <tbody>${records
        .map(
          (x) => `<tr data-trace="${echapper(x.trace)}" data-classe="${echapper(x.classe)}"
              title="${t("leaderboard.voir_circuit")}">
            <td><span class="cellule-icone">${drapeau(pays.get(x.circuit))}<span>${echapper(x.trace)}</span></span></td>
            <td class="centre">${badgeClasse(x.classe)}</td>
            <td>${voitureDate(x)}</td>
            <td class="nombre">${tourGomme(x, null)}</td>
            <td class="nombre">${ecart(x.ecart)}</td>
            <td class="nombre arrivee">${
              x.rang === 1 && x.pilotes > 1 ? `<span class="badge victoire">P1</span>` : `<b>P${x.rang}</b>`
            }<small class="sur">/${x.pilotes}</small></td>
            <td class="nombre">${nombre(x.seances)}</td>
            <td class="nombre">${nombre(x.tours)}</td>
          </tr>`
        )
        .join("")}</tbody>
    </table></div>
  </div>`;
}

function tableCategories(categories) {
  if (!categories.length) return vide(t("leaderboard.aucune_course"));
  return `<div class="groupe-records classe-autre">
    <div class="defilement-table"><table class="table-leaderboard">
      ${colonnes(LARGEURS_CATEGORIES)}
      <thead><tr>
        <th>${t("leaderboard.filtre.categorie")}</th>
        <th class="nombre">${t("leaderboard.col.seances")}</th>
        <th class="nombre">${t("leaderboard.col.courses")}</th>
        <th class="nombre">${t("leaderboard.col.victoires")}</th>
        <th class="nombre">${t("leaderboard.col.podiums")}</th>
        <th class="nombre">${t("leaderboard.col.top10")}</th>
        <th class="nombre">${t("leaderboard.col.abandons")}</th>
        <th class="nombre" title="${t("leaderboard.col.place_moyenne_titre")}">${t("leaderboard.col.place_moyenne")}</th>
        <th class="nombre" title="${t("leaderboard.col.tours_total_titre")}">${t("leaderboard.col.tours_total")}</th>
      </tr></thead>
      <tbody>${categories
        .map(
          (c) => `<tr>
            <td>${badgeClasse(c.classe)}</td>
            <td class="nombre">${nombre(c.seances)}</td>
            <td class="nombre">${nombre(c.courses)}</td>
            <td class="nombre">${c.victoires ? `<b class="victoires">${nombre(c.victoires)}</b>` : "0"}</td>
            <td class="nombre">${nombre(c.podiums)}</td>
            <td class="nombre">${nombre(c.top10)}</td>
            <td class="nombre">${nombre(c.abandons)}</td>
            <td class="nombre">${c.place_moyenne === null ? "—" : nombre(c.place_moyenne, 1)}</td>
            <td class="nombre">${nombre(c.tours)}</td>
          </tr>`
        )
        .join("")}</tbody>
    </table></div>
  </div>`;
}

// ---------------------------------------------------------------------
// Les trois pages
// ---------------------------------------------------------------------

function pageHistorique(r) {
  const pilotes = tp("leaderboard.membres", r.pilotes.length);
  let groupe = r.pilotes.length > 1 ? pilotes : noteGroupe(r);
  if (r.groupe) groupe = `${t("groupe.note", { code: echapper(r.groupe.code) })} · ${pilotes}`;
  return `${entete(r, {
      visuel: `<span class="grand-icone">${ICONES.calendrier}</span>`,
      titre: t("leaderboard.historique"),
      sous: `${t("leaderboard.historique_texte")} ${groupe}`,
    })}
    ${tableHistorique(r)}
    ${titreSection(t("leaderboard.bilan_titre"))}
    ${tableCourses(r.courses)}`;
}

function pageCircuit(r, circuit) {
  const f = r.filtres;
  const trace = circuit.traces.find((x) => x.nom === f.trace) || circuit.traces[0];
  const chiffres = [
    tp("leaderboard.nb_courses", trace.courses),
    tp("leaderboard.nb_seances", trace.seances),
    tp("leaderboard.membres", trace.pilotes),
    tp("leaderboard.nb_voitures", trace.voitures),
    tp("leaderboard.nb_tours", trace.tours),
  ].join(" · ");
  const variante = circuit.traces.length === 1 && f.trace !== circuit.circuit ? `${echapper(f.trace)} · ` : "";
  const note = noteGroupe(r);
  const choixTrace =
    circuit.traces.length > 1
      ? `<label class="choix-trace"><small>${t("temps.trace")}</small>
        <select id="lb-trace">${circuit.traces
          .map(
            (x) => `<option value="${echapper(x.nom)}" ${x.nom === f.trace ? "selected" : ""}>${
              echapper(x.nom)
            }</option>`
          )
          .join("")}</select></label>`
      : "";
  let contenu;
  if (vue.onglet === "voitures") {
    contenu = r.voitures.map(groupeVoitures).join("") || vide(t("leaderboard.aucun_tour"));
  } else if (vue.onglet === "courses") {
    contenu = `${titreSection(t("leaderboard.bilan_titre"))}
      ${tableCourses(r.courses)}
      ${titreSection(t("leaderboard.historique"))}
      ${barreComparer(r.historique.lignes)}
      ${tableHistorique(r, { choix: true })}`;
  } else {
    contenu = `${barreComparer(r.tours.flatMap((c) => c.lignes))}${
      r.tours.map(groupeTours).join("") || vide(t("leaderboard.aucun_tour"))
    }`;
  }
  return `${entete(r, {
      visuel: `<span class="grand-drapeau">${drapeau(circuit.pays)}</span>`,
      titre: echapper(circuit.circuit),
      sous: `${variante}${chiffres}${note ? `<br>${note}` : ""}`,
      droite: choixTrace,
      fond: contourSvg(r.contour),
    })}
    <div class="barre-onglets onglets-leaderboard">${Object.entries(ONGLETS_CIRCUIT)
      .map(
        ([onglet, cle]) => `<button type="button" data-onglet-lb="${onglet}"
          class="${onglet === vue.onglet ? "actif" : ""}">${t(cle)}</button>`
      )
      .join("")}</div>
    ${contenu}`;
}

function tuile(libelle, valeur) {
  return `<div class="tuile-totale"><small>${libelle}</small><b>${valeur}</b></div>`;
}

function pageProfil(r) {
  const p = r.profil;
  const b = p.bilan;
  const sous = [
    p.depuis ? t("leaderboard.depuis", { date: dateJour(p.depuis) }) : "",
    p.circuit_favori ? t("leaderboard.circuit_favori", { circuit: echapper(p.circuit_favori.circuit) }) : "",
    p.voiture_favorite ? t("leaderboard.voiture_favorite", { voiture: echapper(p.voiture_favorite.voiture) }) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const note = noteGroupe(r);
  return `${entete(r, {
      visuel: `<span class="grand-avatar">${echapper(initiales(p.pilote))}</span>`,
      titre: `${echapper(p.pilote)}${badgeToi(p)}`,
      sous: `${sous}${note ? `<br>${note}` : ""}`,
      avecPilote: false,
      tuiles: `<div class="tuiles-profil">
        ${tuile(t("leaderboard.col.seances"), nombre(p.seances))}
        ${tuile(t("leaderboard.col.courses"), nombre(b.courses))}
        ${tuile(t("leaderboard.col.victoires"), nombre(b.victoires))}
        ${tuile(t("leaderboard.col.podiums"), nombre(b.podiums))}
        ${tuile(t("leaderboard.col.top10"), nombre(b.top10))}
        ${tuile(t("leaderboard.col.place_moyenne"), b.place_moyenne === null ? "—" : nombre(b.place_moyenne, 1))}
        ${tuile(t("leaderboard.col.tours_total"), nombre(b.tours))}
      </div>`,
    })}
    ${titreSection(t("leaderboard.records_titre"), `<small>${tp("leaderboard.nb_records", p.records.length)}</small>`)}
    ${tableRecords(r, p.records)}
    ${titreSection(t("leaderboard.categories_titre"))}
    ${tableCategories(p.categories)}
    ${titreSection(t("leaderboard.historique"))}
    ${tableHistorique(r)}`;
}

// ---------------------------------------------------------------------
// Le groupe : le créer, le rejoindre, le voir, le quitter
// ---------------------------------------------------------------------

function texteSynchro(g) {
  const s = g.synchro;
  if (s.etat === "en_cours") return t("groupe.etat.en_cours");
  if (s.etat === "erreur") return t("groupe.etat.erreur", { erreur: traduire(s.erreur) });
  if (s.etat === "ok") {
    return t("groupe.etat.ok", { date: dateCourte(s.derniere), envoyees: s.envoyees, recues: s.recues });
  }
  return g.groupe.derniere ? t("groupe.etat.derniere", { date: dateCourte(g.groupe.derniere) }) : t("groupe.etat.jamais");
}

const partage = () => `<div class="carte carte-groupe-texte">
    <h3>${t("groupe.partage_titre")}</h3><p class="note">${t("groupe.partage_texte")}</p>
  </div>`;

function pageGroupe() {
  const g = groupe.etat;
  const entete = `<div class="carte entete-leaderboard">
    <div class="entete-temps-haut">
      <span class="grand-icone">${ICONES.groupe}</span>
      <div class="titres"><h1>${t("groupe.titre")}</h1><p>${t("groupe.sous_titre")}</p></div>
    </div>
  </div>`;
  if (!g) return `${entete}${etatVide({ chargement: true, titre: t("groupe.chargement") })}`;
  const erreur = groupe.erreur ? `<div class="erreur-dossier erreur-groupe">${echapper(groupe.erreur)}</div>` : "";
  const occupe = groupe.occupe ? "disabled" : "";
  if (!g.service) {
    return `${entete}${etatVide({
      icone: "avertissement", titre: t("groupe.sans_service_titre"), texte: t("groupe.sans_service_texte"),
    })}`;
  }
  if (!g.groupe) {
    const nom = echapper(g.nom_propose || "");
    return `${entete}${erreur}
      <div class="cartes-groupe">
        <form class="carte carte-groupe-action" id="form-creer">
          <h3>${t("groupe.creer_titre")}</h3>
          <p class="note">${t("groupe.creer_texte")}</p>
          <label class="champ"><small>${t("groupe.nom")}</small>
            <input name="nom" maxlength="40" value="${nom}" required autocomplete="off"></label>
          <button type="submit" class="principal" ${occupe}>${ICONES.groupe}${t("groupe.creer")}</button>
        </form>
        <form class="carte carte-groupe-action" id="form-rejoindre">
          <h3>${t("groupe.rejoindre_titre")}</h3>
          <p class="note">${t("groupe.rejoindre_texte")}</p>
          <label class="champ"><small>${t("groupe.code")}</small>
            <input name="code" maxlength="12" placeholder="K7M2-QX9P" required autocomplete="off" spellcheck="false"
              class="saisie-code"></label>
          <label class="champ"><small>${t("groupe.nom")}</small>
            <input name="nom" maxlength="40" value="${nom}" required autocomplete="off"></label>
          <button type="submit" class="principal" ${occupe}>${t("groupe.rejoindre")}</button>
        </form>
      </div>
      ${partage()}`;
  }
  const gr = g.groupe;
  const membres = gr.membres.length
    ? `<div class="groupe-records classe-autre"><div class="defilement-table"><table class="table-leaderboard">
        ${colonnes([null, 190, 190])}
        <thead><tr>
          <th>${t("groupe.col.nom")}</th><th>${t("groupe.col.rejoint")}</th><th>${t("groupe.col.vu")}</th>
        </tr></thead>
        <tbody>${gr.membres
          .map(
            (m) => `<tr class="${m.moi ? "joueur" : ""}">
              <td><span class="nom-pilote">${echapper(m.nom)}</span>${badgeToi(m)}</td>
              <td>${m.rejoint_le ? dateCourte(m.rejoint_le) : "—"}</td>
              <td>${m.vu_le ? dateCourte(m.vu_le) : "—"}</td>
            </tr>`
          )
          .join("")}</tbody>
      </table></div></div>`
    : vide(t("groupe.aucun_membre"));
  return `${entete}${erreur}
    <div class="carte carte-code">
      <div class="code-et-texte">
        <small>${t("groupe.code")}</small>
        <b class="code-grand">${echapper(gr.code)}</b>
      </div>
      <button type="button" class="pilule claire" id="copier-code">${t("groupe.copier")}</button>
      <p class="note">${t("groupe.inviter")}</p>
    </div>
    ${titreSection(t("groupe.membres_titre"), `<small>${tp("groupe.membres", gr.membres.length)}</small>`)}
    ${membres}
    ${titreSection(t("groupe.synchro"))}
    <div class="carte carte-synchro">
      <span class="etat-synchro etat-${echapper(g.synchro.etat)}">${texteSynchro(g)}</span>
      <span class="espace"></span>
      <button type="button" class="pilule" id="synchroniser" ${occupe}>${t("groupe.synchroniser")}</button>
    </div>
    ${partage()}
    <div class="zone-quitter">
      <button type="button" class="bouton-quitter ${groupe.quitter ? "arme" : ""}" id="quitter-groupe" ${occupe}>${
        t(groupe.quitter ? "groupe.quitter_confirmer" : "groupe.quitter")
      }</button>
    </div>`;
}

function brancherGroupe(cible) {
  const formulaire = (id, route, champs) => {
    const form = cible.querySelector(id);
    if (!form) return;
    form.onsubmit = (e) => {
      e.preventDefault();
      const donnees = Object.fromEntries(champs.map((c) => [c, form.elements[c].value]));
      actionGroupe(route, donnees);
    };
  };
  formulaire("#form-creer", "creer", ["nom"]);
  formulaire("#form-rejoindre", "rejoindre", ["code", "nom"]);
  const copier = $("#copier-code");
  if (copier) {
    copier.onclick = async () => {
      try {
        await navigator.clipboard.writeText(groupe.etat.groupe.code);
        copier.textContent = t("groupe.copie");
      } catch {
        // Sans presse-papiers, le code reste à recopier à la main : on le sélectionne.
        getSelection().selectAllChildren(cible.querySelector(".code-grand"));
      }
    };
  }
  const synchroniser = $("#synchroniser");
  if (synchroniser) synchroniser.onclick = () => actionGroupe("synchroniser");
  const quitter = $("#quitter-groupe");
  if (quitter) {
    // Un premier clic arme le bouton, le second quitte : partir efface ses performances.
    quitter.onclick = () => {
      if (!groupe.quitter) {
        groupe.quitter = true;
        afficher();
        setTimeout(() => {
          groupe.quitter = false;
          if (vue.page === "groupe") afficher();
        }, 5000);
        return;
      }
      groupe.quitter = false;
      actionGroupe("quitter");
    };
  }
}

async function chargerGroupe() {
  try {
    groupe.etat = await api("/api/groupe");
    groupe.erreur = null;
  } catch (e) {
    groupe.erreur = e.message;
  }
}

async function ouvrirGroupe() {
  vue.page = "groupe";
  remonter = true;
  afficher();
  await chargerGroupe();
  afficher();
}

async function actionGroupe(route, corps = {}) {
  groupe.occupe = true;
  groupe.erreur = null;
  afficher();
  try {
    groupe.etat = await envoyer(`/api/groupe/${route}`, corps);
  } catch (e) {
    groupe.erreur = e.message;
  }
  groupe.occupe = false;
  // Le groupe a changé : le leaderboard aussi (ses pilotes, la carte du groupe).
  await recharger();
}

// Onglet ouvert, on regarde de temps en temps si la synchronisation en tâche de fond a
// apporté du neuf : la page se met à jour d'elle-même.
function suivreGroupe() {
  clearTimeout(suiviGroupe);
  suiviGroupe = setTimeout(async () => {
    if (etat.onglet !== "leaderboard") return;
    try {
      await chargerGroupe();
      const version = groupe.etat?.groupe?.version;
      if (donnees?.groupe && version !== undefined && version !== donnees.groupe.version) await recharger();
      else if (vue.page === "groupe") afficher();
    } catch {
      // Le serveur de l'outil s'est arrêté : rien à suivre.
    }
    suivreGroupe();
  }, SUIVI_GROUPE);
}

// ---------------------------------------------------------------------
// L'écran
// ---------------------------------------------------------------------

function afficher() {
  if (etat.onglet !== "leaderboard" || !donnees) return;
  const r = donnees;
  const cible = $("#ecran-leaderboard");
  if (vue.page === "groupe") {
    afficherLaterale(r);
    cible.innerHTML = pageGroupe();
    if (remonter) {
      cible.scrollTop = 0;
      remonter = false;
    }
    cible.onclick = null;
    brancherGroupe(cible);
    return;
  }
  if (!r.circuits.length) {
    // Rien à classer : la colonne garde la carte du groupe, pour en créer ou en rejoindre un.
    afficherLaterale(r);
    cible.innerHTML = r.resultats
      ? etatVide({ icone: "chrono", titre: t("leaderboard.vide_titre"), texte: t("leaderboard.vide_texte") })
      : etatVide({
          icone: "avertissement", titre: t("leaderboard.sans_resultats"), texte: t("leaderboard.sans_resultats_texte"),
        });
    return;
  }
  afficherLaterale(r);
  const circuit = r.vue === "circuit" ? circuitDuTrace(r, r.filtres.trace) : null;
  if (circuit) cible.innerHTML = pageCircuit(r, circuit);
  else if (r.vue === "pilote") cible.innerHTML = pageProfil(r);
  else cible.innerHTML = pageHistorique(r);
  if (remonter) {
    cible.scrollTop = 0;
    remonter = false;
  }

  $("#lb-classe").onchange = (e) => changer({ classe: e.target.value || null });
  $("#lb-voiture").onchange = (e) => changer({ voiture: e.target.value || null });
  const choixPilote = $("#lb-pilote");
  if (choixPilote) choixPilote.onchange = (e) => changer({ pilote: e.target.value || null });
  const choixTrace = $("#lb-trace");
  if (choixTrace) choixTrace.onchange = (e) => changer({ trace: e.target.value });
  // Comme dans Résultats : une pastille donne son rôle au tour ; un tour qui avait l'autre
  // rôle l'échange ; recliquer une pastille choisie la retire.
  for (const pastille of cible.querySelectorAll(".pastille-choix")) {
    pastille.onclick = () => {
      const tour = choixTours.tours.get(pastille.dataset.cle);
      const role = pastille.dataset.role;
      const autre = role === "ref" ? "cmp" : "ref";
      if (choixTours[role]?.cle === tour.cle) choixTours[role] = null;
      else {
        if (choixTours[autre]?.cle === tour.cle) choixTours[autre] = choixTours[role];
        choixTours[role] = tour;
      }
      afficher();
    };
  }

  cible.onclick = (e) => {
    // Le nom d'un pilote ouvre sa fiche, même dans une ligne qui mène ailleurs.
    const lien = e.target.closest("[data-profil]");
    if (lien) {
      ouvrirFiche(lien.dataset.profil);
      return;
    }
    const onglet = e.target.closest("[data-onglet-lb]");
    if (onglet) {
      vue.onglet = onglet.dataset.ongletLb;
      afficher();
      return;
    }
    if (e.target.closest("#lb-plus")) {
      demande.historique += PAR_PAGE;
      recharger();
      return;
    }
    if (e.target.closest("#lb-comparer")) {
      comparerDansTelemetrie();
      return;
    }
    // Les pastilles Réf. / Comp. d'une course ont leur propre clic.
    if (e.target.closest(".pastille-choix")) return;
    // Une course ouvre son classement dans Résultats.
    const course = e.target.closest(".table-cliquable tbody tr[data-seance]");
    if (course) {
      ouvrirCourse(course.dataset.seance);
      return;
    }
    // Un record ouvre le circuit, dans sa catégorie.
    const ligne = e.target.closest(".table-cliquable tbody tr[data-trace]");
    if (ligne) {
      vue.onglet = "pilotes";
      changer({ trace: ligne.dataset.trace, classe: ligne.dataset.classe, voiture: null, pilote: null, profil: null });
    }
  };
}

// Une fiche s'ouvre entière : sans les filtres de catégorie et de voiture de la page d'où
// l'on vient, qui la montreraient en partie sans qu'on le voie.
function ouvrirFiche(nom) {
  changer({ profil: nom, trace: null, classe: null, voiture: null, pilote: null });
}

// Une course dans l'onglet Résultats : la session de ce PC qui l'a enregistrée, ou son seul
// classement (« seance:… », la course d'un ami). Celle d'un ami n'est pas dans la colonne
// des sessions : elle reste affichée tant qu'on n'en choisit pas une autre.
function ouvrirCourse(designation) {
  // Connue avant de changer d'onglet, qui ouvrirait sinon la dernière session.
  etat.sessionChoisie = designation;
  navigation.aller("resultats");
  ouvrirSession(designation).catch((e) => erreur(e.message));
}

// La référence et le tour comparé choisis, dans l'onglet Télémétrie.
function comparerDansTelemetrie() {
  const { ref, cmp } = choixTours;
  if (!ref) return;
  ouvrirTelemetrie({
    ref: ref.chemin, tourRef: ref.numero, cmp: cmp ? cmp.chemin : null, tourCmp: cmp ? cmp.numero : null,
  }).catch((e) => erreurLeaderboard(e));
}

function erreurLeaderboard(e) {
  $("#ecran-leaderboard").innerHTML = etatVide({
    icone: "avertissement", titre: t("leaderboard.impossible"), texte: echapper(e.message),
  });
}

function changer(valeurs) {
  remonter =
    ("trace" in valeurs && valeurs.trace !== demande.trace) ||
    ("profil" in valeurs && valeurs.profil !== demande.profil);
  Object.assign(demande, valeurs, { historique: PAR_PAGE });
  recharger();
}

async function recharger() {
  try {
    if (await charger()) afficher();
  } catch (e) {
    $("#ecran-leaderboard").innerHTML = etatVide({
      icone: "avertissement", titre: t("leaderboard.impossible"), texte: echapper(e.message),
    });
  }
}

/** L'onglet vient d'être affiché : on relit, une séance a pu s'ajouter. */
export async function surLeaderboard() {
  if (donnees) {
    afficher();
  } else {
    $("#laterale").innerHTML = "";
    $("#ecran-leaderboard").innerHTML = etatVide({ chargement: true, titre: t("leaderboard.chargement") });
  }
  await recharger();
  if (vue.page === "groupe") {
    await chargerGroupe();
    afficher();
  }
  suivreGroupe();
}

export const ecranLeaderboard = {
  rafraichir: afficher,
};
