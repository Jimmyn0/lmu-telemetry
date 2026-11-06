// Carte du circuit.
//
// Deux toiles superposées : le fond, redessiné quand les données ou le mode changent,
// et le calque des voitures, redessiné à chaque mouvement du curseur. Redessiner les
// quelque 5 800 segments du tracé à chaque image ralentissait la lecture du tour.

import { COULEURS } from "/graphes.js";

// Marge autour du tracé, et hauteur de la carte. Elle suit la forme du circuit : un
// tracé tout en longueur comme Monza serait sinon réduit à une mince bande au milieu
// d'une carte large.
const MARGE = 8;
const HAUTEUR_MINIMALE = 170;
const HAUTEUR_MAXIMALE = 270;

/** Une couleur #rrggbb de la palette, rendue plus ou moins transparente. */
function transparence(couleur, opacite) {
  return couleur + Math.round(opacite * 255).toString(16).padStart(2, "0");
}

// Une couleur par segment du tracé, selon ce que la carte montre.
const MODES = {
  // Le tracé est coloré par la pente locale du delta : rouge là où le tour comparé
  // perd, vert là où il gagne. C'est la même information que le graphique de delta,
  // posée sur le circuit.
  delta(c, i) {
    const fenetre = Math.max(2, Math.round(25 / c.distance.pas));
    const avant = c.delta[Math.max(0, i - fenetre)];
    const apres = c.delta[Math.min(c.delta.length - 1, i + fenetre)];
    const pente = apres - avant;
    const force = Math.min(1, Math.abs(pente) / 0.05);
    if (force < 0.15) return null;
    return transparence(pente > 0 ? COULEURS.perte : COULEURS.gain, 0.35 + 0.65 * force);
  },

  // Une seule teinte, du lent au rapide : le bleu clair dans les virages, le blanc
  // à fond.
  vitesse(c, i, bornes) {
    const v = c.traces["Ground Speed"].reference[i];
    const part = Math.max(0, Math.min(1, (v - bornes.min) / (bornes.max - bornes.min || 1)));
    const canal = (a, b) => Math.round(a + (b - a) * part);
    return `rgb(${canal(40, 225)}, ${canal(90, 235)}, ${canal(150, 245)})`;
  },

  // Ce que font les pieds : frein en rouge, accélérateur en vert, rien en gris.
  entrees(c, i) {
    const gaz = (c.traces["Throttle Pos Unfiltered"] || c.traces["Throttle Pos"]).reference[i];
    if (c.traces["Brake Pos"].reference[i] > 5) return COULEURS.perte;
    if (gaz > 15) return COULEURS.gain;
    return null;
  },

  secteurs(c, i) {
    const d = c.distance.debut + i * c.distance.pas;
    const { fin_s1: s1, fin_s2: s2 } = c.reference;
    if (s1 === null || s2 === null) return null;
    if (d < s1) return COULEURS.secteur1;
    return d < s2 ? COULEURS.secteur2 : COULEURS.secteur3;
  },
};

export class Carte {
  constructor(fond, calque) {
    this.fond = fond;
    this.calque = calque;
    this.mode = "delta";
    this.comparaison = null;
    this.trace = null;
  }

  /** Nouveaux tours. Les coordonnées du jeu sont locales et fictives : seule la
   *  forme compte, et le cos(latitude) garde les proportions entre les deux axes. */
  definir(comparaison) {
    this.comparaison = comparaison;
    const lat = comparaison.traces["GPS Latitude"];
    const lon = comparaison.traces["GPS Longitude"];
    if (!lat || !lon) {
      this.trace = null;
      return;
    }
    const moyenneLat = lat.reference.reduce((a, b) => a + b, 0) / lat.reference.length;
    const k = Math.cos((moyenneLat * Math.PI) / 180);
    const xs = lon.reference.map((v) => v * k);
    const ys = lat.reference.map((v) => -v);
    this.trace = {
      xs, ys,
      cxs: lon.compare.map((v) => v * k),
      cys: lat.compare.map((v) => -v),
      x0: Math.min(...xs), x1: Math.max(...xs),
      y0: Math.min(...ys), y1: Math.max(...ys),
    };
    const vitesses = comparaison.traces["Ground Speed"].reference;
    this.bornes = { min: Math.min(...vitesses), max: Math.max(...vitesses) };
    this.dessiner();
  }

