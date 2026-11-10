// Le rythme de deux pilotes, tour par tour (maquette 03) : leurs chronos sur un même
// graphique, et sous la souris, les deux temps du tour et l'écart.
//
// Comme `chronos.js`, des points sur un axe de numéros de tour. Un tour sans temps
// coupe la ligne. Un tour bien plus lent que les autres (le départ, un passage aux
// stands) est posé en haut du cadre : à l'échelle, il écraserait tous les autres.

import { chrono, signe } from "/format.js";
import { POLICE } from "/graphes.js";
import { t } from "/i18n.js";

const MARGE = { gauche: 64, droite: 18, haut: 24, bas: 30 };

// Un tour plus lent que le meilleur des deux de plus de 7 % sort de l'échelle.
const PLAFOND = 1.07;

export class GrapheRythme {
  constructor(canvas) {
    this.canvas = canvas;
    this.donnees = null;
    this.survol = null; // numéro du tour sous la souris
    canvas.onmousemove = (e) => {
      const tour = this.tourSous(e.offsetX);
      if (tour !== this.survol) {
        this.survol = tour;
        this.dessiner();
      }
    };
    canvas.onmouseleave = () => {
      this.survol = null;
      this.dessiner();
    };
    // La page se redimensionne : on redessine, tant que le graphique est affiché.
    const observateur = new ResizeObserver(() => {
      if (!canvas.isConnected) observateur.disconnect();
      else this.dessiner();
    });
    observateur.observe(canvas);
  }

  /** `donnees` : { series: [{ couleur, tours: [{ numero, chrono, stands }] }] x 2, couleurs } */
  afficher(donnees) {
    this.donnees = donnees;
    this.dessiner();
  }

  // Le cadre et l'échelle, recalculés à chaque dessin : la taille peut avoir changé.
  repere() {
    const largeur = this.canvas.clientWidth;
    const hauteur = this.canvas.clientHeight;
    const { series } = this.donnees;
    const valeurs = series.flatMap((s) => s.tours.map((x) => x.chrono).filter((v) => v !== null));
    const dernier = Math.max(1, ...series.flatMap((s) => s.tours.map((x) => x.numero)));
    const bas = valeurs.length ? Math.min(...valeurs) : 0;
    const haut = valeurs.length ? Math.min(Math.max(...valeurs), bas * PLAFOND) : 1;
    const marge = (haut - bas) * 0.12 || 0.5;
    const x0 = MARGE.gauche;
    const x1 = largeur - MARGE.droite;
    const y0 = MARGE.haut;
    const y1 = hauteur - MARGE.bas;
    return {
      largeur, hauteur, x0, x1, y0, y1, bas, haut, marge, dernier, vide: !valeurs.length,
      versX: (n) => (dernier === 1 ? (x0 + x1) / 2 : x0 + ((n - 1) / (dernier - 1)) * (x1 - x0)),
      versY: (v) => y1 - ((Math.min(v, haut + marge) - (bas - marge)) / (haut - bas + 2 * marge)) * (y1 - y0),
    };
  }

  tourSous(x) {
    if (!this.donnees) return null;
    const r = this.repere();
    if (x < r.x0 - 10 || x > r.x1 + 10) return null;
    const n = r.dernier === 1 ? 1 : Math.round(1 + ((x - r.x0) / (r.x1 - r.x0)) * (r.dernier - 1));
    return Math.min(Math.max(n, 1), r.dernier);
  }

