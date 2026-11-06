// Point d'entrée de la page : les onglets, la fenêtre, la langue, les réglages.
//
// Chaque onglet vit dans son propre fichier `ecran_*.js`. Aucun cadriciel : le
// besoin ne le justifie pas et ça garde le code lisible pour quelqu'un qui n'écrit
// pas du JavaScript tous les jours.

import { $, $$, api, envoyer, erreur, etat, navigation } from "/commun.js";
import { definirLogosDisponibles, echapper } from "/emblemes.js";
import { ICONES } from "/icones.js";
import {
  LANGUES_DISPONIBLES, definirLangue, langue, langueParDefaut, t, traduire, traduirePage,
} from "/i18n.js";
import { ecranDossier, surDossierChange } from "/ecran_dossier.js";
import { arreterOverlay, ouvrirOverlay } from "/ecran_overlay.js";
import { ecranResultats, surResultats } from "/ecran_resultats.js";
import { ecranTelemetrie, surTelemetrie } from "/ecran_telemetrie.js";
import { ecranTemps, surTemps } from "/ecran_temps.js";
import { preparerFenetre } from "/fenetre.js";
import { barreSessions, chargerSessions } from "/barre_sessions.js";

const ECRANS = ["resultats", "telemetrie", "overlay", "temps", "dossier"];

/** Montre un onglet. La colonne de gauche n'existe que pour deux d'entre eux. */
function aller(demande) {
  // Sans dossier de télémétrie, les onglets n'ont rien à montrer : l'écran qui permet
  // de l'indiquer reste la seule issue. L'overlay, lui, ne lit que le jeu.
  const onglet = etat.sansDossier && demande !== "overlay" ? "dossier" : demande;
  etat.onglet = onglet;
  for (const nom of ECRANS) $(`#ecran-${nom}`).hidden = nom !== onglet;
  for (const bouton of $$("#onglets button")) {
    bouton.classList.toggle("actif", bouton.dataset.onglet === onglet);
  }
  const lateral = onglet === "resultats" || onglet === "temps";
  document.body.classList.toggle("sans-laterale", !lateral);
  // Invisible plutôt que retiré : les onglets ne doivent pas bouger d'un écran à l'autre.
  $("#bascule-laterale").style.visibility = lateral ? "visible" : "hidden";
  if (onglet !== "overlay") arreterOverlay();

  erreur(null);
  if (onglet === "resultats") {
    barreSessions.afficher();
    surResultats();
  } else if (onglet === "telemetrie") {
    surTelemetrie();
  } else if (onglet === "overlay") {
    ouvrirOverlay();
  } else if (onglet === "temps") {
    surTemps();
  }
}

navigation.aller = aller;

for (const bouton of $$("#onglets button")) {
  bouton.onclick = () => aller(bouton.dataset.onglet);
}

$("#erreur-fermer").onclick = () => erreur(null);

$("#bascule-laterale").onclick = () => document.body.classList.toggle("laterale-repliee");

// ---------------------------------------------------------------------
// Réglages
// ---------------------------------------------------------------------

async function afficherReglages() {
  const panneau = $("#reglages");
  let dossier = null;
  try {
    dossier = await api("/api/dossier");
  } catch {
    // Sans dossier, le panneau reste utile pour la langue.
  }
  panneau.innerHTML = `
    <h3>${t("reglages.titre")}</h3>
    <div class="reglage">
      <span>${t("reglages.langue")}</span>
      <div id="choix-langue" class="choix-langue" role="group" aria-label="Langue / Language">
        ${LANGUES_DISPONIBLES.map(
          (code) => `<button type="button" data-langue="${code}"
             class="${code === langue() ? "actif" : ""}"
             aria-pressed="${code === langue()}">${code.toUpperCase()}</button>`
        ).join("")}
      </div>
    </div>
    <div class="reglage colonne">
      <span>${t("reglages.dossier")}</span>
      <code>${echapper(dossier?.dossier || "—")}</code>
      ${dossier && !dossier.impose
        ? `<button id="changer-dossier" type="button" class="lien">${t("source.changer")}</button>`
        : ""}
    </div>
    <div class="reglage colonne">
      <span>${t("reglages.donnees")}</span>
      <code>${echapper(version?.donnees || "—")}</code>
    </div>
    <div class="note">Télémétrie LMU v${echapper(version?.version || "?")}</div>`;

  for (const bouton of panneau.querySelectorAll("[data-langue]")) {
    bouton.onclick = () => changerLangue(bouton.dataset.langue);
  }
  const changer = $("#changer-dossier");
  if (changer) {
    changer.onclick = () => {
      panneau.hidden = true;
      ecranDossier.ouvrir({ cle: "dossier.autre" }, true, dossier.dossier);
    };
  }
}

