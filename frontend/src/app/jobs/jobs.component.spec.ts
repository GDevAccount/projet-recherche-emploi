import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Account, Job, JobStatus } from '../core/api.models';
import { SessionService } from '../core/session.service';
import { JobsComponent } from './jobs.component';

/** États que l'API annonce pour une offre, selon le sien : la règle est côté serveur, ceci la recopie pour les tests. */
function nextStatuses(status: JobStatus, hadInterview: boolean): JobStatus[] {
  switch (status) {
    case 'todo':
      return ['applied'];
    case 'applied':
      return ['interview', 'rejected', 'todo'];
    case 'interview':
      return ['rejected', 'applied'];
    default:
      return [hadInterview ? 'interview' : 'applied'];
  }
}

function job(id: number, values: Partial<Job> = {}): Job {
  const status = values.status ?? 'todo';
  return {
    id,
    url: `https://www.exemple-emploi.fr/offres/${id}`,
    title: `Offre ${id}`,
    content: null,
    score: null,
    contract_type: 'CDI',
    work_location: 'Paris',
    query: 'ingénieur IA',
    match_reason: 'Le profil correspond.',
    status,
    applied_at: null,
    interview_at: null,
    rejected_at: null,
    created_at: '2026-10-08T10:00:00Z',
    next_statuses: nextStatuses(status, !!values.interview_at),
    ...values,
  };
}

const APPLIED: Partial<Job> = { status: 'applied', applied_at: '2026-10-08T12:00:00Z' };
const INTERVIEW: Partial<Job> = { ...APPLIED, status: 'interview', interview_at: '2026-10-09T12:00:00Z' };
const REJECTED: Partial<Job> = { ...APPLIED, status: 'rejected', rejected_at: '2026-10-10T12:00:00Z' };

const NO_CONTENT = { status: 204, statusText: 'No Content' };

const SEARCHING: Account = {
  user_id: 2,
  is_owner: false, is_trial: false, is_admin: false,
  email: null,
  name: null,
  picture: null,
  can_search: true,
  search_running: true,
  remaining_searches: 1,
  max_searches_per_day: 2,
};

