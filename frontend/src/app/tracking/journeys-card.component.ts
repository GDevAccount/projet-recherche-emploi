import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';

import { apiErrorMessage } from '../core/api-error';
import { AccountDetail, AccountJourney, JourneyOverview } from '../core/api.models';
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
  /** Fiche du compte choisi ; undefined tant qu'aucun ne l'est. */
  protected readonly detail = signal<AccountDetail | undefined>(undefined);
  protected readonly selected = signal<number | undefined>(undefined);

  private readonly tracking = inject(TrackingService);

  constructor() {
    const tracking = this.tracking;
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

  /** Ouvre la fiche d'un compte, ou la referme si c'est déjà la sienne. */
  protected toggle(account: AccountJourney): void {
    if (this.selected() === account.user_id) {
      this.close();
      return;
    }
    this.selected.set(account.user_id);
    this.detail.set(undefined);
    this.tracking.getJourney(account.user_id).subscribe({
      next: (detail) => {
        // Une réponse tardive ne doit pas remplacer la fiche d'un compte choisi depuis
        if (this.selected() === detail.account.user_id) {
          this.detail.set(detail);
        }
      },
      error: (error: unknown) => {
        this.error.set(apiErrorMessage(error));
        this.close();
      },
    });
  }

  protected close(): void {
    this.selected.set(undefined);
    this.detail.set(undefined);
  }

  /** « aujourd'hui », « il y a 1 jour », « il y a 6 jours » ; vide quand la dernière visite n'est pas connue. */
  protected idle(days: number | null): string {
    if (days === null) {
      return '';
    }
    return days === 0 ? "aujourd'hui" : `il y a ${days} ${days > 1 ? 'jours' : 'jour'}`;
  }

  protected nameOf(account: AccountJourney): string {
    return account.email ?? (account.is_owner ? 'Propriétaire' : `Compte nº ${account.user_id}`);
  }
}
