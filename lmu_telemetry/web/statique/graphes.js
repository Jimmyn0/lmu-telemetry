// Moteur de graphiques.
//
// Écrit à la main plutôt qu'emprunté à une bibliothèque : l'outil doit
// fonctionner hors ligne sans rien télécharger, et le besoin est étroit — des
// courbes empilées partageant un axe de distance, un curseur commun, un zoom.
//
// Toutes les courbes d'une pile partagent le même axe X (la distance) et le
// même curseur. C'est ce qui permet de lire d'un coup ce que faisaient les
// pédales à l'endroit précis où le delta décroche.

import { statistiques } from "/format.js";
import { t, locale } from "/i18n.js";

const MARGE_BAS_DERNIER = 18; // le dernier graphique porte l'axe des distances

// En dessous d'une vingtaine de points visibles, il n'y a plus rien à lire.
const POINTS_MINIMUM = 20;

// Les couleurs des graphiques sont celles de style.css : une seule palette
// pour la page et les tracés. Chaque entrée nomme sa variable CSS et une valeur
// de secours, utilisée si la feuille de style n'est pas (encore) chargée. Les
// valeurs sont en #rrggbb : les tracés y ajoutent leur transparence (« 33 »).
const PALETTE = {
  reference: ["--reference", "#a25ee8"],
  compare: ["--compare", "#ee8a35"],
  grille: ["--grille", "#26323e"],
  axe: ["--axe", "#8a99a8"],
  texte: ["--texte", "#eef2f6"],
  fond: ["--fond-graphe", "#16212d"],
  curseur: ["--curseur", "#ffffff"],
  perte: ["--perte", "#ef4465"],
  gain: ["--gain", "#22c55e"],
  record: ["--record", "#a25ee8"],
  accent: ["--accent", "#28c8f0"],
  bord: ["--bord-fort", "#3b4c5a"],
  route: ["--route", "#1a2531"],
  bordRoute: ["--bord-route", "#5f7d96"],
  bordRouteEstime: ["--bord-route-estime", "#3c4f60"],
  traceNeutre: ["--trace-neutre", "#5f7d96"],
  secteur1: ["--secteur-1", "#2898d0"],
  secteur2: ["--secteur-2", "#c8a818"],
  secteur3: ["--secteur-3", "#9f55d0"],
  interieur: ["--interieur-circuit", "#121921"],
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
export const POLICE = 'Bahnschrift, "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif';

// ---------------------------------------------------------------------
// Un graphique
// ---------------------------------------------------------------------

export class Graphe {
  constructor(canvas, options) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.unite = options.unite || "";
    this.series = options.series; // [{valeurs, couleur, epaisseur, tirets}]
    this.zero = options.zero || false; // axe symétrique autour de 0
    this.basZero = options.basZero || false; // axe qui part de 0
    this.remplirZero = options.remplirZero || false;
    this.escalier = options.escalier || false;
    this.dernier = false;
    this.min = options.min;
    this.max = options.max;
    this.decimales = options.decimales ?? 1;
    // `entier` : pour le rapport engagé, l'échelle tombe sur des valeurs entières.
    this.entier = options.entier || false;
    // Valeurs à écrire sur l'axe, si ce ne sont pas le haut, le milieu et le bas.
    this.echelle = options.echelle;
    this.reperes = [];
  }

  get margeBas() {
    return this.dernier ? MARGE_BAS_DERNIER : 0;
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
    if (this.entier) return [0, Math.ceil(haut)];
    if (this.zero) {
      const ampleur = Math.max(Math.abs(bas), Math.abs(haut), 0.01);
      return [-ampleur * 1.08, ampleur * 1.08];
    }
    if (this.basZero) return [0, haut * 1.04 || 1];
    const marge = (haut - bas) * 0.08 || 1;
    return [bas - marge, haut + marge];
  }

  dessiner(vue) {
    const { i0, i1 } = vue;
    const ctx = this.ctx;
    const ratio = window.devicePixelRatio || 1;
    const largeurCss = this.canvas.clientWidth;
    const hauteurCss = this.canvas.clientHeight;
    if (!largeurCss || !hauteurCss) return;
    this.canvas.width = largeurCss * ratio;
    this.canvas.height = hauteurCss * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

    const x0 = 0;
    const x1 = largeurCss;
    const y0 = 0;
    const y1 = hauteurCss - this.margeBas;
    this.zone = { x0, x1, y0, y1 };

    ctx.clearRect(0, 0, largeurCss, hauteurCss);

    const [bas, haut] = this.domaine(i0, i1);
    this.bas = bas;
    this.haut = haut;

    const versX = (i) => x0 + ((i - i0) / Math.max(1, i1 - i0)) * (x1 - x0);
    const versY = (v) => y1 - ((v - bas) / (haut - bas || 1)) * (y1 - y0);
    this.versX = versX;
    this.versY = versY;

    this.grille(ctx, vue);
    if (this.remplirZero) this.remplissage(ctx, vue, versX, versY);
    this.traits(ctx, vue);
    for (const serie of this.series) {
      this.courbe(ctx, serie, vue, versX, versY);
    }
    this.etiquettes(ctx);

    if (this.dernier) this.axeDistances(ctx, vue, versX, y1);
  }

  // Le repère reste discret : trois niveaux et quelques verticales suffisent à
  // situer une valeur, le reste se lit au curseur.
  grille(ctx, vue) {
    const { x0, x1, y0, y1 } = this.zone;
    ctx.strokeStyle = COULEURS.grille;
    ctx.lineWidth = 1;
    ctx.beginPath();
    const milieu = Math.round((y0 + y1) / 2) + 0.5;
    ctx.moveTo(x0, milieu);
    ctx.lineTo(x1, milieu);
    const d0 = vue.distance.debut + vue.i0 * vue.distance.pas;
    const d1 = vue.distance.debut + vue.i1 * vue.distance.pas;
    for (const d of graduations(d0, d1, 10)) {
      const x = Math.round(this.versX((d - vue.distance.debut) / vue.distance.pas)) + 0.5;
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
    }
    ctx.stroke();
  }

  // Les limites de secteur.
  traits(ctx) {
    const { y0, y1 } = this.zone;
    for (const { indice, couleur } of this.reperes) {
      const x = Math.round(this.versX(indice)) + 0.5;
      ctx.strokeStyle = couleur;
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  // Trois valeurs, posées sur le tracé et sur fond sombre : une courbe qui passe
  // derrière les rendrait sinon illisibles.
  etiquettes(ctx) {
    const { x0, y0, y1 } = this.zone;
    const milieu = (this.haut + this.bas) / 2;
    const libelle = (v) => `${formater(v, this.entier ? 0 : this.decimales)}${this.unite ? ` ${this.unite}` : ""}`;
    ctx.font = `600 9.5px ${POLICE}`;
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    const borner = (y) => Math.max(y0 + 8, Math.min(y1 - 8, y));
    const places = this.echelle
      ? this.echelle.map((v) => [v, borner(this.versY(v))])
      : [
          [this.haut, y0 + 8],
          [milieu, (y0 + y1) / 2],
          [this.bas, y1 - 8],
        ];
    for (const [valeur, y] of places) {
      const texte = libelle(valeur);
      const largeur = ctx.measureText(texte).width;
      ctx.fillStyle = COULEURS.fond + "e0";
      ctx.fillRect(x0 + 4, y - 6.5, largeur + 8, 13);
      ctx.fillStyle = COULEURS.axe;
      ctx.fillText(texte, x0 + 8, y + 0.5);
    }
  }

  // Tracé décimé : au-delà d'un point par pixel, on garde le minimum et le maximum
  // de chaque colonne. Prendre un point sur N ferait disparaître les pics de
  // freinage, qui sont précisément ce qu'on vient regarder. Le tout forme un seul
  // chemin : c'est ce qui permet au pointillé du tour comparé de rester régulier.
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
    ctx.lineWidth = serie.epaisseur || 1.5;
    ctx.lineJoin = "round";
    if (serie.tirets) ctx.setLineDash(serie.tirets);
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
      let commence = false;
      for (let colonne = 0; colonne < largeur; colonne++) {
        const debut = i0 + Math.floor(colonne * parPixel);
        const fin = Math.min(i1, i0 + Math.floor((colonne + 1) * parPixel));
        let bas = Infinity;
        let haut = -Infinity;
        let iBas = debut;
        let iHaut = debut;
        for (let i = debut; i <= fin; i++) {
          const v = serie.valeurs[i];
          if (v === null || v === undefined) continue;
          if (v < bas) { bas = v; iBas = i; }
          if (v > haut) { haut = v; iHaut = i; }
        }
        if (!Number.isFinite(bas)) continue;
        const x = x0 + colonne;
        const [a, b] = iBas <= iHaut ? [bas, haut] : [haut, bas];
        if (!commence) { ctx.moveTo(x, versY(a)); commence = true; }
        else ctx.lineTo(x, versY(a));
        if (a !== b) ctx.lineTo(x, versY(b));
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
    ctx.strokeStyle = COULEURS.axe + "80";
    ctx.beginPath();
    ctx.moveTo(x0, Math.round(yZero) + 0.5);
    ctx.lineTo(x1, Math.round(yZero) + 0.5);
    ctx.stroke();
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
    ctx.font = `500 10px ${POLICE}`;
    ctx.fillStyle = COULEURS.axe;
    ctx.textBaseline = "top";

    const libelle = t("graphe.axe_distance");
    // Le libellé occupe le bord droit : on n'y écrit pas de graduation, sinon
    // les deux se chevauchent dans une colonne étroite.
    const reserve = this.zone.x1 - ctx.measureText(libelle).width - 16;

    for (const d of graduations(d0, d1, 10)) {
      const i = (d - distance.debut) / distance.pas;
      if (i < i0 || i > i1) continue;
      const x = versX(i);
      if (x > reserve || x < 12) continue;
      ctx.textAlign = "center";
      ctx.fillText(`${Math.round(d)}`, x, y1 + 5);
    }
    ctx.textAlign = "right";
    ctx.fillText(libelle, this.zone.x1 - 6, y1 + 5);
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

function graduations(bas, haut, cible) {
  const brut = (haut - bas) / cible;
  const ordre = Math.pow(10, Math.floor(Math.log10(Math.abs(brut) || 1)));
  const pas = [1, 2, 2.5, 5, 10].map((m) => m * ordre).find((p) => p >= brut) || ordre;
  const debut = Math.ceil(bas / pas) * pas;
  const valeurs = [];
  for (let v = debut; v <= haut; v += pas) valeurs.push(Math.round(v / pas) * pas);
  return valeurs;
}

function formater(v, decimales) {
  if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString(locale());
  return v.toFixed(decimales);
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
    this.rangees = [];
    this.i0 = 0;
    this.i1 = distance.nombre - 1;
    this.indice = null;
    this.selection = null;
    this.fige = false;
    // Tous les écouteurs meurent avec la pile : les fenêtres gardent sinon ceux de
    // chaque comparaison ouverte depuis le lancement.
    this.abandon = new AbortController();
    window.addEventListener("resize", () => this.redessiner(), { signal: this.abandon.signal });
  }

  detruire() {
    this.abandon.abort();
    this.conteneur.innerHTML = "";
  }

  /**
   * Ajoute une rangée : la légende à gauche, le tracé à droite. La légende donne les
   * valeurs sous le curseur et le résumé de la portion visible.
   */
  ajouter(options, hauteur) {
    const rangee = document.createElement("div");
    rangee.className = "rangee-canal";
    rangee.dataset.cle = options.cle;
    const legende = document.createElement("div");
    legende.className = "legende";
    legende.innerHTML = `<div class="legende-titre">${options.titre}</div>${
      options.series
        .map(
          (s, k) => `<div class="legende-ligne ${s.classe || ""}"><i></i><span>${s.nom}</span>
            <b data-serie="${k}">--</b></div>`
        )
        .join("")
    }${options.stats === false ? (options.note ? `<div class="legende-note">${options.note}</div>` : "") : `
      <div class="legende-stats">
        <span><small>${t("tele.min")}</small><b data-stat="min"></b></span>
        <span><small>${t("tele.max")}</small><b data-stat="max"></b></span>
        <span><small>${t("tele.moy")}</small><b data-stat="moyenne" class="accent"></b></span>
      </div>`}`;

    const bloc = document.createElement("div");
    bloc.className = "graphe";
    bloc.style.height = `${hauteur}px`;
    const fond = document.createElement("canvas");
    const calque = document.createElement("canvas");
    calque.className = "calque";
    bloc.append(fond, calque);
    rangee.append(legende, bloc);
    this.conteneur.append(rangee);

    const graphe = new Graphe(fond, options);
    const entree = {
      graphe, calque, rangee, legende, cle: options.cle,
      decimales: options.decimales ?? 1,
      visible: true,
    };
    this.rangees.push(entree);
    this._brancher(calque, graphe);
    return graphe;
  }

  terminer() {
    this.redessiner();
    this.surVue(this.i0, this.i1);
  }

  get vue() {
    return { i0: this.i0, i1: this.i1, distance: this.distance };
  }

  get visibles() {
    return this.rangees.filter((r) => r.visible);
  }

  redessiner() {
    const visibles = this.visibles;
    visibles.forEach((r, k) => {
      r.graphe.dernier = k === visibles.length - 1;
      r.graphe.dessiner(this.vue);
    });
    this.majResumes();
    this.redessinerCurseur();
  }

  redessinerCurseur() {
    for (const r of this.visibles) {
      r.graphe.dessinerCurseur(r.calque, this.indice, this.selection);
    }
    this.majValeurs();
  }

  majValeurs() {
    for (const r of this.visibles) {
      for (const b of r.legende.querySelectorAll("[data-serie]")) {
        const v = this.indice === null ? null : r.graphe.series[+b.dataset.serie].valeurs[this.indice];
        b.textContent = v === null || v === undefined ? "--" : v.toFixed(r.decimales);
      }
    }
  }

  majResumes() {
    for (const r of this.visibles) {
      const champs = r.legende.querySelectorAll("[data-stat]");
      if (!champs.length) continue;
      const s = statistiques(r.graphe.series[0].valeurs, this.i0, this.i1);
      for (const b of champs) {
        b.textContent = s ? s[b.dataset.stat].toFixed(r.decimales) : "--";
      }
    }
  }

  /** Montre ou cache une rangée. */
  basculer(cle, visible) {
    const r = this.rangees.find((x) => x.cle === cle);
    if (!r) return;
    r.visible = visible;
    r.rangee.hidden = !visible;
    this.redessiner();
  }

  /** Traits verticaux posés sur tous les graphiques. */
  definirReperes(reperes) {
    for (const r of this.rangees) r.graphe.reperes = reperes;
    this.redessiner();
  }

  /** Place le curseur sans passer par la souris : la lecture du tour s'en sert. */
  placerCurseur(indice) {
    this.indice = indice;
    this.redessinerCurseur();
  }

  // Proportion de la zone de tracé sous une abscisse, bornée à [0, 1].
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
    const signal = this.abandon.signal;

    calque.addEventListener("mousemove", (e) => {
      if (this.fige) return;
      const rect = calque.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const i = this.indiceDepuisX(graphe, x);
      this.indice = Math.max(this.i0, Math.min(this.i1, i));
      this.selection = depart === null ? null : [depart, x];
      this.redessinerCurseur();
      this.surCurseur(this.indice);
    }, { signal });

    calque.addEventListener("mouseleave", () => {
      if (depart !== null || this.fige) return;
      this.indice = null;
      this.redessinerCurseur();
      this.surCurseur(null);
    }, { signal });

    calque.addEventListener("mousedown", (e) => {
      const rect = calque.getBoundingClientRect();
      depart = e.clientX - rect.left;
    }, { signal });

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
    }, { signal });

    calque.addEventListener("dblclick", () => this.reinitialiser(), { signal });

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
      { passive: false, signal }
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
