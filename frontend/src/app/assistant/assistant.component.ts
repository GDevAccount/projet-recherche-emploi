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

import { apiErrorMessage } from '../core/api-error';
import { AssistantConversation, AssistantMessage } from '../core/api.models';
import { AssistantService } from '../core/assistant.service';

/** Questions proposées tant que la conversation est vide. */
const SUGGESTIONS = [
  'Comment déposer mon CV ?',
  'Que devient mon CV après le dépôt ?',
  'Combien de recherches puis-je lancer ?',
  'Comment supprimer mes données ?',
];

/**
 * Assistant de l'application : un bouton en bas de l'écran, qui ouvre une conversation. Il ne répond qu'aux
 * questions sur JobGrep, à partir des textes du site ; réponses, sources et quota viennent de l'API.
 */
@Component({
  selector: 'app-assistant',
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
  protected readonly error = signal('');

  protected readonly exhausted = computed(() => this.remaining() === 0);
  protected readonly canSend = computed(
    () => !!this.conversation() && !this.pending() && !this.exhausted() && !!this.draft().trim(),
  );

  constructor() {
    // Le dernier message reste visible : la conversation suit ce qui s'y ajoute
    afterRenderEffect(() => {
      this.messages();
      this.pending();
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
    // Après l'affichage du panneau : le champ n'existe pas avant
    setTimeout(() => this.field()?.nativeElement.focus());
  }

  protected close(): void {
    this.open.set(false);
  }

  protected send(question = this.draft()): void {
    question = question.trim();
    if (!question || this.pending() || this.exhausted() || !this.conversation()) {
      return;
    }
    this.pending.set(question);
    this.draft.set('');
    this.error.set('');
    this.assistant.ask(question).subscribe({
      next: (reply) => {
        this.messages.update((messages) => [...messages, reply.message]);
        this.remaining.set(reply.remaining_questions);
        this.pending.set('');
      },
      error: (error: unknown) => {
        // La question revient dans le champ : elle n'est pas perdue
        this.draft.set(question);
        this.pending.set('');
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  protected onEnter(event: Event): void {
    // Entrée envoie ; Maj + Entrée va à la ligne
    if (!(event as KeyboardEvent).shiftKey) {
      event.preventDefault();
      this.send();
    }
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
