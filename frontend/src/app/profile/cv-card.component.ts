import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';

import { CvDeposit, CvStatus, CvStep } from '../core/api.models';
import { apiErrorMessage } from '../core/api-error';
import { CvService } from '../core/cv.service';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { QueryService } from '../core/query.service';
import { SessionService } from '../core/session.service';

/** Ce que l'écran dit de chaque étape du dépôt, pendant qu'elle se fait. */
const STEP_LABELS: Record<CvStep, string> = {
  read: 'Lecture du PDF',
  anonymize: 'Retrait de vos coordonnées',
  save: 'Enregistrement du CV',
  extract: 'Recherche des postes qui vous correspondent',
  queries: 'Création de vos postes recherchés',
};

/**
 * CV en place et dépôt d'un nouveau. Le fichier choisi n'est envoyé qu'à la confirmation : il remplace l'ancien,
 * et le serveur en tire les postes recherchés, à la place de ceux en place si l'utilisateur le demande.
 */
@Component({
  selector: 'app-cv-card',
  imports: [Button, Message, ParisDatePipe],
  templateUrl: './cv-card.component.html',
  styleUrl: './cv-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CvCardComponent {
  private readonly cvService = inject(CvService);
  private readonly queryService = inject(QueryService);
  private readonly session = inject(SessionService);

  // undefined : en cours de lecture
  protected readonly status = signal<CvStatus | undefined>(undefined);
  protected readonly file = signal<File | null>(null);
  protected readonly dragging = signal(false);
  protected readonly saving = signal(false);
  // Les étapes franchies par le dépôt en cours, la dernière étant celle qui se fait
  protected readonly steps = signal<CvStep[]>([]);
  protected readonly stepLabels = STEP_LABELS;
  protected readonly deposit = signal<CvDeposit | null>(null);
  protected readonly error = signal('');

  /** Nombre de postes recherchés en place : s'il y en a, c'est à l'utilisateur de dire s'ils sont remplacés. */
  protected readonly queryCount = computed(() => this.queryService.queries()?.length ?? 0);
  // null : la question n'a pas encore reçu de réponse
  protected readonly replaceQueries = signal<boolean | null>(null);
  protected readonly undecided = computed(() => this.queryCount() > 0 && this.replaceQueries() === null);

  constructor() {
    this.cvService.getStatus().subscribe({
      next: (status) => this.status.set(status),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  protected choose(input: HTMLInputElement): void {
    this.select(input.files?.[0]);
    // Sans cela, rechoisir le même fichier après une annulation ne déclencherait rien
    input.value = '';
  }

  protected drop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    this.select(event.dataTransfer?.files[0]);
  }

  protected dragOver(event: DragEvent): void {
    // Sans cela, le navigateur ouvrirait le fichier déposé à la place de la page
    event.preventDefault();
    this.dragging.set(true);
  }

  protected cancel(): void {
    this.file.set(null);
    this.error.set('');
  }

  protected async save(): Promise<void> {
    const file = this.file();
    if (!file || this.undecided() || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.steps.set([]);
    this.error.set('');
    try {
      const deposit = await this.cvService.deposit(file, this.replaceQueries() === true, (progress) =>
        this.steps.update((steps) => [...steps, progress.step]),
      );
      this.status.set({ updated_at: deposit.updated_at });
      this.deposit.set(deposit);
      this.file.set(null);
      if (deposit.queries_outcome === 'created') {
        // La carte des postes recherchés montre aussitôt ceux tirés du CV
        this.queryService.queries.set(deposit.queries);
      }
      // Le compte dit si une recherche peut être lancée : un premier CV, ou ses postes, peuvent le changer
      this.session.refresh().subscribe();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : apiErrorMessage(error));
    } finally {
      this.saving.set(false);
    }
  }

  protected size(file: File): string {
    const megabytes = file.size / (1024 * 1024);
    return megabytes >= 1 ? `${megabytes.toFixed(1).replace('.', ',')} Mo` : `${Math.ceil(file.size / 1024)} ko`;
  }

  private select(file: File | undefined): void {
    if (file) {
      this.file.set(file);
      this.deposit.set(null);
      this.replaceQueries.set(null);
      this.error.set('');
    }
  }
}
