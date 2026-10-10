import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Account, SearchQuery } from '../core/api.models';
import { QueriesCardComponent } from './queries-card.component';

const ACCOUNT: Account = {
  user_id: 2,
  is_owner: false, is_trial: false, is_admin: false,
  email: null,
  name: null,
  picture: null,
  can_search: true,
  search_running: false,
  remaining_searches: 2,
  max_searches_per_day: 2,
};

function query(id: number, values: Partial<SearchQuery> = {}): SearchQuery {
  return {
    id,
    contract_type: 'CDI',
    query: `poste ${id}`,
    location: '',
    remote: false,
    created_at: '2026-10-08T10:00:00Z',
    ...values,
  };
}

describe('QueriesCardComponent', () => {
  let fixture: ComponentFixture<QueriesCardComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QueriesCardComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(QueriesCardComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(root: Element = element()): string {
    return (root.textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  /** Une ligne de la liste : contrat, intitulé et lieu. */
  function rows(): string[] {
    return [...element().querySelectorAll('li')].map((row) =>
      ['.contract', 'strong', '.where'].map((part) => text(row.querySelector(part)!)).join(' | '),
    );
  }

  async function serve(queries: SearchQuery[]): Promise<void> {
    http
      .expectOne('/api/config')
      .flush({ login_mode: 'google', google_client_id: 'id', contract_types: ['CDI', 'freelance', 'stage'] });
    http.expectOne({ method: 'GET', url: '/api/queries' }).flush(queries);
    await fixture.whenStable();
  }

  async function type(name: string, value: string): Promise<void> {
    const input = element().querySelector<HTMLInputElement>(`input[name=${name}]`)!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  async function click(label: string): Promise<void> {
    [...element().querySelectorAll('button')].find((button) => text(button) === label)!.click();
    await fixture.whenStable();
  }

  async function submit(): Promise<void> {
    element().querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  function submitButton(): HTMLButtonElement {
    return element().querySelector<HTMLButtonElement>('button[type=submit]')!;
  }

  it('should list each search with its contract and place', async () => {
    await serve([
      query(1, { query: 'ingénieur IA', location: 'Île-de-France' }),
      query(2, { query: 'AI engineer', contract_type: 'freelance', remote: true }),
      query(3, { query: 'data engineer' }),
    ]);

    expect(rows()).toEqual([
      'CDI | ingénieur IA | Île-de-France',
      'freelance | AI engineer | Télétravail complet',
      'CDI | data engineer | Toute la France',
    ]);
    expect(text(element().querySelector('.count')!)).toBe('3');
  });

  it('should invite to describe a first position when there is none', async () => {
    await serve([]);

    expect(text()).toContain("Aucun poste pour l'instant");
    expect(element().querySelector('.count')).toBeNull();
  });

  it('should offer the contract types listed by the API', async () => {
    await serve([]);

    const pills = [...element().querySelectorAll('[aria-labelledby=contract-label] button')].map((pill) => text(pill));
    expect(pills).toEqual(['CDI', 'freelance', 'stage']);
  });

  it('should add a search for all of France by default', async () => {
    await serve([]);
    expect(submitButton().disabled).toBe(true);

    await type('query', 'ingénieur IA');
    await submit();

    const request = http.expectOne({ method: 'POST', url: '/api/queries' });
    expect(request.request.body).toEqual({ contract_type: 'CDI', query: 'ingénieur IA', location: '', remote: false });
    request.flush(query(7, { query: 'ingénieur IA' }));
    // Un premier poste peut rendre la recherche possible : c'est l'API qui le dit
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    expect(rows()).toEqual(['CDI | ingénieur IA | Toute la France']);
    expect(element().querySelector<HTMLInputElement>('input[name=query]')!.value).toBe('');
  });

  it('should send the chosen contract and place', async () => {
    await serve([]);

    await type('query', 'développeur Python');
    await click('freelance');
    await click('Un lieu précis');
    // Un lieu précis laissé vide deviendrait « toute la France »
    expect(submitButton().disabled).toBe(true);
    await type('location', 'Lyon');
    await submit();

    const request = http.expectOne({ method: 'POST', url: '/api/queries' });
    expect(request.request.body).toEqual({
      contract_type: 'freelance',
      query: 'développeur Python',
      location: 'Lyon',
      remote: false,
    });
    request.flush(query(8, { contract_type: 'freelance', query: 'développeur Python', location: 'Lyon' }));
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  it('should ignore a typed place once full remote is chosen', async () => {
    await serve([]);

    await type('query', 'AI engineer');
    await click('Un lieu précis');
    await type('location', 'Lyon');
    await click('Télétravail complet');
    await submit();

    const request = http.expectOne({ method: 'POST', url: '/api/queries' });
    expect(request.request.body).toEqual({ contract_type: 'CDI', query: 'AI engineer', location: '', remote: true });
    request.flush(query(9, { query: 'AI engineer', remote: true }));
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  it('should show why the API refused a search, and keep what was typed', async () => {
    await serve([query(1, { query: 'ingénieur IA' })]);

    await type('query', 'ingénieur IA');
    await submit();
    http
      .expectOne({ method: 'POST', url: '/api/queries' })
      .flush({ detail: 'Cette recherche existe déjà.' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    expect(text()).toContain('Cette recherche existe déjà.');
    expect(element().querySelector<HTMLInputElement>('input[name=query]')!.value).toBe('ingénieur IA');
    expect(element().querySelectorAll('li').length).toBe(1);
  });

  it('should delete a search and refresh the account', async () => {
    await serve([query(1), query(2)]);

    element().querySelector<HTMLButtonElement>('button[aria-label="Supprimer la recherche « poste 1 »"]')!.click();
    http.expectOne({ method: 'DELETE', url: '/api/queries/1' }).flush(null, { status: 204, statusText: 'No Content' });
    http.expectOne('/api/me').flush({ ...ACCOUNT, can_search: false });
    await fixture.whenStable();

    expect(rows()).toEqual(['CDI | poste 2 | Toute la France']);
  });

  it('should drop a search already deleted elsewhere', async () => {
    await serve([query(1)]);

    element().querySelector<HTMLButtonElement>('.remove')!.click();
    http
      .expectOne({ method: 'DELETE', url: '/api/queries/1' })
      .flush({ detail: "Cette recherche n'existe pas." }, { status: 404, statusText: 'Not Found' });
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    expect(element().querySelectorAll('li').length).toBe(0);
    expect(text()).not.toContain("n'existe pas");
  });
});
