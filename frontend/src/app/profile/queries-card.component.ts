import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { catchError, map, of } from 'rxjs';

import { apiErrorMessage } from '../core/api-error';
import { SearchQuery } from '../core/api.models';
import { ConfigService } from '../core/config.service';
import { QueryService } from '../core/query.service';
import { SessionService } from '../core/session.service';

/** Où chercher : l'API le reçoit comme un lieu (vide pour toute la France) et un indicateur de télétravail. */
type Place = 'france' | 'location' | 'remote';

const PLACES: { value: Place; label: string }[] = [
  { value: 'france', label: 'Toute la France' },
  { value: 'location', label: 'Un lieu précis' },
  { value: 'remote', label: 'Télétravail complet' },
];

/** Postes recherchés : la liste, l'ajout et la suppression. */
@Component({
  selector: 'app-queries-card',
  imports: [FormsModule, NgTemplateOutlet, Button, InputText, Message],
  templateUrl: './queries-card.component.html',
  styleUrl: './queries-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QueriesCardComponent {
  private readonly queryService = inject(QueryService);
  private readonly session = inject(SessionService);

  protected readonly places = PLACES;
  protected readonly contractTypes = toSignal(
    inject(ConfigService)
      .getConfig()
      .pipe(
        map((config) => config.contract_types),
        catchError(() => of<string[]>([])),
      ),
    { initialValue: [] },
  );

  // undefined : en cours de lecture
  protected readonly queries = signal<SearchQuery[] | undefined>(undefined);
  protected readonly text = signal('');
  // Vide : le premier type proposé par l'API
  private readonly chosenContract = signal('');
  protected readonly contract = computed(() => this.chosenContract() || (this.contractTypes()[0] ?? ''));
  protected readonly place = signal<Place>('france');
  protected readonly location = signal('');
  protected readonly adding = signal(false);
  protected readonly deleting = signal<number | null>(null);
  protected readonly error = signal('');

  /** Un lieu précis laissé vide serait enregistré comme « toute la France » : on attend qu'il soit saisi. */
  protected readonly incomplete = computed(
    () => !this.text().trim() || !this.contract() || (this.place() === 'location' && !this.location().trim()),
  );

  constructor() {
    this.queryService.list().subscribe({
      next: (queries) => this.queries.set(queries),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  protected chooseContract(contract: string): void {
    this.chosenContract.set(contract);
  }

  protected add(): void {
    if (this.incomplete() || this.adding()) {
      return;
    }
    this.adding.set(true);
    this.error.set('');
    const place = this.place();
    this.queryService
      .add({
        contract_type: this.contract(),
        query: this.text(),
        location: place === 'location' ? this.location() : '',
        remote: place === 'remote',
      })
      .subscribe({
        next: (created) => {
          this.queries.update((queries) => [...(queries ?? []), created]);
          // Le contrat et le lieu restent : on ajoute souvent plusieurs intitulés pour la même cible
          this.text.set('');
          this.adding.set(false);
          this.refreshAccount();
        },
        error: (error: unknown) => {
          this.adding.set(false);
          this.error.set(apiErrorMessage(error));
        },
      });
  }

  protected remove(query: SearchQuery): void {
    this.deleting.set(query.id);
    this.error.set('');
    const forget = () => {
      this.queries.update((queries) => queries?.filter((other) => other.id !== query.id));
      this.deleting.set(null);
      this.refreshAccount();
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

  protected placeOf(query: SearchQuery): Place {
    if (query.remote) {
      return 'remote';
    }
    return query.location ? 'location' : 'france';
  }

  private refreshAccount(): void {
    // Le compte dit si une recherche peut être lancée : il faut au moins un poste recherché
    this.session.refresh().subscribe();
  }
}
