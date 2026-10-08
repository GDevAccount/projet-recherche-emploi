import { ChangeDetectionStrategy, Component } from '@angular/core';

import { CvCardComponent } from './cv-card.component';
import { QueriesCardComponent } from './queries-card.component';

/** Rubrique Profil : ce sur quoi chaque annonce est jugée, le CV et les postes recherchés. */
@Component({
  selector: 'app-profile',
  imports: [CvCardComponent, QueriesCardComponent],
  template: `
    <app-cv-card />
    <app-queries-card />
  `,
  styleUrl: './profile.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfileComponent {}
