import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';

import { Job } from '../core/api.models';
import { ParisDatePipe } from '../core/paris-date.pipe';

/** Site d'une annonce, pour l'en-tête de sa carte : « welcometothejungle.com ». */
function siteOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

/** Teinte stable par site, pour reconnaître d'un coup d'œil d'où vient une annonce. */
function hueOf(text: string): number {
  let hash = 0;
  for (const character of text) {
    hash = (hash * 31 + character.charCodeAt(0)) % 360;
  }
  return hash;
}

/** Une offre retenue. La carte ne modifie rien elle-même : elle demande, l'écran appelle l'API. */
@Component({
  selector: 'app-job-card',
  imports: [ParisDatePipe],
  templateUrl: './job-card.component.html',
  styleUrl: './job-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[class.applied]': 'job().applied',
    '[class.busy]': 'busy()',
  },
})
export class JobCardComponent {
  readonly job = input.required<Job>();
  /** Un appel à l'API est en cours pour cette offre */
  readonly busy = input(false);

  readonly appliedChange = output<boolean>();
  readonly remove = output<void>();

  protected readonly site = computed(() => siteOf(this.job().url));
  protected readonly hue = computed(() => hueOf(this.site()));
  protected readonly expanded = signal(false);
  // Une offre supprimée ne revient pas : la corbeille demande une confirmation
  protected readonly confirming = signal(false);
}
