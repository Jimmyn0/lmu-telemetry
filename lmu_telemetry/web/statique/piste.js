// Vue rapprochée de la route.
//
// Montre la portion de circuit autour du curseur, orientée dans le sens de
// marche, avec les deux trajectoires et la position des deux voitures. C'est ce
// qui permet de voir OÙ passe chaque tour — la courbe de delta dit combien on
// perd, celle-ci dit pourquoi.
//
// La géométrie vient du serveur (voir lmu_telemetry/piste.py) : axe de la
// piste, deux bords, et les deux trajectoires, le tout en mètres dans un repère
// local commun.

import { POLICE } from "/graphes.js";

const MARGE = 18;

export class VuePiste {
  constructor(canvas, piste, couleurs) {
    this.canvas = canvas;
    this.piste = piste;
    this.couleurs = couleurs;
    this.fenetre = 80; // mètres de piste visibles
    this.indice = null;
  }

  /** Longueur de piste affichée, en mètres. */
  regler(fenetre) {
    this.fenetre = fenetre;
    this.dessiner(this.indice);
  }

  dessiner(indice) {
    this.indice = indice;
    const p = this.piste;
    const n = p.axe.x.length;
    const centre = Math.max(0, Math.min(n - 1, indice ?? Math.round(n / 2)));

    const ctx = this.canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const largeur = this.canvas.clientWidth;
    const hauteur = this.canvas.clientHeight;
    this.canvas.width = largeur * ratio;
    this.canvas.height = hauteur * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, largeur, hauteur);

    // Fenêtre de points. La grille vaut un point par mètre : la demi-fenêtre en
    // indices est donc la demi-fenêtre en mètres.
    const demi = Math.round(this.fenetre / 2);
    const i0 = Math.max(0, centre - demi);
    const i1 = Math.min(n - 1, centre + demi);

    // Orientation : la tangente à l'axe, au point du curseur, pointe vers le
    // haut de l'écran. On voit ainsi la route comme depuis la voiture.
    const base = Math.max(i0, Math.min(i1 - 1, centre));
    const suivant = Math.min(n - 1, base + Math.max(1, Math.round(this.fenetre / 20)));
    const dx = p.axe.x[suivant] - p.axe.x[base];
    const dy = p.axe.y[suivant] - p.axe.y[base];
    const angle = Math.atan2(dy, dx) - Math.PI / 2;
    const cos = Math.cos(-angle);
    const sin = Math.sin(-angle);

    const cx = p.axe.x[centre];
    const cy = p.axe.y[centre];

    // L'échelle doit tenir compte des DEUX dimensions. Sur la hauteur, on veut
    // voir `fenetre` mètres de piste. Mais dans un virage, la portion visible
    // s'étale aussi latéralement, parfois sur plus que la largeur disponible :
    // on garde alors la plus contraignante des deux échelles.
    const lateral = (x, y) => (x - cx) * cos - (y - cy) * sin;
    let ecart = 0;
    for (let i = i0; i <= i1; i++) {
      ecart = Math.max(
        ecart,
        Math.abs(lateral(p.bord_gauche.x[i], p.bord_gauche.y[i])),
        Math.abs(lateral(p.bord_droit.x[i], p.bord_droit.y[i]))
      );
    }
    const echelle = Math.min(
      (hauteur - 2 * MARGE) / this.fenetre,
      (largeur / 2 - MARGE) / Math.max(ecart, 6)
    );
    const versEcran = (x, y) => {
      const ax = x - cx;
      const ay = y - cy;
      // Rotation, puis inversion de l'axe vertical (le canvas descend).
      return [
        largeur / 2 + (ax * cos - ay * sin) * echelle,
        hauteur * 0.62 - (ax * sin + ay * cos) * echelle,
      ];
    };
    this.versEcran = versEcran;

    this._corridor(ctx, i0, i1, versEcran);
    this._axe(ctx, i0, i1, versEcran);
    this._trace(ctx, p.trace_reference, i0, i1, versEcran, this.couleurs.reference);
    this._trace(ctx, p.trace_compare, i0, i1, versEcran, this.couleurs.compare);

