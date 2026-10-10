import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AssistantConversation, AssistantMessage, AssistantProgress } from '../core/api.models';
import { FETCH } from '../core/search-run.service';
import { AssistantComponent } from './assistant.component';

const ANSWER: AssistantMessage = {
  id: 1,
  created_at: '2026-10-10T10:00:00Z',
  question: 'Comment déposer mon CV ?',
  answer: 'Ouvrez la rubrique Profil.',
  outcome: 'answered',
  sources: [
    {
      title: "Guide d'utilisation",
      section: 'Déposer ou remplacer son CV',
      url: null,
      screen: '/profil',
    },
    {
      title: 'Règles de confidentialité',
      section: 'Vos droits',
      url: '/confidentialite#vos-droits',
      screen: null,
    },
  ],
  consulted: [],
  feedback: null,
};

function conversation(changes: Partial<AssistantConversation> = {}): AssistantConversation {
  return {
    messages: [],
    remaining_questions: 20,
    max_questions_per_day: 20,
    max_account_questions_per_day: 10,
    max_question_chars: 500,
    retention_days: 90,
    ...changes,
  };
}

function event(name: string, data: unknown): string {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}

function progress(values: Partial<AssistantProgress>): string {
  return event('progress', { step: 'generate', answer: null, ...values });
}

/** Flux d'une réponse, que le test laisse avancer morceau par morceau. */
function controlledStream(): {
  response: Response;
  push: (chunk: string) => void;
  end: () => void;
} {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start: (given) => void (controller = given) });
  return {
    response: new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } }),
    push: (chunk) => controller.enqueue(encoder.encode(chunk)),
    end: () => controller.close(),
  };
}

