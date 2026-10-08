import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Message } from 'primeng/message';

import { apiErrorMessage } from '../core/api-error';
import { Job } from '../core/api.models';
import { JobService } from '../core/job.service';
import { normalize } from '../core/text';
import { JobCardComponent } from './job-card.component';

/** Libellé du filtre pour les offres dont l'annonce ne dit pas le contrat. */
const NOT_STATED = 'non précisé';

function contractOf(job: Job): string {
  return job.contract_type ?? NOT_STATED;
}

/**
 * Rubrique Offres : un tableau de bord en deux colonnes, à traiter et postulées.
 * Une carte passe de l'une à l'autre par son bouton, ou en la faisant glisser.
 */
@Component({
  selector: 'app-jobs',
  imports: [FormsModule, Message, JobCardComponent],
  templateUrl: './jobs.component.html',
  styleUrl: './jobs.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JobsComponent {
  private readonly jobService = inject(JobService);

  // undefined : en cours de lecture
  protected readonly jobs = signal<Job[] | undefined>(undefined);
  protected readonly search = signal('');
  // Vide : tous les contrats
  protected readonly contracts = signal<ReadonlySet<string>>(new Set());
  protected readonly busy = signal<ReadonlySet<number>>(new Set());
  protected readonly dragged = signal<Job | null>(null);
  /** Colonne survolée pendant un glissement : true pour « Postulées » */
  protected readonly dropTarget = signal<boolean | null>(null);
  protected readonly error = signal('');

  protected readonly total = computed(() => this.jobs()?.length ?? 0);
  protected readonly appliedCount = computed(() => this.jobs()?.filter((job) => job.applied).length ?? 0);
  protected readonly todoCount = computed(() => this.total() - this.appliedCount());
  protected readonly progress = computed(() =>
    this.total() ? Math.round((this.appliedCount() / this.total()) * 100) : 0,
  );

  protected readonly contractOptions = computed(() =>
    [...new Set((this.jobs() ?? []).map(contractOf))].sort((first, second) => first.localeCompare(second, 'fr')),
  );

  protected readonly visible = computed(() => {
    const words = normalize(this.search().trim());
    const contracts = this.contracts();
    return (this.jobs() ?? []).filter((job) => {
      if (contracts.size && !contracts.has(contractOf(job))) {
        return false;
      }
      const searched = normalize(`${job.title} ${job.work_location ?? ''} ${job.match_reason ?? ''}`);
      return !words || searched.includes(words);
    });
  });
  protected readonly todo = computed(() => this.visible().filter((job) => !job.applied));
  protected readonly applied = computed(() => this.visible().filter((job) => job.applied));
  protected readonly filtered = computed(() => this.visible().length !== this.total());

  constructor() {
    this.load();
  }

  protected toggleContract(contract: string): void {
    this.contracts.update((selected) => {
      const next = new Set(selected);
      if (!next.delete(contract)) {
        next.add(contract);
      }
      return next;
    });
  }

  protected clearFilters(): void {
    this.search.set('');
    this.contracts.set(new Set());
  }

  protected setApplied(job: Job, applied: boolean): void {
    if (job.applied === applied || this.busy().has(job.id)) {
      return;
    }
    this.start(job.id);
    this.jobService.setApplied(job.id, applied).subscribe({
      next: () => {
        // La carte change de colonne tout de suite ; la date de candidature, elle, vient de l'API
        this.replace({ ...job, applied, applied_at: null });
        this.finish(job.id);
        this.load();
      },
      error: (error: unknown) => this.fail(job.id, error),
    });
  }

  protected remove(job: Job): void {
    this.start(job.id);
    this.jobService.delete(job.id).subscribe({
      next: () => {
        this.jobs.update((jobs) => jobs?.filter((other) => other.id !== job.id));
        this.finish(job.id);
      },
      error: (error: unknown) => this.fail(job.id, error),
    });
  }

  protected dragStart(event: DragEvent, job: Job): void {
    this.dragged.set(job);
    // Firefox n'entame un glissement que si des données l'accompagnent
    event.dataTransfer?.setData('text/plain', String(job.id));
  }

  protected dragOver(event: DragEvent, applied: boolean): void {
    const job = this.dragged();
    if (job && job.applied !== applied) {
      // Sans cela, la colonne refuserait le dépôt
      event.preventDefault();
      this.dropTarget.set(applied);
    }
  }

  protected drop(event: DragEvent, applied: boolean): void {
    event.preventDefault();
    const job = this.dragged();
    this.dragEnd();
    if (job) {
      this.setApplied(job, applied);
    }
  }

  protected dragEnd(): void {
    this.dragged.set(null);
    this.dropTarget.set(null);
  }

  private load(): void {
    this.jobService.list().subscribe({
      next: (jobs) => this.jobs.set(jobs),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  private replace(job: Job): void {
    this.jobs.update((jobs) => jobs?.map((other) => (other.id === job.id ? job : other)));
  }

  private start(id: number): void {
    this.error.set('');
    this.busy.update((busy) => new Set(busy).add(id));
  }

  private finish(id: number): void {
    this.busy.update((busy) => new Set([...busy].filter((other) => other !== id)));
  }

  private fail(id: number, error: unknown): void {
    this.finish(id);
    this.error.set(apiErrorMessage(error));
  }
}
