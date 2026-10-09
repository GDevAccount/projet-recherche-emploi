import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { OutcomeGroup, SearchStats } from '../core/api.models';
import { CountPipe, SharePipe, UsdPipe } from '../core/format.pipe';

/** Regroupements proposés, dans l'ordre des onglets. */
const BREAKDOWNS = [
  { key: 'outcomes_by_query', label: 'Par poste recherché' },
  { key: 'outcomes_by_site', label: 'Par site' },
  { key: 'outcomes_by_prompt', label: 'Par prompt' },
] as const;

type BreakdownKey = (typeof BREAKDOWNS)[number]['key'];

/** Nombre de groupes montrés d'abord : les offres viennent de dizaines de sites. */
const GROUPS_SHOWN = 8;

/**
 * Ce que deviennent les offres retenues : c'est ce qui dit si le tri retient les bonnes. Les nombres et les
 * taux viennent de l'API, qui les tire de l'état de chaque candidature.
 */
@Component({
  selector: 'app-outcomes-card',
  imports: [CountPipe, SharePipe, UsdPipe],
  templateUrl: './outcomes-card.component.html',
  styleUrl: './outcomes-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OutcomesCardComponent {
  readonly stats = input.required<SearchStats>();

  protected readonly breakdowns = BREAKDOWNS;
  protected readonly breakdown = signal<BreakdownKey>('outcomes_by_query');
  protected readonly allGroups = signal(false);

  private readonly groups = computed(() => this.stats()[this.breakdown()]);
  protected readonly hiddenGroups = computed(() =>
    this.allGroups() ? 0 : Math.max(0, this.groups().length - GROUPS_SHOWN),
  );
  /** Groupes du regroupement choisi. Les largeurs sont relatives au groupe le plus fourni. */
  protected readonly rows = computed(() => {
    const groups = this.groups();
    const largest = Math.max(1, ...groups.map((group) => group.kept));
    return groups.slice(0, this.allGroups() ? undefined : GROUPS_SHOWN).map((group) => ({
      group,
      width: (group.kept / largest) * 100,
      parts: this.partsOf(group),
    }));
  });

  protected choose(key: BreakdownKey): void {
    this.breakdown.set(key);
    this.allGroups.set(false);
  }

  protected showAllGroups(): void {
    this.allGroups.set(true);
  }

  /** Parts d'un groupe, en pourcentage de ses offres. */
  private partsOf(group: OutcomeGroup): { interviews: number; applied: number; pending: number; deleted: number } {
    const share = (count: number) => (group.kept ? (count / group.kept) * 100 : 0);
    return {
      interviews: share(group.interviews),
      applied: share(group.applied - group.interviews),
      pending: share(group.pending),
      deleted: share(group.deleted),
    };
  }
}
