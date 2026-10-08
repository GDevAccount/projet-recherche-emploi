import { ChangeDetectionStrategy, Component } from '@angular/core';

import { CvCardComponent } from './cv-card.component';

/** Rubrique Profil : ce sur quoi chaque annonce est jugée, le CV et les postes recherchés. */
@Component({
  selector: 'app-profile',
  imports: [CvCardComponent],
  template: `
    <app-cv-card />
    <article class="app-card upcoming">
      <span class="app-eyebrow">Postes recherchés</span>
      <h2>Bientôt ici</h2>
      <p>Les métiers, contrats et lieux que vous visez. En attendant, ils se règlent dans l'ancienne interface.</p>
    </article>
  `,
  styleUrl: './profile.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfileComponent {}
