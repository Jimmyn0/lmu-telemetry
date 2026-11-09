// Ingénieur : l'état du jeu, tel que le voit l'outil.
//
// L'ingénieur de course vient dans les étapes suivantes. Cet écran dit déjà si le jeu
// tourne et si sa mémoire partagée est accessible : c'est la première chose à vérifier.

import { $, api, etatVide } from "/commun.js";
import { echapper } from "/emblemes.js";
import { t } from "/i18n.js";

const FREQUENCE_MS = 2000;
let suivi = null;

function afficher(jeu) {
  const cible = $("#ecran-ingenieur");
  let etatJeu;
  if (!jeu.detecte) {
    etatJeu = jeu.format_inconnu
      ? etatVide({
          icone: "avertissement", titre: t("ingenieur.format_inconnu"),
          texte: t("ingenieur.format_inconnu_texte"),
        })
      : etatVide({
          icone: "jeu", titre: t("ingenieur.absent"), texte: t("ingenieur.absent_texte"),
        });
  } else {
    etatJeu = `<div class="carte jeu-detecte">
      <span class="voyant"></span>
      <div>
        <strong>${t(jeu.en_piste ? "ingenieur.en_piste" : "ingenieur.menu")}</strong>
        <small>${
          jeu.circuit ? `${echapper(jeu.circuit)} · ${echapper(jeu.modele || "")}` : t("ingenieur.detecte")
        }</small>
      </div>
    </div>`;
  }
  cible.innerHTML = `
    ${etatJeu}
    <p class="note">${t("ingenieur.bientot")}</p>`;
}

async function verifier() {
  try {
    afficher(await api("/api/jeu"));
  } catch {
    afficher({ detecte: false });
  }
}

export function ouvrirIngenieur() {
  arreterIngenieur();
  verifier();
  suivi = setInterval(verifier, FREQUENCE_MS);
}

export function arreterIngenieur() {
  clearInterval(suivi);
  suivi = null;
}