  dessiner() {
    if (!this.donnees || !this.canvas.isConnected) return;
    const { series, couleurs } = this.donnees;
    const ctx = this.canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const r = this.repere();
    this.canvas.width = r.largeur * ratio;
    this.canvas.height = r.hauteur * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = couleurs.fond;
    ctx.fillRect(0, 0, r.largeur, r.hauteur);
    ctx.font = `10px ${POLICE}`;
    if (r.vide) {
      ctx.fillStyle = couleurs.axe;
      ctx.textAlign = "center";
      ctx.fillText(t("rythme.aucun_temps"), r.largeur / 2, r.hauteur / 2);
      return;
    }

    // --- graduations : les secondes, puis les numéros de tour ------------------
    const etendue = r.haut - r.bas + 2 * r.marge;
    const pas = [0.2, 0.5, 1, 2, 5, 10, 30].find((p) => etendue / p <= 6) || 60;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let v = Math.ceil((r.bas - r.marge) / pas) * pas; v <= r.haut + r.marge; v += pas) {
      const y = Math.round(r.versY(v)) + 0.5;
      ctx.strokeStyle = couleurs.grille;
      ctx.beginPath();
      ctx.moveTo(r.x0, y);
      ctx.lineTo(r.x1, y);
      ctx.stroke();
      ctx.fillStyle = couleurs.axe;
      ctx.fillText(chrono(v, 1), r.x0 - 8, y);
    }
    const ecartEtiquettes = Math.ceil(28 / Math.max(1, (r.x1 - r.x0) / Math.max(1, r.dernier - 1)));
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let n = 1; n <= r.dernier; n += 1) {
      if ((n - 1) % ecartEtiquettes && n !== r.dernier) continue;
      ctx.fillStyle = couleurs.axe;
      ctx.fillText(String(n), r.versX(n), r.y1 + 6);
    }
    ctx.textAlign = "right";
    ctx.fillText(t("chronos.axe_tours"), r.x1, r.y1 + 17);

    // --- le tour sous la souris --------------------------------------------------
    if (this.survol !== null) {
      ctx.strokeStyle = couleurs.curseur + "55";
      ctx.beginPath();
      ctx.moveTo(Math.round(r.versX(this.survol)) + 0.5, r.y0);
      ctx.lineTo(Math.round(r.versX(this.survol)) + 0.5, r.y1);
      ctx.stroke();
    }

    // --- les deux pilotes ----------------------------------------------------------
    series.forEach((serie, i) => this.dessinerSerie(ctx, r, serie, i === 0 ? -1 : 1));

    ctx.strokeStyle = couleurs.grille;
    ctx.lineWidth = 1;
    ctx.strokeRect(r.x0 + 0.5, r.y0 + 0.5, r.x1 - r.x0, r.y1 - r.y0);
    if (this.survol !== null) this.dessinerBulle(ctx, r);
  }

  // `cote` : -1, l'étiquette du meilleur tour au-dessus du point ; 1, en dessous.
  dessinerSerie(ctx, r, serie, cote) {
    const { couleurs } = this.donnees;
    const avecTemps = serie.tours.filter((x) => x.chrono !== null);
    const meilleur = avecTemps.length ? Math.min(...avecTemps.map((x) => x.chrono)) : null;
    ctx.strokeStyle = serie.couleur;
    ctx.lineWidth = 2;
    ctx.beginPath();
    let leve = true;
    for (const x of serie.tours) {
      if (x.chrono === null) {
        leve = true;
        continue;
      }
      const [px, py] = [r.versX(x.numero), r.versY(x.chrono)];
      leve ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
      leve = false;
    }
    ctx.stroke();

    for (const x of avecTemps) {
      const px = r.versX(x.numero);
      const py = r.versY(x.chrono);
      if (x.chrono > r.haut + r.marge) {
        // Hors échelle : un triangle pointé vers le haut, au bord du cadre.
        ctx.fillStyle = serie.couleur;
        ctx.beginPath();
        ctx.moveTo(px, r.y0 + 1);
        ctx.lineTo(px - 5, r.y0 + 9);
        ctx.lineTo(px + 5, r.y0 + 9);
        ctx.fill();
        continue;
      }
      const record = x.chrono === meilleur;
      ctx.beginPath();
      ctx.arc(px, py, record ? 5.5 : 3.5, 0, Math.PI * 2);
      if (x.stands) {
        // Un tour passé aux stands : un rond creux.
        ctx.fillStyle = couleurs.fond;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = serie.couleur;
        ctx.stroke();
      } else {
        ctx.fillStyle = serie.couleur;
        ctx.fill();
      }
      if (record) {
        this.etiquette(ctx, r, px, py + cote * 16, t("rythme.meilleur").toUpperCase(), serie.couleur);
      }
    }
  }

  etiquette(ctx, r, x, y, texte, couleur) {
    ctx.font = `bold 9.5px ${POLICE}`;
    const largeur = ctx.measureText(texte).width + 10;
    const gauche = Math.min(Math.max(x - largeur / 2, r.x0 + 2), r.x1 - largeur - 2);
    const haut = Math.min(Math.max(y - 8, r.y0 + 2), r.y1 - 18);
    ctx.fillStyle = this.donnees.couleurs.fond + "ee";
    ctx.strokeStyle = couleur;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(gauche, haut, largeur, 16, 4);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = couleur;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(texte, gauche + 5, haut + 8.5);
    ctx.font = `10px ${POLICE}`;
  }

  // La bulle du tour sous la souris : les deux temps, et l'écart du premier sur le second.
  dessinerBulle(ctx, r) {
    const { series, couleurs } = this.donnees;
    const temps = series.map((s) => s.tours.find((x) => x.numero === this.survol)?.chrono ?? null);
    const lignes = [
      { texte: t("rythme.tour", { n: this.survol }), couleur: couleurs.texte },
      ...series.map((s, i) => ({ texte: chrono(temps[i]), couleur: s.couleur })),
    ];
    if (temps[0] !== null && temps[1] !== null) {
      const ecart = temps[0] - temps[1];
      lignes.push({
        texte: t("rythme.ecart", { ecart: signe(ecart) }),
        couleur: ecart < 0 ? couleurs.gain : ecart > 0 ? couleurs.perte : couleurs.texte,
      });
    }
    ctx.font = `bold 11px ${POLICE}`;
    const largeur = Math.max(...lignes.map((l) => ctx.measureText(l.texte).width)) + 20;
    const hauteur = lignes.length * 16 + 10;
    const x = r.versX(this.survol);
    const gauche = x + 12 + largeur > r.x1 ? x - 12 - largeur : x + 12;
    ctx.fillStyle = couleurs.fond + "f2";
    ctx.strokeStyle = couleurs.bord;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(gauche, r.y0 + 6, largeur, hauteur, 6);
    ctx.fill();
    ctx.stroke();
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    lignes.forEach((l, i) => {
      ctx.fillStyle = l.couleur;
      ctx.fillText(l.texte, gauche + 10, r.y0 + 6 + 13 + i * 16);
    });
    ctx.font = `10px ${POLICE}`;
  }
}
