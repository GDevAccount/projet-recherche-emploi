import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';

import { apiErrorMessage } from '../core/api-error';
import { BudgetOverview } from '../core/api.models';
import { CountPipe, UsdPipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { TrackingService } from '../core/tracking.service';

/**
 * Dépense du mois en cours sur tous les comptes, face au budget de l'instance, et ce qu'elle sera en fin de
 * mois au rythme des jours écoulés. Montants, parts et dépassements viennent de l'API.
 */
@Component({
  selector: 'app-budget-card',
  imports: [UsdPipe, CountPipe, ParisDatePipe],
  templateUrl: './budget-card.component.html',
  styleUrl: './budget-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BudgetCardComponent {
  /** Change quand les chiffres sont à relire : une recherche vient de se terminer. */
  readonly version = input(0);

  // undefined : en cours de lecture
  protected readonly budget = signal<BudgetOverview | undefined>(undefined);
  protected readonly error = signal('');

  constructor() {
    const tracking = inject(TrackingService);
    effect(() => {
      this.version();
      tracking.getBudget().subscribe({
        next: (budget) => {
          this.budget.set(budget);
          this.error.set('');
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  /** Position sur la jauge, en pourcentage : une part au-delà du budget s'arrête au bord. */
  protected position(rate: number | null): number {
    return Math.min(rate ?? 0, 1) * 100;
  }
}