  definirMode(mode) {
    this.mode = mode;
    this.dessiner();
  }

  _preparer(toile) {
    const ratio = window.devicePixelRatio || 1;
    const largeur = toile.clientWidth;
    const hauteur = toile.clientHeight;
    toile.width = largeur * ratio;
    toile.height = hauteur * ratio;
    const ctx = toile.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, largeur, hauteur);
    return { ctx, largeur, hauteur };
  }

  _ajusterHauteur() {
    const cadre = this.fond.parentElement;
    const { x0, x1, y0, y1 } = this.trace;
    const voulue = ((cadre.clientWidth - 2 * MARGE) * (y1 - y0)) / (x1 - x0 || 1) + 2 * MARGE;
    const hauteur = Math.max(HAUTEUR_MINIMALE, Math.min(HAUTEUR_MAXIMALE, voulue));
    cadre.style.height = `${Math.round(hauteur)}px`;
  }

  /** Redessine le fond : le tracé, coloré selon le mode. */
  dessiner() {
    if (!this.trace) return;
    this._ajusterHauteur();
    const { ctx, largeur, hauteur } = this._preparer(this.fond);
    if (!largeur || !hauteur) return;

    const { xs, ys, x0, x1, y0, y1 } = this.trace;
    const echelle = Math.min(
      (largeur - 2 * MARGE) / (x1 - x0 || 1),
      (hauteur - 2 * MARGE) / (y1 - y0 || 1)
    );
    const decalageX = (largeur - (x1 - x0) * echelle) / 2;
    const decalageY = (hauteur - (y1 - y0) * echelle) / 2;
    const px = (i) => (xs[i] - x0) * echelle + decalageX;
    const py = (i) => (ys[i] - y0) * echelle + decalageY;
    this.versEcran = (x, y) => [(x - x0) * echelle + decalageX, (y - y0) * echelle + decalageY];

    // L'intérieur du circuit, puis la piste en large, puis la couleur du mode.
    ctx.beginPath();
    ctx.moveTo(px(0), py(0));
    for (let i = 1; i < xs.length; i += 2) ctx.lineTo(px(i), py(i));
    ctx.closePath();
    ctx.fillStyle = COULEURS.interieur;
    ctx.fill();
    ctx.strokeStyle = COULEURS.traceNeutre;
    ctx.lineWidth = 6;
    ctx.lineJoin = "round";
    ctx.stroke();

    const couleur = MODES[this.mode];
    const c = this.comparaison;
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    for (let i = 1; i < xs.length; i++) {
      const teinte = couleur(c, i, this.bornes);
      if (!teinte) continue;
      ctx.strokeStyle = teinte;
      ctx.beginPath();
      ctx.moveTo(px(i - 1), py(i - 1));
      ctx.lineTo(px(i), py(i));
      ctx.stroke();
    }

    this._ligneDepart(ctx, px, py);
  }

  // Un petit damier en travers de la piste, comme sur les cartes de circuit.
  _ligneDepart(ctx, px, py) {
    const dx = px(4) - px(0);
    const dy = py(4) - py(0);
    const norme = Math.hypot(dx, dy) || 1;
    const nx = -dy / norme;
    const ny = dx / norme;
    for (let k = -3; k <= 2; k++) {
      ctx.fillStyle = k % 2 ? "#ffffff" : "#000000";
      ctx.fillRect(px(0) + nx * k * 2 - 1, py(0) + ny * k * 2 - 1, 2.4, 2.4);
    }
  }

  /** Les deux voitures. Sans `indiceCompare`, elles sont au même point de la piste. */
  placer(indice, indiceCompare = indice) {
    const { ctx } = this._preparer(this.calque);
    if (indice === null || !this.trace || !this.versEcran) return;
    const point = (x, y, couleur) => {
      const [ex, ey] = this.versEcran(x, y);
      ctx.fillStyle = couleur;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.arc(ex, ey, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    };
    const t = this.trace;
    if (indiceCompare !== indice) point(t.cxs[indiceCompare], t.cys[indiceCompare], COULEURS.compare);
    if (indice < t.xs.length) point(t.xs[indice], t.ys[indice], COULEURS.reference);
  }
}