$("#ouvrir-reglages").onclick = async (e) => {
  e.stopPropagation();
  const panneau = $("#reglages");
  if (panneau.hidden) await afficherReglages();
  panneau.hidden = !panneau.hidden;
};

// Un clic ailleurs referme le panneau, comme un menu.
document.addEventListener("click", (e) => {
  if (!e.target.closest("#reglages")) $("#reglages").hidden = true;
});

// ---------------------------------------------------------------------
// Langue
// ---------------------------------------------------------------------

// Le choix est enregistré par le serveur, dans les réglages de l'utilisateur,
// et non par le navigateur : le .exe peut changer de port d'un lancement à
// l'autre, et le navigateur range ses données par port — le choix serait perdu.
async function changerLangue(code) {
  if (code === langue()) return;
  definirLangue(code);
  rafraichir();
  await afficherReglages();
  try {
    await envoyer("/api/langue", { langue: code });
  } catch {
    // Pas enregistré : la page reste dans la langue choisie jusqu'à la fermeture.
  }
}

// Redessine tout ce qui est déjà affiché, dans la nouvelle langue. Les écrans
// sont reconstruits à partir des données déjà chargées : rien n'est redemandé
// au serveur, sauf le découpage en virages, en cache de son côté.
function rafraichir() {
  traduirePage();
  poserIcones();
  // Une erreur déjà affichée resterait dans l'ancienne langue : on la retire,
  // la prochaine action la redonnera si elle se reproduit.
  erreur(null);
  ecranDossier.rafraichir();
  barreSessions.rafraichir();
  ecranResultats.rafraichir();
  ecranTelemetrie.rafraichir();
  ecranTemps.rafraichir();
  if (etat.onglet === "overlay") ouvrirOverlay();
}

function poserIcones() {
  $("#bascule-laterale").innerHTML = ICONES.menu;
  $("#ouvrir-reglages").innerHTML = ICONES.reglages;
}

surDossierChange(async () => {
  etat.session = null;
  etat.sessionChoisie = null;
  etat.circuits = null;
  await demarrer();
});

// ---------------------------------------------------------------------
// Démarrage
// ---------------------------------------------------------------------

async function demarrer() {
  etat.sansDossier = false;
  try {
    await chargerSessions();
  } catch (e) {
    if (e.code === "dossier_introuvable") {
      etat.sansDossier = true;
      ecranDossier.ouvrir(e.brut, false);
      return;
    }
    erreur(e.message);
  }
  aller("resultats");
}

let version = null;
try {
  version = await api("/api/version");
} catch {
  version = null;
}
definirLangue((version && version.langue) || langueParDefaut());
traduirePage();
poserIcones();
preparerFenetre();

// Quelles marques ont un logo dans le dossier `logos/`. Sans cette liste, on
// demanderait une image pour chaque marque et on récolterait des 404. Un échec
// ici n'empêche rien : les pastilles colorées prennent le relais.
api("/api/logos")
  .then(definirLogosDisponibles)
  .catch(() => {});

demarrer().catch((e) => erreur(traduire(e.brut) || e.message));
