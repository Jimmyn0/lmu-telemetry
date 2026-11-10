// L'évolution des positions d'une course (maquette 04) : une ligne par voiture, de la
// grille à l'arrivée, la première place en haut.
//
// Les lignes se croisent sans cesse : la voiture sous la souris, ou désignée dans la
// liste, passe devant les autres, qui s'estompent.

import { POLICE } from "/graphes.js";
import { t } from "/i18n.js";

const MARGE = { gauche: 46, droite: 22, haut: 16, bas: 30 };

// Distance (px) en deçà de laquelle la souris désigne une voiture.
const PORTEE = 12;

export class GraphePositions {
  /** `surSurvol(rang)` : prévient la liste quand la souris désigne une voiture du graphique. */
  constructor(canvas, { surSurvol } = {}) {
    this.canvas = canvas;
    this.donnees = null;
    this.survol = null; // rang de la voiture désignée, dans le graphique ou dans la liste
    this.enAvant = null; // rang de la voiture mise en avant quand rien n'est désigné
    this.surSurvol = surSurvol;
    canvas.onmousemove = (e) => this.designer(this.voitureSous(e.offsetX, e.offsetY), true);
    canvas.onmouseleave = () => this.designer(null, true);
    const observateur = new ResizeObserver(() => {
      if (!canvas.isConnected) observateur.disconnect();
      else this.dessiner();
    });
    observateur.observe(canvas);
  }

  /** `donnees` : { voitures: [{ rang, nom, couleur, abandon, points: [[x, place]] }], places, tours, couleurs } */
  afficher(donnees) {
    this.donnees = donnees;
    this.dessiner();
  }

  designer(rang, depuisGraphe = false) {
    if (rang === this.survol) return;
    this.survol = rang;
    this.dessiner();
    if (depuisGraphe && this.surSurvol) this.surSurvol(rang);
  }

  mettreEnAvant(rang) {
    this.enAvant = rang;
    this.dessiner();
  }

  // x vaut 0 sur la grille, n au tour n, et `tours + 1` à l'arrivée.
  repere() {
    const largeur = this.canvas.clientWidth;
    const hauteur = this.canvas.clientHeight;
    const { places, tours } = this.donnees;
    const x0 = MARGE.gauche;
    const x1 = largeur - MARGE.droite;
    const y0 = MARGE.haut;
    const y1 = hauteur - MARGE.bas;
    return {
      largeur, hauteur, x0, x1, y0, y1,
      versX: (x) => x0 + (x / Math.max(1, tours + 1)) * (x1 - x0),
      versY: (place) => (places <= 1 ? (y0 + y1) / 2 : y0 + ((place - 1) / (places - 1)) * (y1 - y0)),
    };
  }

  voitureSous(x, y) {
    if (!this.donnees) return null;
    const r = this.repere();
    const colonne = Math.round(((x - r.x0) / (r.x1 - r.x0)) * (this.donnees.tours + 1));
    let trouvee = null;
    let distance = PORTEE;
    for (const v of this.donnees.voitures) {
      const point = v.points.find(([px]) => px === colonne);
      if (!point) continue;
      const d = Math.abs(r.versY(point[1]) - y);
      if (d < distance) {
        distance = d;
        trouvee = v.rang;
      }
    }
    return trouvee;
  }

  dessiner() {
    if (!this.donnees || !this.canvas.isConnected) return;
    const { voitures, places, tours, couleurs } = this.donnees;
    const ctx = this.canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const r = this.repere();
    this.canvas.width = r.largeur * ratio;
    this.canvas.height = r.hauteur * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = couleurs.fond;
    ctx.fillRect(0, 0, r.largeur, r.hauteur);
    ctx.font = `10px ${POLICE}`;

    // --- les places, de haut en bas ----------------------------------------------
    const pasPlaces = places > 24 ? 2 : 1;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let place = 1; place <= places; place += 1) {
      const y = Math.round(r.versY(place)) + 0.5;
      ctx.strokeStyle = couleurs.grille;
      ctx.beginPath();
      ctx.moveTo(r.x0, y);
      ctx.lineTo(r.x1, y);
      ctx.stroke();
      if ((place - 1) % pasPlaces === 0 || place === places) {
        ctx.fillStyle = couleurs.axe;
        ctx.fillText(`P${place}`, r.x0 - 10, y);
      }
    }

    // --- la grille, chaque tour, l'arrivée ---------------------------------------
    const largeurTour = (r.x1 - r.x0) / Math.max(1, tours + 1);
    const pasTours = Math.max(1, Math.ceil(26 / largeurTour));
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let x = 0; x <= tours + 1; x += 1) {
      const etiquette =
        x === 0 ? t("positions.grille") : x === tours + 1 ? t("positions.arrivee") : x % pasTours ? "" : String(x);
      if (!etiquette) continue;
      ctx.fillStyle = couleurs.axe;
      ctx.fillText(etiquette, r.versX(x), r.y1 + 8);
    }

    // --- les voitures : la désignée par-dessus les autres ----------------------
    const designee = this.survol ?? this.enAvant;
    const ordre = [...voitures].sort((a, b) => (a.rang === designee) - (b.rang === designee));
    for (const v of ordre) {
      const enRelief = v.rang === designee;
      ctx.globalAlpha = designee === null || enRelief ? 1 : 0.22;
      ctx.strokeStyle = v.couleur;
      ctx.lineWidth = enRelief ? 3.5 : v.joueur ? 3 : 2;
      ctx.lineJoin = "round";
      ctx.beginPath();
      v.points.forEach(([x, place], i) => {
        const [px, py] = [r.versX(x), r.versY(place)];
        i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
      });
      ctx.stroke();
      const dernier = v.points[v.points.length - 1];
      if (v.abandon && dernier) {
        // Un abandon : une croix au dernier tour bouclé.
        const [px, py] = [r.versX(dernier[0]), r.versY(dernier[1])];
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(px - 4, py - 4);
        ctx.lineTo(px + 4, py + 4);
        ctx.moveTo(px + 4, py - 4);
        ctx.lineTo(px - 4, py + 4);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    ctx.strokeStyle = couleurs.grille;
    ctx.lineWidth = 1;
    ctx.strokeRect(r.x0 + 0.5, r.y0 - 6.5, r.x1 - r.x0, r.y1 - r.y0 + 12);
    if (designee !== null) this.etiquette(ctx, r, voitures.find((v) => v.rang === designee));
  }

  // Le nom de la voiture désignée, au bout de sa ligne.
  etiquette(ctx, r, v) {
    const dernier = v?.points[v.points.length - 1];
    if (!dernier) return;
    const texte = `${v.nom} · P${dernier[1]}`;
    ctx.font = `bold 11px ${POLICE}`;
    const largeur = ctx.measureText(texte).width + 12;
    const x = Math.min(r.versX(dernier[0]) - largeur - 8, r.x1 - largeur - 2);
    const y = Math.min(Math.max(r.versY(dernier[1]) - 10, r.y0 - 4), r.y1 - 16);
    ctx.fillStyle = this.donnees.couleurs.fond + "f0";
    ctx.strokeStyle = v.couleur;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(Math.max(x, r.x0 + 2), y, largeur, 20, 5);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = v.couleur;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(texte, Math.max(x, r.x0 + 2) + 6, y + 10.5);
    ctx.font = `10px ${POLICE}`;
  }
}
