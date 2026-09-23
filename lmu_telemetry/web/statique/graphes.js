// Moteur de graphiques.
//
// Écrit à la main plutôt qu'emprunté à une bibliothèque : l'outil doit
// fonctionner hors ligne sans rien télécharger, et le besoin est étroit — des
// courbes empilées partageant un axe de distance, un curseur commun, un zoom.
//
// Toutes les courbes d'une pile partagent le même axe X (la distance) et le
// même curseur. C'est ce qui permet de lire d'un coup ce que faisaient les
// pédales à l'endroit précis où le delta décroche.

const MARGE = { gauche: 62, droite: 14, haut: 16, bas: 6 };
const MARGE_BAS_DERNIER = 26; // le dernier graphique porte l'axe des distances

// En dessous d'une vingtaine de points visibles, il n'y a plus rien à lire.
const POINTS_MINIMUM = 20;

// Les couleurs des graphiques sont celles de style.css : une seule palette
// pour la page et les tracés. Chaque entrée nomme sa variable CSS et une valeur
// de secours, utilisée si la feuille de style n'est pas (encore) chargée. Les
// valeurs sont en #rrggbb : les tracés y ajoutent leur transparence (« 33 »).
const PALETTE = {
  reference: ["--reference", "#4da6ff"],
  compare: ["--compare", "#ff9d3d"],
  grille: ["--grille", "#1f2738"],
  axe: ["--axe", "#7d889e"],
  texte: ["--texte", "#e4e9f2"],
  fond: ["--fond-bloc", "#111623"],
  curseur: ["--curseur", "#ffffff"],
  perte: ["--perte", "#ff5f6d"],
  gain: ["--gain", "#3ddc84"],
  record: ["--record", "#b57bff"],
  accent: ["--accent", "#7c6cff"],
  bord: ["--bord-fort", "#33405a"],
  route: ["--route", "#1a2031"],
  bordRoute: ["--bord-route", "#5d6a82"],
  bordRouteEstime: ["--bord-route-estime", "#3b4660"],
  traceNeutre: ["--trace-neutre", "#4a5470"],
};

export const COULEURS = {};

/** Relit la palette dans la feuille de style. */
export function lirePalette() {
  const style = getComputedStyle(document.documentElement);
  for (const [nom, [variable, secours]] of Object.entries(PALETTE)) {
    const valeur = style.getPropertyValue(variable).trim();
    COULEURS[nom] = /^#[0-9a-f]{6}$/i.test(valeur) ? valeur : secours;
  }
}
lirePalette();

// Police des textes dessinés dans les graphiques, la même que la page.
export const POLICE = '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif';

// ---------------------------------------------------------------------
// Un graphique
// ---------------------------------------------------------------------

