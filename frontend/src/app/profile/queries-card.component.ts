import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable, toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { catchError, debounce, distinctUntilChanged, map, of, switchMap, timer } from 'rxjs';

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

/** Attente après la dernière frappe avant d'interroger le référentiel des compétences. */
const SUGGEST_DELAY_MS = 150;

/** Compare deux compétences sans tenir compte des accents ni des majuscules, comme le référentiel. */
function sameSkill(first: string, second: string): boolean {
  return first.localeCompare(second, 'fr', { sensitivity: 'base' }) === 0;
}

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
  // null : pas encore lue, ou illisible
  private readonly config = toSignal(
    inject(ConfigService)
      .getConfig()
      .pipe(catchError(() => of(null))),
    { initialValue: null },
  );
  protected readonly contractTypes = computed(() => this.config()?.contract_types ?? []);
  /** Nombre de compétences qu'un poste accepte ; sans réponse de l'API, c'est elle qui refusera. */
  protected readonly maxSkills = computed(() => this.config()?.max_skills_per_query ?? Infinity);

  // undefined : en cours de lecture
  protected readonly queries = this.queryService.queries;
  protected readonly text = signal('');
  protected readonly skills = signal<string[]>([]);
  // La compétence en cours de saisie, pas encore devenue un tag
  protected readonly skillDraft = signal('');
  // Ce que le référentiel propose, et le texte pour lequel il l'a proposé
  private readonly suggested = signal<{ text: string; names: string[] }>({ text: '', names: [] });
  private readonly skillFocused = signal(false);
  /** Les compétences proposées, sans celles déjà choisies. */
  protected readonly options = computed(() =>
    this.suggested().names.filter((name) => !this.skills().some((skill) => sameSkill(skill, name))),
  );
  /** Le texte saisi, quand il n'est pas dans le référentiel : il s'ajoute alors tel quel. */
  protected readonly newSkill = computed(() => {
    const typed = this.skillDraft().trim();
    const { text, names } = this.suggested();
    const known = [...names, ...this.skills()].some((name) => sameSkill(name, typed));
    // Tant que le référentiel n'a pas répondu pour ce texte, on ne sait pas s'il y est
    return typed && text === typed && !known ? typed : '';
  });
  protected readonly skillsFull = computed(() => this.skills().length >= this.maxSkills());
  protected readonly listOpen = computed(
    () => this.skillFocused() && !!this.skillDraft().trim() && (this.options().length > 0 || !!this.newSkill()),
  );
  // Rang de la ligne désignée au clavier dans la liste ; -1 : aucune, Entrée ajoute le texte saisi
  protected readonly activeOption = signal(-1);
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
    toObservable(this.skillDraft)
      .pipe(
        map((draft) => draft.trim()),
        distinctUntilChanged(),
        debounce((text) => (text ? timer(SUGGEST_DELAY_MS) : of(0))),
        switchMap((text) =>
          (text ? this.queryService.suggestSkills(text).pipe(catchError(() => of<string[]>([]))) : of([])).pipe(
            map((names) => ({ text, names })),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((suggested) => {
        this.suggested.set(suggested);
        this.activeOption.set(-1);
      });

    // Ceux d'une visite précédente de l'écran ont pu changer depuis
    this.queries.set(undefined);
    this.queryService.list().subscribe({
      next: (queries) => this.queries.set(queries),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  protected chooseContract(contract: string): void {
    this.chosenContract.set(contract);
  }

  /** Fait un tag de ce qui est saisi ; une virgule sépare plusieurs compétences collées d'un coup. */
  protected addSkill(): void {
    const typed = this.skillDraft()
      .split(',')
      .map((skill) => skill.trim().replace(/\s+/g, ' '))
      .filter(Boolean);
    this.skillDraft.set('');
    if (!typed.length) {
      return;
    }
    this.skills.update((skills) => {
      const merged = [...skills];
      for (const skill of typed) {
        if (!merged.some((other) => other.toLowerCase() === skill.toLowerCase())) {
          merged.push(skill);
        }
      }
      // Plusieurs compétences collées d'un coup peuvent dépasser ce qu'un poste accepte
      return merged.slice(0, this.maxSkills());
    });
  }

  protected removeSkill(skill: string): void {
    this.skills.update((skills) => skills.filter((other) => other !== skill));
  }

  /** Prend une compétence proposée par le référentiel, à la place de ce qui est saisi. */
  protected pickSkill(name: string): void {
    this.skillDraft.set(name);
    this.addSkill();
  }

  protected focusSkill(focused: boolean): void {
    this.skillFocused.set(focused);
    this.activeOption.set(-1);
  }

  protected onSkillKey(event: KeyboardEvent): void {
    const options = this.options();
    // La ligne « Ajouter », quand elle est là, suit les compétences proposées
    const rows = options.length + (this.newSkill() ? 1 : 0);
    if (this.listOpen() && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      // De la dernière ligne on revient au champ, et du champ à la dernière ligne
      this.activeOption.update((active) => ((active + 1 + step + rows + 1) % (rows + 1)) - 1);
    } else if (event.key === 'Escape' && this.listOpen()) {
      event.stopPropagation();
      this.skillFocused.set(false);
    } else if ((event.key === 'Enter' && this.skillDraft().trim()) || event.key === ',') {
      // Entrée valide la compétence, pas le formulaire ; sans rien de saisi, elle l'envoie
      event.preventDefault();
      const picked = this.listOpen() ? options[this.activeOption()] : undefined;
      if (picked) {
        this.pickSkill(picked);
      } else {
        this.addSkill();
      }
    } else if (event.key === 'Backspace' && !this.skillDraft()) {
      this.skills.update((skills) => skills.slice(0, -1));
    } else {
      // Une frappe rouvre la liste fermée par Échap
      this.skillFocused.set(true);
    }
  }

  protected add(): void {
    if (this.incomplete() || this.adding()) {
      return;
    }
    // Une compétence saisie sans être validée compte aussi
    this.addSkill();
    this.adding.set(true);
    this.error.set('');
    const place = this.place();
    this.queryService
      .add({
        contract_type: this.contract(),
        query: this.text(),
        skills: this.skills(),
        location: place === 'location' ? this.location() : '',
        remote: place === 'remote',
      })
      .subscribe({
        next: (created) => {
          this.queries.update((queries) => [...(queries ?? []), created]);
          // Le contrat et le lieu restent : on ajoute souvent plusieurs intitulés pour la même cible
          this.text.set('');
          this.skills.set([]);
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
