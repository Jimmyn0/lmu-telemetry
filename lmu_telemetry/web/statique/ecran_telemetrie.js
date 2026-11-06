// Télémétrie : deux tours superposés.
//
// Le tour de référence et le tour comparé peuvent venir de deux sessions, tant que
// c'est le même tracé. La lecture du tour déplace le curseur en temps réel : les
// deux voitures avancent alors sur la carte, et leur écart se voit.

import {
  $, api, badgeClasse, badgeType, dateCourte, erreur, etat, etatVide, fleche, navigation, nomType,
} from "/commun.js";
import { Carte } from "/carte.js";
import { COULEURS, Pile } from "/graphes.js";
import { drapeau, echapper } from "/emblemes.js";
import { chrono, circuitDe, indiceAuTemps, partsSecteurs, signe, tourVoisin } from "/format.js";
import { ICONES } from "/icones.js";
import { t, traduire } from "/i18n.js";
import { VuePiste } from "/piste.js";
import { derniereSessionUtile } from "/barre_sessions.js";

// Remarque « pris sans freiner » : affichée en étiquette dans la case du virage
// plutôt qu'en remarque. Même clé que virages.SANS_FREINER côté serveur.
const SANS_FREINER = "serveur.virage.sans_freiner";

// Nom du canal d'angle volant en degrés, calculé par donnees_tour.py. Absent
// des données quand le débattement du volant n'a pas pu être lu.
const CANAL_VOLANT = "Angle Volant";
const CANAL_GAZ_BRUT = "Throttle Pos Unfiltered";

const HAUTEUR_RANGEE = 100;

// Ce qui est affiché en ce moment. `selection` dit quels tours regarder,
// `donnees` ce que le serveur a répondu.
const vue = {
  selection: null,
  donnees: null,
  virages: null,
  pile: null,
  carte: new Carte($("#carte-fond"), $("#carte-calque")),
  route: null,
  masques: new Set(),
  secteursVisibles: true,
  sessions: new Map(),
  lecture: null,
};

// ---------------------------------------------------------------------
// Choix des tours
// ---------------------------------------------------------------------

/** Ouvre l'onglet sur ces tours. Sans `cmp`, seule la référence est affichée. */
export async function ouvrirTelemetrie(selection) {
  vue.selection = selection;
  navigation.aller("telemetrie");
  await charger();
}

async function session(chemin) {
  if (!vue.sessions.has(chemin)) {
    vue.sessions.set(chemin, await api("/api/session", { chemin }));
  }
  return vue.sessions.get(chemin);
}

async function charger() {
  arreterLecture();
  const s = vue.selection;
  afficherVide({ chargement: true });
  try {
    const [donnees] = await Promise.all([
      api("/api/comparaison", {
        ref: s.ref, tour_ref: s.tourRef, cmp: s.cmp, tour_cmp: s.tourCmp,
      }),
      session(s.ref),
      s.cmp ? session(s.cmp) : null,
    ]);
    vue.donnees = donnees;
  } catch (e) {
    afficherVide({ message: e.message });
    return;
  }
  etat.telemetrie = s;
  document.querySelector('[data-onglet="telemetrie"]').classList.add("charge");
  afficher();
}

function afficherVide({ chargement = false, message = null } = {}) {
  $("#tele-page").hidden = true;
  const cible = $("#tele-vide");
  cible.hidden = false;
  if (chargement) {
    cible.innerHTML = etatVide({ chargement: true, titre: t("tele.chargement") });
    return;
  }
  if (message) {
    cible.innerHTML = etatVide({
      icone: "avertissement", titre: t("tele.impossible"), texte: echapper(message),
    });
    return;
  }
  const derniere = derniereSessionUtile();
  cible.innerHTML = etatVide({
    titre: t("tele.vide_titre"),
    texte: t("tele.vide_texte"),
    action: derniere
      ? `<button id="dernier-tour" type="button" class="principal">${t("tele.dernier_tour")}</button>`
      : "",
  });
  const bouton = $("#dernier-tour");
  if (bouton) {
    bouton.onclick = async () => {
      const s = await session(derniere.id);
      const valides = s.tours.filter((x) => x.valide && x.chrono !== null);
      const meilleur = valides.reduce((a, b) => (a.chrono <= b.chrono ? a : b));
      const voisin = tourVoisin(s.tours, meilleur);
      await ouvrirTelemetrie({
        ref: s.id, tourRef: meilleur.numero,
        cmp: voisin ? s.id : null, tourCmp: voisin?.numero ?? null,
      });
    };
  }
}

