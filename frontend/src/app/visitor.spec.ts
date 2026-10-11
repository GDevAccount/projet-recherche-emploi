import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Type } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Account, AppConfig, CvDeposit, TrialStatus } from './core/api.models';
import { FETCH } from './core/search-run.service';
import { SessionService } from './core/session.service';
import { JobsComponent } from './jobs/jobs.component';
import { CvCardComponent } from './profile/cv-card.component';
import { QueriesCardComponent } from './profile/queries-card.component';
import { RejectedComponent } from './rejected/rejected.component';

const PDF = new File(['%PDF-1.4'], 'mon-cv.pdf', { type: 'application/pdf' });

const TRIAL: Account = {
  user_id: 7,
  is_owner: false, is_trial: true, is_admin: false,
  email: null,
  name: null,
  picture: null,
  can_search: false,
  has_searched: false,
  search_running: false,
  remaining_searches: 1,
  max_searches_per_day: 2,
};

const DEPOSIT: CvDeposit = {
  updated_at: '2026-12-31T23:30:00Z',
  queries_outcome: 'created',
  message: 'CV enregistré. Vos postes recherchés ont été préparés à partir de lui : vérifiez-les.',
  queries: [],
};

function config(trial: TrialStatus | null): AppConfig {
  return {
    login_mode: 'google',
    google_client_id: 'id',
    trial,
    contract_types: ['CDI'],
    max_skills_per_query: 5,
    delete_reasons: [],
  };
}

/** Les écrans sont ouverts à tous : sans session, ils ne demandent aucune donnée à l'API, qui les refuserait. */
describe('screens without a session', () => {
  let http: HttpTestingController;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    fetchMock = vi.fn();
    await TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: FETCH, useValue: fetchMock },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  // Aucun appel resté sans réponse : c'est ce qui dit qu'un écran n'a rien demandé d'autre
  afterEach(() => http.verify());

  async function open<T>(component: Type<T>, trial: TrialStatus | null = 'available'): Promise<ComponentFixture<T>> {
    const fixture = TestBed.createComponent(component);
    fixture.detectChanges();
    // La seule lecture permise : les réglages publics de l'instance
    http.match('/api/config').forEach((request) => request.flush(config(trial)));
    await fixture.whenStable();
    return fixture;
  }

  function text(fixture: ComponentFixture<unknown>): string {
    return ((fixture.nativeElement as HTMLElement).textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  it('should show the offers screen empty, and say where to start', async () => {
    const fixture = await open(JobsComponent);

    expect(text(fixture)).toContain("Pas encore d'offre");
    expect(text(fixture)).toContain('Une fois votre profil complété');
  });

  it('should read the offers once a session opens', async () => {
    const fixture = await open(JobsComponent);

    TestBed.inject(SessionService).openTrial().subscribe();
    http.expectOne('/api/session/trial').flush(TRIAL);
    await fixture.whenStable();

    http.expectOne({ method: 'GET', url: '/api/jobs' }).flush([]);
  });

  it('should show the rejected pages screen empty', async () => {
    const fixture = await open(RejectedComponent);

    expect(text(fixture)).toContain('Aucune page écartée');
  });

  it('should say that the searched jobs come from the CV, without offering to add one', async () => {
    const fixture = await open(QueriesCardComponent);

    expect(text(fixture)).toContain('Déposez votre CV : vos postes recherchés en seront tirés');
    expect(text(fixture)).not.toContain('Ajouter un poste');
  });

  it('should open a trial account when the first CV is saved, with the terms within reach', async () => {
    fetchMock.mockResolvedValue(
      new Response(`event: result\ndata: ${JSON.stringify(DEPOSIT)}\n\n`, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      }),
    );
    const fixture = await open(CvCardComponent);
    const element = fixture.nativeElement as HTMLElement;
    expect(text(fixture)).toContain('Sans inscription : déposer votre CV ouvre un essai');
    expect(element.querySelector('a[href="/conditions"]')).not.toBeNull();

    const input = element.querySelector<HTMLInputElement>('input[type=file]')!;
    Object.defineProperty(input, 'files', { value: [PDF], configurable: true });
    input.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    // Choisir un fichier n'ouvre rien : c'est l'enregistrement qui engage
    http.expectNone('/api/session/trial');

    [...element.querySelectorAll('button')].find((button) => button.textContent?.includes('Enregistrer ce CV'))!.click();
    http.expectOne('/api/session/trial').flush(TRIAL);
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();

    expect(fetchMock).toHaveBeenCalledWith('/api/cv/stream', expect.objectContaining({ method: 'POST' }));
    http.expectOne('/api/me').flush({ ...TRIAL, can_search: true });
    await fixture.whenStable();
    expect(text(fixture)).toContain('Votre CV est en place');
    expect(text(fixture)).not.toContain('Sans inscription');
  });

  it('should send nothing and say why when no trial is left to open', async () => {
    const fixture = await open(CvCardComponent);
    const element = fixture.nativeElement as HTMLElement;
    const input = element.querySelector<HTMLInputElement>('input[type=file]')!;
    Object.defineProperty(input, 'files', { value: [PDF], configurable: true });
    input.dispatchEvent(new Event('change'));
    await fixture.whenStable();

    [...element.querySelectorAll('button')].find((button) => button.textContent?.includes('Enregistrer ce CV'))!.click();
    http
      .expectOne('/api/session/trial')
      .flush({ detail: "Trop d'essais ont été ouverts aujourd'hui." }, { status: 429, statusText: 'Too Many Requests' });
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();

    expect(text(fixture)).toContain("Trop d'essais ont été ouverts aujourd'hui.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ['exhausted', 'Les essais sans compte sont épuisés pour aujourd'],
    [null, 'Connectez-vous pour déposer votre CV'],
  ] as const)('should send to the login screen when the trial is %s', async (trial, words) => {
    const fixture = await open(CvCardComponent, trial);
    const element = fixture.nativeElement as HTMLElement;

    expect(text(fixture)).toContain(words);
    expect(element.querySelector('input[type=file]')).toBeNull();
    expect(element.querySelector('a.signin')?.getAttribute('href')).toBe('/connexion');
  });
});
