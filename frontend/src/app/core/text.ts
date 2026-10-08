/** Texte comparable sans tenir compte des accents ni de la casse : « ingenieur » trouve « Ingénieur ». */
export function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase();
}

/** Site d'une page, pour l'affichage : « welcometothejungle.com ». */
export function siteOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}