// Une session peut être comparée à toute autre session du même tracé — une autre
// sortie à toi, ou le fichier d'un autre pilote déposé dans le dossier.
function sessionsDuTrace(trace, courante) {
  const memes = etat.sessions.filter(
    (x) => circuitDe(x) === trace && (x.valides > 0 || x.id === courante)
  );
  return memes
    .slice(0, 60)
    .map(
      (x) => `<option value="${echapper(x.id)}" ${x.id === courante ? "selected" : ""}>
        ${dateCourte(x.date)} — ${echapper(nomType(x.type))}${
          x.voiture?.modele ? ` — ${echapper(x.voiture.modele)}` : ""
        }</option>`
    )
    .join("");
}

function optionsTours(tours, choisi, meilleur) {
  return tours
    .filter((x) => x.valide || x.numero === choisi)
    .map(
      (x) => `<option value="${x.numero}" ${x.numero === choisi ? "selected" : ""}>
        ${t("tour.n", { n: x.numero })} : ${chrono(x.chrono)}${
          meilleur && x.numero === meilleur.numero ? " ★" : ""
        }</option>`
    )
    .join("");
}

function meilleurDe(tours) {
  const valides = tours.filter((x) => x.valide && x.chrono !== null);
  return valides.length ? valides.reduce((a, b) => (a.chrono <= b.chrono ? a : b)) : null;
}

function carteTour(role, tour) {
  const s = vue.selection;
  const cible = $(`#carte-${role}`);
  const chemin = role === "ref" ? s.ref : s.cmp;
  const numero = role === "ref" ? s.tourRef : s.tourCmp;

  if (!chemin) {
    const reference = vue.sessions.get(s.ref);
    const voisin = tourVoisin(reference.tours, { numero: s.tourRef, chrono: vue.donnees.reference.chrono });
    cible.classList.add("inactive");
    cible.innerHTML = `
      <div class="carte-tour-etat"><i></i>${t("tele.comparaison")} · ${t("tele.inactive")}</div>
      <div class="carte-tour-vide">
        <span>${t("tele.aucune_comparaison")}</span>
        ${voisin ? `<button id="ajouter-cmp" type="button" class="pilule">${t("tele.ajouter")}</button>` : ""}
      </div>`;
    const ajouter = $("#ajouter-cmp");
    if (ajouter) {
      ajouter.onclick = () => {
        s.cmp = s.ref;
        s.tourCmp = voisin.numero;
        charger();
      };
    }
    return;
  }

  cible.classList.remove("inactive");
  const lue = vue.sessions.get(chemin);
  const meilleur = meilleurDe(lue.tours);
  cible.innerHTML = `
    <div class="carte-tour-etat"><i></i>${
      t(role === "ref" ? "tele.reference" : "tele.comparaison")
    } · ${t("tele.active")}
      <span class="espace"></span>
      ${badgeClasse(lue.voiture.classe || lue.categorie)}${badgeType(lue.type)}
      ${role === "cmp" ? `<button type="button" class="fermer-carte" title="${t("tele.retirer")}">${ICONES.fermer}</button>` : ""}
    </div>
    <div class="carte-tour-corps">
      <div class="carte-tour-qui">
        <strong>${echapper(tour.pilote)}</strong>
        <label class="choix-session" title="${t("tele.choix_session")}">
          <span>${echapper(tour.voiture.engagement)}</span>
          <select>${sessionsDuTrace(lue.circuit, chemin)}</select>
        </label>
      </div>
      <select class="choix-tour">${optionsTours(lue.tours, numero, meilleur)}</select>
    </div>`;

  cible.querySelector(".choix-tour").onchange = (e) => {
    s[role === "ref" ? "tourRef" : "tourCmp"] = +e.target.value;
    charger();
  };
  cible.querySelector(".choix-session select").onchange = async (e) => {
    const autre = await session(e.target.value).catch((x) => erreur(x.message));
    const m = autre && meilleurDe(autre.tours);
    if (!m) return;
    s[role] = e.target.value;
    s[role === "ref" ? "tourRef" : "tourCmp"] = m.numero;
    charger();
  };
  const fermer = cible.querySelector(".fermer-carte");
  if (fermer) {
    fermer.onclick = () => {
      s.cmp = null;
      s.tourCmp = null;
      charger();
    };
  }
}

