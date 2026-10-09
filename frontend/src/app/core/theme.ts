import { definePreset } from '@primeuix/themes';
import Aura from '@primeuix/themes/aura';

/** Classe posée sur <html> en thème sombre : PrimeNG et styles.scss s'y accordent. */
export const DARK_CLASS = 'app-dark';
/** Classe posée en thème clair : les pages légales, hors d'Angular, s'en servent pour quitter le thème sombre. */
export const LIGHT_CLASS = 'app-light';
/** Fonds des deux thèmes (--app-bg de styles.scss), pour la barre du navigateur mobile. */
export const DARK_BACKGROUND = '#0a0b0d';
export const LIGHT_BACKGROUND = '#f5f4ef';

const shades = (color: string) =>
  Object.fromEntries(
    [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((shade) => [shade, `{${color}.${shade}}`]),
  );

/** Thème de PrimeNG : encre et citron vert. Les couleurs propres à l'application sont dans styles.scss. */
export const AppPreset = definePreset(Aura, {
  semantic: {
    primary: shades('lime'),
    colorScheme: {
      light: {
        surface: { 0: '#ffffff', ...shades('stone') },
        // Boutons à l'encre en clair : le citron vert n'est pas lisible en texte sur fond blanc
        primary: {
          color: '{zinc.950}',
          contrastColor: '#ffffff',
          hoverColor: '{zinc.800}',
          activeColor: '{zinc.700}',
        },
        highlight: {
          background: '{lime.200}',
          focusBackground: '{lime.300}',
          color: '{zinc.950}',
          focusColor: '{zinc.950}',
        },
      },
      dark: {
        surface: { 0: '#ffffff', ...shades('zinc') },
        primary: {
          color: '{lime.400}',
          contrastColor: '{zinc.950}',
          hoverColor: '{lime.300}',
          activeColor: '{lime.200}',
        },
        highlight: {
          background: 'color-mix(in srgb, {lime.400}, transparent 84%)',
          focusBackground: 'color-mix(in srgb, {lime.400}, transparent 76%)',
          color: 'rgba(255, 255, 255, 0.87)',
          focusColor: 'rgba(255, 255, 255, 0.87)',
        },
      },
    },
  },
});
