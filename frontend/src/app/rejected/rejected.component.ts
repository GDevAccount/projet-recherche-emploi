import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Message } from 'primeng/message';

import { apiErrorMessage } from '../core/api-error';
import { RejectedJob } from '../core/api.models';
import { JobService } from '../core/job.service';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { JOBS_PATH } from '../core/paths';
import { SearchRunService } from '../core/search-run.service';
import { normalize, siteOf } from '../core/text';

/** Nombre de pages affichées d'un coup : une recherche peut en écarter des dizaines. */
const PAGE_SIZE = 30;

function toggled(selected: ReadonlySet<string>, value: string): ReadonlySet<string> {
  const next = new Set(selected);
  if (!next.delete(value)) {
    next.add(value);
  }
  return next;
}

/**
 * Rubrique Rejets : pourquoi des pages ont été écartées. Le motif et les critères en défaut viennent de l'API ;
 * l'écran les compte, les filtre et les montre, rien de plus.
 */
@Component({
  selector: 'app-rejected',
  imports: [FormsModule, RouterLink, Message, ParisDatePipe],
  templateUrl: './rejected.component.html',
  styleUrl: './rejected.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RejectedComponent {
  protected readonly siteOf = siteOf;

  // undefined : en cours de lecture
  protected readonly pages = signal<RejectedJob[] | undefined>(undefined);
  protected readonly search = signal('');
  // Vides : tous les motifs, toutes les recherches
  protected readonly motives = signal<ReadonlySet<string>>(new Set());
  protected readonly queries = signal<ReadonlySet<string>>(new Set());
  protected readonly shown = signal(PAGE_SIZE);
  protected readonly expanded = signal<ReadonlySet<string>>(new Set());
  protected readonly error = signal('');
  protected readonly jobsPath = `/${JOBS_PATH}`;
  /** Pages dont la remise dans les offres est en cours */
  protected readonly busy = signal<ReadonlySet<string>>(new Set());
  /** Pages remises dans les offres depuis l'ouverture : elles restent affichées, mais ne comptent plus */
  protected readonly restored = signal<ReadonlySet<string>>(new Set());

  private readonly rejected = computed(() => (this.pages() ?? []).filter((page) => !this.restored().has(page.url)));
  protected readonly total = computed(() => this.rejected().length);

  /** Répartition par motif, du plus fréquent au plus rare. Les parts sont relatives au motif le plus fréquent. */
  protected readonly breakdown = computed(() => {
    const counts = new Map<string, number>();
    for (const page of this.rejected()) {
      counts.set(page.motive, (counts.get(page.motive) ?? 0) + 1);
    }
    const largest = Math.max(1, ...counts.values());
    return [...counts]
      .map(([motive, count]) => ({
        motive,
        count,
        width: (count / largest) * 100,
        share: Math.round((count / this.total()) * 100),
      }))
      .sort((first, second) => second.count - first.count || first.motive.localeCompare(second.motive, 'fr'));
  });

  protected readonly queryOptions = computed(() =>
    [...new Set((this.pages() ?? []).flatMap((page) => (page.query ? [page.query] : [])))].sort((first, second) =>
      first.localeCompare(second, 'fr'),
    ),
  );

  protected readonly visible = computed(() => {
    const words = normalize(this.search().trim());
    const motives = this.motives();
    const queries = this.queries();
    return (this.pages() ?? []).filter((page) => {
      if (motives.size && !motives.has(page.motive)) {
        return false;
      }
      if (queries.size && !(page.query && queries.has(page.query))) {
        return false;
      }
      return !words || normalize(`${page.title} ${page.url} ${page.reject_reason ?? ''}`).includes(words);
    });
  });
  protected readonly listed = computed(() => this.visible().slice(0, this.shown()));
  protected readonly remaining = computed(() => this.visible().length - this.listed().length);
  /** Pages écartées qui passent les filtres : celles remises dans les offres restent affichées sans compter */
  protected readonly matching = computed(
    () => this.visible().filter((page) => !this.restored().has(page.url)).length,
  );
  protected readonly filtered = computed(() => this.matching() !== this.total());

  private readonly jobService = inject(JobService);

  constructor() {
    const jobService = this.jobService;
    const run = inject(SearchRunService);
    // À l'ouverture, puis après chaque recherche : elle a pu écarter de nouvelles pages
    effect(() => {
      run.completed();
      jobService.listRejected().subscribe({
        next: (pages) => {
          this.pages.set(pages);
          this.restored.set(new Set());
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  protected toggleMotive(motive: string): void {
    this.motives.update((selected) => toggled(selected, motive));
    this.shown.set(PAGE_SIZE);
  }

  protected toggleQuery(query: string): void {
    this.queries.update((selected) => toggled(selected, query));
    this.shown.set(PAGE_SIZE);
  }

  protected searchFor(words: string): void {
    this.search.set(words);
    this.shown.set(PAGE_SIZE);
  }

  protected clearFilters(): void {
    this.search.set('');
    this.motives.set(new Set());
    this.queries.set(new Set());
    this.shown.set(PAGE_SIZE);
  }

  protected showMore(): void {
    this.shown.update((shown) => shown + PAGE_SIZE);
  }

  protected restore(page: RejectedJob): void {
    if (this.busy().has(page.url)) {
      return;
    }
    this.error.set('');
    this.busy.update((busy) => toggled(busy, page.url));
    this.jobService.restore(page.url).subscribe({
      next: () => {
        this.restored.update((restored) => new Set(restored).add(page.url));
        this.busy.update((busy) => toggled(busy, page.url));
      },
      error: (error: unknown) => {
        this.busy.update((busy) => toggled(busy, page.url));
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  protected toggleReason(url: string): void {
    this.expanded.update((expanded) => toggled(expanded, url));
  }
}
