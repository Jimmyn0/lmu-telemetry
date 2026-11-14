// La colonne des sessions.
//
// La liste s'affiche tout de suite à partir des noms de fichiers. Le reste vient de
// l'index, que le serveur complète en tâche de fond : tant qu'il reste des sessions
// à lire, on redemande, et les cartes se précisent pendant qu'on les regarde.

import { $, api, badgeClasse, badgeType, contourSvg, dateCourte, erreur, etat } from "/commun.js";
import { drapeau, echapper, nomDuPays } from "/emblemes.js";
import { chrono, circuitDe, codeType, filtrerSessions, trierSessions } from "/format.js";
import { ICONES } from "/icones.js";
import { langue, t, tp } from "/i18n.js";
import { ouvrirSession, surResultats } from "/ecran_resultats.js";

// Cartes ajoutées à chaque fois qu'on approche du bas de la liste. Créer d'un coup
// les 583 cartes du disque figerait la page une fraction de seconde à chaque tri.
const PAR_PAQUET = 30;

// Part de la hauteur de la liste au-dessus de laquelle les cartes ne sont pas estompées
// (voir `.liste-laterale` dans style.css).
const PART_LISIBLE = 0.56;

const filtres = { circuit: "", tri: "date", masquerVides: true, enLigne: false, ouverts: false };
let limite = PAR_PAQUET;
let suivi = null;

export async function chargerSessions() {
  const reponse = await api("/api/sessions");
  etat.sessions = reponse.sessions;
  etat.restant = reponse.restant;
  etat.contours = reponse.contours || {};
  clearTimeout(suivi);
  if (reponse.restant > 0) {
    suivi = setTimeout(() => chargerSessions().then(rafraichirSiVisible).catch(() => {}), 1500);
  }
}

// Au tout premier lancement, aucune session n'est encore lue : la première utile
// s'ouvre dès qu'elle est connue.
function rafraichirSiVisible() {
  if (etat.onglet !== "resultats") return;
  barreSessions.afficher();
  if (!etat.session) surResultats();
}

// Une session finie (le jeu referme son fichier en quittant la séance) apparaît sans
// relancer l'outil : la liste se redemande toutes les 20 s, et dès que la fenêtre revient
// au premier plan, en sortant du jeu. Elle ne se redessine que si quelque chose a changé.
const VEILLE = 20000;
let derniereVerification = 0;

async function verifierSessions() {
  // Sans dossier, rien à surveiller ; une lecture en cours se redemande déjà toute seule.
  if (etat.sansDossier || etat.restant > 0 || Date.now() - derniereVerification < 3000) return;
  derniereVerification = Date.now();
  const avant = JSON.stringify(etat.sessions || []);
  try {
    await chargerSessions();
  } catch {
    return;
  }
  if (JSON.stringify(etat.sessions) !== avant) rafraichirSiVisible();
}

let surveillance = null;

export function surveillerSessions() {
  if (surveillance) return;
  surveillance = setInterval(verifierSessions, VEILLE);
  window.addEventListener("focus", verifierSessions);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) verifierSessions();
  });
}

function retenues() {
  return trierSessions(filtrerSessions(etat.sessions, filtres), filtres.tri);
}

function carte(s) {
  const code = codeType(s.type) || "autre";
  const part = s.tours ? Math.round((100 * (s.tours - s.valides)) / s.tours) : 100;
  const classe = s.voiture?.classe || s.categorie;
  const actif = etat.sessionChoisie === s.id;
  return `<button type="button" class="carte-session type-${code}${actif ? " actif" : ""}"
      data-id="${echapper(s.id)}">
    ${contourSvg(etat.contours[s.trace])}
    <span class="ligne-titre">${drapeau(s.pays)}
      <span class="nom">${echapper(circuitDe(s))}</span>${badgeType(s.type)}</span>
    <span class="pays">${echapper(s.pays ? nomDuPays(s.pays) : "")}</span>
    <span class="filet" title="${t("sessions.part_valides")}"><i style="width:${part}%"></i></span>
    <span class="date">${ICONES.calendrier}${dateCourte(s.date)}</span>
    <span class="bas">${badgeClasse(classe)}${etiquettes(s)}
      <span class="espace"></span>
      ${s.indisponible ? `<span class="badge alerte">${t("sessions.illisible")}</span>` : ""}
      ${s.journal ? `<span class="badge alerte" title="${t("session.non_refermee")}">!</span>` : ""}
      ${s.meilleur ? `<span class="temps-carte">${chrono(s.meilleur)}</span>` : ""}
      ${s.tours ? `<span class="badge compteur" title="${t("sessions.col.tours")}">${s.tours}</span>` : ""}
    </span>
  </button>`;
}

// Ce que les fichiers de résultats et la télémétrie disent de la séance : une victoire,
// un départ de nuit, une séance en ligne.
function etiquettes(s) {
  return [
    s.victoire ? `<span class="badge victoire">${t("sessions.victoire")}</span>` : "",
    s.nuit
      ? `<span class="badge icone-seule nuit" title="${t("sessions.nuit")}">${ICONES.lune}</span>`
      : "",
    s.en_ligne
      ? `<span class="badge icone-seule en-ligne" title="${t("sessions.en_ligne")}">${ICONES.en_ligne}</span>`
      : "",
  ].join("");
}

function optionsCircuits() {
  const nombres = new Map();
  for (const s of etat.sessions) {
    const nom = circuitDe(s);
    nombres.set(nom, (nombres.get(nom) || 0) + 1);
  }
  return (
    `<option value="">${t("sessions.tous", { n: etat.sessions.length })}</option>` +
    [...nombres.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], langue()))
      .map(
        ([nom, n]) => `<option value="${echapper(nom)}" ${nom === filtres.circuit ? "selected" : ""}>
          ${echapper(nom)} (${n})</option>`
      )
      .join("")
  );
}

