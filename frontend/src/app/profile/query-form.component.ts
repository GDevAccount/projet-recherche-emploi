import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  linkedSignal,
  output,
  signal,
} from '@angular/core';
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
import { Place, PlaceIconComponent } from './place-icon.component';

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

export function placeOf(query: SearchQuery | undefined): Place {
  if (query?.remote) {
    return 'remote';
  }
  return query?.location ? 'location' : 'france';
}

/** Le formulaire d'un poste recherché, montré dans une fenêtre : il en ajoute un, ou modifie celui qu'on lui donne. */
@Component({
  selector: 'app-query-form',
  imports: [FormsModule, Button, InputText, Message, PlaceIconComponent],
  templateUrl: './query-form.component.html',
  styleUrl: './query-form.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QueryFormComponent {
  private readonly queryService = inject(QueryService);
  private readonly session = inject(SessionService);

  /** Le poste à modifier ; sans lui, le formulaire en ajoute un. */
  readonly query = input<SearchQuery>();
  /** Le poste est enregistré, ou la saisie abandonnée. */
  readonly closed = output<void>();

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

  protected readonly text = linkedSignal(() => this.query()?.query ?? '');
  protected readonly skills = linkedSignal(() => this.query()?.skills ?? []);
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
  private readonly chosenContract = linkedSignal(() => this.query()?.contract_type ?? '');
  protected readonly contract = computed(() => this.chosenContract() || (this.contractTypes()[0] ?? ''));
  protected readonly place = linkedSignal(() => placeOf(this.query()));
  protected readonly location = linkedSignal(() => this.query()?.location ?? '');
  protected readonly saving = signal(false);
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
      // Échap ferme la liste, pas la fenêtre
      event.preventDefault();
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
    } else if (event.key !== 'Escape') {
      // Une frappe rouvre la liste fermée par Échap
      this.skillFocused.set(true);
    }
  }

  protected cancel(): void {
    this.closed.emit();
  }

  protected save(): void {
    if (this.incomplete() || this.saving()) {
      return;
    }
    // Une compétence saisie sans être validée compte aussi
    this.addSkill();
    this.saving.set(true);
    this.error.set('');
    const place = this.place();
    const edited = this.query();
    const job = {
      contract_type: this.contract(),
      query: this.text(),
      skills: this.skills(),
      location: place === 'location' ? this.location() : '',
      remote: place === 'remote',
    };
    (edited ? this.queryService.update(edited.id, job) : this.queryService.add(job)).subscribe({
      next: (saved) => {
        this.saving.set(false);
        if (edited) {
          this.queryService.queries.update((queries) =>
            queries?.map((other) => (other.id === saved.id ? saved : other)),
          );
        } else {
          this.queryService.queries.update((queries) => [...(queries ?? []), saved]);
          // Le compte dit si une recherche peut être lancée : il faut au moins un poste recherché
          this.session.refresh().subscribe();
        }
        this.closed.emit();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }
}
