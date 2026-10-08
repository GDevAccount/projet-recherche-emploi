import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Job } from '../core/api.models';
import { JobsComponent } from './jobs.component';

function job(id: number, values: Partial<Job> = {}): Job {
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
    applied: false,
    applied_at: null,
    created_at: '2026-10-08T10:00:00Z',
    ...values,
  };
}

const NO_CONTENT = { status: 204, statusText: 'No Content' };

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

  /** Titres des cartes d'une colonne, dans l'ordre affiché. */
  function titles(column: 'todo' | 'applied'): string[] {
    return [...element().querySelectorAll(`.column.${column} app-job-card h3`)].map((title) => text(title));
  }

  function card(title: string): HTMLElement {
    return [...element().querySelectorAll<HTMLElement>('app-job-card')].find(
      (candidate) => text(candidate.querySelector('h3')!) === title,
    )!;
  }

  async function click(root: Element, label: string): Promise<void> {
    [...root.querySelectorAll('button')].find((button) => text(button) === label)!.click();
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
    expect(element().querySelector('.board')).toBeNull();
  });

  it('should split offers between to-do and applied, in the order of the API', async () => {
    await serve([job(3), job(2, { applied: true, applied_at: '2026-10-08T22:30:00Z' }), job(1)]);

    expect(titles('todo')).toEqual(['Offre 3', 'Offre 1']);
    expect(titles('applied')).toEqual(['Offre 2']);
    expect(text(card('Offre 2'))).toContain('Postulé le 9 oct.');
  });

  it('should count the offers, whatever the filters', async () => {
    await serve([job(1), job(2), job(3, { applied: true }), job(4, { applied: true, contract_type: 'freelance' })]);
    await search('introuvable');

    const tiles = [...element().querySelectorAll('.stats .tile')].map((tile) => text(tile));
    expect(tiles[0]).toMatch(/^2\s*à traiter$/);
    expect(tiles[1]).toMatch(/^2\s*candidatures envoyées$/);
    expect(tiles[2]).toContain('4 offres retenues');
    expect(tiles[2]).toContain('50 %');
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
    const request = http.expectOne({ method: 'PATCH', url: '/api/jobs/1' });
    expect(request.request.body).toEqual({ applied: true });
    request.flush(null, NO_CONTENT);
    await fixture.whenStable();

    // La carte change de colonne sans attendre ; la date, elle, n'est pas inventée
    expect(titles('applied')).toEqual(['Offre 1']);
    expect(text(card('Offre 1'))).not.toContain('Postulé le');

    await serve([job(1, { applied: true, applied_at: '2026-10-08T12:00:00Z' }), job(2)]);
    expect(text(card('Offre 1'))).toContain('Postulé le 8 oct.');
  });

  it('should put an applied offer back to do', async () => {
    await serve([job(1, { applied: true, applied_at: '2026-10-08T12:00:00Z' })]);

    await click(card('Offre 1'), 'Remettre à traiter');
    const request = http.expectOne({ method: 'PATCH', url: '/api/jobs/1' });
    expect(request.request.body).toEqual({ applied: false });
    request.flush(null, NO_CONTENT);
    await serve([job(1)]);

    expect(titles('todo')).toEqual(['Offre 1']);
  });

  it('should mark an offer as applied when it is dropped on the applied column', async () => {
    await serve([job(1), job(2, { applied: true })]);

    card('Offre 1').dispatchEvent(new Event('dragstart'));
    const over = new Event('dragover', { cancelable: true });
    const column = element().querySelector('.column.applied')!;
    column.dispatchEvent(over);
    // Une colonne n'accepte que les cartes de l'autre
    expect(over.defaultPrevented).toBe(true);
    const back = new Event('dragover', { cancelable: true });
    element().querySelector('.column.todo')!.dispatchEvent(back);
    expect(back.defaultPrevented).toBe(false);

    column.dispatchEvent(new Event('drop', { cancelable: true }));
    http.expectOne({ method: 'PATCH', url: '/api/jobs/1' }).flush(null, NO_CONTENT);
    await serve([job(1, { applied: true }), job(2, { applied: true })]);

    expect(titles('applied')).toEqual(['Offre 1', 'Offre 2']);
  });

  it('should delete an offer only once confirmed', async () => {
    await serve([job(1), job(2)]);

    card('Offre 1').querySelector<HTMLButtonElement>('button[aria-label="Supprimer l\'offre « Offre 1 »"]')!.click();
    await fixture.whenStable();
    http.expectNone({ method: 'DELETE', url: '/api/jobs/1' });
    expect(text(card('Offre 1'))).toContain('Elle ne reviendra pas');

    await click(card('Offre 1'), 'Garder');
    http.expectNone({ method: 'DELETE', url: '/api/jobs/1' });

    card('Offre 1').querySelector<HTMLButtonElement>('button[aria-label^="Supprimer"]')!.click();
    await fixture.whenStable();
    await click(card('Offre 1'), 'Supprimer');
    http.expectOne({ method: 'DELETE', url: '/api/jobs/1' }).flush(null, NO_CONTENT);
    await fixture.whenStable();

    expect(titles('todo')).toEqual(['Offre 2']);
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