describe('AssistantComponent', () => {
  let fixture: ComponentFixture<AssistantComponent>;
  let http: HttpTestingController;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    fetchMock = vi.fn();
    await TestBed.configureTestingModule({
      imports: [AssistantComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: FETCH, useValue: fetchMock },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AssistantComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return (element().textContent ?? '').replace(/\s+/g, ' ');
  }

  function button(label: string): HTMLButtonElement {
    return [...element().querySelectorAll('button')].find(
      (candidate) =>
        candidate.getAttribute('aria-label') === label || candidate.textContent?.includes(label),
    )!;
  }

  async function settle(): Promise<void> {
    // Le flux se lit par promesses successives : on laisse la file se vider avant de regarder l'écran
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  }

  async function openWith(served: AssistantConversation): Promise<void> {
    button("Ouvrir l'assistant").click();
    http.expectOne({ method: 'GET', url: '/api/assistant' }).flush(served);
    await fixture.whenStable();
  }

  async function type(question: string): Promise<void> {
    const field = element().querySelector('textarea')!;
    field.value = question;
    field.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  function sentBody(): unknown {
    return JSON.parse(fetchMock.mock.calls.at(-1)![1].body as string);
  }

  it('should call nothing until it is opened', () => {
    expect(element().querySelector('.panel')).toBeNull();
    http.expectNone('/api/assistant');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('should suggest questions while the conversation is empty', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await openWith(conversation());

    expect(text()).toContain('Une question sur JobGrep ?');
    expect(text()).toContain("20 questions restantes aujourd'hui");
    expect(text()).toContain('gardées 90 jours');

    button('Comment supprimer mes données ?').click();
    await settle();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/assistant/questions/stream');
    expect(sentBody()).toEqual({
      question: 'Comment supprimer mes données ?',
      new_conversation: false,
    });
    stream.push(event('result', { message: ANSWER, remaining_questions: 19 }));
    stream.end();
    await settle();
  });

  it('should show each step, then the answer while it is written, then where it comes from', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await openWith(conversation());
    await type('  Comment déposer mon CV ?  ');

    button('Envoyer la question').click();
    await settle();
    // La question est affichée dès son envoi, et rien d'autre ne part en attendant
    expect(text()).toContain('Comment déposer mon CV ?');
    expect(button('Envoyer la question').disabled).toBe(true);
    expect(sentBody()).toEqual({ question: 'Comment déposer mon CV ?', new_conversation: false });

    stream.push(progress({ step: 'retrieve' }));
    await settle();
    expect(text()).toContain('Je cherche dans les textes du site…');
    stream.push(progress({ step: 'generate' }));
    await settle();
    expect(text()).toContain('Je rédige la réponse…');
    stream.push(progress({ answer: 'Ouvrez la rubrique' }));
    await settle();
    expect(text()).toContain('Ouvrez la rubrique');
    expect(text()).not.toContain('Je rédige la réponse…');

    stream.push(event('result', { message: ANSWER, remaining_questions: 19 }));
    stream.end();
    await settle();

    expect(text()).toContain('Ouvrez la rubrique Profil.');
    expect(text()).toContain("Guide d'utilisation · Déposer ou remplacer son CV");
    // Une page du site s'ouvre à sa section ; une section du guide mène à l'écran dont elle parle
    const links = [...element().querySelectorAll<HTMLAnchorElement>('.sources a')];
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/profil',
      '/confidentialite#vos-droits',
    ]);
    expect(text()).toContain('19 questions restantes');
    expect(element().querySelector('textarea')!.value).toBe('');
  });

  it('should say that it consults the account, and that it did', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await openWith(conversation());
    await type('Combien de recherches me reste-t-il ?');

    button('Envoyer la question').click();
    await settle();
    stream.push(progress({ step: 'consult' }));
    await settle();
    expect(text()).toContain('Je consulte votre compte…');

    const answered = {
      ...ANSWER,
      answer: 'Il vous reste 1 recherche.',
      consulted: ['État de votre compte'],
    };
    stream.push(event('result', { message: answered, remaining_questions: 19 }));
    stream.end();
    await settle();
    expect(text()).toContain('Consulté : État de votre compte');
    // L'avertissement dit ce que l'assistant peut voir, et ce qu'il ne voit jamais
    expect(text()).toContain(
      "Il peut consulter l'état de votre compte, jamais votre CV ni vos offres",
    );
  });

  it('should show the earlier conversation again', async () => {
    await openWith(conversation({ messages: [ANSWER], remaining_questions: null }));

    expect(text()).toContain('Ouvrez la rubrique Profil.');
    // Le propriétaire n'a pas de quota : rien n'est décompté
    expect(text()).not.toContain('restante');
    expect(element().querySelector('.welcome')).toBeNull();
  });

  it('should start a new conversation that forgets the previous one', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await openWith(conversation({ messages: [ANSWER] }));

    button('Nouvelle conversation').click();
    await fixture.whenStable();
    expect(text()).not.toContain('Ouvrez la rubrique Profil.');
    expect(element().querySelector('.welcome')).not.toBeNull();

    await type('Comment changer de thème ?');
    button('Envoyer la question').click();
    await settle();
    // L'API apprend que cette question ouvre une conversation
    expect(sentBody()).toEqual({ question: 'Comment changer de thème ?', new_conversation: true });
    stream.push(event('result', { message: { ...ANSWER, id: 2 }, remaining_questions: 18 }));
    stream.end();
    await settle();

    // La suivante, elle, continue la conversation
    fetchMock.mockResolvedValue(controlledStream().response);
    await type('Et ensuite ?');
    button('Envoyer la question').click();
    await settle();
    expect(sentBody()).toEqual({ question: 'Et ensuite ?', new_conversation: false });
  });

  it('should rate an answer, and take the rating back', async () => {
    await openWith(conversation({ messages: [ANSWER] }));

    button('Réponse pas utile').click();
    await fixture.whenStable();
    const request = http.expectOne({ method: 'PUT', url: '/api/assistant/messages/1/feedback' });
    expect(request.request.body).toEqual({ feedback: 'down' });
    request.flush(null);
    expect(button('Réponse pas utile').getAttribute('aria-pressed')).toBe('true');

    // Cliquer la note déjà donnée la retire ; si le serveur refuse, elle revient
    button('Réponse pas utile').click();
    await fixture.whenStable();
    const undo = http.expectOne({ method: 'PUT', url: '/api/assistant/messages/1/feedback' });
    expect(undo.request.body).toEqual({ feedback: null });
    undo.flush({ detail: 'Erreur' }, { status: 500, statusText: '' });
    await fixture.whenStable();
    expect(button('Réponse pas utile').getAttribute('aria-pressed')).toBe('true');
  });

  it('should keep the question when the API refuses it', async () => {
    const detail = "Le budget du jour de l'application est atteint : revenez demain.";
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 429 }));
    await openWith(conversation());
    await type('Comment déposer mon CV ?');

    button('Envoyer la question').click();
    await settle();

    expect(text()).toContain('revenez demain');
    expect(element().querySelector('textarea')!.value).toBe('Comment déposer mon CV ?');
  });

  it('should say when the assistant fails while answering', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await openWith(conversation());
    await type('Comment déposer mon CV ?');

    button('Envoyer la question').click();
    await settle();
    stream.push(progress({ step: 'retrieve' }));
    stream.push(
      event('error', {
        detail: "L'assistant ne répond pas pour l'instant. Réessayez dans un moment.",
      }),
    );
    stream.end();
    await settle();

    expect(text()).toContain("L'assistant ne répond pas pour l'instant");
    expect(element().querySelector('textarea')!.value).toBe('Comment déposer mon CV ?');
    expect(text()).not.toContain('Je cherche dans les textes');
  });

  it('should stop asking once the daily quota is used', async () => {
    await openWith(conversation({ remaining_questions: 0 }));

    expect(text()).toContain("Vous avez posé toutes vos questions d'aujourd'hui.");
    expect(element().querySelector('textarea')!.disabled).toBe(true);
    expect(button('Comment déposer mon CV ?').disabled).toBe(true);
  });
});
