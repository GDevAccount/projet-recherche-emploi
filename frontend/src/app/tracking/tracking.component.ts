import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { Message } from 'primeng/message';
import { forkJoin } from 'rxjs';

import { apiErrorMessage } from '../core/api-error';
import { EvaluationGroup, SearchRun, SearchStats } from '../core/api.models';
import { CountPipe, DurationPipe, UsdPipe } from '../core/format.pipe';
import { SearchRunService } from '../core/search-run.service';
import { TrackingService } from '../core/tracking.service';
import { BudgetCardComponent } from './budget-card.component';
import { CorrectionsCardComponent } from './corrections-card.component';
import { HealthCardComponent } from './health-card.component';
import { JourneysCardComponent } from './journeys-card.component';
import { OutcomesCardComponent } from './outcomes-card.component';
import { RunListComponent } from './run-list.component';
import { TrendsCardComponent } from './trends-card.component';
import { UsageCardComponent } from './usage-card.component';
import { YieldCardComponent } from './yield-card.component';

/** Répartitions de la synthèse, dans l'ordre des onglets. */
const BREAKDOWNS = [
  { key: 'by_query', label: 'Par poste recherché' },
  { key: 'by_site', label: 'Par site' },
  { key: 'by_page_kind', label: 'Par nature de page' },
  { key: 'by_text', label: 'Par texte lu' },
] as const;

type BreakdownKey = (typeof BREAKDOWNS)[number]['key'];

/** Nombre de groupes montrés d'abord : une recherche touche des dizaines de sites. */
const GROUPS_SHOWN = 8;

/**
 * Rubrique Suivi, pour les administrateurs : ce que les recherches coûtent, ce qu'elles rapportent, et où
 * partent les pages évaluées. Tous les chiffres viennent de l'API ; l'écran les met en forme.
 */
@Component({
  selector: 'app-tracking',
  imports: [
    Message,
    UsdPipe,
    DurationPipe,
    CountPipe,
    BudgetCardComponent,
    CorrectionsCardComponent,
    HealthCardComponent,
    JourneysCardComponent,
    OutcomesCardComponent,
    RunListComponent,
    TrendsCardComponent,
    UsageCardComponent,
    YieldCardComponent,
  ],
  templateUrl: './tracking.component.html',
  styleUrl: './tracking.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TrackingComponent {
  protected readonly breakdowns = BREAKDOWNS;

  // undefined : en cours de lecture
  protected readonly stats = signal<SearchStats | undefined>(undefined);
  protected readonly runs = signal<SearchRun[]>([]);
  protected readonly error = signal('');
  protected readonly breakdown = signal<BreakdownKey>('by_query');
  protected readonly allGroups = signal(false);
  /** Change après chaque recherche : les cartes de l'instance relisent alors leurs chiffres. */
  protected readonly version = signal(0);

  /** Part du moteur de recherche dans le coût total, en pourcentage ; null quand le total n'est pas connu. */
  protected readonly searchShare = computed(() => {
    const stats = this.stats();
    return stats?.cost_usd ? Math.round((stats.search_cost_usd / stats.cost_usd) * 100) : null;
  });

  protected readonly evaluated = computed(() =>
    (this.stats()?.by_text ?? []).reduce((total, group) => total + group.evaluated, 0),
  );

  private readonly groups = computed(() => this.stats()?.[this.breakdown()] ?? []);
  protected readonly hiddenGroups = computed(() =>
    this.allGroups() ? 0 : Math.max(0, this.groups().length - GROUPS_SHOWN),
  );
  /** Groupes de la répartition choisie. Les largeurs sont relatives au groupe le plus fourni. */
  protected readonly rows = computed(() => {
    const groups = this.groups();
    const largest = Math.max(1, ...groups.map((group) => group.evaluated));
    return groups.slice(0, this.allGroups() ? undefined : GROUPS_SHOWN).map((group) => ({
      group,
      width: (group.evaluated / largest) * 100,
      parts: this.partsOf(group),
    }));
  });

  constructor() {
    const tracking = inject(TrackingService);
    const run = inject(SearchRunService);
    // À l'ouverture, puis après chaque recherche : elle vient d'ajouter ses mesures
    effect(() => {
      run.completed();
      forkJoin({ stats: tracking.getStats(), runs: tracking.listRuns() }).subscribe({
        next: ({ stats, runs }) => {
          this.stats.set(stats);
          this.runs.set(runs);
          this.version.update((version) => version + 1);
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  protected choose(key: BreakdownKey): void {
    this.breakdown.set(key);
    this.allGroups.set(false);
  }

  protected showAllGroups(): void {
    this.allGroups.set(true);
  }

  /** Parts d'un groupe, en pourcentage de ses pages : retenues, offres écartées, pages qui n'étaient pas des offres. */
  private partsOf(group: EvaluationGroup): { kept: number; rejected: number; other: number } {
    const share = (count: number) => (group.evaluated ? (count / group.evaluated) * 100 : 0);
    return { kept: share(group.kept), rejected: share(group.rejected_offers), other: share(group.not_an_offer) };
  }
}
