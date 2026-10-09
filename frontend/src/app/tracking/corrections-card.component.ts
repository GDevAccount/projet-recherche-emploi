import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { SearchStats } from '../core/api.models';
import { CountPipe, SharePipe } from '../core/format.pipe';

/**
 * Ce que l'utilisateur a corrigé du tri : pages écartées remises dans les offres, offres supprimées et pourquoi.
 * Les nombres et les taux viennent de l'API, par version du prompt.
 */
@Component({
  selector: 'app-corrections-card',
  imports: [CountPipe, SharePipe],
  templateUrl: './corrections-card.component.html',
  styleUrl: './corrections-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CorrectionsCardComponent {
  readonly stats = input.required<SearchStats>();
}
