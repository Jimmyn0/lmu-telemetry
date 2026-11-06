// La fenêtre sans bordure : barre de titre, bords et boutons.
//
// Dans un navigateur, `window.pywebview` n'existe pas : rien de tout ça n'apparaît,
// et la page reste utilisable telle quelle.

import { $, $$ } from "/commun.js";
import { ICONES } from "/icones.js";
import { t } from "/i18n.js";

function surEnfoncement(element, geste) {
  element.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    geste(e);
  });
}

function brancher(fenetre) {
  document.body.classList.add("fenetre-native");
  $("#controles-fenetre").hidden = false;
  $("#poignees").hidden = false;
  $("#fenetre-reduire").innerHTML = ICONES.reduire;
  $("#fenetre-fermer").innerHTML = ICONES.fermer;

  const majAgrandir = (agrandie) => {
    $("#fenetre-agrandir").innerHTML = agrandie ? ICONES.restaurer : ICONES.agrandir;
    $("#fenetre-agrandir").title = t(agrandie ? "fenetre.restaurer" : "fenetre.agrandir");
    document.body.classList.toggle("fenetre-agrandie", agrandie);
  };
  fenetre.agrandie().then(majAgrandir);

  const agrandir = () => fenetre.agrandir().then(majAgrandir);
  $("#fenetre-reduire").onclick = () => fenetre.reduire();
  $("#fenetre-agrandir").onclick = agrandir;
  $("#fenetre-fermer").onclick = () => fenetre.fermer();

  // La barre de titre : tout ce qui n'est pas un bouton sert à déplacer la fenêtre.
  const barre = $("#barre-titre");
  surEnfoncement(barre, (e) => {
    if (e.target.closest("button")) return;
    fenetre.deplacer().then(() => fenetre.agrandie().then(majAgrandir));
  });
  barre.addEventListener("dblclick", (e) => {
    if (!e.target.closest("button")) agrandir();
  });

  for (const poignee of $$("#poignees [data-bord]")) {
    surEnfoncement(poignee, () => fenetre.redimensionner(poignee.dataset.bord));
  }
}

export function preparerFenetre() {
  if (window.pywebview?.api) brancher(window.pywebview.api);
  else window.addEventListener("pywebviewready", () => brancher(window.pywebview.api));
}
