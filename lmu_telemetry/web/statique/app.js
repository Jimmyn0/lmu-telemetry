// Enchaînement des écrans et remplissage des graphiques.
//
// Trois écrans : la liste des sessions, les tours d'une session, puis la
// comparaison de deux tours. Aucun cadriciel : le besoin ne le justifie pas et
// ça garde le code lisible pour quelqu'un qui n'écrit pas du JavaScript tous
// les jours.

import { Pile, COULEURS, POLICE } from "/graphes.js";
import { VuePiste } from "/piste.js";
import { dessinerChronos } from "/chronos.js";
import { drapeau, libelleVoiture, definirLogosDisponibles, echapper } from "/emblemes.js";

const $ = (s) => document.querySelector(s);

const etat = {
  sessions: [],
  session: null,
  comparaison: null,
  pile: null,
  // Chargement des chronos en cours (tri par chrono), et ce qu'il en reste.
  chargement: null,
  attente: 0,
};

// Nom du canal d'angle volant en degrés, calculé par donnees_tour.py. Absent
// des données quand le débattement du volant n'a pas pu être lu.
const CANAL_VOLANT = "Angle Volant";

// ---------------------------------------------------------------------
// Petits utilitaires
// ---------------------------------------------------------------------

function chrono(secondes, decimales = 3) {
  if (secondes === null || secondes === undefined) return "—";
  const minutes = Math.floor(secondes / 60);
  const reste = secondes - minutes * 60;
  return `${minutes}:${reste.toFixed(decimales).padStart(decimales + 3, "0")}`;
}

function signe(v, decimales = 3) {
  if (v === null || v === undefined) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(decimales);
}

// Sens du virage, déduit du signe de la courbure de la piste. Une chicane
// change de sens en son milieu : elle a droit à son propre symbole plutôt qu'à
// une flèche qui devrait choisir un camp.
const FLECHES = {
  gauche: ["↰", "vers la gauche"],
  droite: ["↱", "vers la droite"],
  chicane: ["⇄", "chicane : la piste change de sens"],
};

function fleche(sens) {
  const f = FLECHES[sens];
  return f ? ` <span class="sens" title="${f[1]}">${f[0]}</span>` : "";
}

// Type de session en étiquette colorée. La liste des sessions donne le code
// (P, Q, R), l'écran d'une session le nom anglais lu dans le fichier.
const TYPES = { P: "Essais", Q: "Qualifs", R: "Course" };
const CODES_TYPE = { practice: "P", qualifying: "Q", qualify: "Q", race: "R" };

function codeType(type) {
  const t = String(type || "");
  return TYPES[t] ? t : CODES_TYPE[t.toLowerCase()] || null;
}

function nomType(type) {
  const code = codeType(type);
  return code ? TYPES[code] : String(type || "?");
}

function etiquetteType(type) {
  const code = codeType(type);
  return `<span class="type type-${code || "autre"}">${echapper(nomType(type))}</span>`;
}