function ajouterCartes(cible, sessions) {
  const debut = cible.querySelectorAll(".carte-session").length;
  cible.insertAdjacentHTML(
    "beforeend",
    sessions.slice(debut, limite).map(carte).join("")
  );
}

export const barreSessions = {
  afficher() {
    const lateral = $("#laterale");
    const sessions = retenues();
    const haut = lateral.querySelector(".liste-laterale")?.scrollTop || 0;
    lateral.innerHTML = `
      <div class="entete-laterale">
        <h2>${t("sessions.titre")}</h2>
        <span class="badge compteur-blanc">${sessions.length}</span>
        <span class="espace"></span>
        <button id="bascule-tri" type="button" class="pilule">${
          t(filtres.tri === "date" ? "sessions.tri_date" : "sessions.tri_chrono")
        }</button>
        <button id="bascule-filtres" type="button" class="pilule">${t("sessions.filtres")}</button>
      </div>
      <div id="panneau-filtres" class="filtres" ${filtres.ouverts ? "" : "hidden"}>
        <label>${t("sessions.filtre_circuit")}
          <select id="circuit">${optionsCircuits()}</select></label>
        <label class="case"><input type="checkbox" id="avec-tours"
          ${filtres.masquerVides ? "checked" : ""}> ${t("sessions.masquer_vides")}</label>
        <label class="case"><input type="checkbox" id="en-ligne"
          ${filtres.enLigne ? "checked" : ""}> ${t("sessions.filtre_en_ligne")}</label>
      </div>
      ${etat.restant
        ? `<div class="note avancement"><span class="roue"></span>${tp("sessions.lecture", etat.restant)}</div>`
        : ""}
      <div class="liste-laterale" id="liste-sessions"></div>`;

    const liste = $("#liste-sessions");
    if (!sessions.length) {
      liste.innerHTML = `<div class="note vide">${t("sessions.aucune")}</div>`;
    }
    ajouterCartes(liste, sessions);
    liste.scrollTop = haut;

    liste.onclick = (e) => {
      const bouton = e.target.closest(".carte-session");
      if (!bouton) return;
      // Elle est sous la souris : inutile de faire défiler la liste.
      ouvrirSession(bouton.dataset.id, { montrer: false }).catch((x) => erreur(x.message));
    };
    liste.onscroll = () => {
      if (liste.scrollTop + liste.clientHeight < liste.scrollHeight - 300) return;
      if (limite >= sessions.length) return;
      limite += PAR_PAQUET;
      ajouterCartes(liste, sessions);
    };

    $("#bascule-tri").onclick = () => {
      filtres.tri = filtres.tri === "date" ? "chrono" : "date";
      limite = PAR_PAQUET;
      barreSessions.afficher();
      $("#liste-sessions").scrollTop = 0;
    };
    $("#bascule-filtres").onclick = () => {
      filtres.ouverts = !filtres.ouverts;
      $("#panneau-filtres").hidden = !filtres.ouverts;
    };
    $("#circuit").onchange = (e) => {
      filtres.circuit = e.target.value;
      limite = PAR_PAQUET;
      barreSessions.afficher();
    };
    $("#avec-tours").onchange = (e) => {
      filtres.masquerVides = e.target.checked;
      limite = PAR_PAQUET;
      barreSessions.afficher();
    };
    $("#en-ligne").onchange = (e) => {
      filtres.enLigne = e.target.checked;
      limite = PAR_PAQUET;
      barreSessions.afficher();
    };
  },

  /**
   * Fait de cette session celle qui est surlignée, d'où qu'elle ait été ouverte.
   *
   * Une session ouverte depuis un autre onglet peut ne pas être dans la liste : trop
   * ancienne pour le paquet affiché, ou écartée par un filtre. Elle y est ramenée,
   * sinon l'écran montrerait une session qu'on ne retrouve nulle part à gauche.
   */
  marquer(id, { montrer = true } = {}) {
    etat.sessionChoisie = id;
    if (!$("#liste-sessions")) return;

    const rangDe = () => retenues().findIndex((s) => s.id === id);
    let rang = rangDe();
    const ecartee = rang < 0 && etat.sessions.some((s) => s.id === id);
    if (ecartee) {
      filtres.circuit = "";
      filtres.masquerVides = false;
      filtres.enLigne = false;
      rang = rangDe();
    }
    if (ecartee || rang >= limite) {
      limite = Math.max(limite, rang + PAR_PAQUET);
      barreSessions.afficher();
    }

    const liste = $("#liste-sessions");
    let trouvee = null;
    for (const c of liste.querySelectorAll(".carte-session")) {
      const voulue = c.dataset.id === id;
      c.classList.toggle("actif", voulue);
      if (voulue) trouvee = c;
    }
    if (trouvee && montrer) amenerEnHaut(liste, trouvee);
  },

  rafraichir() {
    if (etat.onglet === "resultats") barreSessions.afficher();
  },
};

// Le bas de la liste s'efface : une carte n'y serait pas lisible. On ne fait défiler
// que si la carte n'est pas déjà bien visible, pour ne pas bousculer la liste.
function amenerEnHaut(liste, carte) {
  const cadre = liste.getBoundingClientRect();
  const rect = carte.getBoundingClientRect();
  const lisible = cadre.top + cadre.height * PART_LISIBLE;
  if (rect.top >= cadre.top && rect.bottom <= lisible) return;
  liste.scrollTop += rect.top - cadre.top - 4;
}

/** La session la plus récente qui contient au moins un tour valide. */
export function derniereSessionUtile() {
  return etat.sessions.find((s) => s.valides > 0) || null;
}
