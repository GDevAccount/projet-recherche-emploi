import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';

import { apiErrorMessage } from '../core/api-error';
import {
  AssistantJournalEntry,
  AssistantOutcome,
  AssistantOverview,
  AssistantSource,
} from '../core/api.models';
import { CountPipe, UsdPipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { TrackingService } from '../core/tracking.service';

/** Périodes proposées : le texte d'une question n'est pas gardé au-delà de la plus longue. */
const PERIODS = [
  { days: 7, label: '7 jours' },
  { days: 30, label: '30 jours' },
  { days: 90, label: '90 jours' },
] as const;

type Days = (typeof PERIODS)[number]['days'];

/** Ce que la liste montre : tout, une issue, ou les réponses que leur lecteur a jugées inutiles. */
type Filter = AssistantOutcome | 'all' | 'down';

/** Filtres de la liste, dans l'ordre des onglets. */
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Toutes' },
  { key: 'unknown', label: 'Sans réponse' },
  { key: 'off_topic', label: 'Hors sujet' },
  { key: 'down', label: 'Mal notées' },
];

const OUTCOME_LABELS: Record<AssistantOutcome, string> = {
  answered: 'Répondu',
  unknown: 'Sans réponse',
  off_topic: 'Hors sujet',
};

/** Nombre de questions montrées d'abord. */
const ENTRIES_SHOWN = 8;

/**
 * Ce qui est demandé à l'assistant, tous comptes réunis : les questions qu'il n'a pas su traiter disent ce qui
 * manque aux textes du site. L'API ne dit jamais quel compte a posé une question.
 */
@Component({
  selector: 'app-assistant-card',
  imports: [CountPipe, UsdPipe, ParisDatePipe],
  templateUrl: './assistant-card.component.html',
  styleUrl: './assistant-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssistantCardComponent {
  /** Change quand les chiffres sont à relire. */
  readonly version = input(0);

  protected readonly periods = PERIODS;
  protected readonly filters = FILTERS;
  protected readonly labels = OUTCOME_LABELS;
  protected readonly days = signal<Days>(30);
  protected readonly filter = signal<Filter>('all');
  protected readonly all = signal(false);
  // undefined : en cours de lecture
  protected readonly overview = signal<AssistantOverview | undefined>(undefined);
  protected readonly error = signal('');
  /** Dernière question copiée pour le jeu d'évaluation, et si la copie a réussi. */
  protected readonly copied = signal<{ question: string; state: 'copied' | 'failed' } | null>(null);

  private readonly window = inject(DOCUMENT).defaultView;

  private readonly filtered = computed(() => {
    const filter = this.filter();
    const entries = this.overview()?.entries ?? [];
    if (filter === 'all') {
      return entries;
    }
    return entries.filter((entry) =>
      filter === 'down' ? entry.feedback === 'down' : entry.outcome === filter,
    );
  });
  protected readonly entries = computed(() =>
    this.filtered().slice(0, this.all() ? undefined : ENTRIES_SHOWN),
  );
  protected readonly hidden = computed(() => this.filtered().length - this.entries().length);

  constructor() {
    const tracking = inject(TrackingService);
    effect(() => {
      this.version();
      tracking.getAssistant(this.days()).subscribe({
        next: (overview) => {
          this.overview.set(overview);
          this.error.set('');
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  /** Dit si la réponse cite ce texte, parmi ceux où la recherche est allée. */
  protected isCited(entry: AssistantJournalEntry, source: AssistantSource): boolean {
    return entry.sources.some(
      (cited) => cited.title === source.title && cited.section === source.section,
    );
  }

  /**
   * Copie la question au format du jeu d'évaluation (evaluation_cases.json), à coller dans le fichier puis à
   * compléter : un identifiant, les sections des textes qui portent la réponse, et la réponse attendue.
   */
  protected copyCase(entry: AssistantJournalEntry): void {
    const skeleton = {
      id: '',
      question: entry.question,
      outcome: 'answered',
      sections: [],
      reference: '',
    };
    const done = (state: 'copied' | 'failed') =>
      this.copied.set({ question: entry.question, state });
    // Refusé hors d'une page sécurisée, ou si le navigateur l'interdit : on le dit plutôt que de se taire
    const copy = this.window?.navigator.clipboard?.writeText(
      `${JSON.stringify(skeleton, null, 2)},`,
    );
    if (copy) {
      copy.then(
        () => done('copied'),
        () => done('failed'),
      );
    } else {
      done('failed');
    }
  }

  protected choose(days: Days): void {
    this.days.set(days);
    this.all.set(false);
  }

  protected show(filter: Filter): void {
    this.filter.set(filter);
    this.all.set(false);
  }

  protected showAll(): void {
    this.all.set(true);
  }
}