// ---------------------------------------------------------------------
// Affichage
// ---------------------------------------------------------------------

function afficher(garderZoom = false) {
  const c = vue.donnees;
  const seul = !vue.selection.cmp;
  $("#tele-vide").hidden = true;
  $("#tele-page").hidden = false;

  carteTour("ref", c.reference);
  carteTour("cmp", c.compare);
  afficherOutils();
  afficherFrise();

  const avertir = $("#avertissements");
  const messages = seul ? [] : c.avertissements;
  avertir.innerHTML = messages
    .map((a) => `<p>${ICONES.avertissement}${echapper(traduire(a))}</p>`)
    .join("");
  avertir.hidden = !messages.length;

  const zoom = garderZoom && vue.pile && vue.pile.zoome ? [vue.pile.i0, vue.pile.i1] : null;
  if (vue.pile) vue.pile.detruire();
  const pile = new Pile($("#graphiques"), c.distance, surCurseur);
  vue.pile = pile;

  const paire = (nom) => {
    const ref = {
      nom: t("tele.reference"), classe: "ref",
      valeurs: c.traces[nom].reference, couleur: COULEURS.reference,
    };
    if (seul) return [ref];
    return [ref, {
      nom: t("tele.comparaison"), classe: "cmp",
      valeurs: c.traces[nom].compare, couleur: COULEURS.compare, tirets: [5, 4],
    }];
  };

  if (!seul) {
    pile.ajouter({
      cle: "delta", titre: t("graphe.delta"), unite: "s", decimales: 3, zero: true,
      remplirZero: true, stats: false, note: t("graphe.delta_note"),
      series: [{
        nom: t("tele.ecart"), classe: "delta",
        valeurs: c.delta, couleur: COULEURS.texte, epaisseur: 1.6,
      }],
    }, HAUTEUR_RANGEE);
  }
  pile.ajouter({
    cle: "vitesse", titre: t("graphe.vitesse"), unite: "km/h", basZero: true,
    series: paire("Ground Speed"),
  }, HAUTEUR_RANGEE);
  // Le geste du pilote : l'accélérateur filtré porte aussi les coupures automatiques
  // du changement de rapport et de l'antipatinage.
  pile.ajouter({
    cle: "gaz", titre: t("graphe.accelerateur"), unite: "%", min: 0, max: 105,
    echelle: [100, 50, 0],
    series: paire(c.traces[CANAL_GAZ_BRUT] ? CANAL_GAZ_BRUT : "Throttle Pos"),
  }, HAUTEUR_RANGEE);
  pile.ajouter({
    cle: "frein", titre: t("graphe.frein"), unite: "%", min: 0, max: 105,
    echelle: [100, 50, 0],
    series: paire("Brake Pos"),
  }, HAUTEUR_RANGEE);
  // Le jeu n'enregistre le braquage qu'en pourcentage de la butée, ce qui
  // n'est pas comparable d'une voiture à l'autre. On affiche des degrés dès
  // que le débattement du volant est connu, et on retombe sur le pourcentage
  // sinon — voir donnees_tour._ajouter_volant.
  const volant = c.traces[CANAL_VOLANT] ? CANAL_VOLANT : "Steering Pos";
  pile.ajouter({
    cle: "volant", titre: t("graphe.volant"), unite: volant === CANAL_VOLANT ? "°" : "%",
    zero: true, series: paire(volant),
  }, HAUTEUR_RANGEE);
  if (c.traces.Gear) {
    pile.ajouter({
      cle: "rapport", titre: t("graphe.rapport"), series: paire("Gear"),
      escalier: true, decimales: 0, entier: true,
    }, HAUTEUR_RANGEE);
  }
  if (c.traces["Virtual Energy"]) {
    pile.ajouter({
      cle: "energie", titre: t("graphe.energie"), unite: "%", series: paire("Virtual Energy"),
    }, HAUTEUR_RANGEE);
  }
  for (const cle of vue.masques) {
    const r = pile.rangees.find((x) => x.cle === cle);
    if (r) {
      r.visible = false;
      r.rangee.hidden = true;
    }
  }
  poserSecteurs();
  pile.terminer();
  if (zoom) pile.zoomer(zoom[0], zoom[1]);

  afficherCote(seul);
  vue.carte.definir(c);
  vue.route = new VuePiste($("#vue-piste"), c.piste, COULEURS);
  $("#fenetre-piste").onchange = (e) => vue.route.regler(+e.target.value);
  vue.route.regler(+$("#fenetre-piste").value);
  $("#note-piste").textContent = t("piste.note", { largeur: c.piste.largeur.toFixed(1) });
  surCurseur(null);
  chargerVirages();
}

