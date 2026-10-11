import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';

import { apiErrorMessage } from '../core/api-error';
import { SearchQuery } from '../core/api.models';
import { QueryService } from '../core/query.service';
import { SessionService } from '../core/session.service';
import { PlaceIconComponent } from './place-icon.component';
import { QueryFormComponent, placeOf } from './query-form.component';

/** Postes recherchés : la liste, la suppression, et la fenêtre où un poste s'ajoute ou se modifie. */
@Component({
  selector: 'app-queries-card',
  imports: [Button, Message, PlaceIconComponent, QueryFormComponent],
  templateUrl: './queries-card.component.html',
  styleUrl: './queries-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QueriesCardComponent {
  private readonly queryService = inject(QueryService);
  private readonly session = inject(SessionService);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly injector = inject(Injector);

  // undefined : en cours de lecture
  protected readonly queries = this.queryService.queries;
  // Le formulaire ouvert dans la fenêtre : celui d'un poste à modifier, ou sans poste, celui de l'ajout
  protected readonly form = signal<{ query?: SearchQuery } | null>(null);
  protected readonly deleting = signal<number | null>(null);
  protected readonly error = signal('');
  protected readonly placeOf = placeOf;

  constructor() {
    // Ceux d'une visite précédente de l'écran ont pu changer depuis
    this.queries.set(undefined);
    this.queryService.list().subscribe({
      next: (queries) => this.queries.set(queries),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  protected openForm(query?: SearchQuery): void {
    this.form.set({ query });
    // Une fois le formulaire dessiné : la fenêtre donne alors le clavier à son premier champ
    afterNextRender(
      () => {
        const dialog = this.dialog().nativeElement;
        // showModal retient le clavier dans la fenêtre, la ferme sur Échap, puis le rend au bouton d'origine
        if (dialog.showModal) {
          dialog.showModal();
        } else {
          dialog.setAttribute('open', '');
        }
      },
      { injector: this.injector },
    );
  }

  protected closeForm(): void {
    const dialog = this.dialog().nativeElement;
    if (dialog.close) {
      dialog.close();
    } else {
      dialog.removeAttribute('open');
      this.formClosed();
    }
  }

  /** Le formulaire est détruit avec sa saisie : le suivant repart des valeurs du poste, ou vide. */
  protected formClosed(): void {
    this.form.set(null);
  }

  protected remove(query: SearchQuery): void {
    this.deleting.set(query.id);
    this.error.set('');
    const forget = () => {
      this.queries.update((queries) => queries?.filter((other) => other.id !== query.id));
      this.deleting.set(null);
      // Le compte dit si une recherche peut être lancée : il faut au moins un poste recherché
      this.session.refresh().subscribe();
    };
    this.queryService.delete(query.id).subscribe({
      next: forget,
      error: (error: unknown) => {
        // Déjà supprimée depuis un autre onglet : elle disparaît ici aussi
        if (error instanceof HttpErrorResponse && error.status === 404) {
          forget();
        } else {
          this.deleting.set(null);
          this.error.set(apiErrorMessage(error));
        }
      },
    });
  }
}
