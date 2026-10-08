import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';

import { apiErrorMessage } from '../core/api-error';
import { CvStatus } from '../core/api.models';
import { CvService } from '../core/cv.service';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { SessionService } from '../core/session.service';

/** CV en place et dépôt d'un nouveau. Le fichier choisi n'est envoyé qu'à la confirmation : il remplace l'ancien. */
@Component({
  selector: 'app-cv-card',
  imports: [Button, Message, ParisDatePipe],
  templateUrl: './cv-card.component.html',
  styleUrl: './cv-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CvCardComponent {
  private readonly cvService = inject(CvService);
  private readonly session = inject(SessionService);

  // undefined : en cours de lecture
  protected readonly status = signal<CvStatus | undefined>(undefined);
  protected readonly file = signal<File | null>(null);
  protected readonly dragging = signal(false);
  protected readonly saving = signal(false);
  protected readonly saved = signal(false);
  protected readonly error = signal('');

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

  protected save(): void {
    const file = this.file();
    if (!file) {
      return;
    }
    this.saving.set(true);
    this.error.set('');
    this.cvService.save(file).subscribe({
      next: (status) => {
        this.status.set(status);
        this.file.set(null);
        this.saving.set(false);
        this.saved.set(true);
        // Le compte dit si une recherche peut être lancée : un premier CV peut le changer
        this.session.refresh().subscribe();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  protected size(file: File): string {
    const megabytes = file.size / (1024 * 1024);
    return megabytes >= 1 ? `${megabytes.toFixed(1).replace('.', ',')} Mo` : `${Math.ceil(file.size / 1024)} ko`;
  }

  private select(file: File | undefined): void {
    if (file) {
      this.file.set(file);
      this.saved.set(false);
      this.error.set('');
    }
  }
}
