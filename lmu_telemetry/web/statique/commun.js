// Ce que partagent les écrans : l'état de la page, les échanges avec le serveur, les
// étiquettes et les messages.

import { codeType, familleClasse } from "/format.js";
import { echapper } from "/emblemes.js";
import { ICONES } from "/icones.js";
import { locale, t, traduire } from "/i18n.js";

export const $ = (s) => document.querySelector(s);
export const $$ = (s) => [...document.querySelectorAll(s)];

export const etat = {
  onglet: "resultats",
  sessions: [],
  session: null,
  // La session demandée, connue avant que le serveur ait répondu.
  sessionChoisie: null,
  telemetrie: null,
  circuits: null,
  sansDossier: false,
};

/** Changer d'onglet depuis un écran, sans que les écrans s'importent entre eux. */
export const navigation = { aller: () => {} };

/** Message d'erreur d'une réponse du serveur, dans la langue de la page. */
export function messageErreur(charge) {
  return charge.message ? traduire(charge.message) : charge.erreur || t("erreur.inconnue");
}

export async function api(route, params = {}, options = {}) {
  const url = new URL(route, location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined) url.searchParams.set(k, v);
  }
  let reponse;
  try {
    reponse = await fetch(url, options);
  } catch {
    // Le serveur s'est arrêté mais la page reste affichée. Sans ce message, le
    // moindre clic échouerait sur un « Failed to fetch » incompréhensible.
    throw new Error(t("erreur.hors_ligne"));
  }
  let charge;
  try {
    charge = await reponse.json();
  } catch {
    throw new Error(t("erreur.reponse_inattendue", { code: reponse.status }));
  }
  if (!reponse.ok || charge.erreur) {
    const e = new Error(messageErreur(charge));
    e.code = charge.code;
    // Le message lui-même, pour pouvoir le réécrire si la langue change.
    e.brut = charge.message || charge.erreur;
    throw e;
  }
  return charge;
}

/** Envoie des données au serveur. */
export function envoyer(route, donnees) {
  return api(route, {}, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(donnees),
  });
}

/** Affiche une erreur par-dessus la page ; sans message, la retire. */
export function erreur(message) {
  const bloc = $("#erreur");
  bloc.hidden = !message;
  $("#erreur-texte").textContent = message || "";
}

export function dateCourte(iso) {
  if (!iso) return "?";
  const d = new Date(iso);
  const jour = d.toLocaleDateString(locale(), { day: "2-digit", month: "2-digit", year: "numeric" });
  const heure = d.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
  return `${jour} · ${heure}`;
}

export function dateJour(iso) {
  if (!iso) return "?";
  return new Date(iso).toLocaleDateString(locale(), {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
}

const TYPES = { P: "type.P", Q: "type.Q", R: "type.R" };

export function nomType(type) {
  const code = codeType(type);
  return code ? t(TYPES[code]) : String(type || "?");
}

/** Étiquette du type de session. */
export function badgeType(type) {
  const code = codeType(type) || "autre";
  return `<span class="badge type-${code}">${echapper(nomType(type))}</span>`;
}

/** Étiquette de catégorie : la couleur vient de la famille, le texte aussi. */
export function badgeClasse(brut) {
  const famille = familleClasse(brut);
  if (!brut) return "";
  return `<span class="badge classe-${famille || "autre"}">${echapper(famille || brut)}</span>`;
}

/** Sens d'un virage, en flèche. */
export function fleche(sens) {
  const fleches = { gauche: ["↰", "sens.gauche"], droite: ["↱", "sens.droite"] };
  const f = fleches[sens];
  return f ? ` <span class="sens" title="${t(f[1])}">${f[0]}</span>` : "";
}

/** Un écran vide, en chargement ou en erreur : toujours la même présentation. */
export function etatVide({ icone = "courbe", titre, texte = "", action = "", chargement = false }) {
  return `<div class="etat-vide${chargement ? " chargement" : ""}">
    <div class="etat-icone">${chargement ? `<span class="roue"></span>` : ICONES[icone]}</div>
    <h2>${titre}</h2>
    ${texte ? `<p>${texte}</p>` : ""}
    ${action}
  </div>`;
}