export class Graphe {
  constructor(canvas, options) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.titre = options.titre;
    this.unite = options.unite || "";
    this.series = options.series; // [{valeurs, couleur, epaisseur}]
    this.zero = options.zero || false; // forcer l'axe à contenir 0
    this.remplirZero = options.remplirZero || false;
    this.escalier = options.escalier || false;
    this.dernier = options.dernier || false;
    this.min = options.min;
    this.max = options.max;
    this.decimales = options.decimales;
    // `entier` : une graduation par valeur entière, sans marge décimale.
    // Pour le rapport engagé, un axe gradué de 2 en 2 oblige à compter les
    // interlignes pour savoir si on est en 3e ou en 4e.
    this.entier = options.entier || false;
  }

  get margeBas() {
    return this.dernier ? MARGE_BAS_DERNIER : MARGE.bas;
  }

  // Domaine vertical, calculé sur la seule portion visible : sinon, zoomer
  // sur une épingle laisserait l'échelle réglée sur la ligne droite.
  domaine(i0, i1) {
    if (this.min !== undefined && this.max !== undefined) {
      return [this.min, this.max];
    }
    let bas = Infinity;
    let haut = -Infinity;
    for (const serie of this.series) {
      for (let i = i0; i <= i1; i++) {
        const v = serie.valeurs[i];
        if (v === null || v === undefined || Number.isNaN(v)) continue;
        if (v < bas) bas = v;
        if (v > haut) haut = v;
      }
    }
    if (!Number.isFinite(bas)) return [0, 1];
    if (this.entier) return [Math.floor(bas), Math.ceil(haut)];
    if (this.zero) {
      const ampleur = Math.max(Math.abs(bas), Math.abs(haut), 0.01);
      return [-ampleur, ampleur];
    }
    const marge = (haut - bas) * 0.08 || 1;
    return [bas - marge, haut + marge];
  }

  dessiner(vue) {
    const { i0, i1, distance } = vue;
    const ctx = this.ctx;
    const ratio = window.devicePixelRatio || 1;
    const largeurCss = this.canvas.clientWidth;
    const hauteurCss = this.canvas.clientHeight;
    this.canvas.width = largeurCss * ratio;
    this.canvas.height = hauteurCss * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

    const x0 = MARGE.gauche;
    const x1 = largeurCss - MARGE.droite;
    const y0 = MARGE.haut;
    const y1 = hauteurCss - this.margeBas;
    this.zone = { x0, x1, y0, y1 };

    ctx.fillStyle = COULEURS.fond;
    ctx.fillRect(0, 0, largeurCss, hauteurCss);

    const [bas, haut] = this.domaine(i0, i1);
    this.bas = bas;
    this.haut = haut;

    const versX = (i) => x0 + ((i - i0) / Math.max(1, i1 - i0)) * (x1 - x0);
    const versY = (v) => y1 - ((v - bas) / (haut - bas || 1)) * (y1 - y0);
    this.versX = versX;
    this.versY = versY;

    this.grille(ctx, bas, haut);

    if (this.remplirZero) this.remplissage(ctx, vue, versX, versY);

    for (const serie of this.series) {
      this.courbe(ctx, serie, vue, versX, versY);
    }

    // Le cadre par-dessus les courbes, pour qu'elles soient nettement coupées.
    ctx.strokeStyle = COULEURS.grille;
    ctx.lineWidth = 1;
    ctx.strokeRect(x0 + 0.5, y0 + 0.5, x1 - x0, y1 - y0);

    // Le titre est posé dans la zone de tracé : sans fond, une courbe qui passe
    // derrière le rend illisible.
    const libelle = this.unite ? `${this.titre}  (${this.unite})` : this.titre;
    ctx.font = `600 11px ${POLICE}`;
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    const largeurTitre = ctx.measureText(libelle).width;
    ctx.fillStyle = COULEURS.fond + "e6";
    ctx.fillRect(x0 + 1, y0 + 1, largeurTitre + 12, 16);
    ctx.fillStyle = COULEURS.texte;
    ctx.fillText(libelle, x0 + 6, y0 + 13);

    if (this.dernier) this.axeDistances(ctx, vue, versX, y1);
  }

  grille(ctx, bas, haut) {
    const { x0, x1, y0, y1 } = this.zone;
    // Un axe entier est gradué de 1 en 1, quel que soit le nombre de lignes que
    // ça fait : c'est une échelle de rapports, pas une échelle continue.
    const graduations = this.entier
      ? Array.from({ length: Math.round(haut - bas) + 1 }, (_, k) => Math.round(bas) + k)
      : this.graduations(bas, haut, 4);
    ctx.font = `10px ${POLICE}`;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (const v of graduations) {
      const y = this.versY(v);
      if (y < y0 - 1 || y > y1 + 1) continue;
      ctx.strokeStyle = v === 0 && this.zero ? COULEURS.axe : COULEURS.grille;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, Math.round(y) + 0.5);
      ctx.lineTo(x1, Math.round(y) + 0.5);
      ctx.stroke();
      ctx.fillStyle = COULEURS.axe;
      ctx.fillText(formater(v, this.decimales), x0 - 6, y);
    }
  }

  graduations(bas, haut, cible) {
    const brut = (haut - bas) / cible;
    const ordre = Math.pow(10, Math.floor(Math.log10(Math.abs(brut) || 1)));
    const pas = [1, 2, 2.5, 5, 10].map((m) => m * ordre).find((p) => p >= brut) || ordre;
    const debut = Math.ceil(bas / pas) * pas;
    const valeurs = [];
    for (let v = debut; v <= haut; v += pas) valeurs.push(Math.round(v / pas) * pas);
    return valeurs;
  }

  // Tracé décimé : au-delà d'un point par pixel, on dessine le minimum et le
  // maximum de chaque colonne. Prendre un point sur N ferait disparaître les
  // pics de freinage, qui sont précisément ce qu'on vient regarder.
  courbe(ctx, serie, vue, versX, versY) {
    const { i0, i1 } = vue;
    const { x0, x1, y0, y1 } = this.zone;
    const largeur = x1 - x0;
    const points = i1 - i0 + 1;

    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, y0, largeur, y1 - y0);
    ctx.clip();

    ctx.strokeStyle = serie.couleur;
    ctx.lineWidth = serie.epaisseur || 1.4;
    ctx.lineJoin = "round";
    ctx.beginPath();

    if (points <= largeur * 1.5) {
      let commence = false;
      for (let i = i0; i <= i1; i++) {
        const v = serie.valeurs[i];
        if (v === null || v === undefined) { commence = false; continue; }
        const x = versX(i);
        const y = versY(v);
        if (!commence) { ctx.moveTo(x, y); commence = true; }
        else if (this.escalier) { ctx.lineTo(x, versY(serie.valeurs[i - 1] ?? v)); ctx.lineTo(x, y); }
        else ctx.lineTo(x, y);
      }
    } else {
      const parPixel = points / largeur;
      for (let colonne = 0; colonne < largeur; colonne++) {
        const debut = i0 + Math.floor(colonne * parPixel);
        const fin = Math.min(i1, i0 + Math.floor((colonne + 1) * parPixel));
        let bas = Infinity;
        let haut = -Infinity;
        for (let i = debut; i <= fin; i++) {
          const v = serie.valeurs[i];
          if (v === null || v === undefined) continue;
          if (v < bas) bas = v;
          if (v > haut) haut = v;
        }
        if (!Number.isFinite(bas)) continue;
        const x = x0 + colonne;
        ctx.moveTo(x, versY(bas));
        ctx.lineTo(x, versY(haut));
      }
    }
    ctx.stroke();
    ctx.restore();
  }

  // Pour le delta : colorer ce qui est au-dessus et au-dessous de zéro rend la
  // lecture immédiate, sans avoir à se souvenir du sens de la convention.
  remplissage(ctx, vue, versX, versY) {
    const { i0, i1 } = vue;
    const valeurs = this.series[0].valeurs;
    const yZero = versY(0);
    const { x0, x1, y0, y1 } = this.zone;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, y0, x1 - x0, y1 - y0);
    ctx.clip();
    for (const [signe, couleur] of [[1, COULEURS.perte], [-1, COULEURS.gain]]) {
      ctx.beginPath();
      ctx.moveTo(versX(i0), yZero);
      for (let i = i0; i <= i1; i++) {
        const v = valeurs[i];
        const utile = v !== null && v !== undefined && Math.sign(v) === signe;
        ctx.lineTo(versX(i), utile ? versY(v) : yZero);
      }
      ctx.lineTo(versX(i1), yZero);
      ctx.closePath();
      ctx.fillStyle = couleur + "33";
      ctx.fill();
    }
    ctx.restore();
  }

  axeDistances(ctx, vue, versX, y1) {
    const { i0, i1, distance } = vue;
    const d0 = distance.debut + i0 * distance.pas;
    const d1 = distance.debut + i1 * distance.pas;
    ctx.font = `10px ${POLICE}`;
    ctx.fillStyle = COULEURS.axe;
    ctx.textBaseline = "top";

    const libelle = "mètres depuis la ligne";
    // Le libellé occupe le bord droit : on n'y écrit pas de graduation, sinon
    // les deux se chevauchent dans une colonne étroite.
    const reserve = this.zone.x1 - ctx.measureText(libelle).width - 8;

    for (const d of this.graduations(d0, d1, 8)) {
      const i = (d - distance.debut) / distance.pas;
      if (i < i0 || i > i1) continue;
      const x = versX(i);
      if (x > reserve) continue;
      ctx.textAlign = "center";
      ctx.fillText(`${Math.round(d)}`, x, y1 + 5);
      ctx.strokeStyle = COULEURS.grille;
      ctx.beginPath();
      ctx.moveTo(Math.round(x) + 0.5, y1);
      ctx.lineTo(Math.round(x) + 0.5, y1 + 3);
      ctx.stroke();
    }
    ctx.textAlign = "right";
    ctx.fillText(libelle, this.zone.x1, y1 + 5);
  }

  // Curseur et sélection sont dessinés dans un calque séparé, pour ne pas
  // avoir à redessiner toutes les courbes à chaque mouvement de souris.
  dessinerCurseur(calque, indice, selection) {
    const ctx = calque.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    calque.width = calque.clientWidth * ratio;
    calque.height = calque.clientHeight * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, calque.clientWidth, calque.clientHeight);
    if (!this.zone) return;
    const { x0, x1, y0, y1 } = this.zone;

    if (selection) {
      ctx.fillStyle = COULEURS.accent + "2e";
      const a = Math.max(x0, Math.min(selection[0], selection[1]));
      const b = Math.min(x1, Math.max(selection[0], selection[1]));
      ctx.fillRect(a, y0, b - a, y1 - y0);
    }
    if (indice !== null && this.versX) {
      const x = Math.round(this.versX(indice)) + 0.5;
      if (x >= x0 && x <= x1) {
        ctx.strokeStyle = COULEURS.curseur;
        ctx.globalAlpha = 0.55;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, y0);
        ctx.lineTo(x, y1);
        ctx.stroke();
        ctx.globalAlpha = 1;
        for (const serie of this.series) {
          const v = serie.valeurs[indice];
          if (v === null || v === undefined) continue;
          ctx.fillStyle = serie.couleur;
          ctx.beginPath();
          ctx.arc(x, this.versY(v), 3, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }
}

function formater(v, decimales) {
  if (decimales !== undefined) return v.toFixed(decimales);
  if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString("fr-FR");
  if (Math.abs(v) >= 10) return v.toFixed(0);
  if (Math.abs(v) >= 1) return v.toFixed(1);
  return v.toFixed(2);
}

// ---------------------------------------------------------------------
// Une pile de graphiques partageant l'axe X, le curseur et le zoom
// ---------------------------------------------------------------------

export class Pile {
  constructor(conteneur, distance, surCurseur, surVue = () => {}) {
    this.conteneur = conteneur;
    this.distance = distance;
    this.surCurseur = surCurseur;
    this.surVue = surVue;
    this.graphes = [];
    this.calques = [];
    this.i0 = 0;
    this.i1 = distance.nombre - 1;
    this.indice = null;
    this.selection = null;
    this._redessinerLie = () => this.redessiner();
    window.addEventListener("resize", this._redessinerLie);
  }

  detruire() {
    window.removeEventListener("resize", this._redessinerLie);
    this.conteneur.innerHTML = "";
  }

  ajouter(options, hauteur) {
    const bloc = document.createElement("div");
    bloc.className = "graphe";
    bloc.style.height = `${hauteur}px`;
    const fond = document.createElement("canvas");
    const calque = document.createElement("canvas");
    calque.className = "calque";
    bloc.append(fond, calque);
    this.conteneur.append(bloc);

    const graphe = new Graphe(fond, { ...options, dernier: false });
    this.graphes.push(graphe);
    this.calques.push(calque);
    this._brancher(calque, graphe);
    return graphe;
  }

  terminer() {
    if (this.graphes.length) {
      this.graphes[this.graphes.length - 1].dernier = true;
    }
    this.redessiner();
    this.surVue(this.i0, this.i1);
  }

  get vue() {
    return { i0: this.i0, i1: this.i1, distance: this.distance };
  }

  redessiner() {
    for (const g of this.graphes) g.dessiner(this.vue);
    this.redessinerCurseur();
  }

  redessinerCurseur() {
    this.graphes.forEach((g, k) =>
      g.dessinerCurseur(this.calques[k], this.indice, this.selection)
    );
  }

  // Proportion de la zone de tracé sous une abscisse, bornée à [0, 1].
  // Sans ce bornage, la souris sur la marge de l'axe (62 px à gauche) donne
  // une proportion négative, et le zoom part hors du tour.
  proportionDepuisX(graphe, x) {
    if (!graphe.zone) return 0;
    const { x0, x1 } = graphe.zone;
    return Math.min(1, Math.max(0, (x - x0) / (x1 - x0)));
  }

  indiceDepuisX(graphe, x) {
    const proportion = this.proportionDepuisX(graphe, x);
    return Math.round(this.i0 + proportion * (this.i1 - this.i0));
  }

  _brancher(calque, graphe) {
    let depart = null;

    calque.addEventListener("mousemove", (e) => {
      const rect = calque.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const i = this.indiceDepuisX(graphe, x);
      this.indice = Math.max(this.i0, Math.min(this.i1, i));
      this.selection = depart === null ? null : [depart, x];
      this.redessinerCurseur();
      this.surCurseur(this.indice);
    });

    calque.addEventListener("mouseleave", () => {
      if (depart !== null) return;
      this.indice = null;
      this.redessinerCurseur();
      this.surCurseur(null);
    });

    calque.addEventListener("mousedown", (e) => {
      const rect = calque.getBoundingClientRect();
      depart = e.clientX - rect.left;
    });

    window.addEventListener("mouseup", (e) => {
      if (depart === null) return;
      const rect = calque.getBoundingClientRect();
      const fin = e.clientX - rect.left;
      const largeur = Math.abs(fin - depart);
      if (largeur > 8) {
        const a = this.indiceDepuisX(graphe, Math.min(depart, fin));
        const b = this.indiceDepuisX(graphe, Math.max(depart, fin));
        this.zoomer(a, b);
      }
      depart = null;
      this.selection = null;
      this.redessinerCurseur();
    });

    calque.addEventListener("dblclick", () => this.reinitialiser());

    // Zoom molette. Le point sous le curseur doit rester SOUS le curseur :
    // c'est ce qui distingue un zoom d'un saut. Recentrer la vue sur la souris
    // à chaque cran, comme le faisait la première version, donne l'impression
    // que la vue part au hasard dès qu'on ne vise pas le milieu du graphique.
    calque.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const rect = calque.getBoundingClientRect();
        const proportion = this.proportionDepuisX(graphe, e.clientX - rect.left);
        const ancre = this.i0 + proportion * (this.i1 - this.i0);
        // On ne lit que le SIGNE de deltaY : son amplitude varie du tout au
        // tout entre une molette crantée et un pavé tactile.
        const facteur = e.deltaY > 0 ? 1.3 : 1 / 1.3;
        const largeur = (this.i1 - this.i0) * facteur;
        this.zoomer(ancre - proportion * largeur, ancre + (1 - proportion) * largeur);
      },
      { passive: false }
    );
  }

  // On fixe d'abord la LARGEUR de la fenêtre, puis on la fait glisser dans les
  // bornes. Rogner directement les deux extrémités, comme avant, rétrécissait
  // la fenêtre dès qu'on atteignait le début ou la fin du tour : le zoom
  // continuait de grossir alors qu'on demandait à dézoomer.
  zoomer(a, b) {
    const maximum = this.distance.nombre - 1;
    const largeur = Math.round(
      Math.min(maximum, Math.max(POINTS_MINIMUM, Math.abs(b - a)))
    );
    const i0 = Math.round(Math.max(0, Math.min(maximum - largeur, Math.min(a, b))));
    this.i0 = i0;
    this.i1 = i0 + largeur;
    this.redessiner();
    this.surVue(this.i0, this.i1);
  }

  reinitialiser() {
    this.i0 = 0;
    this.i1 = this.distance.nombre - 1;
    this.redessiner();
    this.surVue(this.i0, this.i1);
  }

  get zoome() {
    return this.i0 > 0 || this.i1 < this.distance.nombre - 1;
  }
}