function poserSecteurs() {
  const c = vue.donnees;
  const { fin_s1: s1, fin_s2: s2 } = c.reference;
  if (!vue.secteursVisibles || s1 === null || s2 === null) {
    vue.pile.definirReperes([]);
    return;
  }
  const indice = (d) => (d - c.distance.debut) / c.distance.pas;
  vue.pile.definirReperes([
    { indice: indice(s1), couleur: COULEURS.secteur1 + "99" },
    { indice: indice(s2), couleur: COULEURS.secteur2 + "99" },
  ]);
}

// ---------------------------------------------------------------------
// Outils
// ---------------------------------------------------------------------

const CANAUX = [
  ["delta", "graphe.delta"],
  ["vitesse", "graphe.vitesse"],
  ["gaz", "graphe.accelerateur"],
  ["frein", "graphe.frein"],
  ["volant", "graphe.volant"],
  ["rapport", "graphe.rapport"],
  ["energie", "graphe.energie"],
];

function afficherOutils() {
  const outils = $("#outils-tele");
  const seul = !vue.selection.cmp;
  outils.innerHTML = `
    ${seul ? "" : `<button id="outil-delta" type="button" class="bouton-carre ${vue.masques.has("delta") ? "" : "allume"}"
      title="${t("tele.courbe_delta")}">${ICONES.delta}</button>`}
    <button id="outil-canaux" type="button" class="bouton-carre" title="${t("tele.choix_canaux")}">${ICONES.filtre}</button>
    <button id="outil-secteurs" type="button" class="bouton-carre ${vue.secteursVisibles ? "allume" : ""}"
      title="${t("tele.limites_secteurs")}">${ICONES.secteurs}</button>
    <button id="outil-zoom" type="button" class="bouton-carre" title="${t("comparaison.voir_tour_entier")}">${ICONES.plein}</button>
    <div id="panneau-canaux" class="panneau" hidden></div>`;

  $("#outil-secteurs").onclick = (e) => {
    vue.secteursVisibles = !vue.secteursVisibles;
    e.currentTarget.classList.toggle("allume", vue.secteursVisibles);
    poserSecteurs();
  };
  $("#outil-zoom").onclick = () => vue.pile.reinitialiser();
  const delta = $("#outil-delta");
  if (delta) {
    delta.onclick = () => {
      const visible = vue.masques.has("delta");
      if (visible) vue.masques.delete("delta");
      else vue.masques.add("delta");
      delta.classList.toggle("allume", visible);
      vue.pile.basculer("delta", visible);
    };
  }
  $("#outil-canaux").onclick = (e) => {
    e.stopPropagation();
    const panneau = $("#panneau-canaux");
    const presents = new Set(vue.pile.rangees.map((r) => r.cle));
    panneau.innerHTML = CANAUX.filter(([cle]) => presents.has(cle))
      .map(
        ([cle, titre]) => `<label class="case"><input type="checkbox" data-canal="${cle}"
          ${vue.masques.has(cle) ? "" : "checked"}> ${t(titre)}</label>`
      )
      .join("");
    panneau.hidden = !panneau.hidden;
    for (const c of panneau.querySelectorAll("input")) {
      c.onchange = () => {
        if (c.checked) vue.masques.delete(c.dataset.canal);
        else vue.masques.add(c.dataset.canal);
        vue.pile.basculer(c.dataset.canal, c.checked);
      };
    }
  };
}