describe('JobsComponent', () => {
  let fixture: ComponentFixture<JobsComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [JobsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobsComponent);
    fixture.detectChanges();
    http.expectOne('/api/config').flush({
      login_mode: 'google',
      google_client_id: 'id',
      contract_types: ['CDI'],
      delete_reasons: [
        { code: 'not_my_job', label: "Ce n'est pas mon métier" },
        { code: 'not_interested', label: "Elle ne m'intéresse pas" },
      ],
    });
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(root: Element = element()): string {
    return (root.textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  async function serve(jobs: Job[]): Promise<void> {
    http.expectOne({ method: 'GET', url: '/api/jobs' }).flush(jobs);
    await fixture.whenStable();
  }

  /** Titres des cartes d'une zone, dans l'ordre affiché. */
  function titles(zone: 'todo' | 'applied' | 'interviews' | 'refused'): string[] {
    return [...element().querySelectorAll(`.${zone} app-job-card h3`)].map((title) => text(title));
  }

  function card(title: string): HTMLElement {
    return [...element().querySelectorAll<HTMLElement>('app-job-card')].find(
      (candidate) => text(candidate.querySelector('h3')!) === title,
    )!;
  }

  function dialog(): HTMLDialogElement {
    return element().querySelector('dialog')!;
  }

  /** Clique le bouton qui porte ce texte, ou ce libellé s'il n'a qu'une icône. */
  async function click(root: Element, label: string): Promise<void> {
    [...root.querySelectorAll('button')]
      .find((button) => text(button).startsWith(label) || button.getAttribute('aria-label') === label)!
      .click();
    await fixture.whenStable();
  }

  async function openDiscard(title: string): Promise<void> {
    await click(card(title), `Retirer l'offre « ${title} »`);
  }

  /** Répond à la demande de changement d'état par l'offre telle que l'API la renverrait. */
  async function answerStatus(id: number, status: JobStatus, values: Partial<Job>): Promise<void> {
    const request = http.expectOne({ method: 'PATCH', url: `/api/jobs/${id}` });
    expect(request.request.body).toEqual({ status });
    request.flush(job(id, values));
    await fixture.whenStable();
  }

  async function search(words: string): Promise<void> {
    const input = element().querySelector<HTMLInputElement>('input[name=search]')!;
    input.value = words;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  it('should invite to launch a search when there is no offer', async () => {
    await serve([]);

    expect(text()).toContain("Pas encore d'offre");
    expect(text()).toContain('Lancez une recherche :');
    expect(element().querySelector('.board')).toBeNull();
  });

  it('should not invite to launch a search before the profile is ready', async () => {
    TestBed.inject(SessionService).open('preuve').subscribe();
    http.expectOne('/api/session').flush({ ...SEARCHING, can_search: false, search_running: false });
    await serve([]);

    expect(text()).toContain("Pas encore d'offre");
    expect(text()).toContain('Une fois votre profil complété');
    expect(text()).not.toContain('Lancez une recherche :');
  });

  it('should not invite to launch a search while one is running', async () => {
    TestBed.inject(SessionService).open('preuve').subscribe();
    http.expectOne('/api/session').flush(SEARCHING);
    await serve([]);

    expect(text()).toContain('Recherche en cours');
    expect(text()).not.toContain('Lancez une recherche');
  });

  it('should tell the API when an offer is opened, without waiting for its answer', async () => {
    await serve([job(7)]);
    const link = element().querySelector<HTMLAnchorElement>('app-job-card h3 a')!;
    // Le navigateur de test n'ouvre pas d'onglet : seul le signalement compte ici
    link.addEventListener('click', (event) => event.preventDefault());

    link.click();

    const request = http.expectOne({ method: 'POST', url: '/api/jobs/7/open' });
    // Un refus de l'API ne doit rien afficher : l'annonce, elle, s'est ouverte
    request.flush(null, { status: 500, statusText: 'Erreur' });
    await fixture.whenStable();
    expect(element().querySelector('.p-message-error')).toBeNull();
  });

  it('should sort offers by the state of the application, in the order of the API', async () => {
    await serve([job(5, REJECTED), job(4, INTERVIEW), job(3), job(2, APPLIED), job(1)]);

    expect(titles('todo')).toEqual(['Offre 3', 'Offre 1']);
    expect(titles('applied')).toEqual(['Offre 2']);
    expect(titles('interviews')).toEqual(['Offre 4']);
    expect(titles('refused')).toEqual(['Offre 5']);
    expect(text(card('Offre 2'))).toContain('Postulé le 8 oct.');
    expect(text(card('Offre 4'))).toContain('Entretien depuis le 9 oct.');
    expect(text(card('Offre 5'))).toContain('Refusée le 10 oct.');
  });

  it('should put interviews first and keep refused applications folded', async () => {
    await serve([job(3, REJECTED), job(2, INTERVIEW), job(1)]);

    const zones = [...element().querySelectorAll('.tracking > *')].map((zone) => zone.className);
    expect(zones[0]).toContain('interviews');
    expect(zones.at(-1)).toContain('refused');
    const refused = element().querySelector<HTMLDetailsElement>('details.refused')!;
    expect(refused.open).toBe(false);
    expect(text(refused.querySelector('summary')!)).toBe('Candidatures refusées 1');
  });

  it('should show neither interviews nor refused applications when there is none', async () => {
    await serve([job(2, APPLIED), job(1)]);

    expect(element().querySelector('.interviews')).toBeNull();
    expect(element().querySelector('.refused')).toBeNull();
  });

  it('should count the offers, whatever the filters', async () => {
    await serve([job(1), job(2), job(3, APPLIED), job(4, { ...INTERVIEW, contract_type: 'freelance' }), job(5, REJECTED)]);
    await search('introuvable');

    const tiles = [...element().querySelectorAll('.stats .tile')].map((tile) => text(tile));
    expect(tiles[0]).toMatch(/^2\s*à traiter$/);
    // Une candidature refusée ou suivie d'un entretien a bien été envoyée
    expect(tiles[1]).toMatch(/^3\s*candidatures envoyées$/);
    expect(tiles[2]).toMatch(/^1\s*entretien$/);
    expect(tiles[3]).toMatch(/3\s+offres sur\s+5\s+ont reçu une candidature/);
    expect(tiles[3]).toContain('60 %');
  });

  it('should not count the interviews until there is one', async () => {
    await serve([job(1), job(2, APPLIED)]);

    const tiles = () => [...element().querySelectorAll('.stats .tile')].map((tile) => text(tile));
    expect(tiles().length).toBe(3);
    expect(tiles().join(' ')).not.toContain('entretien');

    await click(card('Offre 2'), 'Entretien obtenu');
    await answerStatus(2, 'interview', INTERVIEW);

    expect(tiles()[2]).toMatch(/^1\s*entretien$/);
  });

  it('should show what the model read on the page, or say it was not stated', async () => {
    await serve([job(1, { contract_type: null, work_location: null }), job(2, { work_location: 'Remote (Berlin)' })]);

    expect(text(card('Offre 1'))).toContain('Contrat non précisé');
    expect(text(card('Offre 1'))).toContain('Lieu non précisé');
    expect(text(card('Offre 2'))).toContain('Remote (Berlin)');
    expect(text(card('Offre 2'))).toContain('exemple-emploi.fr');
  });

  it('should search in titles, places and reasons, ignoring accents and case', async () => {
    await serve([
      job(1, { title: 'Ingénieur IA chez Acme' }),
      job(2, { work_location: 'Lyon' }),
      job(3, { match_reason: 'Expérience LangGraph demandée' }),
    ]);

    await search('ingenieur');
    expect(titles('todo')).toEqual(['Ingénieur IA chez Acme']);
    await search('LYON');
    expect(titles('todo')).toEqual(['Offre 2']);
    await search('langgraph');
    expect(titles('todo')).toEqual(['Offre 3']);
    expect(text(element().querySelector('.result')!)).toContain('1 sur 3');

    await click(element(), 'Tout afficher');
    expect(titles('todo').length).toBe(3);
  });

  it('should filter by the contracts found in the offers', async () => {
    await serve([job(1), job(2, { contract_type: 'freelance' }), job(3, { contract_type: null })]);

    const chips = [...element().querySelectorAll('.chips button')].map((chip) => text(chip));
    expect(chips).toEqual(['CDI', 'freelance', 'non précisé']);

    await click(element(), 'freelance');
    expect(titles('todo')).toEqual(['Offre 2']);
    await click(element(), 'non précisé');
    expect(titles('todo')).toEqual(['Offre 2', 'Offre 3']);
  });

  it('should mark an offer as applied and read its date from the API', async () => {
    await serve([job(1), job(2)]);

    await click(card('Offre 1'), "J'ai postulé");
    await answerStatus(1, 'applied', APPLIED);

    // L'offre renvoyée par l'API remplace la carte : la date n'est pas inventée, et la liste n'est pas rechargée
    expect(titles('applied')).toEqual(['Offre 1']);
    expect(text(card('Offre 1'))).toContain('Postulé le 8 oct.');
    http.expectNone('/api/jobs');
  });

  it('should keep each card in its column when two offers are marked one after the other', async () => {
    await serve([job(1), job(2)]);

    await click(card('Offre 1'), "J'ai postulé");
    await click(card('Offre 2'), "J'ai postulé");
    const [first, second] = [1, 2].map((id) => http.expectOne({ method: 'PATCH', url: `/api/jobs/${id}` }));
    // Les réponses arrivent dans le désordre : aucune ne défait l'autre
    second.flush(job(2, APPLIED));
    first.flush(job(1, APPLIED));
    await fixture.whenStable();

    expect(titles('applied')).toEqual(['Offre 1', 'Offre 2']);
    expect(titles('todo')).toEqual([]);
  });

  it('should move an application to the interviews, and back', async () => {
    await serve([job(1, APPLIED)]);

    await click(card('Offre 1'), 'Entretien obtenu');
    await answerStatus(1, 'interview', INTERVIEW);

    expect(titles('interviews')).toEqual(['Offre 1']);
    expect(titles('applied')).toEqual([]);
    // Une carte en entretien n'a plus d'étape suivante à proposer : seulement le retour, et la corbeille
    expect(card('Offre 1').querySelector('button.primary')).toBeNull();

    await click(card('Offre 1'), "Annuler l'entretien");
    await answerStatus(1, 'applied', APPLIED);

    expect(titles('applied')).toEqual(['Offre 1']);
    expect(element().querySelector('.interviews')).toBeNull();
  });

  it('should put an applied offer back to do', async () => {
    await serve([job(1, APPLIED)]);

    await click(card('Offre 1'), 'Remettre à traiter');
    await answerStatus(1, 'todo', {});

    expect(titles('todo')).toEqual(['Offre 1']);
  });

  it('should only offer the states the API announces for an offer', async () => {
    await serve([job(1, { ...APPLIED, next_statuses: ['todo'] })]);

    expect(card('Offre 1').querySelector('button.primary')).toBeNull();
    await openDiscard('Offre 1');
    expect(text(dialog())).not.toContain("L'employeur a refusé");
  });

  it('should mark an offer as applied when it is dropped on the applied column', async () => {
    await serve([job(1), job(2, APPLIED)]);

    card('Offre 1').dispatchEvent(new Event('dragstart'));
    const over = new Event('dragover', { cancelable: true });
    const column = element().querySelector('.column.applied')!;
    column.dispatchEvent(over);
    // Une zone n'accepte que les cartes qui peuvent prendre son état
    expect(over.defaultPrevented).toBe(true);
    const back = new Event('dragover', { cancelable: true });
    element().querySelector('.column.todo')!.dispatchEvent(back);
    expect(back.defaultPrevented).toBe(false);

    column.dispatchEvent(new Event('drop', { cancelable: true }));
    await answerStatus(1, 'applied', APPLIED);

    expect(titles('applied')).toEqual(['Offre 1', 'Offre 2']);
  });

  it('should ask what to do with an offer when its bin is clicked, and do nothing if cancelled', async () => {
    await serve([job(1, APPLIED)]);
    expect(dialog().hasAttribute('open')).toBe(false);

    await openDiscard('Offre 1');

    expect(dialog().hasAttribute('open')).toBe(true);
    expect(text(dialog())).toContain('Que faire de cette offre ?');
    expect(text(dialog())).toContain('Offre 1');

    await click(dialog(), 'Annuler');
    expect(dialog().hasAttribute('open')).toBe(false);
    expect(titles('applied')).toEqual(['Offre 1']);
  });

  it('should file an application refused by the employer, where it can be found and reopened', async () => {
    await serve([job(1, APPLIED), job(2, APPLIED)]);

    await openDiscard('Offre 1');
    await click(dialog(), "L'employeur a refusé ma candidature");
    await answerStatus(1, 'rejected', REJECTED);

    expect(dialog().hasAttribute('open')).toBe(false);
    expect(titles('applied')).toEqual(['Offre 2']);
    expect(titles('refused')).toEqual(['Offre 1']);

    await click(card('Offre 1'), 'Rouvrir la candidature');
    await answerStatus(1, 'applied', APPLIED);
    expect(titles('applied')).toEqual(['Offre 1', 'Offre 2']);
  });

  it('should not offer to declare a refusal for an offer never applied to', async () => {
    await serve([job(1)]);

    await openDiscard('Offre 1');

    expect(text(dialog())).not.toContain("L'employeur a refusé");
    expect(text(dialog())).toContain('Supprimer cette annonce');
  });

  it('should delete an offer from the same window', async () => {
    await serve([job(1), job(2)]);

    await openDiscard('Offre 1');
    http.expectNone({ method: 'DELETE', url: '/api/jobs/1' });
    expect(text(dialog())).toContain('ne reviendra pas');

    // La fenêtre demande d'abord pourquoi : rien n'est supprimé avant la réponse
    await click(dialog(), 'Supprimer cette annonce');
    http.expectNone((request) => request.method === 'DELETE');
    expect(text(dialog())).toContain('Pourquoi la supprimer ?');

    await click(dialog(), "Ce n'est pas mon métier");
    const request = http.expectOne((sent) => sent.method === 'DELETE' && sent.url === '/api/jobs/1');
    expect(request.request.params.get('reason')).toBe('not_my_job');
    request.flush(null, NO_CONTENT);
    await fixture.whenStable();

    expect(titles('todo')).toEqual(['Offre 2']);
    expect(dialog().hasAttribute('open')).toBe(false);
  });

  it('should delete an offer without a reason when none is given', async () => {
    await serve([job(1)]);

    await openDiscard('Offre 1');
    await click(dialog(), 'Supprimer cette annonce');
    await click(dialog(), 'Supprimer sans préciser');
    const request = http.expectOne((sent) => sent.method === 'DELETE' && sent.url === '/api/jobs/1');
    expect(request.request.params.has('reason')).toBe(false);
    request.flush(null, NO_CONTENT);
    await fixture.whenStable();

    expect(titles('todo')).toEqual([]);
    // La fenêtre rouverte repart de sa première question
    expect(text(dialog())).not.toContain('Pourquoi la supprimer ?');
  });

  it('should leave an offer in place and say why when the API refuses', async () => {
    await serve([job(1)]);

    await click(card('Offre 1'), "J'ai postulé");
    http
      .expectOne({ method: 'PATCH', url: '/api/jobs/1' })
      .flush({ detail: "Cette offre n'existe pas." }, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();

    expect(titles('todo')).toEqual(['Offre 1']);
    expect(text()).toContain("Cette offre n'existe pas.");
  });
});
