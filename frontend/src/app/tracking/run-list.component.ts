import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';

import { apiErrorMessage } from '../core/api-error';
import { PageEvaluation, SearchRun, SearchRunStatus } from '../core/api.models';
import { CountPipe, DurationPipe, UsdPipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { siteOf } from '../core/text';
import { TrackingService } from '../core/tracking.service';

/** Nombre de recherches affichées d'un coup. */
const PAGE_SIZE = 10;

const STATUS_LABELS: Record<SearchRunStatus, string> = {
  running: 'En cours',
  done: 'Terminée',
  failed: 'Échouée',
  interrupted: 'Interrompue',
};

/** Critères du verdict, dans l'ordre où l'API les juge, et le mot qui les désigne. */
const CRITERIA = [
  ['matches_search', 'métier'],
  ['matches_contract', 'contrat'],
  ['matches_skills', 'compétences'],
  ['matches_level', 'niveau'],
  ['matches_location', 'lieu'],
] as const;

/** Nature d'une page qui est bien une offre (PageKind côté Python). */
const OFFER_PAGE_KIND = 'offre';

/** Pages d'une recherche : en cours de lecture (undefined), lues, ou le message de l'erreur. */
type Loaded = PageEvaluation[] | string | undefined;

/** Liste des recherches, la plus récente en premier. Une recherche s'ouvre sur ses mesures et ses pages évaluées. */
@Component({
  selector: 'app-run-list',
  imports: [UsdPipe, DurationPipe, CountPipe, ParisDatePipe],
  templateUrl: './run-list.component.html',
  styleUrl: './run-list.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RunListComponent {
  private readonly tracking = inject(TrackingService);

  readonly runs = input.required<SearchRun[]>();

  protected readonly siteOf = siteOf;
  protected readonly shown = signal(PAGE_SIZE);
  protected readonly opened = signal<ReadonlySet<number>>(new Set());
  /** Pages évaluées de chaque recherche ouverte, lues à sa première ouverture. */
  protected readonly evaluations = signal<ReadonlyMap<number, Loaded>>(new Map());

  protected readonly listed = computed(() => this.runs().slice(0, this.shown()));
  protected readonly remaining = computed(() => this.runs().length - this.listed().length);

  protected statusLabel(run: SearchRun): string {
    return run.status ? STATUS_LABELS[run.status] : 'Non suivie';
  }

  protected toggle(run: SearchRun): void {
    const opening = !this.opened().has(run.id);
    this.opened.update((opened) => {
      const next = new Set(opened);
      if (!next.delete(run.id)) {
        next.add(run.id);
      }
      return next;
    });
    if (opening && !this.evaluations().has(run.id)) {
      this.load(run.id);
    }
  }

  protected showMore(): void {
    this.shown.update((shown) => shown + PAGE_SIZE);
  }

  protected pagesOf(run: SearchRun): PageEvaluation[] | undefined {
    const loaded = this.evaluations().get(run.id);
    return typeof loaded === 'string' ? undefined : loaded;
  }

  protected errorOf(run: SearchRun): string {
    const loaded = this.evaluations().get(run.id);
    return typeof loaded === 'string' ? loaded : '';
  }

  /** Critères en défaut d'une page écartée : « métier, lieu ». Vide pour une page qui n'était pas une offre. */
  protected failedCriteria(page: PageEvaluation): string {
    // Le modèle met tous ses avis à faux pour une page qui n'est pas une offre : sa nature suffit à le dire
    if (page.page_kind && page.page_kind !== OFFER_PAGE_KIND) {
      return '';
    }
    return CRITERIA.filter(([criterion]) => page[criterion] === false)
      .map(([, label]) => label)
      .join(', ');
  }

  protected place(page: PageEvaluation): string {
    return [page.work_city, page.work_country].filter(Boolean).join(', ');
  }

  private load(runId: number): void {
    const store = (loaded: Loaded) =>
      this.evaluations.update((evaluations) => new Map(evaluations).set(runId, loaded));
    this.tracking.listEvaluations(runId).subscribe({
      next: store,
      error: (error: unknown) => store(apiErrorMessage(error)),
    });
  }
}