document.addEventListener("click", (e) => {
  const panneau = $("#panneau-canaux");
  if (panneau && !e.target.closest("#panneau-canaux")) panneau.hidden = true;
});

// ---------------------------------------------------------------------
// Frise et lecture du tour
// ---------------------------------------------------------------------

function afficherFrise() {
  const c = vue.donnees;
  const parts = partsSecteurs(c.reference.fin_s1, c.reference.fin_s2, c.reference.longueur);
  const frise = $("#frise");
  frise.innerHTML = `
    <div class="frise-barre">${
      parts
        ? parts.map((p, i) => `<i class="secteur-${i + 1}" style="width:${p}%"></i>`).join("")
        : `<i class="secteur-1" style="width:100%"></i>`
    }</div>
    <div class="frise-noms">${
      parts ? parts.map((p, i) => `<span style="width:${p}%">S${i + 1}</span>`).join("") : ""
    }</div>
    <div class="frise-curseur" id="frise-curseur"></div>`;
  $("#temps-total").textContent = chrono(c.reference.chrono ?? c.reference.temps.at(-1));
  $("#temps-lecture").textContent = chrono(0);
  $("#lecture").innerHTML = ICONES.lecture;

  const placerDepuisSouris = (e) => {
    const rect = frise.getBoundingClientRect();
    const part = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const indice = Math.round(part * (c.distance.nombre - 1));
    vue.pile.placerCurseur(indice);
    surCurseur(indice);
  };
  frise.onmousedown = (e) => {
    placerDepuisSouris(e);
    const glisser = (m) => placerDepuisSouris(m);
    const lacher = () => {
      window.removeEventListener("mousemove", glisser);
      window.removeEventListener("mouseup", lacher);
    };
    window.addEventListener("mousemove", glisser);
    window.addEventListener("mouseup", lacher);
  };
}

function arreterLecture() {
  if (vue.lecture) cancelAnimationFrame(vue.lecture.image);
  vue.lecture = null;
  if (vue.pile) vue.pile.fige = false;
  const bouton = $("#lecture");
  if (bouton) bouton.innerHTML = ICONES.lecture;
}

function lancerLecture() {
  const c = vue.donnees;
  const temps = c.reference.temps;
  const fin = temps[temps.length - 1];
  const depart = vue.pile.indice === null ? 0 : temps[vue.pile.indice];
  const vitesse = () => +$("#vitesse-lecture").value;

  vue.pile.fige = true;
  $("#lecture").innerHTML = ICONES.pause;
  vue.lecture = { t: depart >= fin ? 0 : depart, avant: performance.now(), image: 0 };

  const avancer = (maintenant) => {
    const l = vue.lecture;
    if (!l) return;
    l.t += ((maintenant - l.avant) / 1000) * vitesse();
    l.avant = maintenant;
    if (l.t >= fin) {
      arreterLecture();
      return;
    }
    const indice = indiceAuTemps(temps, l.t);
    vue.pile.placerCurseur(indice);
    // À un instant donné, le tour comparé n'est pas au même endroit : c'est
    // l'écart entre les deux voitures, qu'on voit sur la carte.
    surCurseur(indice, indiceAuTemps(c.compare.temps, l.t), l.t);
    l.image = requestAnimationFrame(avancer);
  };
  vue.lecture.image = requestAnimationFrame(avancer);
}

