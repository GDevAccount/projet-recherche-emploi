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
  AssistantEvaluation,
  AssistantEvaluationCase,
  AssistantEvaluationDetail,
  AssistantOutcome,
} from '../core/api.models';
import { DurationPipe, SharePipe, UsdPipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';
import { TrackingService } from '../core/tracking.service';

/** Mesures d'une évaluation, dans l'ordre des colonnes. */
const MEASURES: { key: keyof AssistantEvaluation; label: string; hint: string }[] = [
  {
    key: 'retrieval_rate',
    label: 'Section retrouvée',
    hint: 'La section attendue est parmi les passages donnés au modèle',
  },
  {
    key: 'outcome_rate',
    label: 'Bonne issue',
    hint: "Réponse, renvoi vers l'exploitant ou refus, comme attendu",
  },
  {
    key: 'correct_rate',
    label: 'Réponse juste',
    hint: 'La réponse dit ce que dit la réponse de référence',
  },
  {
    key: 'faithful_rate',
    label: 'Fidèle',
    hint: 'La réponse ne dit que ce que disent les passages',
  },
  {
    key: 'refusal_rate',
    label: 'Hors-sujet refusé',
    hint: 'Les questions hors sujet sont refusées',
  },
  {
    key: 'consult_rate',
    label: 'Compte consulté à propos',
    hint: 'Le compte est consulté quand la question le demande, et seulement alors',
  },
];

const OUTCOME_LABELS: Record<AssistantOutcome, string> = {
  answered: 'une réponse',
  unknown: "un renvoi vers l'exploitant",
  off_topic: 'un refus',
};

/**
 * Évaluations de l'assistant sur ses questions de référence : une ligne par passage du banc, à comparer d'une
 * version des consignes à l'autre. Les mesures viennent de l'API ; une évaluation se lance par « jobgrep evaluate ».
 */
@Component({
  selector: 'app-evaluation-card',
  imports: [SharePipe, UsdPipe, DurationPipe, ParisDatePipe],
  templateUrl: './evaluation-card.component.html',
  styleUrl: './evaluation-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EvaluationCardComponent {
  /** Change quand les chiffres sont à relire. */
  readonly version = input(0);

  private readonly tracking = inject(TrackingService);

  protected readonly measures = MEASURES;
  // undefined : en cours de lecture
  protected readonly evaluations = signal<AssistantEvaluation[] | undefined>(undefined);
  /** Évaluation dépliée, avec le détail de ses questions une fois lu. */
  protected readonly opened = signal<number | null>(null);
  protected readonly detail = signal<AssistantEvaluationDetail | undefined>(undefined);
  protected readonly error = signal('');

  /** Questions à revoir de l'évaluation dépliée. */
  protected readonly failures = computed(() =>
    (this.detail()?.results ?? []).filter((result) => !result.passed),
  );

  constructor() {
    effect(() => {
      this.version();
      this.tracking.listAssistantEvaluations().subscribe({
        next: (evaluations) => {
          this.evaluations.set(evaluations);
          this.error.set('');
        },
        error: (error: unknown) => this.error.set(apiErrorMessage(error)),
      });
    });
  }

  protected rate(evaluation: AssistantEvaluation, key: keyof AssistantEvaluation): number | null {
    return evaluation[key] as number | null;
  }

  protected toggle(evaluation: AssistantEvaluation): void {
    if (this.opened() === evaluation.id) {
      this.opened.set(null);
      return;
    }
    this.opened.set(evaluation.id);
    this.detail.set(undefined);
    this.tracking.getAssistantEvaluation(evaluation.id).subscribe({
      next: (detail) => this.detail.set(detail),
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }

  /** Ce qui est reproché à une question, dans l'ordre où le chercher : la recherche, l'issue, puis la réponse. */
  protected reproach(result: AssistantEvaluationCase): string {
    if (result.rank === null && result.cited !== null) {
      return "La section attendue n'est pas parmi les passages retrouvés.";
    }
    if (result.consult_expected !== null && result.consulted !== result.consult_expected) {
      return result.consult_expected
        ? "Le compte devait être consulté, et ne l'a pas été."
        : 'Le compte a été consulté sans raison.';
    }
    if (result.outcome !== result.expected_outcome) {
      return `Attendu : ${OUTCOME_LABELS[result.expected_outcome]}. Obtenu : ${OUTCOME_LABELS[result.outcome]}.`;
    }
    return result.judge_reason || 'Réponse jugée fausse ou infidèle aux passages.';
  }
}
