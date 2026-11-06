// Overlay : l'état du jeu, tel que le voit l'outil.
//
// L'overlay lui-même vient à l'étape suivante. Cet écran dit déjà si la mémoire
// partagée est accessible : c'est la première chose à vérifier.

import { $, api, etatVide } from "/commun.js";
import { echapper } from "/emblemes.js";
import { ICONES } from "/icones.js";
import { t } from "/i18n.js";

const FREQUENCE_MS = 2000;
let suivi = null;

function afficher(jeu) {
  const cible = $("#ecran-overlay");
  let etatJeu;
  if (!jeu.detecte) {
    etatJeu = jeu.format_inconnu
      ? etatVide({
          icone: "avertissement", titre: t("overlay.format_inconnu"),
          texte: t("overlay.format_inconnu_texte"),
        })
      : etatVide({
          icone: "jeu", titre: t("overlay.absent"), texte: t("overlay.absent_texte"),
        });
  } else {
    etatJeu = `<div class="carte jeu-detecte">
      <span class="voyant"></span>
      <div>
        <strong>${t(jeu.en_piste ? "overlay.en_piste" : "overlay.menu")}</strong>
        <small>${
          jeu.circuit ? `${echapper(jeu.circuit)} · ${echapper(jeu.modele || "")}` : t("overlay.detecte")
        }</small>
      </div>
    </div>`;
  }
  cible.innerHTML = `
    ${etatJeu}
    <h3 class="titre-section">${t("overlay.apercu")}</h3>
    <div class="scene-overlay">
      <div class="message-overlay">
        <span class="virage">${t("overlay.exemple_virage")}</span>
        <b class="moins">−0,12 s</b>
        <span class="conseil">${ICONES.chrono}${t("overlay.exemple_conseil")}</span>
      </div>
    </div>
    <p class="note">${t("overlay.bientot")}</p>`;
}

async function verifier() {
  try {
    afficher(await api("/api/jeu"));
  } catch {
    afficher({ detecte: false });
  }
}

export function ouvrirOverlay() {
  arreterOverlay();
  verifier();
  suivi = setInterval(verifier, FREQUENCE_MS);
}

export function arreterOverlay() {
  clearInterval(suivi);
  suivi = null;
}