$("#lecture").onclick = () => (vue.lecture ? arreterLecture() : lancerLecture());

function surCurseur(indice, indiceCompare = indice, instant = null) {
  const c = vue.donnees;
  vue.carte.placer(indice, indiceCompare);
  if (vue.route) vue.route.dessiner(indice);
  const curseur = $("#frise-curseur");
  if (!curseur) return;
  const i = indice ?? 0;
  curseur.style.left = `${(100 * i) / (c.distance.nombre - 1)}%`;
  $("#temps-lecture").textContent = chrono(instant ?? c.reference.temps[i] ?? 0);
}

// ---------------------------------------------------------------------
// Colonne de droite
// ---------------------------------------------------------------------

const MODES_CARTE = [
  ["delta", "tele.mode_delta"],
  ["vitesse", "tele.mode_vitesse"],
  ["entrees", "tele.mode_entrees"],
  ["secteurs", "tele.mode_secteurs"],
];

function afficherCote(seul) {
  const c = vue.donnees;
  const a = c.reference;
  const b = c.compare;

  $("#titre-carte").innerHTML = `${drapeau(a.pays)}<span>${echapper(a.circuit)}</span>`;
  if (seul && vue.carte.mode === "delta") vue.carte.mode = "vitesse";
  const modes = seul ? MODES_CARTE.slice(1) : MODES_CARTE;
  $("#modes-carte").innerHTML = modes
    .map(
      ([mode, cle]) => `<button type="button" data-mode="${mode}"
        class="${mode === vue.carte.mode ? "actif" : ""}">${t(cle)}<i></i></button>`
    )
    .join("");
  for (const bouton of $("#modes-carte").querySelectorAll("button")) {
    bouton.onclick = () => {
      for (const x of $("#modes-carte").children) x.classList.toggle("actif", x === bouton);
      vue.carte.definirMode(bouton.dataset.mode);
    };
  }

  const titre = (cle, tour) => `${t(cle)} · ${t("tour.n", { n: tour.numero })}`;
  // Sous deux chronos, l'écart affiché est leur différence. Le delta en bout de
  // courbe peut s'en éloigner de quelques centièmes : les deux tours n'ont jamais
  // exactement la même longueur.
  const ecart = c.ecart_chronos ?? c.ecart_final;
  $("#bloc-chronos").innerHTML = `
    <div class="duo-chronos">
      <div><small class="ref">${titre("tele.reference", a)}</small><b>${chrono(a.chrono)}</b></div>
      ${seul ? "" : `<div><small class="cmp">${titre("tele.comparaison", b)}</small><b>${chrono(b.chrono)}</b></div>`}
    </div>
    ${seul ? "" : `<div class="ecart-chronos"><small>${t("tele.comparaison_moins_reference")}</small>
      <b class="${ecart > 0 ? "cmp" : "mieux"}">${signe(ecart)} s</b></div>`}
    ${c.coherent ? "" : `<div class="note">${t("comparaison.incoherent")}</div>`}`;

  $("#bloc-secteurs").innerHTML = [0, 1, 2]
    .map((i) => {
      const x = a.secteurs[i];
      const y = b.secteurs[i];
      const ecart = x !== null && y !== null ? y - x : null;
      return `<div class="carte secteur">
        <small>S${i + 1}</small>
        <b class="ref">${x === null ? "—" : x.toFixed(3)}</b>
        ${seul ? "" : `<b class="cmp">${y === null ? "—" : y.toFixed(3)}</b>
        <em class="${ecart !== null && ecart <= 0 ? "mieux" : "cmp"}">${ecart === null ? "" : signe(ecart)}</em>`}
      </div>`;
    })
    .join("");

  const duo = (cle, nom, unite, dec = 1) => {
    const valeur = (v) => (v === null || v === undefined ? "—" : `${v.toFixed(dec)} ${unite}`);
    return `<div class="carte stat-duo"><small>${t(nom)}</small>
      <b class="ref">${valeur(a[cle])}</b>
      ${seul ? "" : `<b class="cmp">${valeur(b[cle])}</b>`}</div>`;
  };
  $("#bloc-vitesses").innerHTML =
    duo("vitesse_max", "tele.vitesse_max", "km/h") + duo("vitesse_moyenne", "tele.vitesse_moy", "km/h");
  $("#bloc-carburant").innerHTML =
    (a.carburant !== null ? duo("carburant", "tele.carburant", "L", 2) : "") +
    (a.energie !== null ? duo("energie", "tele.energie", "%", 2) : "");
}

