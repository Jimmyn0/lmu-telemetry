// Choisir le dossier de télémétrie, quand il n'a pas été trouvé tout seul ou qu'on
// veut en changer.

import { $, envoyer, etat, navigation } from "/commun.js";
import { traduire } from "/i18n.js";

let surChange = async () => {};

/** `rappel` est appelé une fois un nouveau dossier retenu. */
export function surDossierChange(rappel) {
  surChange = rappel;
}

let message = null;

async function valider() {
  const bouton = $("#valider-dossier");
  bouton.disabled = true;
  try {
    await envoyer("/api/dossier", { dossier: $("#saisie-dossier").value });
    await surChange();
  } catch (e) {
    $("#erreur-dossier").textContent = e.message;
    $("#erreur-dossier").hidden = false;
  } finally {
    bouton.disabled = false;
  }
}

$("#valider-dossier").addEventListener("click", valider);
$("#saisie-dossier").addEventListener("keydown", (e) => {
  if (e.key === "Enter") valider();
});

export const ecranDossier = {
  // `texte` est un message à traduire (clé et valeurs) : on le garde tel quel pour
  // pouvoir le réécrire si la langue change pendant que l'écran est ouvert.
  ouvrir(texte, annulable, valeur = "") {
    message = texte;
    const precedent = etat.onglet;
    navigation.aller("dossier");
    $("#message-dossier").textContent = traduire(texte);
    $("#saisie-dossier").value = valeur;
    $("#erreur-dossier").hidden = true;
    $("#annuler-dossier").hidden = !annulable;
    $("#annuler-dossier").onclick = () => navigation.aller(precedent);
    $("#saisie-dossier").focus();
  },

  rafraichir() {
    $("#erreur-dossier").hidden = true;
    if (message) $("#message-dossier").textContent = traduire(message);
  },
};
