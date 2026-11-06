// Icônes de l'interface, dessinées ici : l'outil fonctionne sans connexion.

const icone = (contenu, plein = false) =>
  `<svg class="icone" viewBox="0 0 24 24" aria-hidden="true" fill="${
    plein ? "currentColor" : "none"
  }" stroke="${plein ? "none" : "currentColor"}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${contenu}</svg>`;

export const ICONES = {
  menu: icone(`<path d="M3 6h18M3 12h18M3 18h18"/>`),
  reglages: icone(
    `<path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z" fill="var(--fond-barre)" stroke="none"/><path fill="currentColor" stroke="none" d="M19.4 13a7.6 7.6 0 0 0 0-2l2-1.6-2-3.4-2.4.9a7.6 7.6 0 0 0-1.7-1L15 3.3h-4l-.4 2.6a7.6 7.6 0 0 0-1.7 1L6.6 6l-2 3.4 2 1.6a7.6 7.6 0 0 0 0 2l-2 1.6 2 3.4 2.4-.9a7.6 7.6 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7.6 7.6 0 0 0 1.7-1l2.4.9 2-3.4-2-1.6ZM13 15.4a3.5 3.5 0 1 1 0-6.8 3.5 3.5 0 0 1 0 6.8Z"/>`
  ),
  reduire: icone(`<path d="M5 12h14"/>`),
  agrandir: icone(`<rect x="5" y="5" width="14" height="14" rx="1"/>`),
  restaurer: icone(`<path d="M8 8V5h11v11h-3"/><rect x="5" y="8" width="11" height="11" rx="1"/>`),
  fermer: icone(`<path d="M6 6l12 12M18 6 6 18"/>`),
  calendrier: icone(`<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>`),
  courbe: icone(`<path d="M3 20h18"/><path d="m4 15 5-6 4 4 7-8"/>`),
  chrono: icone(`<circle cx="12" cy="14" r="7"/><path d="M12 10v4l2 2M9 3h6M12 3v3"/>`),
  lien: icone(`<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>`),
  lecture: icone(`<path d="M7 4.5v15l13-7.5-13-7.5Z"/>`, true),
  pause: icone(`<rect x="6" y="4" width="4.5" height="16" rx="1"/><rect x="13.5" y="4" width="4.5" height="16" rx="1"/>`, true),
  delta: icone(`<path d="m3 12 3-5 4 8 3-6 3 5 2-3 3 1"/><path d="M3 20h18" stroke-dasharray="3 3"/>`),
  filtre: icone(`<path d="M4 5h16l-6 8v5l-4 2v-7L4 5Z"/>`),
  secteurs: icone(`<path d="M4 7h16" stroke="var(--vert)"/><path d="M4 12h16" stroke="var(--rouge)"/><path d="M4 17h16"/>`),
  plein: icone(`<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>`),
  gauche: icone(`<path d="M9 18V8h9"/><path d="m12 11-3-3-3 3" transform="rotate(-90 9 8) translate(0 0)"/>`),
  avertissement: icone(`<path d="M12 4 2.5 20h19L12 4Z"/><path d="M12 10v5M12 17.5v.5"/>`),
  jeu: icone(`<rect x="3" y="7" width="18" height="11" rx="4"/><path d="M8 11v3M6.5 12.5h3M15.5 11.5h.01M18 13.5h.01"/>`),
};