// ---------------------------------------------------------------------
// Tableau par virage
// ---------------------------------------------------------------------

// Colonnes du tableau. `sens` dit ce qui est meilleur : +1 quand une valeur
// plus grande est meilleure (vitesse), -1 quand c'est l'inverse (coasting).
// Le freinage et le point de remise des gaz n'ont PAS de sens : freiner plus
// tard n'est pas mieux en soi, ça dépend de ce qu'on fait ensuite. L'outil
// montre l'écart, il ne le juge pas.
const COLONNES_VIRAGE = [
  { cle: "distance_freinage", titre: "virages.col.freinage_avant", unite: "m", dec: 0, sens: 0 },
  { cle: "vitesse_entree", titre: "virages.col.v_entree", unite: "km/h", dec: 0, sens: 0 },
  { cle: "duree_freinage", titre: "virages.col.duree_frein", unite: "s", dec: 2, sens: 0 },
  { cle: "frein_max", titre: "virages.col.frein_max", unite: "%", dec: 0, sens: 0 },
  { cle: "vitesse_min", titre: "virages.col.v_mini", unite: "km/h", dec: 0, sens: 1 },
  { cle: "remise_gaz", titre: "virages.col.remise_gaz", unite: "m", dec: 0, sens: 0 },
  { cle: "vitesse_sortie", titre: "virages.col.v_sortie", unite: "km/h", dec: 0, sens: 1 },
  { cle: "temps_coasting", titre: "virages.col.coasting", unite: "s", dec: 2, sens: -1 },
];

async function chargerVirages() {
  const s = vue.selection;
  $("#entete-virages").textContent = t("virages.decoupage_en_cours");
  $("#table-virages").innerHTML = "";
  let virages;
  try {
    virages = await api("/api/virages", {
      ref: s.ref, tour_ref: s.tourRef, cmp: s.cmp || s.ref, tour_cmp: s.tourCmp ?? s.tourRef,
    });
  } catch (e) {
    $("#entete-virages").textContent = e.message;
    return;
  }
  // La sélection a changé pendant la requête : cette réponse ne sert plus à rien.
  if (s !== vue.selection) return;
  vue.virages = virages;
  afficherVirages();
}

