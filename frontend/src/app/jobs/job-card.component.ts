import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';

import { Job, JobStatus } from '../core/api.models';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { siteOf } from '../core/text';

/** Teinte stable par site, pour reconnaître d'un coup d'œil d'où vient une annonce. */
function hueOf(text: string): number {
  let hash = 0;
  for (const character of text) {
    hash = (hash * 31 + character.charCodeAt(0)) % 360;
  }
  return hash;
}

/** Libellé du bouton qui mène à un état : l'étape suivante, ou le retour à la précédente. */
const FORWARD_LABELS: Partial<Record<JobStatus, string>> = { applied: "J'ai postulé", interview: 'Entretien obtenu' };
const BACK_LABELS: Partial<Record<JobStatus, string>> = { todo: 'Remettre à traiter', applied: "Annuler l'entretien" };
const REOPEN_LABEL = 'Rouvrir la candidature';
/** Étapes d'une candidature, dans l'ordre : ce qui distingue avancer de revenir en arrière. */
const STEPS: readonly JobStatus[] = ['todo', 'applied', 'interview'];

interface Action {
  status: JobStatus;
  label: string;
}

/**
 * Une offre retenue. La carte ne modifie rien elle-même : elle demande, l'écran appelle l'API.
 * Elle ne propose que les états que l'API annonce pour cette offre (next_statuses).
 */
@Component({
  selector: 'app-job-card',
  imports: [ParisDatePipe],
  templateUrl: './job-card.component.html',
  styleUrl: './job-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[class.tracked]': "job().status !== 'todo'",
    '[class.interview]': "job().status === 'interview'",
    '[class.rejected]': "job().status === 'rejected'",
    '[class.busy]': 'busy()',
  },
})
export class JobCardComponent {
  readonly job = input.required<Job>();
  /** Un appel à l'API est en cours pour cette offre */
  readonly busy = input(false);

  readonly statusChange = output<JobStatus>();
  /** La corbeille : l'écran demande s'il s'agit d'un refus de l'employeur ou d'une suppression */
  readonly discard = output<void>();
  /** L'utilisateur ouvre l'annonce, par un clic ou dans un nouvel onglet. */
  readonly opened = output<void>();

  protected readonly site = computed(() => siteOf(this.job().url));
  protected readonly hue = computed(() => hueOf(this.site()));
  protected readonly expanded = signal(false);

  /** L'étape suivante de la candidature, mise en avant. */
  protected readonly forward = computed<Action | null>(() => {
    if (this.job().status === 'rejected') {
      return null;
    }
    return this.actionAmong(FORWARD_LABELS, (next, current) => next > current);
  });

  /** Le retour en arrière, discret : corriger une erreur, ou rouvrir une candidature refusée. */
  protected readonly back = computed<Action | null>(() => {
    const [reopened] = this.job().next_statuses;
    if (this.job().status === 'rejected') {
      return reopened ? { status: reopened, label: REOPEN_LABEL } : null;
    }
    return this.actionAmong(BACK_LABELS, (next, current) => next < current);
  });

  private actionAmong(
    labels: Partial<Record<JobStatus, string>>,
    fits: (next: number, current: number) => boolean,
  ): Action | null {
    const current = STEPS.indexOf(this.job().status);
    const status = this.job().next_statuses.find((next) => labels[next] && fits(STEPS.indexOf(next), current));
    return status ? { status, label: labels[status]! } : null;
  }
}