function dateCourte(iso) {
  if (!iso) return "?";
  const d = new Date(iso);
  return d.toLocaleString("fr-FR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// Quand la fenêtre de l'outil est fermée, le serveur s'arrête mais la page
// reste affichée : sans ce message, le moindre clic échouerait sur un
// « Failed to fetch » incompréhensible.
const HORS_LIGNE =
  "L'outil ne répond plus : sa fenêtre a sans doute été fermée.\n"
  + "Relance Télémétrie LMU, puis recharge cette page (touche F5).";

async function api(route, params = {}, options = {}) {
  const url = new URL(route, location.origin);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  let reponse;
  try {
    reponse = await fetch(url, options);
  } catch {
    throw new Error(HORS_LIGNE);
  }
  let charge;
  try {
    charge = await reponse.json();
  } catch {
    throw new Error(`Réponse inattendue de l'outil (code ${reponse.status}).`);
  }
  if (!reponse.ok || charge.erreur) {
    const e = new Error(charge.erreur || "Erreur inconnue");
    e.code = charge.code;
    throw e;
  }
  return charge;
}

/** Envoie des données au serveur (seule route concernée : le dossier). */
function envoyer(route, donnees) {
  return api(route, {}, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(donnees),
  });
}

function erreur(message) {
  const bloc = $("#erreur");
  bloc.hidden = !message;
  bloc.textContent = message || "";
  // Le bloc est en bas de la page : sur un long tableau, il serait hors de vue
  // et le clic semblerait n'avoir rien fait.
  if (message) bloc.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function ecran(nom) {
  for (const id of ["dossier", "sessions", "session", "comparaison", "regularite"]) {
    $(`#ecran-${id}`).hidden = id !== nom;
  }
  $("#bloc-virages").hidden = nom !== "comparaison";
  erreur(null);
  filAriane(nom);
}

function filAriane(nom) {
  const fil = $("#fil");
  fil.innerHTML = "";
  const ajouter = (texte, action) => {
    if (fil.children.length) {
      const sep = document.createElement("span");
      sep.className = "separateur";
      sep.textContent = "›";
      fil.append(sep);
    }
    if (action) {
      const b = document.createElement("button");
      b.textContent = texte;
      b.onclick = action;
      fil.append(b);
    } else {
      const s = document.createElement("span");
      s.className = "actuel";
      s.textContent = texte;
      fil.append(s);
    }
  };
  if (nom === "dossier") {
    ajouter("Choix du dossier", null);
    return;
  }
  ajouter("Sessions", nom === "sessions" ? null : () => ecran("sessions"));
  if (nom !== "sessions" && etat.session) {
    const titre = `${etat.session.circuit} — ${dateCourte(etat.session.date)}`;
    ajouter(titre, nom === "session" ? null : () => ecran("session"));
  }
  if (nom === "comparaison") ajouter("Comparaison", null);
  if (nom === "regularite") ajouter("Régularité", null);
}

// ---------------------------------------------------------------------
// Écran 1 — les sessions
// ---------------------------------------------------------------------

// Les noms de fichiers suffisent à dresser la liste, et c'est instantané.
// Le nombre de tours et le meilleur chrono, eux, obligent à OUVRIR chaque
// session : une douzaine de secondes pour les 378 du disque. On n'analyse donc
// que les sessions réellement affichées, par paquets.
const PAR_PAQUET = 10;

// Paquet utilisé pour le tri par chrono, qui doit finir par tout ouvrir. Plus
// gros que l'affichage : chaque aller-retour a un coût fixe, et on ne rend pas
// la main entre deux fichiers.
const PAR_PAQUET_CHRONO = 25;

async function chargerSessions() {
  try {
    etat.sessions = await api("/api/sessions");
  } catch (e) {
    if (e.code === "dossier_introuvable") return choisirDossier(e.message, false);
    throw e;
  }
  etat.limite = PAR_PAQUET;
  ecran("sessions");
  remplirCircuits();
  afficherSessions();
  chargerTraces();
  afficherSource();
}

// ---------------------------------------------------------------------
// Écran 0 — le dossier de télémétrie
// ---------------------------------------------------------------------

// D'où viennent les sessions affichées, avec de quoi en changer. Chez un ami à
// qui on a passé l'outil, c'est le premier endroit où regarder si la liste ne
// ressemble pas à ce qu'il attend.
async function afficherSource() {
  const cible = $("#source-sessions");
  try {
    const etatDossier = await api("/api/dossier");
    cible.innerHTML =
      `Sessions lues dans <span class="chemin">${echapper(etatDossier.dossier)}</span>`
      + (etatDossier.impose
        ? ""
        : ` · <button type="button" class="lien" id="changer-dossier">changer de dossier</button>`);
    const bouton = $("#changer-dossier");
    if (bouton) {
      bouton.onclick = () =>
        choisirDossier("Indique un autre dossier de télémétrie.", true, etatDossier.dossier);
    }
  } catch {
    cible.textContent = "";
  }
}

function choisirDossier(message, annulable, valeur = "") {
  ecran("dossier");
  $("#message-dossier").textContent = message;
  $("#saisie-dossier").value = valeur;
  $("#erreur-dossier").hidden = true;
  $("#annuler-dossier").hidden = !annulable;
  $("#annuler-dossier").onclick = () => ecran("sessions");
  $("#saisie-dossier").focus();
}

async function validerDossier() {
  const bouton = $("#valider-dossier");
  bouton.disabled = true;
  try {
    await envoyer("/api/dossier", { dossier: $("#saisie-dossier").value });
    etat.session = null;
    await chargerSessions();
  } catch (e) {
    $("#erreur-dossier").textContent = e.message;
    $("#erreur-dossier").hidden = false;
  } finally {
    bouton.disabled = false;
  }
}

// Le TRACÉ d'une session — « Monza Curva Grande Circuit » plutôt que
// « Autodromo Nazionale Monza » — ne se lit pas dans le nom du fichier, il
// faut l'ouvrir. Le serveur les lit en tâche de fond ; on redemande jusqu'à ce
// qu'il ait fini, et la liste se précise pendant ce temps.
//
// Un échec ici n'empêche rien : sans les tracés, la liste reste utilisable,
// les variantes d'un même circuit étant simplement regroupées.
async function chargerTraces() {
  let reponse;
  try {
    reponse = await api("/api/traces");
  } catch (e) {
    return;
  }
  let change = false;
  for (const s of etat.sessions) {
    const trace = reponse.traces[s.id];
    if (trace && s.trace !== trace) {
      s.trace = trace;
      change = true;
    }
  }
  if (change) {
    remplirCircuits();
    afficherSessions();
  }
  if (reponse.restant > 0) setTimeout(chargerTraces, 1500);
}

// Ce qu'on affiche et sur quoi on filtre : le tracé dès qu'on le connaît, le
// nom du circuit en attendant.
function circuitDe(session) {
  return session.trace || session.circuit;
}

// La liste des circuits vient des sessions elles-mêmes, avec leur nombre : pas
// de table à tenir à jour, et un circuit roulé une fois apparaît tout seul.
function remplirCircuits() {
  const nombres = new Map();
  for (const s of etat.sessions) {
    const nom = circuitDe(s);
    nombres.set(nom, (nombres.get(nom) || 0) + 1);
  }
  const choix = $("#circuit");
  const garde = choix.value;
  choix.innerHTML =
    `<option value="">Tous (${etat.sessions.length})</option>` +
    [...nombres.entries()]
      .sort((a, b) => a[0].localeCompare(b[0], "fr"))
      .map(([nom, n]) => `<option value="${echapper(nom)}">${echapper(nom)} (${n})</option>`)
      .join("");
  choix.value = garde;
}

/** Sessions retenues par les filtres, avant limitation au paquet affiché. */
function sessionsFiltrees() {
  const circuit = $("#circuit").value;
  const seulementUtiles = $("#avec-tours").checked;
  return etat.sessions.filter(
    (s) =>
      (!circuit || circuitDe(s) === circuit) &&
      // Une session pas encore analysée est gardée : on ne peut pas savoir.
      (!seulementUtiles || s.valides === undefined || s.valides > 0)
  );
}

// Le tri par chrono ne peut pas se faire sur la seule liste des fichiers : le
// meilleur tour n'est connu qu'après avoir OUVERT la session. On classe donc
// avec ce qu'on a, et `completerChronos` va chercher le reste en tâche de
// fond. Une session dont on ignore encore le chrono passe à la fin plutôt que
// de sauter en tête et de faire danser la liste à chaque paquet reçu.
function ordonner(sessions) {
  if ($("#tri").value !== "chrono") return sessions;
  return [...sessions].sort((a, b) => {
    const ca = a.meilleur ?? Infinity;
    const cb = b.meilleur ?? Infinity;
    if (ca !== cb) return ca - cb;
    return (b.date || "").localeCompare(a.date || "");
  });
}

// Charge les chronos manquants du lot filtré, par paquets, en rafraîchissant
// l'affichage entre chaque. Ouvrir un fichier coûte une trentaine de
// millisecondes : sur les 388 sessions du disque, c'est une douzaine de
// secondes, d'où l'avancement affiché et le classement qui se précise au fur
// et à mesure plutôt qu'un écran figé.
async function completerChronos() {
  if ($("#tri").value !== "chrono") return;
  const jeton = Symbol("chargement");
  etat.chargement = jeton;
  let restant = sessionsFiltrees().filter((s) => s.valides === undefined);
  while (restant.length) {
    // Le filtre ou le tri a changé pendant l'attente : ce chargement-ci ne
    // sert plus à rien.
    if (etat.chargement !== jeton) return;
    etat.attente = restant.length;
    afficherSessions();
    await enrichir(restant.slice(0, PAR_PAQUET_CHRONO));
    restant = sessionsFiltrees().filter((s) => s.valides === undefined);
  }
  if (etat.chargement === jeton) {
    etat.chargement = null;
    etat.attente = 0;
    afficherSessions();
  }
}

async function enrichir(sessions) {
  const manquantes = sessions.filter((s) => s.valides === undefined);
  if (!manquantes.length) return;

  const url = new URL("/api/resumes", location.origin);
  for (const s of manquantes) url.searchParams.append("chemin", s.id);
  try {
    const reponse = await fetch(url);
    const resumes = await reponse.json();
    if (resumes.erreur) throw new Error(resumes.erreur);
    const parId = new Map(resumes.map((r) => [r.id, r]));
    for (const s of manquantes) Object.assign(s, parId.get(s.id) || { valides: 0 });
  } catch (e) {
    // Marquer quand même comme traitées, sinon on redemande en boucle.
    for (const s of manquantes) s.valides = s.valides ?? 0;
    erreur(e.message);
  }
  afficherSessions();
}

function afficherSessions() {
  const filtrees = ordonner(sessionsFiltrees());
  const affichees = filtrees.slice(0, etat.limite);

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>
    <th>Date</th><th>Circuit</th><th>Type</th><th>Voiture</th>
    <th class="nombre">Tours</th><th class="nombre">Meilleur</th><th></th>
  </tr></thead>`;
  const corps = document.createElement("tbody");

  for (const s of affichees) {
    const tr = document.createElement("tr");
    tr.className = "cliquable";
    const analysee = s.valides !== undefined;
    tr.innerHTML = `
      <td>${dateCourte(s.date)}</td>
      <td>${drapeau(s.pays)}${echapper(circuitDe(s))}</td>
      <td>${etiquetteType(s.type)}</td>
      <td class="discret voiture">${libelleVoiture(s.voiture)}</td>
      <td class="nombre">${analysee ? s.valides : "…"}</td>
      <td class="nombre">${s.meilleur ? chrono(s.meilleur) : analysee ? "—" : "…"}</td>
      <td class="remarque">${s.journal ? "⚠ non refermée" : ""}${
        s.indisponible ? "⚠ illisible" : ""
      }</td>`;
    tr.onclick = () => ouvrirSession(s.id);
    corps.append(tr);
  }
  table.append(corps);

  const cible = $("#liste-sessions");
  cible.innerHTML = "";
  if (!affichees.length) {
    cible.innerHTML = `<div class="vide">Aucune session ne correspond.</div>`;
  } else {
    cible.append(table);
  }

  const reste = filtrees.length - affichees.length;
  const total = `<span class="discret">${affichees.length} affichées sur ${filtrees.length}
       ${etat.sessions.length !== filtrees.length ? ` (${etat.sessions.length} au total)` : ""}</span>`;
  const avancement = etat.chargement
    ? `<span class="discret">Lecture des chronos… ${etat.attente} session(s)
       restante(s). Le classement se précise au fur et à mesure.</span>`
    : "";
  $("#pied-liste").innerHTML = reste
    ? `<button id="charger-plus" type="button">Charger ${Math.min(
        PAR_PAQUET,
        reste
      )} sessions de plus</button>${total}${avancement}`
    : `<span class="discret">${affichees.length} session(s) affichée(s).</span>${avancement}`;
  if (reste) {
    $("#charger-plus").onclick = () => {
      etat.limite += PAR_PAQUET;
      afficherSessions();
    };
  }

  // En tri par chrono, c'est `completerChronos` qui mène les requêtes : on ne
  // veut pas deux chargements concurrents sur les mêmes fichiers.
  if (!etat.chargement) enrichir(affichees);
}


// ---------------------------------------------------------------------
// Écran 2 — les tours d'une session
// ---------------------------------------------------------------------

async function ouvrirSession(chemin) {
  try {
    etat.session = await api("/api/session", { chemin });
  } catch (e) {
    ecran("sessions");
    return erreur(e.message);
  }
  afficherSession();
  ecran("session");
}

function afficherSession() {
  const s = etat.session;
  const valides = s.tours.filter((t) => t.valide && t.chrono !== null);
  const meilleur = valides.length
    ? valides.reduce((a, b) => (a.chrono <= b.chrono ? a : b))
    : null;

  $("#entete-session").innerHTML = `
    <div class="resume">
      <div><span class="discret">Circuit</span><br>${drapeau(s.pays)}${echapper(s.circuit)}</div>
      <div><span class="discret">Session</span><br>${etiquetteType(s.type)} ${dateCourte(s.date)}</div>
      <div class="voiture"><span class="discret">Voiture</span><br>${libelleVoiture(s.voiture)}
        <span class="discret">[${echapper(s.categorie)}]</span>
        <br><span class="discret engagement">${echapper(s.voiture.engagement)}</span></div>
      <div><span class="discret">Météo</span><br>${echapper(s.meteo)}</div>
      <div class="tuile-record"><span class="discret">Meilleur tour</span><br>
        <span class="gros record">${meilleur ? chrono(meilleur.chrono) : "—"}</span></div>
      ${s.journal ? `<div class="remarque">⚠ session non refermée par le jeu, la fin peut manquer</div>` : ""}
    </div>`;

  // Meilleur temps de chaque secteur parmi les tours valides, en violet comme
  // sur les écrans de chrono en course.
  const meilleursSecteurs = [0, 1, 2].map((i) =>
    Math.min(...valides.map((t) => t.secteurs[i] ?? Infinity))
  );

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>
    <th></th><th class="nombre">Tour</th><th class="nombre">Chrono</th>
    <th class="nombre">S1</th><th class="nombre">S2</th><th class="nombre">S3</th>
    <th class="nombre">v. min</th><th>Remarques</th>
  </tr></thead>`;
  const corps = document.createElement("tbody");

  for (const t of s.tours) {
    const tr = document.createElement("tr");
    if (!t.valide) tr.className = "invalide";
    else if (meilleur && t.numero === meilleur.numero) tr.className = "meilleur";
    const marque = !t.valide ? "✗" : meilleur && t.numero === meilleur.numero ? "★" : "✓";
    const sect = (i) => {
      if (t.secteurs[i] === null) return "—";
      const texte = t.secteurs[i].toFixed(3);
      return t.valide && t.secteurs[i] === meilleursSecteurs[i]
        ? `<span class="record">${texte}</span>`
        : texte;
    };
    tr.innerHTML = `
      <td class="marque">${marque}</td>
      <td class="nombre">${t.numero}</td>
      <td class="nombre chrono-tour">${chrono(t.chrono)}</td>
      <td class="nombre">${sect(0)}</td>
      <td class="nombre">${sect(1)}</td>
      <td class="nombre">${sect(2)}</td>
      <td class="nombre">${t.vitesse_min.toFixed(0)}</td>
      <td class="remarque">${echapper(t.remarques.join(" ; "))}</td>`;
    corps.append(tr);
  }
  table.append(corps);
  $("#liste-tours").innerHTML = "";
  $("#liste-tours").append(table);

  // Sélecteurs : par défaut le meilleur tour contre le suivant le plus proche.
  const options = (selection) =>
    s.tours
      .map(
        (t) =>
          `<option value="${t.numero}" ${t.numero === selection ? "selected" : ""}
            ${t.valide ? "" : "disabled"}>
            Tour ${t.numero} — ${chrono(t.chrono)}${t.valide ? "" : " (écarté)"}
          </option>`
      )
      .join("");

  if (!meilleur) {
    $("#choix-tours").innerHTML = `<span class="discret">
      Aucun tour valide dans cette session : il n'y a rien à comparer.</span>`;
    return;
  }

  // Le tour comparé peut venir d'une AUTRE session — une autre sortie à toi,
  // ou le fichier d'un autre pilote déposé dans le dossier. Seule contrainte :
  // le même TRACÉ, sinon la comparaison n'a pas de sens.
  //
  // Le tracé et non le circuit : « Monza Curva Grande Circuit » et
  // « Autodromo Nazionale Monza » partagent le même `TrackName` mais n'ont ni
  // la même longueur ni les mêmes virages. Une session dont le tracé n'est pas
  // encore lu est proposée d'après son nom de circuit ; si elle ne correspond
  // pas, le serveur refuse la comparaison avec un message clair.
  const memeCircuit = etat.sessions.filter((x) => circuitDe(x) === s.circuit);
  const sessionsCmp = memeCircuit
    .map(
      (x) =>
        `<option value="${x.id}" ${x.id === s.id ? "selected" : ""}>
          ${x.id === s.id ? "cette session" : dateCourte(x.date)}
          — ${echapper(nomType(x.type))}
        </option>`
    )
    .join("");

  $("#choix-tours").innerHTML = `
    <label>Référence <select id="sel-ref">${options(meilleur.numero)}</select></label>
    <label>Comparé à <select id="sel-session-cmp">${sessionsCmp}</select>
      <select id="sel-cmp"></select></label>
    <button id="lancer" class="principal">Comparer</button>
    <button id="voir-regularite" type="button">Régularité de la session</button>
    <span id="etat-cmp" class="discret"></span>`;

  $("#sel-session-cmp").onchange = () => remplirToursCompares(meilleur.numero);
  remplirToursCompares(meilleur.numero);

  $("#lancer").onclick = () =>
    lancerComparaison(
      s.id,
      +$("#sel-ref").value,
      $("#sel-session-cmp").value,
      +$("#sel-cmp").value
    );
  $("#voir-regularite").onclick = () => ouvrirRegularite(s.id);
}

/** Remplit la liste des tours de la session choisie pour la comparaison. */
async function remplirToursCompares(tourReference) {
  const chemin = $("#sel-session-cmp").value;
  const select = $("#sel-cmp");
  const etatCmp = $("#etat-cmp");
  const memeSession = chemin === etat.session.id;

  select.innerHTML = `<option>…</option>`;
  select.disabled = true;
  $("#lancer").disabled = true;
  etatCmp.textContent = memeSession ? "" : "lecture de la session…";

  let tours;
  try {
    tours = memeSession
      ? etat.session.tours
      : (await api("/api/session", { chemin })).tours;
  } catch (e) {
    etatCmp.textContent = "";
    select.innerHTML = "";
    return erreur(e.message);
  }

  const valides = tours.filter(
    (t) => t.valide && t.chrono !== null && !(memeSession && t.numero === tourReference)
  );
  if (!valides.length) {
    select.innerHTML = `<option>aucun tour valide</option>`;
    etatCmp.textContent = "Cette session ne contient aucun autre tour valide.";
    return;
  }
  select.innerHTML = valides
    .map((t) => `<option value="${t.numero}">Tour ${t.numero} — ${chrono(t.chrono)}</option>`)
    .join("");
  select.disabled = false;
  $("#lancer").disabled = false;
  etatCmp.textContent = memeSession ? "" : `${valides.length} tour(s) valide(s).`;
}

// ---------------------------------------------------------------------
// Écran 4 — la régularité
// ---------------------------------------------------------------------

async function ouvrirRegularite(chemin) {
  $("#note-regularite").textContent = "Analyse de tous les tours de la session…";
  ecran("regularite");
  try {
    etat.regularite = await api("/api/regularite", { chemin });
  } catch (e) {
    ecran("session");
    return erreur(e.message);
  }
  afficherRegularite();
}

function afficherRegularite() {
  const r = etat.regularite;

  $("#resume-regularite").innerHTML = `
    <div class="tuile-accent"><span class="discret">Tours valides</span><br>
      <span class="gros">${r.tours.length}</span></div>
    <div class="tuile-record"><span class="discret">Meilleur</span><br>
      <span class="gros record">${chrono(r.meilleur)}</span></div>
    <div class="tuile-cmp"><span class="discret">Médian</span><br>${chrono(r.median)}
      <span class="discret">(+${r.ecart_meilleur_median.toFixed(3)} s)</span></div>
    <div><span class="discret">Écart-type</span><br>${r.ecart_type.toFixed(3)} s</div>
    <div class="tuile-gain"><span class="discret">Tour idéal</span><br>
      <span class="gros mieux">${chrono(r.tour_ideal)}</span>
      <span class="discret">−${r.marge_de_regularite.toFixed(3)} s</span></div>`;

  $("#note-regularite").innerHTML =
    `Le <strong>tour idéal</strong> enchaîne tes meilleurs passages dans chaque `
    + `virage : <strong>${r.marge_de_regularite.toFixed(3)} s</strong> sous ton `
    + `meilleur tour, sans rien améliorer, juste en répétant ce que tu as déjà fait.`
    + (r.course
        ? ` <span class="moins">⚠ Session de course : trafic, stratégie et `
          + `drapeaux pèsent sur les chronos sans rien dire de ton pilotage.</span>`
        : "")
    + (r.fiable
        ? ""
        : ` <span class="moins">⚠ Seulement ${r.tours.length} tours : les `
          + `dispersions ci-dessous sont indicatives. Il en faudrait au moins `
          + `cinq pour s'y fier.</span>`);

  dessinerChronos(
    $("#graphe-chronos"),
    { tours: r.tours, meilleur: r.meilleur, median: r.median, ideal: r.tour_ideal },
    COULEURS
  );

  const sens = r.tendance < 0 ? "tu accélères" : "tu ralentis";
  $("#tendance").innerHTML = `
    <strong>Au fil de la session</strong>
    <p>${Math.abs(r.tendance) < 0.01
        ? "Tes chronos ne dérivent pas : la droite ajustée est plate."
        : `<strong>${signe(r.tendance)} s par tour</strong> — en moyenne, ${sens}
           au fil de la session.`}</p>
    <p>Première moitié ${chrono(r.moitie_debut)}, seconde ${chrono(r.moitie_fin)}
       <span class="discret">(médianes)</span>.</p>
    <p class="discret">C'est une description, pas une explication : usure des
       pneus, baisse de carburant et apprentissage s'y mélangent.</p>`;

  afficherClassement();
}

function afficherClassement() {
  const r = etat.regularite;
  const maximum = Math.max(...r.virages.map((v) => v.dispersion), 0.001);

  const table = document.createElement("table");
  table.innerHTML = `<thead><tr>
    <th class="rang"></th><th>Virage</th>
    <th class="nombre">Passage habituel</th>
    <th class="nombre">Dispersion</th>
    <th class="nombre">À gagner</th>
    <th class="nombre">Point de freinage</th>
    <th class="nombre">Vitesse mini</th>
    <th></th></tr></thead>`;
  const corps = document.createElement("tbody");

  r.virages.forEach((v, i) => {
    const tr = document.createElement("tr");
    const largeur = Math.round(60 * (v.dispersion / maximum));
    tr.innerHTML = `
      <td class="rang rang-${i + 1}"><span>${i + 1}</span></td>
      <td><span class="num-virage">${echapper(v.nom)}</span>${fleche(v.sens)} <span class="discret">${Math.round(v.debut)}–${Math.round(v.fin)} m</span></td>
      <td class="nombre">${v.temps_median.toFixed(3)} s</td>
      <td class="nombre">±${v.dispersion.toFixed(3)} s
        <span class="barre-dispersion" style="width:${largeur}px"></span></td>
      <td class="nombre">${v.potentiel.toFixed(3)} s</td>
      <td class="nombre">${
        v.dispersion_freinage === null ? "—" : "±" + v.dispersion_freinage.toFixed(1) + " m"
      }</td>
      <td class="nombre">±${v.dispersion_vitesse_min.toFixed(1)} km/h</td>
      <td class="remarque">${
        v.passage_aberrant
          ? `un passage isolé pèse lourd (tour ${v.tour_le_plus_lent}) — incident, pas irrégularité`
          : ""
      }</td>`;
    corps.append(tr);
  });
  table.append(corps);
  $("#classement-virages").innerHTML = "";
  $("#classement-virages").append(table);
}

// ---------------------------------------------------------------------
// Écran 3 — la comparaison
// ---------------------------------------------------------------------

async function lancerComparaison(ref, tourRef, cmp, tourCmp) {
  etat.refComparaison = { ref, tourRef, cmp, tourCmp };
  try {
    etat.comparaison = await api("/api/comparaison", {
      ref, tour_ref: tourRef, cmp, tour_cmp: tourCmp,
    });
  } catch (e) {
    return erreur(e.message);
  }
  ecran("comparaison");
  afficherComparaison();
}

function afficherComparaison() {
  const c = etat.comparaison;
  const t = c.traces;

  $("#resume-comparaison").innerHTML = `
    <div class="tuile-ref"><span class="discret">Référence</span><br>
      <span class="tour-ref">Tour ${c.reference.numero}</span> — ${chrono(c.reference.chrono)}</div>
    <div class="tuile-cmp"><span class="discret">Comparé</span><br>
      <span class="tour-cmp">Tour ${c.compare.numero}</span> — ${chrono(c.compare.chrono)}</div>
    <div class="${c.ecart_final > 0 ? "tuile-perte" : "tuile-gain"}"><span class="discret">Écart final</span><br>
      <span class="gros" style="color:${c.ecart_final > 0 ? "var(--perte)" : "var(--gain)"}">
        ${signe(c.ecart_final)} s</span></div>
    <div class="remarque">${c.coherent ? "" : "⚠ le delta ne retombe pas sur la différence des chronos"}</div>`;

  const avertir = $("#avertissements");
  avertir.innerHTML = c.avertissements.map((a) => `<p>⚠ ${echapper(a)}</p>`).join("");
  avertir.hidden = !c.avertissements.length;

  if (etat.pile) etat.pile.detruire();
  const pile = new Pile($("#graphiques"), c.distance, majLecture, majEtendue);
  etat.pile = pile;
  $("#reset-zoom").onclick = () => pile.reinitialiser();

  const paire = (nom) => [
    { valeurs: t[nom].reference, couleur: COULEURS.reference },
    { valeurs: t[nom].compare, couleur: COULEURS.compare },
  ];

  pile.ajouter(
    {
      titre: "Delta cumulé — le tour comparé perd du temps quand la courbe monte",
      unite: "s",
      series: [{ valeurs: c.delta, couleur: COULEURS.texte, epaisseur: 1.6 }],
      zero: true,
      remplirZero: true,
    },
    170
  );
  pile.ajouter({ titre: "Vitesse", unite: "km/h", series: paire("Ground Speed") }, 150);
  pile.ajouter(
    {
      titre: "Frein",
      unite: "%",
      series: paire("Brake Pos"),
      min: 0,
      max: 105,
    },
    110
  );
  pile.ajouter(
    {
      titre: "Accélérateur",
      unite: "%",
      series: paire("Throttle Pos"),
      min: 0,
      max: 105,
    },
    110
  );
  // Le jeu n'enregistre le braquage qu'en pourcentage de la butée, ce qui
  // n'est pas comparable d'une voiture à l'autre. On affiche des degrés dès
  // que le débattement du volant est connu, et on retombe sur le pourcentage
  // sinon — voir donnees_tour._ajouter_volant.
  const volant = t[CANAL_VOLANT] ? CANAL_VOLANT : "Steering Pos";
  pile.ajouter(
    {
      titre: "Angle volant",
      unite: volant === CANAL_VOLANT ? "°" : "%",
      series: paire(volant),
    },
    110
  );
  if (t["Gear"]) {
    pile.ajouter(
      { titre: "Rapport", series: paire("Gear"), escalier: true, decimales: 0, entier: true },
      // Plus haut que les autres : ce graphique porte l'axe des distances, qui
      // lui prend 20 px, et son échelle entière compte sept graduations.
      145
    );
  }
  pile.terminer();

  preparerVuePiste();
  preparerCarte();
  majLecture(null);
  chargerVirages();
}

// Rappel de la pile à chaque changement de zoom : on affiche la portion de
// circuit visible, sinon on ne sait plus où l'on est une fois zoomé.
function majEtendue(i0, i1) {
  const c = etat.comparaison;
  const d0 = c.distance.debut + i0 * c.distance.pas;
  const d1 = c.distance.debut + i1 * c.distance.pas;
  const total = c.distance.nombre - 1;
  const entier = i0 === 0 && i1 === total;
  $("#reset-zoom").disabled = entier;
  $("#etendue").textContent = entier
    ? `Tour entier — ${Math.round(d1)} m`
    : `Affiché : ${Math.round(d0)} → ${Math.round(d1)} m  (${Math.round(d1 - d0)} m sur ${Math.round(
        c.distance.pas * total
      )})`;
}

function preparerVuePiste() {
  const c = etat.comparaison;
  etat.vuePiste = new VuePiste($("#vue-piste"), c.piste, COULEURS);
  $("#fenetre-piste").onchange = (e) => etat.vuePiste.regler(+e.target.value);
  etat.vuePiste.regler(+$("#fenetre-piste").value);

  const p = c.piste;
  $("#note-piste").textContent =
    `Largeur mesurée ${p.largeur.toFixed(1)} m en moyenne. Chaque bord est en `
    + `trait plein là où un des deux tours l'a longé, en pointillé ailleurs — il y `
    + `est estimé à partir de ses mesures d'avant et d'après.`;
}

// Libellés courts : la colonne fait moins de cent pixels, « Accélérateur » et
// « Angle volant » y étaient tronqués.
//
// La ligne du volant dépend de la voiture : en degrés si le débattement est
// connu, en pourcentage sinon. Les deux canaux coexistent dans les données —
// on n'en affiche qu'un, sinon la même information apparaîtrait deux fois.
function lignesLecture(traces) {
  const volant = traces[CANAL_VOLANT]
    ? ["Volant", CANAL_VOLANT, "°", 0]
    : ["Volant", "Steering Pos", "%", 1];
  return [
    ["Vitesse", "Ground Speed", "km/h", 0],
    ["Frein", "Brake Pos", "%", 0],
    ["Gaz", "Throttle Pos", "%", 0],
    volant,
    ["Rapport", "Gear", "", 0],
  ];
}

// Le tableau de lecture est TOUJOURS dessiné en entier, rempli de tirets tant
// que la souris n'est sur aucun graphique. Une case qui change de hauteur au
// survol pousserait tout le reste de la colonne vers le bas à chaque
// mouvement : le tableau garde donc sa taille, seules les valeurs changent.
function majLecture(indice) {
  const c = etat.comparaison;
  const lignes = lignesLecture(c.traces).filter(([, cle]) => c.traces[cle]);
  const survol = indice !== null;

  const corps = lignes
    .map(([titre, cle, unite, dec]) => {
      const a = survol ? c.traces[cle].reference[indice] : null;
      const b = survol ? c.traces[cle].compare[indice] : null;
      const ecart = a === null || b === null ? null : b - a;
      // L'unité va dans le libellé, pas dans la cellule d'écart : répétée à
      // droite, elle élargissait la colonne et faisait replier les valeurs.
      return `<tr>
        <td class="discret">${titre}<span class="unite">${unite}</span></td>
        <td class="nombre tour-ref">${a === null ? "—" : a.toFixed(dec)}</td>
        <td class="nombre tour-cmp">${b === null ? "—" : b.toFixed(dec)}</td>
        <td class="nombre discret">${ecart === null ? "" : signe(ecart, dec)}</td>
      </tr>`;
    })
    .join("");

  // Titre court et sur une seule ligne : « 2 298 m depuis la ligne · delta
  // +0,879 s » se repliait en deux lignes dans la colonne, ce qui suffisait à
  // faire bouger tout ce qui est en dessous.
  const titre = survol
    ? `<strong>${Math.round(c.distance.debut + indice * c.distance.pas)} m</strong>`
      + `<span class="discret"> · delta ${signe(c.delta[indice])} s</span>`
    : `<span class="discret">Passe la souris sur un graphique</span>`;

  $("#lecture").innerHTML = `
    <div class="titre-lecture">${titre}</div>
    <table><thead><tr>
      <th></th><th class="nombre tour-ref">réf.</th>
      <th class="nombre tour-cmp">comp.</th><th class="nombre"></th>
    </tr></thead><tbody>${corps}</tbody></table>`;

  dessinerCarte(indice);
  if (etat.vuePiste) etat.vuePiste.dessiner(indice);
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
  { cle: "distance_freinage", titre: "Freinage avant", unite: "m", dec: 0, sens: 0 },
  { cle: "vitesse_entree", titre: "V. entrée", unite: "km/h", dec: 0, sens: 0 },
  { cle: "duree_freinage", titre: "Durée frein", unite: "s", dec: 2, sens: 0 },
  { cle: "frein_max", titre: "Frein max", unite: "%", dec: 0, sens: 0 },
  { cle: "vitesse_min", titre: "V. mini", unite: "km/h", dec: 0, sens: 1 },
  { cle: "remise_gaz", titre: "Remise gaz", unite: "m", dec: 0, sens: 0 },
  { cle: "vitesse_sortie", titre: "V. sortie", unite: "km/h", dec: 0, sens: 1 },
  { cle: "temps_coasting", titre: "Sur l'erre", unite: "s", dec: 2, sens: -1 },
];

async function chargerVirages() {
  const c = etat.comparaison;
  const bloc = $("#bloc-virages");
  bloc.hidden = false;
  $("#entete-virages").textContent = "Découpage du circuit en cours…";
  $("#table-virages").innerHTML = "";
  try {
    etat.virages = await api("/api/virages", {
      ref: etat.refComparaison.ref,
      tour_ref: etat.refComparaison.tourRef,
      cmp: etat.refComparaison.cmp,
      tour_cmp: etat.refComparaison.tourCmp,
    });
  } catch (e) {
    $("#entete-virages").textContent = "";
    bloc.hidden = true;
    return erreur(e.message);
  }
  afficherVirages();
  // La carte est dessinée avant que le découpage soit connu : on la redessine
  // pour y poser les numéros de virage.
  dessinerCarte(null);
}

function afficherVirages() {
  const v = etat.virages;
  const c = etat.comparaison;

  $("#entete-virages").innerHTML =
    `${v.virages.length} virages, détectés sur la courbure de la piste. `
    + `« Temps perdu » répartit l'écart du tour sur les virages : chaque mètre `
    + `compte pour un virage et un seul, la colonne totalise donc exactement `
    + `l'écart final. La frontière est posée au milieu de chaque ligne droite. `
    + `Sur l'erre, ni frein ni gaz : `
    + `<strong>${v.coasting_total.reference.toFixed(2)} s</strong> pour la référence `
    + `contre <strong>${v.coasting_total.compare.toFixed(2)} s</strong> pour le tour comparé. `
    + `Clique sur une ligne pour zoomer les graphiques dessus. `
    + `Découpage modifiable : <code>${echapper(v.fichier)}</code>`;

  const table = document.createElement("table");
  const entete = document.createElement("thead");
  entete.innerHTML =
    `<tr><th class="col-virage">Virage</th>`
    + `<th class="nombre groupe">Temps perdu<br><span class="discret">s</span></th>`
    + COLONNES_VIRAGE.map(
        (col) => `<th class="nombre groupe">${col.titre}<br>
          <span class="discret">${col.unite}</span></th>`
      ).join("")
    + `</tr>`;
  table.append(entete);

  const corps = document.createElement("tbody");
  for (const ligne of v.virages) {
    const tr = document.createElement("tr");
    tr.className = "cliquable";
    tr.title = "Zoomer les graphiques sur ce virage";
    // Une seule ligne : le numéro, puis les bornes et le rayon en petit.
    // L'ancienne version empilait le tout sur deux lignes et laissait une
    // grande colonne vide.
    const perdu = ligne.delta_zone;
    // « Pris sans freiner » est une propriété du virage, pas un incident : il
    // s'affiche comme une étiquette dans la case, et non comme une ligne de
    // remarque, qui se lirait comme un avertissement.
    const sansFrein = ligne.remarques.includes("pris sans freiner");
    let html = `<td class="col-virage"><span class="num-virage">${echapper(ligne.nom)}</span>${fleche(ligne.sens)}
        <span class="discret">${Math.round(ligne.debut)}–${Math.round(ligne.fin)} m
        · r ${Math.round(ligne.rayon_min)} m</span>
        ${sansFrein ? '<span class="etiquette">sans freiner</span>' : ""}</td>
      <td class="nombre groupe">${
        perdu === null || perdu === undefined
          ? "—"
          : `<strong class="${perdu > 0 ? "moins" : "mieux"}">${signe(perdu)}</strong>`
      }</td>`;
    for (const col of COLONNES_VIRAGE) {
      const m = ligne.mesures[col.cle];
      const ref = m.reference === null ? "—" : m.reference.toFixed(col.dec);
      let ecart = "";
      if (m.ecart !== null && Math.abs(m.ecart) >= Math.pow(10, -col.dec) / 2) {
        // Vert / rouge seulement quand « mieux » a un sens.
        const classe =
          col.sens === 0
            ? "neutre"
            : Math.sign(m.ecart) === col.sens
            ? "mieux"
            : "moins";
        ecart = `<br><span class="ecart ${classe}">${signe(m.ecart, col.dec)}</span>`;
      }
      html += `<td class="nombre groupe"><span class="tour-ref">${ref}</span>${ecart}</td>`;
    }
    tr.innerHTML = html;
    tr.onclick = () => zoomerSurVirage(ligne);
    corps.append(tr);

    const autres = [...new Set(ligne.remarques)].filter(
      (r) => r !== "pris sans freiner"
    );
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
  if (!etat.pile) return;
  const c = etat.comparaison;
  const versIndice = (d) => Math.round((d - c.distance.debut) / c.distance.pas);
  // On remonte 250 m en amont : le freinage d'un virage commence bien avant lui.
  etat.pile.zoomer(versIndice(ligne.debut - 250), versIndice(ligne.fin + 100));
  $("#graphiques").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------
// Carte du circuit
// ---------------------------------------------------------------------

// Taille des pastilles de numéro, en proportion du côté de la carte. Elles
// étaient d'abord en pixels fixes ; sur la carte réelle, qui fait moins de
// 300 px de côté, trois pastilles voisines se recouvraient entièrement.
const PART_RAYON_PASTILLE = 1 / 26;
const PART_RECUL_PASTILLE = 1 / 18;
const RAYON_PASTILLE_MIN = 7;
const RAYON_PASTILLE_MAX = 11;

let carte = null;

function preparerCarte() {
  const c = etat.comparaison;
  const lat = c.traces["GPS Latitude"];
  const lon = c.traces["GPS Longitude"];
  const canvas = $("#carte");
  if (!lat || !lon) {
    canvas.hidden = true;
    carte = null;
    return;
  }
  canvas.hidden = false;

  // Les coordonnées du jeu sont locales et fictives ; seule la forme compte.
  // Le cos(latitude) garde les bonnes proportions entre les deux axes.
  const moyenneLat = lat.reference.reduce((a, b) => a + b, 0) / lat.reference.length;
  const k = Math.cos((moyenneLat * Math.PI) / 180);
  const xs = lon.reference.map((v) => v * k);
  const ys = lat.reference.map((v) => -v);
  carte = {
    xs, ys,
    x0: Math.min(...xs), x1: Math.max(...xs),
    y0: Math.min(...ys), y1: Math.max(...ys),
  };
  dessinerCarte(null);
}

function dessinerCarte(indice) {
  if (!carte) return;
  const c = etat.comparaison;
  const canvas = $("#carte");
  const ctx = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const cote = canvas.clientWidth;
  canvas.width = cote * ratio;
  canvas.height = cote * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, cote, cote);

  // La marge doit loger les pastilles de numéro, qui débordent du tracé de
  // leur décalage plus leur rayon — sinon celles des virages situés au bord de
  // la carte sont coupées.
  const pastille = tailles(cote);
  const marge = pastille.recul + pastille.rayon + 2;
  const echelle = Math.min(
    (cote - 2 * marge) / (carte.x1 - carte.x0 || 1),
    (cote - 2 * marge) / (carte.y1 - carte.y0 || 1)
  );
  const largeur = (carte.x1 - carte.x0) * echelle;
  const hauteur = (carte.y1 - carte.y0) * echelle;
  const px = (i) => (carte.xs[i] - carte.x0) * echelle + (cote - largeur) / 2;
  const py = (i) => (carte.ys[i] - carte.y0) * echelle + (cote - hauteur) / 2;

  // Le tracé est coloré par la pente locale du delta : rouge là où le tour
  // comparé perd, vert là où il gagne. C'est la même information que le
  // graphique de delta, posée sur le circuit.
  const fenetre = Math.max(2, Math.round(25 / c.distance.pas));
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  for (let i = 1; i < carte.xs.length; i++) {
    const avant = c.delta[Math.max(0, i - fenetre)];
    const apres = c.delta[Math.min(c.delta.length - 1, i + fenetre)];
    const pente = apres - avant;
    const force = Math.min(1, Math.abs(pente) / 0.05);
    ctx.strokeStyle =
      force < 0.15
        ? COULEURS.traceNeutre
        : pente > 0
        ? transparence(COULEURS.perte, 0.35 + 0.65 * force)
        : transparence(COULEURS.gain, 0.35 + 0.65 * force);
    ctx.beginPath();
    ctx.moveTo(px(i - 1), py(i - 1));
    ctx.lineTo(px(i), py(i));
    ctx.stroke();
  }

  numeroterVirages(ctx, px, py, cote);

  if (indice !== null && indice < carte.xs.length) {
    ctx.fillStyle = COULEURS.curseur;
    ctx.strokeStyle = COULEURS.accent;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(px(indice), py(indice), 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
}

/** Une couleur #rrggbb de la palette, rendue plus ou moins transparente. */
function transparence(couleur, opacite) {
  return couleur + Math.round(opacite * 255).toString(16).padStart(2, "0");
}

// Numéro de chaque virage, posé sur la carte du circuit.
//
// La pastille va vers l'EXTÉRIEUR du virage, sinon elle se pose sur le tracé
// et le cache. L'extérieur se déduit de la courbe DESSINÉE, pas du sens du
// virage : le centre de courbure est du côté vers lequel la trajectoire
// accélère, donc l'extérieur est du côté opposé. Ça évite d'avoir à raisonner
// sur l'orientation des axes de la carte, où le Y descend.
function tailles(cote) {
  const rayon = Math.max(
    RAYON_PASTILLE_MIN,
    Math.min(RAYON_PASTILLE_MAX, cote * PART_RAYON_PASTILLE)
  );
  return { rayon, recul: Math.max(2.2 * rayon, cote * PART_RECUL_PASTILLE) };
}

// Le point est-il à l'intérieur du tracé ? Le circuit est une boucle fermée :
// on peut donc le traiter comme un polygone et compter les intersections d'une
// demi-droite partant du point. Nombre impair : dedans.
//
// Sert à garantir qu'aucun numéro ne se retrouve DANS le circuit. L'extérieur
// d'un virage, au sens de sa courbure, ne suffit pas : dans une chicane les
// deux apex tournent en sens opposés, donc l'extérieur de l'un pointe
// forcément vers l'intérieur de la boucle.
function dansLeCircuit(x, y, px, py) {
  const n = carte.xs.length;
  // Un point sur deux suffit largement pour un test d'appartenance, et divise
  // le coût par deux sur un tour de 5 800 points.
  const pas = 2;
  let dedans = false;
  let jx = px(n - 1);
  let jy = py(n - 1);
  for (let i = 0; i < n; i += pas) {
    const ix = px(i);
    const iy = py(i);
    if (iy > y !== jy > y && x < ((jx - ix) * (y - iy)) / (jy - iy) + ix) {
      dedans = !dedans;
    }
    jx = ix;
    jy = iy;
  }
  return dedans;
}

// Direction pointant vers l'EXTÉRIEUR d'un virage, dans les coordonnées
// brutes de la carte.
//
// On la calcule sur la CORDE du virage, pas sur une dérivée seconde locale.
// Première version essayée : la somme des deux cordes autour du sommet, en
// coordonnées écran. Elle marchait sur une carte de mille pixels et pas sur
// celle de la page : la flèche d'un virage de 200 m de rayon vue sur 20 m ne
// fait que 25 cm, soit un centième de pixel une fois le circuit ramené à
// 290 px. Le calcul tombait sous le seuil de bruit et le code se rabattait sur
// « un côté au hasard » — d'où des numéros à l'intérieur du circuit.
//
// La corde, elle, ne dépend pas de l'échelle : un arc s'écarte toujours de sa
// corde du côté OPPOSÉ à son centre. Le vecteur qui va du milieu de la corde
// au sommet du virage pointe donc vers l'extérieur, quelle que soit la taille
// du virage et quelle que soit celle de la carte.
function versExterieur(debut, sommet, fin) {
  const dernier = carte.xs.length - 1;
  const a = Math.max(0, Math.min(dernier, debut));
  const b = Math.max(0, Math.min(dernier, fin));
  const s = Math.max(0, Math.min(dernier, sommet));

  let vx = carte.xs[s] - (carte.xs[a] + carte.xs[b]) / 2;
  let vy = carte.ys[s] - (carte.ys[a] + carte.ys[b]) / 2;
  let norme = Math.hypot(vx, vy);
  if (norme < 1e-9) {
    // Portion sans courbure mesurable : on se rabat sur la perpendiculaire.
    vx = carte.ys[b] - carte.ys[a];
    vy = carte.xs[a] - carte.xs[b];
    norme = Math.hypot(vx, vy) || 1;
  }
  return { x: vx / norme, y: vy / norme };
}

// Distance du point au tracé le plus proche. Un point sur trois suffit : le
// tracé est échantillonné au mètre, soit une fraction de pixel sur la carte.
function distanceAuTrace(x, y, px, py) {
  let mini = Infinity;
  for (let i = 0; i < carte.xs.length; i += 3) {
    const d = Math.hypot(px(i) - x, py(i) - y);
    if (d < mini) mini = d;
  }
  return mini;
}

// Positions déjà calculées, avec ce qui les rend valides. Le placement coûte
// cher — appartenance au polygone et distance au tracé, sur des milliers de
// points, pour douze emplacements par virage — et `dessinerCarte` est rappelée
// à CHAQUE mouvement de souris sur un graphique. Sans ce cache, la Sarthe et
// ses 29 virages faisaient ramer la page.
let pastilles = null;

// Directions essayées pour poser une pastille, en degrés depuis l'extérieur du
// virage. L'axe d'abord, puis de part et d'autre par écarts croissants.
const ANGLES_PASTILLE = [0, 25, -25, 50, -50, 75, -75, 105, -105, 140, -140, 180];

// Deux segments se croisent-ils ? Sert à empêcher les traits de rappel de se
// couper : quand ils se croisent, on lit les numéros dans le désordre.
function seCroisent(a, b, c, d) {
  const cote = (p, q, r) =>
    Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x));
  const c1 = cote(a, b, c);
  const c2 = cote(a, b, d);
  const c3 = cote(c, d, a);
  const c4 = cote(c, d, b);
  return c1 !== c2 && c3 !== c4;
}

function placerPastilles(px, py, cote) {
  const liste = etat.virages.virages;
  if (
    pastilles &&
    pastilles.cote === cote &&
    pastilles.liste === liste &&
    pastilles.xs === carte.xs
  ) {
    return pastilles.positions;
  }

  const c = etat.comparaison;
  const { rayon, recul } = tailles(cote);
  const indice = (d) => Math.round((d - c.distance.debut) / c.distance.pas);
  // Les points d'ancrage de TOUS les virages, connus avant de placer quoi que
  // ce soit : une pastille doit finir plus près du sien que de n'importe quel
  // autre, sinon on la rattache mentalement au mauvais virage.
  const ancres = liste
    .map((v) => indice((v.debut + v.fin) / 2))
    .filter((i) => i >= 0 && i <= carte.xs.length - 1)
    .map((i) => ({ x: px(i), y: py(i) }));

  const positions = [];
  const posees = [];
  for (const v of liste) {
    const s = indice((v.debut + v.fin) / 2);
    if (s < 0 || s > carte.xs.length - 1) continue;
    const mien = { x: px(s), y: py(s) };
    // Sens de la marche à cet endroit, pour ranger les numéros dans l'ordre.
    const avant = Math.max(0, s - 5);
    const apres = Math.min(carte.xs.length - 1, s + 5);
    const tx = px(apres) - px(avant);
    const ty = py(apres) - py(avant);
    const long = Math.hypot(tx, ty) || 1;
    const marche = { x: tx / long, y: ty / long };
    const precedente = posees[posees.length - 1];
    const dehors = versExterieur(indice(v.debut), s, indice(v.fin));

    // Placement : on cherche TOUT AUTOUR du virage, pas seulement le long de
    // son axe extérieur.
    //
    // Version précédente : la pastille ne pouvait s'écarter que sur cet axe,
    // dans un sens ou dans l'autre. Quand il était encombré, elle partait donc
    // très loin au lieu de se décaler de quelques pixels sur le côté — le
    // numéro 5 de Monza finissait à l'autre bout de la carte, contre le 7.
    //
    // On essaie donc plusieurs directions autour de l'extérieur du virage, à
    // quelques distances, et on note chaque emplacement selon quatre critères.
    let x = px(s) + dehors.x * recul;
    let y = py(s) + dehors.y * recul;
    let meilleure = -Infinity;
    for (const angle of ANGLES_PASTILLE) {
      const a = (angle * Math.PI) / 180;
      const dx = dehors.x * Math.cos(a) - dehors.y * Math.sin(a);
      const dy = dehors.x * Math.sin(a) + dehors.y * Math.cos(a);
      for (let n = 0; n < 3; n++) {
        const d = recul + n * 1.7 * rayon;
        const cx = px(s) + dx * d;
        const cy = py(s) + dy * d;
        if (cx < rayon + 1 || cx > cote - rayon - 1) continue;
        if (cy < rayon + 1 || cy > cote - rayon - 1) continue;

        // 1. Être dans la boucle du circuit coûte plus cher que tout le reste
        //    réuni : c'est le défaut le plus visible.
        let note = dansLeCircuit(cx, cy, px, py) ? -1000 : 0;

        // 2. Il faut dégager le tracé — mais seulement le dégager. Récompenser
        //    l'éloignement au-delà envoyait les pastilles au loin.
        const marge = distanceAuTrace(cx, cy, px, py) - rayon;
        note += marge < 2 ? 12 * marge : 24 + Math.min(marge, 8);

        // 3. Ne pas recouvrir une pastille déjà posée. Les trois virages de la
        //    Variante Ascari tiennent en 250 m, soit six pixels sur la carte.
        for (const p of posees) {
          const gene = 2.15 * rayon - Math.hypot(p.x - cx, p.y - cy);
          if (gene > 0) note -= 30 * gene;
        }

        // 4. Rester près de SON virage, et si possible dans l'axe. Sans ces
        //    deux pénalités, une pastille gênée s'éloigne au lieu de se serrer.
        note -= 1.2 * (d - recul);
        note -= 0.10 * Math.abs(angle);

        // 5. Ne pas se rapprocher d'un AUTRE virage plus que du sien. C'est ce
        //    qui manquait : le numéro 5 de Monza se posait contre le 7, et on
        //    ne savait plus lequel désignait quoi.
        const aMoi = Math.hypot(mien.x - cx, mien.y - cy);
        for (const autre of ancres) {
          if (autre.x === mien.x && autre.y === mien.y) continue;
          const ecart = aMoi - Math.hypot(autre.x - cx, autre.y - cy);
          if (ecart > 0) note -= 3 * ecart;
        }

        // 6. Ne pas croiser le trait de rappel d'une pastille déjà posée. Deux
        //    traits qui se coupent, ce sont deux numéros échangés : à Monza,
        //    le 1 se retrouvait au-dessus du 2 alors qu'il vient avant sur la
        //    piste.
        const ici = { x: cx, y: cy };
        for (const p of posees) {
          if (seCroisent(mien, ici, p.ancre, p)) note -= 60;
        }

        // 7. Deux virages qui se suivent de près partagent presque le même
        //    point sur la carte — les deux moitiés d'une chicane sont à trois
        //    pixels l'une de l'autre. Rien n'impose alors l'ordre des numéros,
        //    et on lisait « 2 » avant « 1 ». On demande donc que le numéro
        //    suivant soit posé plus loin DANS LE SENS DE LA MARCHE.
        if (
          precedente &&
          Math.hypot(precedente.ancre.x - mien.x, precedente.ancre.y - mien.y) <
            4 * rayon
        ) {
          const avance =
            (cx - precedente.x) * marche.x + (cy - precedente.y) * marche.y;
          if (avance < 0) note -= 25 - avance;
        }

        if (note > meilleure) {
          meilleure = note;
          x = cx;
          y = cy;
        }
      }
    }
    // Deux virages collés sur la carte : si le numéro suivant se retrouve
    // malgré tout EN ARRIÈRE du précédent, on échange les deux pastilles.
    //
    // Les replacer ne marche pas — remonter le second le ferait chevaucher un
    // troisième — mais comme les deux ancres sont à quelques pixels l'une de
    // l'autre, les deux emplacements conviennent aussi bien à l'un qu'à
    // l'autre. Constaté à Monza : le 1 se posait au-dessus du 2 alors qu'il
    // vient avant sur la piste.
    if (
      precedente &&
      Math.hypot(precedente.ancre.x - mien.x, precedente.ancre.y - mien.y) <
        4 * rayon &&
      (x - precedente.x) * marche.x + (y - precedente.y) * marche.y < 0
    ) {
      const derniere = positions[positions.length - 1];
      const ancienne = { x: precedente.x, y: precedente.y };
      precedente.x = x;
      precedente.y = y;
      derniere.x = x;
      derniere.y = y;
      x = ancienne.x;
      y = ancienne.y;
    }

    posees.push({ x, y, ancre: mien });
    positions.push({ numero: v.numero, x, y, ancreX: mien.x, ancreY: mien.y });
  }

  pastilles = { cote, liste, xs: carte.xs, positions };
  return positions;
}

function numeroterVirages(ctx, px, py, cote) {
  if (!etat.virages || !etat.virages.virages || !etat.virages.virages.length) return;
  const { rayon } = tailles(cote);

  ctx.font = `700 ${Math.round(rayon * 1.25)}px ${POLICE}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  for (const p of placerPastilles(px, py, cote)) {
    // Un trait relie la pastille à son virage : une fois écartée, on ne sait
    // plus à quel endroit du circuit elle se rapporte.
    ctx.strokeStyle = COULEURS.bord;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(p.ancreX, p.ancreY);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();

    ctx.fillStyle = COULEURS.fond;
    ctx.strokeStyle = COULEURS.accent;
    ctx.beginPath();
    ctx.arc(p.x, p.y, rayon, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = COULEURS.texte;
    ctx.fillText(String(p.numero), p.x, p.y + 0.5);
  }
}

// ---------------------------------------------------------------------
// Tableau des tronçons
// ---------------------------------------------------------------------


// ---------------------------------------------------------------------

function relancerListe() {
  etat.limite = PAR_PAQUET; // un nouveau filtre repart du premier paquet
  etat.chargement = null; // annule un chargement de chronos devenu inutile
  afficherSessions();
  completerChronos();
}

$("#circuit").addEventListener("change", relancerListe);
$("#tri").addEventListener("change", relancerListe);
$("#avec-tours").addEventListener("change", relancerListe);

// Quelles marques ont un logo dans le dossier `logos/`. Sans cette liste, on
// demanderait une image pour chaque marque et on récolterait des 404. Un échec
// ici n'empêche rien : les pastilles colorées prennent le relais.
api("/api/logos")
  .then(definirLogosDisponibles)
  .catch(() => {});

$("#valider-dossier").addEventListener("click", validerDossier);
$("#saisie-dossier").addEventListener("keydown", (e) => {
  if (e.key === "Enter") validerDossier();
});

// Le numéro de version, pour savoir de quoi on parle quand on signale un
// problème ou qu'on se demande si on a la dernière.
api("/api/version")
  .then((v) => {
    $("#version").textContent = `v${v.version}`;
    $("#version").title = `Tes découpages, logos et réglages : ${v.donnees}`;
  })
  .catch(() => {});

chargerSessions().catch((e) => erreur(e.message));