function afficherVirages() {
  const v = vue.virages;
  const seul = !vue.selection.cmp;

  const valeurs = {
    n: v.virages.length,
    ref: v.coasting_total.reference.toFixed(2),
    cmp: v.coasting_total.compare.toFixed(2),
    fichier: `<code>${echapper(v.fichier)}</code>`,
  };
  $("#entete-virages").innerHTML = seul
    ? t("virages.entete_seul", valeurs)
    : t("virages.entete", valeurs);

  const table = document.createElement("table");
  const entete = document.createElement("thead");
  entete.innerHTML =
    `<tr><th class="col-virage">${t("virages.col.virage")}</th>`
    + (seul ? "" : `<th class="nombre">${t("virages.col.temps_perdu")}<small>s</small></th>`)
    + COLONNES_VIRAGE.map(
        (col) => `<th class="nombre">${t(col.titre)}<small>${col.unite}</small></th>`
      ).join("")
    + `</tr>`;
  table.append(entete);

  const corps = document.createElement("tbody");
  for (const ligne of v.virages) {
    const tr = document.createElement("tr");
    tr.className = "cliquable";
    tr.title = t("virages.zoomer");
    const perdu = ligne.delta_zone;
    // « Pris sans freiner » est une propriété du virage, pas un incident : il
    // s'affiche comme une étiquette dans la case, et non comme une ligne de
    // remarque, qui se lirait comme un avertissement.
    const sansFrein = ligne.remarques.some((r) => r.cle === SANS_FREINER);
    let html = `<td class="col-virage"><span class="num-virage">${echapper(ligne.nom)}</span>${fleche(ligne.sens)}
        <span class="discret">${Math.round(ligne.debut)}–${Math.round(ligne.fin)} m
        · r ${Math.round(ligne.rayon_min)} m</span>
        ${sansFrein ? `<span class="etiquette">${t("virages.sans_freiner")}</span>` : ""}</td>`;
    if (!seul) {
      html += `<td class="nombre">${
        perdu === null || perdu === undefined
          ? "—"
          : `<strong class="${perdu > 0 ? "moins" : "mieux"}">${signe(perdu)}</strong>`
      }</td>`;
    }
    for (const col of COLONNES_VIRAGE) {
      const m = ligne.mesures[col.cle];
      const ref = m.reference === null ? "—" : m.reference.toFixed(col.dec);
      let ecart = "";
      if (m.ecart !== null && Math.abs(m.ecart) >= Math.pow(10, -col.dec) / 2) {
        // Vert / rouge seulement quand « mieux » a un sens.
        const classe =
          col.sens === 0 ? "neutre" : Math.sign(m.ecart) === col.sens ? "mieux" : "moins";
        ecart = `<span class="ecart ${classe}">${signe(m.ecart, col.dec)}</span>`;
      }
      html += `<td class="nombre"><span class="valeur-ref">${ref}</span>${ecart}</td>`;
    }
    tr.innerHTML = html;
    tr.onclick = () => zoomerSurVirage(ligne);
    corps.append(tr);

    // Les deux tours peuvent porter la même remarque : on ne l'écrit qu'une fois.
    const autres = [
      ...new Set(ligne.remarques.filter((r) => r.cle !== SANS_FREINER).map(traduire)),
    ];
    if (autres.length) {
      const note = document.createElement("tr");
      note.innerHTML = `<td colspan="${2 + COLONNES_VIRAGE.length}"
        class="remarque">${echapper(autres.join(" ; "))}</td>`;
      corps.append(note);
    }
  }
  table.append(corps);
  $("#table-virages").innerHTML = "";
  $("#table-virages").append(table);
}

function zoomerSurVirage(ligne) {
  if (!vue.pile) return;
  const c = vue.donnees;
  const versIndice = (d) => Math.round((d - c.distance.debut) / c.distance.pas);
  // On remonte 250 m en amont : le freinage d'un virage commence bien avant lui.
  vue.pile.zoomer(versIndice(ligne.debut - 250), versIndice(ligne.fin + 100));
  $("#graphiques").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------

/** L'onglet vient d'être affiché. */
export function surTelemetrie() {
  if (!vue.selection) {
    afficherVide();
    return;
  }
  // Les toiles n'ont pas de taille tant que l'onglet est caché.
  if (vue.donnees && vue.pile) {
    vue.pile.redessiner();
    vue.carte.dessiner();
    surCurseur(vue.pile.indice);
  }
}

export const ecranTelemetrie = {
  rafraichir() {
    if (vue.donnees && vue.selection) afficher(true);
    else if (etat.onglet === "telemetrie") afficherVide();
  },
};
