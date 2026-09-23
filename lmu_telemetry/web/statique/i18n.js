// Langue de l'interface : français ou anglais.
//
// Aucun texte affiché n'est écrit dans le code : chacun a une clé, et sa
// traduction dans `langues/fr.json` et `langues/en.json`. Un test
// (tests/test_langues.py) vérifie que les deux fichiers ont exactement les
// mêmes clés et les mêmes emplacements `{...}`, et que chaque clé utilisée dans
// le code existe : une phrase oubliée dans une langue bloque la construction du
// .exe au lieu de passer inaperçue.
//
// Les traductions sont des textes de CONFIANCE, écrits par nous : elles peuvent
// contenir du HTML (<strong>…). Ce qui vient d'un fichier — nom de circuit,
// chemin, voiture — doit en revanche être passé par `echapper` AVANT d'être
// inséré dans une traduction qui finit en HTML.

export const LANGUES_DISPONIBLES = ["fr", "en"];

// Chargées une fois au démarrage : deux petits fichiers servis en local.
const [FR, EN] = await Promise.all(
  ["fr", "en"].map((l) => fetch(`/langues/${l}.json`).then((r) => r.json()))
);
const TEXTES = { fr: FR, en: EN };

let courante = "fr";

export function langue() {
  return courante;
}

export function definirLangue(code) {
  courante = TEXTES[code] ? code : "fr";
  document.documentElement.lang = courante;
}

/** Langue proposée tant que l'utilisateur n'en a pas choisi une. */
export function langueParDefaut() {
  const navigateur = (navigator.languages || [navigator.language || ""])[0] || "";
  return navigateur.toLowerCase().startsWith("fr") ? "fr" : "en";
}

/** Réglage régional des dates et des nombres, selon la langue. */
export function locale() {
  return courante === "fr" ? "fr-FR" : "en-GB";
}

/**
 * Texte d'une clé, avec ses emplacements `{nom}` remplis par `valeurs`.
 * Une clé absente de la langue courante retombe sur le français, puis sur la
 * clé elle-même : un oubli se voit, il ne casse rien.
 */
export function t(cle, valeurs = {}) {
  const modele = TEXTES[courante][cle] ?? TEXTES.fr[cle] ?? cle;
  return modele.replace(/\{(\w+)\}/g, (brut, nom) => (nom in valeurs ? valeurs[nom] : brut));
}

/**
 * Phrase d'un message envoyé par le serveur : `{ cle, valeurs }` (voir
 * lmu_telemetry/textes.py). Le serveur ne rédige rien lui-même, c'est ce qui
 * permet d'afficher ses remarques et ses erreurs dans la langue choisie.
 * Le résultat est du texte brut : à passer par `echapper` avant tout HTML.
 */
export function traduire(message) {
  if (message && typeof message === "object" && message.cle) {
    return t(message.cle, message.valeurs || {});
  }
  return String(message ?? "");
}

/** Comme `t`, mais au singulier ou au pluriel selon `n` : clés `….un` et `….plusieurs`. */
export function tp(cle, n, valeurs = {}) {
  return t(`${cle}.${n === 1 ? "un" : "plusieurs"}`, { n, ...valeurs });
}

/**
 * Traduit les textes fixes de la page, repérés par des attributs :
 * `data-t` (texte), `data-t-html` (texte avec balises), `data-t-placeholder`,
 * `data-t-title`.
 */
export function traduirePage(racine = document) {
  for (const el of racine.querySelectorAll("[data-t]")) el.textContent = t(el.dataset.t);
  for (const el of racine.querySelectorAll("[data-t-html]")) el.innerHTML = t(el.dataset.tHtml);
  for (const el of racine.querySelectorAll("[data-t-placeholder]")) {
    el.placeholder = t(el.dataset.tPlaceholder);
  }
  for (const el of racine.querySelectorAll("[data-t-title]")) el.title = t(el.dataset.tTitle);
  document.title = t("page.titre");
}
