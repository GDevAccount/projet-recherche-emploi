import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';

import { apiErrorMessage } from '../core/api-error';
import { AccountUsage, UsageOverview } from '../core/api.models';
import { CountPipe, UsdPipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { TrackingService } from '../core/tracking.service';

/** Périodes proposées ; null : depuis le début. */
const PERIODS = [
  { days: 30, label: '30 jours' },
  { days: 90, label: '90 jours' },
  { days: null, label: 'Depuis le début' },
] as const;

type Days = (typeof PERIODS)[number]['days'];

const PLAN_LABELS = { free: 'Gratuit', paid: 'Payant' };

/** Ce que chaque compte a consommé et coûté sur une période, le plus coûteux en premier. */
@Component({
  selector: 'app-usage-card',
  imports: [UsdPipe, CountPipe, ParisDatePipe],
  templateUrl: './usage-card.component.html',
  styleUrl: './usage-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UsageCardComponent {
  /** Change quand les chiffres sont à relire : une recherche vient de se terminer. */
  readonly version = input(0);

  protected readonly periods = PERIODS;
  protected readonly days = signal<Days>(30);
  // undefined : en cours de lecture
  protected readonly usage = signal<UsageOverview | undefined>(undefined);
  protected readonly error = signal('');

  constructor() {
    const tracking = inject(TrackingService);
    effect(() => {
      this.version();
      tracking.getUsage(this.days()).subscribe({
        next: (usage) => {
          this.usage.set(usage);
          this.error.set('');
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  protected choose(days: Days): void {
    this.days.set(days);
  }

  protected nameOf(account: AccountUsage): string {
    if (account.deleted) {
      return `Compte supprimé nº ${account.user_id}`;
    }
    return account.email ?? (account.is_owner ? 'Propriétaire' : `Compte nº ${account.user_id}`);
  }

  protected planOf(account: AccountUsage): string {
    return PLAN_LABELS[account.plan];
  }
}
