import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';

import { apiErrorMessage } from '../core/api-error';
import { AccountJourney, JourneyOverview } from '../core/api.models';
import { CountPipe, SharePipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { TrackingService } from '../core/tracking.service';

/**
 * Parcours des invités : combien déposent un CV, lancent une recherche, postulent et reviennent, puis où en
 * est chaque compte. C'est ce qui dit si l'application sert à d'autres que son propriétaire.
 */
@Component({
  selector: 'app-journeys-card',
  imports: [CountPipe, SharePipe, ParisDatePipe],
  templateUrl: './journeys-card.component.html',
  styleUrl: './journeys-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JourneysCardComponent {
  /** Change quand les chiffres sont à relire : une recherche vient de se terminer. */
  readonly version = input(0);

  // undefined : en cours de lecture
  protected readonly journeys = signal<JourneyOverview | undefined>(undefined);
  protected readonly error = signal('');

  constructor() {
    const tracking = inject(TrackingService);
    effect(() => {
      this.version();
      tracking.getJourneys().subscribe({
        next: (journeys) => {
          this.journeys.set(journeys);
          this.error.set('');
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  protected nameOf(account: AccountJourney): string {
    return account.email ?? (account.is_owner ? 'Propriétaire' : `Compte nº ${account.user_id}`);
  }
}
