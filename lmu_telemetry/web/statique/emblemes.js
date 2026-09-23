// Drapeaux des pays et pastilles de marque.
//
// Tout est dessiné en SVG dans cette page : l'outil doit fonctionner sans
// connexion, donc rien n'est chargé depuis un serveur d'images.
//
// Les drapeaux sont des dessins SIMPLIFIÉS, lisibles à 18 pixels de haut. Les
// armoiries (Portugal, Espagne), les étoiles exactes (États-Unis) et le
// décalage des diagonales du drapeau britannique sont volontairement omis :
// ils sont invisibles à cette taille et alourdiraient le fichier pour rien.
//
// Les LOGOS DE MARQUE, eux, ne sont pas dessinés ici. Ce sont des marques
// déposées : une imitation faite à la main serait approximative et douteuse.
// On affiche donc une pastille aux couleurs du constructeur. Si tu veux les
// vrais logos, dépose des fichiers image dans le dossier `logos/` à côté de
// `virages/`, nommés d'après la marque — `Porsche.png`, `Ferrari.svg`… — et
// ils remplaceront automatiquement la pastille.

// Neutralise un texte avant de l'insérer dans la page.
//
// Tout ce qui vient d'un FICHIER passe par ici : nom de circuit, de voiture,
// d'écurie, météo… On peut déposer dans le dossier de télémétrie le fichier
// d'un autre pilote, et rien ne garantit ce qu'il contient. Vérifié : un nom
// de tracé contenant du HTML s'exécutait au simple affichage de la liste des
// sessions, sans aucun clic.
export function echapper(texte) {
  return String(texte ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const DRAPEAUX = {
  BE: `<rect width="3" height="2" fill="#fff"/><rect width="1" height="2" fill="#000"/>
       <rect x="1" width="1" height="2" fill="#FDDA24"/><rect x="2" width="1" height="2" fill="#EF3340"/>`,
  FR: `<rect width="1" height="2" fill="#002395"/><rect x="1" width="1" height="2" fill="#fff"/>
       <rect x="2" width="1" height="2" fill="#ED2939"/>`,
  IT: `<rect width="1" height="2" fill="#008C45"/><rect x="1" width="1" height="2" fill="#F4F5F0"/>
       <rect x="2" width="1" height="2" fill="#CD212A"/>`,
  JP: `<rect width="3" height="2" fill="#fff"/><circle cx="1.5" cy="1" r="0.6" fill="#BC002D"/>`,
  PT: `<rect width="3" height="2" fill="#DA291C"/><rect width="1.2" height="2" fill="#046A38"/>
       <circle cx="1.2" cy="1" r="0.42" fill="none" stroke="#FFE900" stroke-width="0.16"/>
       <circle cx="1.2" cy="1" r="0.2" fill="#fff" stroke="#DA291C" stroke-width="0.08"/>`,
  ES: `<rect width="3" height="2" fill="#AA151B"/><rect y="0.5" width="3" height="1" fill="#F1BF00"/>`,
  GB: `<rect width="3" height="2" fill="#012169"/>
       <path d="M0,0 3,2 M3,0 0,2" stroke="#fff" stroke-width="0.42"/>
       <path d="M0,0 3,2 M3,0 0,2" stroke="#C8102E" stroke-width="0.22"/>
       <path d="M1.5,0 V2 M0,1 H3" stroke="#fff" stroke-width="0.66"/>
       <path d="M1.5,0 V2 M0,1 H3" stroke="#C8102E" stroke-width="0.4"/>`,
  // Bahreïn : cinq dents, une par pilier de l'islam. Qatar : neuf.
  BH: `<rect width="3" height="2" fill="#CE1126"/>
       <path d="M0,0 H0.9 L1.35,0.2 0.9,0.4 1.35,0.6 0.9,0.8 1.35,1 0.9,1.2 1.35,1.4 0.9,1.6
                1.35,1.8 0.9,2 H0 Z" fill="#fff"/>`,
  QA: `<rect width="3" height="2" fill="#8A1538"/>
       <path d="M0,0 H0.75 L1.1,0.111 0.75,0.222 1.1,0.333 0.75,0.444 1.1,0.556 0.75,0.667
                1.1,0.778 0.75,0.889 1.1,1 0.75,1.111 1.1,1.222 0.75,1.333 1.1,1.444
                0.75,1.556 1.1,1.667 0.75,1.778 1.1,1.889 0.75,2 H0 Z" fill="#fff"/>`,
  BR: `<rect width="3" height="2" fill="#009B3A"/>
       <path d="M1.5,0.2 2.75,1 1.5,1.8 0.25,1 Z" fill="#FEDF00"/>
       <circle cx="1.5" cy="1" r="0.42" fill="#002776"/>
       <path d="M1.13,0.86 A0.75,0.75 0 0 1 1.89,1.1" stroke="#fff" stroke-width="0.11" fill="none"/>`,
  US: `<rect width="3" height="2" fill="#fff"/>
       ${[0, 2, 4, 6, 8, 10, 12]
         .map((i) => `<rect y="${(i * 2) / 13}" width="3" height="${2 / 13}" fill="#B31942"/>`)
         .join("")}
       <rect width="1.2" height="${(7 * 2) / 13}" fill="#0A3161"/>
       ${[0.2, 0.5, 0.8, 1.0]
         .map((x) =>
           [0.15, 0.38, 0.61, 0.84]
             .map((y) => `<circle cx="${x}" cy="${y}" r="0.055" fill="#fff"/>`)
             .join("")
         )
         .join("")}`,
};

// Couleur de la pastille, par marque. Reprend la teinte que le constructeur
// utilise en course, sans reproduire aucun dessin.
const COULEURS_MARQUE = {
  Porsche: "#c8102e",
  Ferrari: "#d40000",
  BMW: "#0066b1",
  "Aston Martin": "#00665e",
  McLaren: "#ff8000",
  Mercedes: "#00a19b",
  Lexus: "#1a1a2e",
  Ford: "#00274d",
  Chevrolet: "#c5a253",
  Lamborghini: "#ddb321",
  Cadillac: "#8f1a2b",
  Peugeot: "#0a3b6b",
  Toyota: "#eb0a1e",
  Alpine: "#0055a4",
  Genesis: "#4a4a4a",
  "Isotta Fraschini": "#6b2d5b",
  Oreca: "#1f6feb",
  ADESS: "#5a6570",
  Duqueine: "#7a2f2f",
  Ginetta: "#2e7d32",
  Ligier: "#1565c0",
};

const COULEUR_MARQUE_INCONNUE = "#5a6570";

// Renvoie le HTML d'un drapeau, ou une chaîne vide si le pays est inconnu.
// `pays` est l'objet { code, nom } renvoyé par l'API.
export function drapeau(pays) {
  if (!pays || !DRAPEAUX[pays.code]) return "";
  return (
    `<svg class="drapeau" viewBox="0 0 3 2" role="img" aria-label="${echapper(pays.nom)}">` +
    `<title>${echapper(pays.nom)}</title>${DRAPEAUX[pays.code]}` +
    `<rect width="3" height="2" fill="none" stroke="rgba(0,0,0,.25)" stroke-width="0.06"/></svg>`
  );
}

// Marques pour lesquelles le dossier `logos/` contient un fichier. Le serveur
// donne la liste une fois au démarrage : sans elle, chaque ligne de la liste
// des sessions demanderait une image inexistante et récolterait un 404.
let LOGOS_DISPONIBLES = new Set();

// Version de chaque logo adaptée au fond sombre (une image `data:`), quand le
// fichier d'origine a dû être retouché. Voir `adapterAuFondSombre`.
const LOGOS_ADAPTES = new Map();

const urlLogo = (marque) => `/logo?marque=${encodeURIComponent(marque)}`;

/** Enregistre les logos disponibles, puis les adapte au fond sombre. */
export async function definirLogosDisponibles(marques) {
  LOGOS_DISPONIBLES = new Set(marques || []);
  await Promise.all(
    [...LOGOS_DISPONIBLES].map(async (marque) => {
      try {
        const adapte = await adapterAuFondSombre(urlLogo(marque));
        if (adapte) LOGOS_ADAPTES.set(marque, adapte);
      } catch {
        // Image illisible : on garde le fichier tel quel.
      }
    })
  );
  // Les logos déjà affichés pendant la retouche passent à la version adaptée.
  for (const img of document.querySelectorAll("img.logo[data-marque]")) {
    const adapte = LOGOS_ADAPTES.get(img.dataset.marque);
    if (adapte) img.src = adapte;
  }
}

// Luminance perçue d'un pixel, de 0 (noir) à 255 (blanc).
const luminance = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

// Beaucoup de logos de constructeurs sont noirs — Aston Martin, McLaren, le
// cheval Ferrari — et disparaissent sur le fond sombre de l'outil. Plutôt que
// de retoucher les fichiers à la main, on corrige à l'affichage, ce qui vaut
// aussi pour un logo ajouté plus tard :
//
//   1. un logo SANS transparence (un JPG sur fond blanc) perd son fond : la
//      couleur des coins devient transparente ;
//   2. un logo gris ou noir et sombre voit sa luminosité inversée : le noir
//      devient blanc, les nuances intermédiaires restent lisibles ;
//   3. un logo en couleur mais sombre et peu saturé (le bleu marine d'Oreca)
//      est éclairci. Un rouge vif, lui, se voit très bien : on n'y touche pas.
//
// Renvoie l'image retouchée (`data:`), ou null s'il n'y avait rien à faire.
async function adapterAuFondSombre(url) {
  const img = new Image();
  img.src = url;
  await img.decode();
  const largeur = img.naturalWidth;
  const hauteur = img.naturalHeight;
  if (!largeur || !hauteur) return null;

  const toile = document.createElement("canvas");
  toile.width = largeur;
  toile.height = hauteur;
  const ctx = toile.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  const image = ctx.getImageData(0, 0, largeur, hauteur);
  const d = image.data;
  let retouche = false;

  // 1. Fond opaque → transparent. La transition est progressive pour garder
  //    des bords lisses.
  let transparents = 0;
  for (let i = 3; i < d.length; i += 4) if (d[i] < 250) transparents++;
  if (transparents < 0.02 * largeur * hauteur) {
    const coins = [0, largeur - 1, (hauteur - 1) * largeur, hauteur * largeur - 1];
    const fond = [0, 1, 2].map((c) => coins.reduce((s, k) => s + d[k * 4 + c], 0) / 4);
    for (let i = 0; i < d.length; i += 4) {
      const ecart = Math.max(
        Math.abs(d[i] - fond[0]), Math.abs(d[i + 1] - fond[1]), Math.abs(d[i + 2] - fond[2])
      );
      d[i + 3] = Math.round(255 * Math.min(1, Math.max(0, (ecart - 20) / 40)));
    }
    retouche = true;
  }

  // Ce qui reste visible : sa luminosité et sa saturation moyennes.
  let visibles = 0;
  let somme = 0;
  let saturation = 0;
  let gris = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i + 3] < 128) continue;
    const ecart = Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]);
    visibles++;
    somme += luminance(d[i], d[i + 1], d[i + 2]);
    saturation += ecart;
    if (ecart < 40) gris++;
  }
  if (!visibles) return null;
  const clarte = somme / visibles;

  if (gris / visibles > 0.9 && clarte < 90) {
    // 2. Gris ou noir, et sombre : on inverse la luminosité.
    for (let i = 0; i < d.length; i += 4) {
      const v = Math.min(236, 255 - luminance(d[i], d[i + 1], d[i + 2]));
      d[i] = d[i + 1] = d[i + 2] = v;
    }
    retouche = true;
  } else if (clarte < 60 && saturation / visibles < 120) {
    // 3. Couleur sombre et terne : on la rapproche du blanc, teinte conservée.
    for (let i = 0; i < d.length; i += 4) {
      for (let c = 0; c < 3; c++) d[i + c] = Math.round(d[i + c] + (255 - d[i + c]) * 0.55);
    }
    retouche = true;
  }

  if (!retouche) return null;
  ctx.putImageData(image, 0, 0);
  return toile.toDataURL("image/png");
}

