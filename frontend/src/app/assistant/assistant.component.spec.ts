import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AssistantConversation, AssistantMessage } from '../core/api.models';
import { AssistantComponent } from './assistant.component';

const ANSWER: AssistantMessage = {
  id: 1,
  created_at: '2026-10-10T10:00:00Z',
  question: 'Comment déposer mon CV ?',
  answer: 'Ouvrez la rubrique Profil.',
  outcome: 'answered',
  sources: [
    { title: "Guide d'utilisation", section: 'Déposer ou remplacer son CV', url: null },
    { title: 'Règles de confidentialité', section: null, url: '/confidentialite' },
  ],
};

function conversation(changes: Partial<AssistantConversation> = {}): AssistantConversation {
  return {
    messages: [],
    remaining_questions: 20,
    max_questions_per_day: 20,
    max_question_chars: 500,
    retention_days: 90,
    ...changes,
  };
}

describe('AssistantComponent', () => {
  let fixture: ComponentFixture<AssistantComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AssistantComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
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

  it('should call nothing until it is opened', () => {
    expect(element().querySelector('.panel')).toBeNull();
    http.expectNone('/api/assistant');
  });

  it('should suggest questions while the conversation is empty', async () => {
    await openWith(conversation());

    expect(text()).toContain('Une question sur JobGrep ?');
    expect(text()).toContain("20 questions restantes aujourd'hui");
    expect(text()).toContain('gardées 90 jours');

    button('Comment supprimer mes données ?').click();
    const request = http.expectOne({ method: 'POST', url: '/api/assistant/questions' });
    expect(request.request.body).toEqual({ question: 'Comment supprimer mes données ?' });
    request.flush({ message: ANSWER, remaining_questions: 19 });
  });

  it('should show the answer with the texts it comes from', async () => {
    await openWith(conversation());
    await type('  Comment déposer mon CV ?  ');
    expect(button('Envoyer la question').disabled).toBe(false);

    button('Envoyer la question').click();
    await fixture.whenStable();
    // La question est affichée dès son envoi, et rien d'autre ne part en attendant
    expect(text()).toContain('Comment déposer mon CV ?');
    expect(button('Envoyer la question').disabled).toBe(true);
    const request = http.expectOne({ method: 'POST', url: '/api/assistant/questions' });
    expect(request.request.body).toEqual({ question: 'Comment déposer mon CV ?' });
    request.flush({ message: ANSWER, remaining_questions: 19 });
    await fixture.whenStable();

    expect(text()).toContain('Ouvrez la rubrique Profil.');
    expect(text()).toContain("Guide d'utilisation · Déposer ou remplacer son CV");
    // Seule une page du site est un lien
    const links = [...element().querySelectorAll<HTMLAnchorElement>('.sources a')];
    expect(links.map((link) => link.getAttribute('href'))).toEqual(['/confidentialite']);
    expect(text()).toContain('19 questions restantes');
    expect(element().querySelector('textarea')!.value).toBe('');
  });

  it('should show the earlier conversation again', async () => {
    await openWith(conversation({ messages: [ANSWER], remaining_questions: null }));

    expect(text()).toContain('Ouvrez la rubrique Profil.');
    // Le propriétaire n'a pas de quota : rien n'est décompté
    expect(text()).not.toContain('restante');
    expect(element().querySelector('.welcome')).toBeNull();
  });

  it('should keep the question when the API refuses it', async () => {
    await openWith(conversation());
    await type('Comment déposer mon CV ?');

    button('Envoyer la question').click();
    http
      .expectOne({ method: 'POST', url: '/api/assistant/questions' })
      .flush(
        { detail: "Le budget du jour de l'application est atteint : revenez demain." },
        { status: 429, statusText: '' },
      );
    await fixture.whenStable();

    expect(text()).toContain('revenez demain');
    expect(element().querySelector('textarea')!.value).toBe('Comment déposer mon CV ?');
  });

  it('should stop asking once the daily quota is used', async () => {
    await openWith(conversation({ remaining_questions: 0 }));

    expect(text()).toContain("Vous avez posé toutes vos questions d'aujourd'hui.");
    expect(element().querySelector('textarea')!.disabled).toBe(true);
    expect(button('Comment déposer mon CV ?').disabled).toBe(true);
  });
});
