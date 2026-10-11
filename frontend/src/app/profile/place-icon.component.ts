import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Où chercher : l'API le reçoit comme un lieu (vide pour toute la France) et un indicateur de télétravail. */
export type Place = 'france' | 'location' | 'remote';

/** Le pictogramme d'un lieu de recherche : un écran, une épingle ou un globe. */
@Component({
  selector: 'app-place-icon',
  template: `
    @switch (place()) {
      @case ('remote') {
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="5" width="16" height="11" rx="2" />
          <path d="M2 20h20" />
        </svg>
      }
      @case ('location') {
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">
          <path d="M12 21s7-6.1 7-11.5a7 7 0 0 0-14 0C5 14.9 12 21 12 21Z" />
          <circle cx="12" cy="9.5" r="2.5" />
        </svg>
      }
      @default {
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c2.7 2.6 4 5.6 4 9s-1.3 6.4-4 9c-2.7-2.6-4-5.6-4-9s1.3-6.4 4-9Z" />
        </svg>
      }
    }
  `,
  styles: `
    :host {
      display: inline-flex;
    }

    svg {
      width: 0.95rem;
      height: 0.95rem;
    }
  `,
  host: { 'aria-hidden': 'true' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PlaceIconComponent {
  readonly place = input.required<Place>();
}