    if (indice !== null) {
      this._voiture(ctx, p.trace_reference, centre, versEcran, this.couleurs.reference);
      this._voiture(ctx, p.trace_compare, centre, versEcran, this.couleurs.compare);
    }
    this._echelle(ctx, largeur, hauteur, echelle);
  }

  _chemin(ctx, serie, i0, i1, versEcran) {
    ctx.beginPath();
    for (let i = i0; i <= i1; i++) {
      const [x, y] = versEcran(serie.x[i], serie.y[i]);
      if (i === i0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
  }

  // Le bitume, plus les deux bords. Un bord estimé — là où aucun des deux tours
  // n'est passé de ce côté — est dessiné en pointillé : il est interpolé entre
  // ses mesures d'avant et d'après, ce n'est pas une mesure de cet endroit.
  //
  // Chaque bord suit SON indicateur de mesure. Avec un seul indicateur commun,
  // un bord réellement longé s'affichait en pointillé dès que l'autre ne
  // l'était pas — le bord extérieur de l'épingle de Long Beach, par exemple.
  _corridor(ctx, i0, i1, versEcran) {
    const p = this.piste;
    ctx.beginPath();
    for (let i = i0; i <= i1; i++) {
      const [x, y] = versEcran(p.bord_gauche.x[i], p.bord_gauche.y[i]);
      if (i === i0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    for (let i = i1; i >= i0; i--) {
      const [x, y] = versEcran(p.bord_droit.x[i], p.bord_droit.y[i]);
      ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fillStyle = this.couleurs.route;
    ctx.fill();

    // Un serveur plus ancien n'envoie que l'indicateur commun : on s'en sert.
    const bords = [
      [p.bord_gauche, p.mesure_gauche || p.mesure],
      [p.bord_droit, p.mesure_droit || p.mesure],
    ];
    for (const [bord, mesure] of bords) {
      // On coupe le tracé en segments continus selon que le bord est mesuré.
      let debut = i0;
      for (let i = i0 + 1; i <= i1; i++) {
        const rupture = i === i1 || mesure[i] !== mesure[debut];
        if (!rupture) continue;
        ctx.setLineDash(mesure[debut] ? [] : [4, 4]);
        ctx.strokeStyle = mesure[debut] ? this.couleurs.bordRoute : this.couleurs.bordRouteEstime;
        ctx.lineWidth = 1.4;
        this._chemin(ctx, bord, debut, i, versEcran);
        ctx.stroke();
        debut = i;
      }
    }
    ctx.setLineDash([]);
  }

  _axe(ctx, i0, i1, versEcran) {
    ctx.setLineDash([6, 7]);
    ctx.strokeStyle = this.couleurs.bordRoute + "55";
    ctx.lineWidth = 1;
    this._chemin(ctx, this.piste.axe, i0, i1, versEcran);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  _trace(ctx, serie, i0, i1, versEcran, couleur) {
    ctx.strokeStyle = couleur;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    this._chemin(ctx, serie, i0, i1, versEcran);
    ctx.stroke();
  }

  // Un rectangle orienté selon la direction locale de la trajectoire : à cette
  // échelle, une voiture fait environ 4,5 m de long sur 2 m de large.
  _voiture(ctx, serie, i, versEcran, couleur) {
    const n = serie.x.length;
    const a = Math.max(0, i - 3);
    const b = Math.min(n - 1, i + 3);
    const [xa, ya] = versEcran(serie.x[a], serie.y[a]);
    const [xb, yb] = versEcran(serie.x[b], serie.y[b]);
    const [x, y] = versEcran(serie.x[i], serie.y[i]);
    const angle = Math.atan2(yb - ya, xb - xa);

    const echelle = Math.hypot(xb - xa, yb - ya) / Math.max(1, b - a);
    const longueur = Math.max(9, 4.5 * echelle);
    const largeur = Math.max(4, 2.0 * echelle);

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.fillStyle = couleur;
    ctx.strokeStyle = this.couleurs.fond;
    ctx.lineWidth = 1.2;
    const r = Math.min(3, largeur / 2);
    ctx.beginPath();
    ctx.roundRect(-longueur / 2, -largeur / 2, longueur, largeur, r);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }

  _echelle(ctx, largeur, hauteur, echelle) {
    const metres = 20;
    const px = metres * echelle;
    const x = largeur - MARGE - px;
    const y = hauteur - 12;
    ctx.strokeStyle = this.couleurs.axe;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + px, y);
    ctx.moveTo(x, y - 3);
    ctx.lineTo(x, y + 3);
    ctx.moveTo(x + px, y - 3);
    ctx.lineTo(x + px, y + 3);
    ctx.stroke();
    ctx.fillStyle = this.couleurs.axe;
    ctx.font = `10px ${POLICE}`;
    ctx.textAlign = "center";
    ctx.fillText(`${metres} m`, x + px / 2, y - 6);
  }
}
