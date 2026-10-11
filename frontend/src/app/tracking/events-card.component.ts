import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';

import { apiErrorMessage } from '../core/api-error';
import { EventOverview, EventRow } from '../core/api.models';
import { CountPipe, SharePipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { TrackingService } from '../core/tracking.service';

const date = new ParisDatePipe();

/**
 * Historique du parcours, semaine par semaine : ce que les comptes ont fait, ceux supprimés compris.
 * La carte du parcours ne montre que les comptes en place ; celle-ci garde ce qu'ils laissent en partant.
 * Les chiffres viennent de l'API ; l'écran ne fait que les dessiner, chaque barre à l'échelle de la plus haute.
 */
@Component({
  selector: 'app-events-card',
  imports: [CountPipe, SharePipe, ParisDatePipe],
  templateUrl: './events-card.component.html',
  styleUrl: './events-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EventsCardComponent {
  /** Change quand les chiffres sont à relire : une recherche vient de se terminer. */
  readonly version = input(0);

  // undefined : en cours de lecture
  protected readonly events = signal<EventOverview | undefined>(undefined);
  protected readonly error = signal('');

  protected readonly groups = computed(() => {
    const events = this.events();
    if (!events) {
      return [];
    }
    return [
      { title: 'Essais sans compte', rows: this.draw(events.trials, events.weeks) },
      { title: 'Comptes', rows: this.draw(events.accounts, events.weeks) },
    ];
  });

  constructor() {
    const tracking = inject(TrackingService);
    effect(() => {
      this.version();
      tracking.getEvents().subscribe({
        next: (events) => {
          this.events.set(events);
          this.error.set('');
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  private draw(rows: EventRow[], weeks: string[]) {
    return rows.map((row) => {
      const highest = Math.max(0, ...row.counts);
      return {
        ...row,
        bars: row.counts.map((count, index) => ({
          start: weeks[index],
          height: highest ? (count / highest) * 100 : 0,
          title: `Semaine du ${date.transform(weeks[index], 'day')} : ${count}`,
        })),
      };
    });
  }
}
