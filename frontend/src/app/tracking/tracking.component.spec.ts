import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import {
  AccountUsage,
  EvaluationGroup,
  PageEvaluation,
  SearchRun,
  SearchStats,
  UsageOverview,
} from '../core/api.models';
import { CountPipe, DurationPipe, UsdPipe } from '../core/format.pipe';
import { TrackingComponent } from './tracking.component';

function group(label: string, values: Partial<EvaluationGroup> = {}): EvaluationGroup {
  return {
    label,
    evaluated: 10,
    kept: 4,
    not_an_offer: 3,
    rejected_offers: 3,
    input_tokens: 40000,
    output_tokens: 4000,
    model_cost_usd: 0.0061,
    ...values,
  };
}

function stats(values: Partial<SearchStats> = {}): SearchStats {
  return {
    runs: 2,
    unfinished_runs: 1,
    found_count: 86,
    new_count: 37,
    kept_count: 11,
    rejected_count: 26,
    search_calls: 6,
    input_tokens: 164786,
    output_tokens: 16330,
    cache_read_tokens: 38262,
    reasoning_tokens: 4025,
    search_cost_usd: 0.096,
    model_cost_usd: 0.024,
    cost_usd: 0.12,
    cost_per_kept_usd: 0.010909,
    average_duration_ms: 47000,
    by_query: [group('ingénieur IA', { evaluated: 20, kept: 8 }), group('AI engineer')],
    by_site: [group('indeed.com'), group('apec.fr', { evaluated: 5, kept: 0 })],
    by_page_kind: [group('offre')],
    by_text: [group('Page entière', { evaluated: 30 }), group('Extrait seul', { evaluated: 7 })],
    ...values,
  };
}

function run(id: number, values: Partial<SearchRun> = {}): SearchRun {
  return {
    id,
    created_at: '2026-10-09T12:12:06Z',
    finished_at: '2026-10-09T12:12:44Z',
    status: 'done',
    error: null,
    model: 'gpt-6-luna',
    prompt_version: '9c9194f68cec',
    found_count: 47,
    new_count: 15,
    kept_count: 2,
    rejected_count: 13,
    inserted_count: 2,
    duration_ms: 38216,
    search_ms: 21321,
    dedupe_ms: 5,
    evaluate_ms: 16864,
    save_ms: 26,
    search_calls: 3,
    input_tokens: 69819,
    output_tokens: 5705,
    cache_read_tokens: 38262,
    cache_write_tokens: 31512,
    reasoning_tokens: 4025,
    search_cost_usd: 0.048,
    model_cost_usd: 0.007179,
    cost_usd: 0.055179,
    ...values,
  };
}

function evaluation(id: number, values: Partial<PageEvaluation> = {}): PageEvaluation {
  return {
    id,
    url: `https://www.exemple-emploi.fr/pages/${id}`,
    title: `Page ${id}`,
    query: 'ingénieur IA',
    score: 0.6,
    kept: false,
    page_kind: 'offre',
    contract_type: 'CDI',
    work_city: 'Lyon',
    work_country: 'France',
    work_mode: 'hybride',
    in_accepted_area: true,
    open_to_candidates_in_france: true,
    matches_search: true,
    matches_skills: true,
    matches_level: true,
    matches_contract: true,
    matches_location: true,
    reason: 'Raison du verdict.',
    page_chars: 5200,
    truncated: false,
    full_page: true,
    input_tokens: 4300,
    output_tokens: 480,
    reasoning_tokens: 300,
    duration_ms: 3200,
    model_cost_usd: 0.00048,
    ...values,
  };
}

function account(user_id: number, values: Partial<AccountUsage> = {}): AccountUsage {
  return {
    user_id,
    email: `compte${user_id}@exemple.fr`,
    is_owner: false,
    deleted: false,
    plan: 'free',
    runs: 3,
    found_count: 40,
    kept_count: 7,
    search_calls: 6,
    input_tokens: 90000,
    output_tokens: 9000,
    search_cost_usd: 0.096,
    model_cost_usd: 0.011,
    cost_usd: 0.107,
    last_search_at: '2026-10-08T10:00:00Z',
    ...values,
  };
}

function usage(values: Partial<UsageOverview> = {}): UsageOverview {
  return {
    since: '2026-09-09T12:00:00Z',
    accounts: [
      account(1, { is_owner: true, email: null, cost_usd: 0.335 }),
      account(2),
      account(4, { deleted: true, email: null, last_search_at: null, cost_usd: 0.074 }),
    ],
    runs: 9,
    kept_count: 21,
    search_cost_usd: 0.4,
    model_cost_usd: 0.116,
    cost_usd: 0.516,
    guests_cost_usd: 0.181,
    ...values,
  };
}