// Emblème d'une marque : le fichier déposé dans `logos/` s'il existe, sinon
// une pastille aux couleurs du constructeur portant ses initiales.
export function embleme(marque) {
  if (!marque) return "";
  if (LOGOS_DISPONIBLES.has(marque)) {
    const source = LOGOS_ADAPTES.get(marque) || urlLogo(marque);
    return (
      `<img class="logo" src="${echapper(source)}" data-marque="${echapper(marque)}"` +
      ` alt="${echapper(marque)}" title="${echapper(marque)}">`
    );
  }
  const couleur = COULEURS_MARQUE[marque] || COULEUR_MARQUE_INCONNUE;
  const initiales = marque
    .split(/[\s-]+/)
    .slice(0, 2)
    .map((mot) => mot[0])
    .join("")
    .toUpperCase();
  return `<span class="pastille" style="background:${couleur}" title="${echapper(marque)}">${echapper(initiales)}</span>`;
}

// Libellé complet d'une voiture : « Porsche 911 GT3 R LMGT3 », l'engagement
// en dessous. Si le modèle est inconnu (dossier de résultats absent), on
// retombe sur l'engagement seul plutôt que d'afficher un vide.
export function libelleVoiture(v) {
  if (!v) return "";
  if (typeof v === "string") return echapper(v);
  if (!v.modele) return echapper(v.engagement);
  return `${embleme(v.marque)}<span class="modele">${echapper(v.modele)}</span>`;
}
