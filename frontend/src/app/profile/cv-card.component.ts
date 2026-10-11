import { ChangeDetectionStrategy, Component, Signal, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';
import { catchError, firstValueFrom, map, of } from 'rxjs';

import { CvDeposit, CvStatus, CvStep, TrialStatus } from '../core/api.models';
import { apiErrorMessage } from '../core/api-error';
import { ConfigService } from '../core/config.service';
import { CvService } from '../core/cv.service';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { LOGIN_PATH } from '../core/paths';
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
 * Pour un visiteur sans session, c'est ce dépôt qui ouvre son compte d'essai, quand l'instance en propose.
 */
@Component({
  selector: 'app-cv-card',
  imports: [RouterLink, Button, Message, ParisDatePipe],
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

  protected readonly loginPath = `/${LOGIN_PATH}`;
  protected readonly signedIn = computed(() => this.session.userId() !== null);
  // undefined : en cours de lecture ; null : l'instance ne propose pas d'essai sans compte. Seul un visiteur
  // sans session a besoin de le savoir
  private readonly trial: Signal<TrialStatus | null | undefined> = this.signedIn()
    ? signal(undefined)
    : toSignal(
        inject(ConfigService)
          .getConfig()
          .pipe(
            map((config) => config.trial),
            catchError(() => of(null)),
          ),
      );
  /**
   * Pourquoi un visiteur sans session ne peut pas déposer de CV : plus d'essai aujourd'hui (« exhausted »), ou
   * aucun sur cette instance (« closed »). null quand il le peut, ou tant que le serveur ne l'a pas dit.
   */
  protected readonly refusal = computed(() => {
    const trial = this.trial();
    if (this.signedIn() || trial === undefined || trial === 'available') {
      return null;
    }
    return trial === 'exhausted' ? 'exhausted' : 'closed';
  });

  constructor() {
    if (!this.signedIn()) {
      // Sans session, il n'y a pas de CV à lire, et l'API refuserait
      this.status.set({ updated_at: null });
      return;
    }
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
      // Le premier dépôt d'un visiteur ouvre son compte d'essai : l'API le refuse s'il n'en reste plus
      await firstValueFrom(this.session.ensure());
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
