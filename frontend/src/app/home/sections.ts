/** Sections de la page d'accueil, dans l'ordre de la navigation. */
export const SECTIONS = [
  { id: 'fonctionnalites', label: 'Fonctionnalités' },
  { id: 'etapes', label: 'Comment ça marche' },
  { id: 'apercu', label: 'Aperçu' },
  { id: 'donnees', label: 'Vos données' },
  { id: 'questions', label: 'Questions' },
] as const;

/** Fait défiler jusqu'à une section, et y porte le focus pour que le clavier et le lecteur d'écran suivent. */
export function scrollToSection(document: Document, event: Event, id: string): void {
  const section = document.getElementById(id);
  if (!section) {
    return;
  }
  event.preventDefault();
  const reduced = document.defaultView?.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  section.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' });
  section.focus({ preventScroll: true });
}
