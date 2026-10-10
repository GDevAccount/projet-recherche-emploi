import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterRenderEffect,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { apiErrorMessage } from '../core/api-error';
import {
  AssistantConversation,
  AssistantFeedback,
  AssistantMessage,
  AssistantStep,
} from '../core/api.models';
import { AssistantService } from '../core/assistant.service';

/** Questions proposées tant que la conversation est vide. */
const SUGGESTIONS = [
  'Comment déposer mon CV ?',
  'Que devient mon CV après le dépôt ?',
  'Combien de recherches puis-je lancer ?',
  'Comment supprimer mes données ?',
];

/** Ce que l'assistant dit faire à chaque étape, tant que sa réponse ne s'écrit pas encore. */
const STEP_LABELS: Record<AssistantStep, string> = {
  retrieve: 'Je cherche dans les textes du site…',
  generate: 'Je rédige la réponse…',
};

/**
 * Assistant de l'application : un bouton en bas de l'écran, qui ouvre une conversation. Il ne répond qu'aux
 * questions sur JobGrep, à partir des textes du site ; réponses, sources et quota viennent de l'API.
 */
@Component({
  selector: 'app-assistant',
  imports: [RouterLink],
  templateUrl: './assistant.component.html',
  styleUrl: './assistant.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown.escape)': 'close()' },
})
export class AssistantComponent {
  private readonly assistant = inject(AssistantService);
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');
  private readonly field = viewChild<ElementRef<HTMLTextAreaElement>>('field');

  protected readonly suggestions = SUGGESTIONS;
  protected readonly open = signal(false);
  // undefined : pas encore lue, ce qui n'arrive qu'à la première ouverture
  protected readonly conversation = signal<AssistantConversation | undefined>(undefined);
  protected readonly messages = signal<AssistantMessage[]>([]);
  protected readonly remaining = signal<number | null>(null);
  protected readonly draft = signal('');
  /** Question partie, dont la réponse est attendue. */
  protected readonly pending = signal('');
  /** Étape en cours de la réponse attendue, et son texte à mesure qu'il s'écrit. */
  protected readonly step = signal<AssistantStep | null>(null);
  protected readonly writing = signal('');
  /** Vrai quand la prochaine question ouvre une conversation : l'assistant oublie les échanges d'avant. */
  protected readonly fresh = signal(false);
  protected readonly error = signal('');

  protected readonly exhausted = computed(() => this.remaining() === 0);
  protected readonly canSend = computed(
    () => !!this.conversation() && !this.pending() && !this.exhausted() && !!this.draft().trim(),
  );
  protected readonly stepLabel = computed(() => {
    const step = this.step();
    return step ? STEP_LABELS[step] : '';
  });

  constructor() {
    // Le dernier message reste visible : la conversation suit ce qui s'y ajoute
    afterRenderEffect(() => {
      this.messages();
      this.pending();
      this.writing();
      const thread = this.thread()?.nativeElement;
      if (this.open() && thread) {
        thread.scrollTop = thread.scrollHeight;
      }
    });
  }

  protected toggle(): void {
    if (this.open()) {
      this.close();
      return;
    }
    this.open.set(true);
    if (!this.conversation()) {
      this.load();
    }
    this.focusField();
  }

  protected close(): void {
    this.open.set(false);
  }

  /** Vide l'écran et repart de zéro : la question suivante ne renverra plus aux précédentes. */
  protected startOver(): void {
    this.messages.set([]);
    this.fresh.set(true);
    this.error.set('');
    this.focusField();
  }

  protected async send(question = this.draft()): Promise<void> {
    question = question.trim();
    if (!question || this.pending() || this.exhausted() || !this.conversation()) {
      return;
    }
    this.pending.set(question);
    this.draft.set('');
    this.error.set('');
    try {
      const reply = await this.assistant.ask(question, this.fresh(), (event) => {
        this.step.set(event.step);
        this.writing.set(event.answer ?? '');
      });
      this.messages.update((messages) => [...messages, reply.message]);
      this.remaining.set(reply.remaining_questions);
      this.fresh.set(false);
    } catch (error) {
      // La question revient dans le champ : elle n'est pas perdue
      this.draft.set(question);
      this.error.set(error instanceof Error ? error.message : apiErrorMessage(error));
    } finally {
      this.pending.set('');
      this.step.set(null);
      this.writing.set('');
    }
  }

  /** Note une réponse ; cliquer la note déjà donnée la retire. */
  protected rate(message: AssistantMessage, feedback: AssistantFeedback): void {
    const previous = message.feedback;
    const next = previous === feedback ? null : feedback;
    this.setFeedback(message.id, next);
    this.assistant.setFeedback(message.id, next).subscribe({
      // La note affichée est celle que le serveur a : un échec la remet comme avant
      error: () => this.setFeedback(message.id, previous),
    });
  }

  protected onEnter(event: Event): void {
    // Entrée envoie ; Maj + Entrée va à la ligne
    if (!(event as KeyboardEvent).shiftKey) {
      event.preventDefault();
      void this.send();
    }
  }

  private setFeedback(id: number, feedback: AssistantFeedback | null): void {
    this.messages.update((messages) =>
      messages.map((message) => (message.id === id ? { ...message, feedback } : message)),
    );
  }

  private focusField(): void {
    // Après l'affichage du panneau : le champ n'existe pas avant
    setTimeout(() => this.field()?.nativeElement.focus());
  }

  private load(): void {
    this.error.set('');
    this.assistant.getConversation().subscribe({
      next: (conversation) => {
        this.conversation.set(conversation);
        this.messages.set(conversation.messages);
        this.remaining.set(conversation.remaining_questions);
      },
      error: (error: unknown) => this.error.set(apiErrorMessage(error)),
    });
  }
}
