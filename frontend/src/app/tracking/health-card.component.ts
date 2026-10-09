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
import { HealthOverview } from '../core/api.models';
import { CountPipe, SharePipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { TrackingService } from '../core/tracking.service';

/** Périodes proposées : les erreurs de l'API ne sont pas gardées au-delà de la plus longue. */
const PERIODS = [
  { days: 7, label: '7 jours' },
  { days: 30, label: '30 jours' },
  { days: 90, label: '90 jours' },
] as const;

type Days = (typeof PERIODS)[number]['days'];

/** Ligne d'un tableau de la carte : où l'erreur s'est produite, laquelle, et combien de fois. */
interface Row {
  where: string;
  error: string;
  count: number;
  accounts: number;
  lastAt: string | null;
}

const SEARCH = 'Recherche';

/**
 * Santé de l'instance : recherches échouées ou interrompues et erreurs de l'API, sur tous les comptes.
 * Les nombres viennent de l'API ; l'écran ne fait que ranger les lignes en pannes et en demandes refusées.
 */
@Component({
  selector: 'app-health-card',
  imports: [CountPipe, SharePipe, ParisDatePipe],
  templateUrl: './health-card.component.html',
  styleUrl: './health-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HealthCardComponent {
  /** Change quand les chiffres sont à relire : une recherche vient de se terminer. */
  readonly version = input(0);

  protected readonly periods = PERIODS;
  protected readonly days = signal<Days>(7);
  // undefined : en cours de lecture
  protected readonly health = signal<HealthOverview | undefined>(undefined);
  protected readonly error = signal('');

  /** Ce qui a mal tourné : recherches échouées, recherches interrompues, pannes du serveur. */
  protected readonly incidents = computed<Row[]>(() => {
    const health = this.health();
    if (!health) {
      return [];
    }
    const rows = health.run_failures.map((group) => ({
      where: SEARCH,
      error: group.error_type,
      count: group.count,
      accounts: group.accounts,
      lastAt: group.last_at,
    }));
    if (health.interrupted_runs) {
      rows.push({
        where: SEARCH,
        error: 'Interrompue par un redémarrage',
        count: health.interrupted_runs,
        accounts: health.interrupted_accounts,
        lastAt: health.last_interrupted_at,
      });
    }
    return [...rows, ...this.serverErrors(health, true)];
  });

  /** Demandes que le serveur a refusées en disant pourquoi : pas des pannes. */
  protected readonly refusals = computed<Row[]>(() => {
    const health = this.health();
    return health ? this.serverErrors(health, false) : [];
  });

  constructor() {
    const tracking = inject(TrackingService);
    effect(() => {
      this.version();
      tracking.getHealth(this.days()).subscribe({
        next: (health) => {
          this.health.set(health);
          this.error.set('');
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  protected choose(days: Days): void {
    this.days.set(days);
  }

  private serverErrors(health: HealthOverview, failures: boolean): Row[] {
    return health.server_errors
      .filter((group) => group.is_failure === failures)
      .map((group) => ({
        where: `${group.method} ${group.route ?? 'route inconnue'}`,
        error: `${group.error_type} · ${group.status_code}`,
        count: group.count,
        accounts: group.accounts,
        lastAt: group.last_at,
      }));
  }
}