describe('TrackingComponent', () => {
  let fixture: ComponentFixture<TrackingComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TrackingComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(TrackingComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  /** Texte d'un élément, ses morceaux séparés par une espace : le gabarit compilé n'en garde pas entre deux balises. */
  function text(root: Element | null = element()): string {
    const pieces: string[] = [];
    const walker = document.createTreeWalker(root ?? element(), NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const piece = (walker.currentNode.textContent ?? '').replace(/\s+/g, ' ').trim();
      if (piece) {
        pieces.push(piece);
      }
    }
    return pieces.join(' ');
  }

  function texts(selector: string): string[] {
    return [...element().querySelectorAll(selector)].map((node) => text(node));
  }

  async function serve(served: SearchStats, runs: SearchRun[] = [run(28)], overview = usage()): Promise<void> {
    http.expectOne({ method: 'GET', url: '/api/searches/stats' }).flush(served);
    http.expectOne({ method: 'GET', url: '/api/searches' }).flush(runs);
    await fixture.whenStable();
    if (served.runs) {
      http.expectOne({ method: 'GET', url: '/api/admin/usage?days=30' }).flush(overview);
      await fixture.whenStable();
    }
  }

  async function click(label: string, scope = 'button'): Promise<void> {
    [...element().querySelectorAll(scope)].find((button) => text(button).startsWith(label))!.dispatchEvent(
      new Event('click'),
    );
    await fixture.whenStable();
  }

  it('should say when no search has been tracked yet', async () => {
    await serve(stats({ runs: 0 }), []);

    expect(text()).toContain('Aucune recherche suivie');
    expect(element().querySelector('.tiles')).toBeNull();
    expect(element().querySelector('app-usage-card')).toBeNull();
  });

  it('should show what the searches cost, as the API computed it', async () => {
    await serve(stats());

    expect(texts('.tile')).toEqual([
      '0,120 $ coût total',
      '0,011 $ par offre retenue',
      '2 recherches · 1 inachevée',
      '47 s durée moyenne',
    ]);
    // La barre partage le coût entre la recherche web et le modèle
    expect(element().querySelector('.split')!.getAttribute('aria-label')).toBe('Tavily 80 %, OpenAI 20 %');
    expect(text(element().querySelector('.spend dl'))).toContain('0,096 $ 6 appels');
    expect(text(element().querySelector('.spend dl'))).toMatch(/164.786 jetons lus, dont 38.262 en cache/);
  });

  it('should not draw a share when the total cost is unknown', async () => {
    await serve(stats({ cost_usd: null, model_cost_usd: null, cost_per_kept_usd: null }));

    expect(element().querySelector('.split')).toBeNull();
    expect(texts('.tile')[0]).toBe('— coût total');
  });

  it('should break the evaluated pages down by query, then by whatever is chosen', async () => {
    await serve(stats());

    expect(text(element().querySelector('.pages h2'))).toBe('37 pages évaluées');
    expect(texts('.groups li')).toEqual(['ingénieur IA 8 sur 20 0,0061 $', 'AI engineer 4 sur 10 0,0061 $']);

    await click('Par site');

    expect(texts('.groups .label')).toEqual(['indeed.com', 'apec.fr']);
    // La barre d'un groupe est à la mesure du plus fourni, et ses parts à celle de ses propres pages
    const [first, second] = [...element().querySelectorAll<HTMLElement>('.groups .stack')];
    expect([first.style.width, second.style.width]).toEqual(['100%', '50%']);
    expect(first.querySelector<HTMLElement>('.kept')!.style.width).toBe('40%');
    expect(second.querySelector<HTMLElement>('.kept')!.style.width).toBe('0%');
  });

  it('should show only the first groups until asked for all of them', async () => {
    const sites = Array.from({ length: 11 }, (_, index) => group(`site-${index}.fr`));
    await serve(stats({ by_site: sites }));
    await click('Par site');

    expect(texts('.groups li').length).toBe(8);

    await click('Tout afficher');

    expect(texts('.groups li').length).toBe(11);
    expect(element().querySelector('.pages .more')).toBeNull();
  });

  it('should list the searches and open one on its measures and its pages', async () => {
    const failed = run(27, { status: 'failed', error: 'RateLimitError', new_count: null, kept_count: null });
    const untracked = run(26, { status: null, found_count: null, duration_ms: null, cost_usd: null });
    await serve(stats(), [run(28), failed, untracked]);

    expect(texts('.runs .status')).toEqual(['Terminée', 'Échouée', 'Non suivie']);
    expect(texts('.runs .counts')).toEqual([
      '47 trouvées · 15 nouvelles · 2 retenues',
      '47 trouvées',
      'Lancée avant le suivi',
    ]);
    expect(texts('.runs .cost')).toEqual(['0,055 $', '0,055 $', '—']);
    // Une recherche d'avant le suivi n'a rien à montrer
    expect(element().querySelectorAll<HTMLButtonElement>('.runs .row')[2].disabled).toBe(true);

    await click('9 oct.', '.runs .row');
    expect(text(element().querySelector('.detail'))).toContain('Chargement des pages évaluées');
    http.expectOne({ method: 'GET', url: '/api/searches/28/evaluations' }).flush([
      evaluation(1, { kept: true }),
      evaluation(2, { matches_search: false, matches_location: false, truncated: true, page_chars: 11800 }),
      evaluation(3, { page_kind: 'article', matches_search: false, matches_skills: false, full_page: false }),
    ]);
    await fixture.whenStable();

    const detail = text(element().querySelector('.detail dl'));
    expect(detail).toContain('Recherche Tavily 21,3 s (3 appels)');
    expect(detail).toMatch(/69.819 lus, dont 38.262 relus en cache et 31.512 écrits en cache/);
    expect(detail).toContain('gpt-6-luna · prompt 9c9194f68cec');
    expect(texts('.runs .pages .verdict')).toEqual(['Retenue', 'Écartée', 'Écartée']);
    const [kept, rejected, article] = texts('.runs .pages .facts');
    expect(kept).toBe('exemple-emploi.fr offre CDI Lyon, France hybride via « ingénieur IA »');
    expect(rejected).toContain('en défaut : métier, lieu');
    expect(rejected).toMatch(/texte tronqué \(11.800 caractères\)/);
    // Une page qui n'est pas une offre porte sa nature, pas une liste de critères
    expect(article).toContain('article');
    expect(article).toContain('extrait seul');
    expect(article).not.toContain('en défaut');

    // Refermée puis rouverte, elle ne redemande pas ses pages
    await click('9 oct.', '.runs .row');
    await click('9 oct.', '.runs .row');
    expect(texts('.runs .pages > li').length).toBe(3);
  });

  it('should tell what each account costs, and reload it for another period', async () => {
    await serve(stats());

    const card = element().querySelector('app-usage-card')!;
    expect(text(card.querySelector('h2'))).toBe('0,516 $ dont 0,181 $ pour les invités');
    expect([...card.querySelectorAll('tbody th')].map((cell) => text(cell))).toEqual([
      'Propriétaire',
      'compte2@exemple.fr',
      'Compte supprimé nº 4',
    ]);
    expect([...card.querySelectorAll('tbody tr')].map((row) => text(row.lastElementChild))).toEqual([
      '0,335 $',
      '0,107 $',
      '0,074 $',
    ]);
    expect(text(card.querySelector('tbody tr.deleted'))).toContain('Gratuit 3 7 —');

    await click('Depuis le début');
    http.expectOne({ method: 'GET', url: '/api/admin/usage' }).flush(usage({ accounts: [], cost_usd: 0 }));
    await fixture.whenStable();

    expect(text(card)).toContain('Aucune recherche sur cette période');
  });

  it('should show the error of the API instead of the screen', async () => {
    http
      .expectOne({ method: 'GET', url: '/api/searches/stats' })
      .flush({ detail: "Réservé aux administrateurs de l'instance." }, { status: 403, statusText: 'Forbidden' });
    http.expectOne({ method: 'GET', url: '/api/searches' });
    await fixture.whenStable();

    expect(text()).toContain("Réservé aux administrateurs de l'instance.");
    expect(element().querySelector('.tiles')).toBeNull();
  });
});

describe('format pipes', () => {
  it('should keep more decimals for smaller amounts', () => {
    const usd = new UsdPipe();
    expect([12.4, 0.055179, 0.007179, 0, null].map((value) => usd.transform(value))).toEqual([
      '12,40 $',
      '0,055 $',
      '0,0072 $',
      '0,00 $',
      '—',
    ]);
  });

  it('should write a duration in the unit that suits it', () => {
    const duration = new DurationPipe();
    expect([26, 16864, 72400, null].map((value) => duration.transform(value))).toEqual([
      '26 ms',
      '16,9 s',
      '1 min 12 s',
      '—',
    ]);
  });

  it('should group thousands, and say when a count is unknown', () => {
    const count = new CountPipe();
    expect(count.transform(69819)).toMatch(/^69.819$/);
    expect(count.transform(null)).toBe('—');
  });
});
