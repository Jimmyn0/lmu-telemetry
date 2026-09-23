// Graphique des chronos d'une session : un point par tour, plus les repères
// qui donnent l'échelle — meilleur tour, tour médian, tour idéal.
//
// Écrit à part du moteur de `graphes.js` : celui-ci trace des courbes sur un axe
// de distance partagé, ici on veut des points sur un axe de numéros de tour.
// Deux besoins différents, deux morceaux de code simples plutôt qu'un seul
// compliqué.

import { POLICE } from "/graphes.js";

const MARGE = { gauche: 66, droite: 16, haut: 14, bas: 30 };

export function dessinerChronos(canvas, donnees, couleurs) {
  const { tours, meilleur, median, ideal } = donnees;
  const ctx = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const largeur = canvas.clientWidth;
  const hauteur = canvas.clientHeight;
  canvas.width = largeur * ratio;
  canvas.height = hauteur * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, largeur, hauteur);

  const x0 = MARGE.gauche;
  const x1 = largeur - MARGE.droite;
  const y0 = MARGE.haut;
  const y1 = hauteur - MARGE.bas;

  // L'échelle part du tour idéal : sans lui en bas du cadre, on ne verrait pas
  // l'écart qui sépare le meilleur tour de ce que la régularité rapporterait.
  const valeurs = tours.map((t) => t.chrono);
  const bas = Math.min(ideal, ...valeurs);
  const haut = Math.max(...valeurs);
  const marge = (haut - bas) * 0.12 || 0.5;
  const versY = (v) => y1 - ((v - (bas - marge)) / (haut - bas + 2 * marge)) * (y1 - y0);
  const versX = (i) =>
    tours.length === 1 ? (x0 + x1) / 2 : x0 + (i / (tours.length - 1)) * (x1 - x0);

  ctx.fillStyle = couleurs.fond;
  ctx.fillRect(0, 0, largeur, hauteur);

  // --- graduations verticales, en secondes ---------------------------
  const etendue = haut - bas + 2 * marge;
  const pas = [0.2, 0.5, 1, 2, 5, 10, 30].find((p) => etendue / p <= 6) || 60;
  ctx.font = `10px ${POLICE}`;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let v = Math.ceil((bas - marge) / pas) * pas; v <= haut + marge; v += pas) {
    const y = versY(v);
    ctx.strokeStyle = couleurs.grille;
    ctx.beginPath();
    ctx.moveTo(x0, Math.round(y) + 0.5);
    ctx.lineTo(x1, Math.round(y) + 0.5);
    ctx.stroke();
    ctx.fillStyle = couleurs.axe;
    ctx.fillText(formaterChrono(v), x0 - 8, y);
  }

  // --- repères horizontaux -------------------------------------------
  // Les trois repères sont souvent à quelques dixièmes les uns des autres : on
  // décale leurs libellés horizontalement, sinon ils se superposent.
  const reperes = [
    { valeur: ideal, couleur: couleurs.gain, texte: "tour idéal", decalage: 6 },
    { valeur: meilleur, couleur: couleurs.record, texte: "meilleur", decalage: 82 },
    { valeur: median, couleur: couleurs.compare, texte: "médian", decalage: 148 },
  ];
  for (const r of reperes) {
    const y = Math.round(versY(r.valeur)) + 0.5;
    ctx.strokeStyle = r.couleur;
    ctx.globalAlpha = 0.55;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(x0, y);
    ctx.lineTo(x1, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    // Un fond derrière le libellé : il se pose sur des lignes de grille.
    const x = x0 + r.decalage;
    const largeurTexte = ctx.measureText(r.texte).width;
    ctx.fillStyle = couleurs.fond + "e6";
    ctx.fillRect(x - 2, y - 14, largeurTexte + 4, 12);
    ctx.fillStyle = r.couleur;
    ctx.fillText(r.texte, x, y - 3);
  }

  // --- les tours ------------------------------------------------------
  ctx.strokeStyle = couleurs.reference;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  tours.forEach((t, i) => {
    const x = versX(i);
    const y = versY(t.chrono);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  tours.forEach((t, i) => {
    const x = versX(i);
    const y = versY(t.chrono);
    ctx.fillStyle = t.chrono === meilleur ? couleurs.record : couleurs.reference;
    ctx.beginPath();
    ctx.arc(x, y, t.chrono === meilleur ? 5 : 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = couleurs.axe;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(String(t.numero), x, y1 + 6);
  });

  ctx.fillStyle = couleurs.axe;
  ctx.textAlign = "right";
  ctx.fillText("n° de tour", x1, y1 + 17);

  ctx.strokeStyle = couleurs.grille;
  ctx.lineWidth = 1;
  ctx.strokeRect(x0 + 0.5, y0 + 0.5, x1 - x0, y1 - y0);
}

function formaterChrono(secondes) {
  const minutes = Math.floor(secondes / 60);
  const reste = secondes - minutes * 60;
  return `${minutes}:${reste.toFixed(1).padStart(4, "0")}`;
}
