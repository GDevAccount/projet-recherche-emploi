import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Message } from 'primeng/message';
import { catchError, map, of } from 'rxjs';

import { apiErrorMessage } from '../core/api-error';
import { Job, JobStatus } from '../core/api.models';
import { ConfigService } from '../core/config.service';
import { JobService } from '../core/job.service';
import { SearchRunService } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { normalize } from '../core/text';
import { JobCardComponent } from './job-card.component';

/** Libellé du filtre pour les offres dont l'annonce ne dit pas le contrat. */
const NOT_STATED = 'non précisé';

function contractOf(job: Job): string {
  return job.contract_type ?? NOT_STATED;
}

/**
 * Rubrique Offres : le suivi des candidatures. Les entretiens en tête, puis deux colonnes, à traiter et
 * postulées, et les candidatures refusées repliées en bas. Une carte change d'état par son bouton, ou en la
 * faisant glisser. Les états proposés sont ceux que l'API annonce pour chaque offre (next_statuses).
 */
@Component({
  selector: 'app-jobs',
  imports: [FormsModule, NgTemplateOutlet, Message, JobCardComponent],
  templateUrl: './jobs.component.html',
  styleUrl: './jobs.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JobsComponent {
  private readonly jobService = inject(JobService);
  private readonly session = inject(SessionService);
  protected readonly run = inject(SearchRunService);
  /** Faux tant qu'il manque le CV ou un poste recherché : inviter à lancer une recherche serait trompeur. */
  protected readonly canSearch = computed(() => this.session.account()?.can_search ?? true);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  // undefined : en cours de lecture
  protected readonly jobs = signal<Job[] | undefined>(undefined);
  protected readonly search = signal('');
  // Vide : tous les contrats
  protected readonly contracts = signal<ReadonlySet<string>>(new Set());
  protected readonly busy = signal<ReadonlySet<number>>(new Set());
  protected readonly dragged = signal<Job | null>(null);
  /** Zone survolée pendant un glissement, nommée par l'état qu'elle donne */
  protected readonly dropTarget = signal<JobStatus | null>(null);
  /** Offre dont la corbeille a été cliquée : la fenêtre demande quoi en faire */
  protected readonly discarding = signal<Job | null>(null);
  /** Second temps de la fenêtre : le motif de la suppression */
  protected readonly askingWhy = signal(false);
  /** Motifs proposés par l'API ; aucun si elle ne les a pas donnés, et la suppression se fait alors sans demander */
  protected readonly reasons = toSignal(
    inject(ConfigService)
      .getConfig()
      .pipe(
        map((config) => config.delete_reasons),
        catchError(() => of([])),
      ),
    { initialValue: [] },
  );
  protected readonly error = signal('');

  protected readonly total = computed(() => this.jobs()?.length ?? 0);
  protected readonly todoCount = computed(() => this.count('todo'));
  protected readonly interviewCount = computed(() => this.count('interview'));
  /** Candidatures envoyées, quelle que soit leur suite */
  protected readonly sentCount = computed(() => this.total() - this.todoCount());
  protected readonly progress = computed(() => (this.total() ? Math.round((this.sentCount() / this.total()) * 100) : 0));

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
  protected readonly todo = computed(() => this.withStatus('todo'));
  protected readonly applied = computed(() => this.withStatus('applied'));
  protected readonly interviews = computed(() => this.withStatus('interview'));
  protected readonly rejected = computed(() => this.withStatus('rejected'));
  protected readonly filtered = computed(() => this.visible().length !== this.total());

  constructor() {
    // À l'ouverture, puis après chaque recherche : elle a pu ajouter des offres
    effect(() => {
      this.run.completed();
      this.load();
    });
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

  /** L'annonce s'ouvre de toute façon dans son onglet : le signalement ne doit rien retarder ni rien afficher. */
  protected markOpened(job: Job): void {
    this.jobService.markOpened(job.id).subscribe({ error: () => undefined });
  }

  protected setStatus(job: Job, status: JobStatus): void {
    if (job.status === status || this.busy().has(job.id)) {
      return;
    }
    this.start(job.id);
    this.jobService.setStatus(job.id, status).subscribe({
      next: (updated) => {
        // L'API renvoie l'offre à jour : pas de rechargement de la liste, dont la réponse pourrait arriver
        // après un autre clic et remettre une carte dans la mauvaise colonne
        this.replace(updated);
        this.finish(job.id);
      },
      error: (error: unknown) => this.fail(job.id, error),
    });
  }

  protected openDiscard(job: Job): void {
    this.discarding.set(job);
    const dialog = this.dialog().nativeElement;
    // showModal retient le clavier dans la fenêtre et la ferme sur Échap
    if (dialog.showModal) {
      dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
    }
  }

  protected closeDiscard(): void {
    const dialog = this.dialog().nativeElement;
    if (dialog.close) {
      dialog.close();
    } else {
      dialog.removeAttribute('open');
      this.discardClosed();
    }
  }

  protected discardClosed(): void {
    this.discarding.set(null);
    this.askingWhy.set(false);
  }

  protected askWhy(job: Job): void {
    if (this.reasons().length) {
      this.askingWhy.set(true);
    } else {
      this.remove(job);
    }
  }

  protected refuse(job: Job): void {
    this.closeDiscard();
    this.setStatus(job, 'rejected');
  }

  protected remove(job: Job, reason?: string): void {
    this.closeDiscard();
    this.start(job.id);
    this.jobService.delete(job.id, reason).subscribe({
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

  protected dragOver(event: DragEvent, status: JobStatus): void {
    // Une zone n'accepte que les cartes qui peuvent prendre son état
    if (this.dragged()?.next_statuses.includes(status)) {
      // Sans cela, la zone refuserait le dépôt
      event.preventDefault();
      this.dropTarget.set(status);
    }
  }

  protected drop(event: DragEvent, status: JobStatus): void {
    event.preventDefault();
    const job = this.dragged();
    this.dragEnd();
    if (job?.next_statuses.includes(status)) {
      this.setStatus(job, status);
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

  private count(status: JobStatus): number {
    return this.jobs()?.filter((job) => job.status === status).length ?? 0;
  }

  private withStatus(status: JobStatus): Job[] {
    return this.visible().filter((job) => job.status === status);
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
