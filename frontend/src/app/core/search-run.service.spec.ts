import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { SearchProgress } from './api.models';
import { BACKGROUND_POLL_MS, FETCH, SearchRunService } from './search-run.service';
import { SessionService } from './session.service';

const ACCOUNT = { user_id: 2, is_owner: false, email: null, name: null, picture: null, can_search: true, search_running: false, remaining_searches: 1, max_searches_per_day: 2 };

function progress(values: Partial<SearchProgress>): string {
  const event: SearchProgress = {
    message: 'avancement',
    step: null,
    done: null,
    total: null,
    found: null,
    new: null,
    title: null,
    kept: null,
    ...values,
  };
  return `event: progress\ndata: ${JSON.stringify(event)}\n\n`;
}

const RESULT = `event: result\ndata: ${JSON.stringify({ found: 4, new: 2, kept: 1, rejected: 1, inserted: 1 })}\n\n`;

/** Réponse en flux, découpée en morceaux comme le réseau les livre. */
function stream(chunks: string[], fail = false): Response {
  const encoder = new TextEncoder();
  const pending = [...chunks];
  const body = new ReadableStream<Uint8Array>({
    // Un morceau par lecture : une coupure n'efface pas ce qui a déjà été reçu
    pull(controller) {
      const chunk = pending.shift();
      if (chunk !== undefined) {
        controller.enqueue(encoder.encode(chunk));
      } else if (fail) {
        controller.error(new Error('connexion coupée'));
      } else {
        controller.close();
      }
    },
  });
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

describe('SearchRunService', () => {
  let run: SearchRunService;
  let http: HttpTestingController;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: FETCH, useValue: fetchMock },
      ],
    });
    run = TestBed.inject(SearchRunService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('should follow a search step by step up to its summary', async () => {
    fetchMock.mockResolvedValue(
      stream([
        progress({ message: 'Recherche Tavily 1/2 : offre', step: 'search', done: 0, total: 2, found: 0 }),
        progress({ message: 'Recherche Tavily 2/2 : job', step: 'search', done: 1, total: 2, found: 3 }),
        progress({ message: '2 page(s) nouvelle(s) sur 4 trouvée(s)', step: 'dedupe', found: 4, new: 2 }),
        progress({ message: 'Évaluation par OpenAI 0/2', step: 'evaluate', done: 0, total: 2 }),
        progress({ message: 'Évaluation par OpenAI 1/2', step: 'evaluate', done: 1, total: 2, title: 'A', kept: true }),
        progress({ message: 'Évaluation par OpenAI 2/2', step: 'evaluate', done: 2, total: 2, title: 'B', kept: false }),
        progress({ message: 'Enregistrement', step: 'save' }),
        RESULT,
      ]),
    );

    await run.launch();

    expect(fetchMock).toHaveBeenCalledWith('/api/searches', expect.objectContaining({ method: 'POST', credentials: 'include' }));
    expect(run.state()).toBe('done');
    expect(run.step()).toBe('save');
    expect(run.found()).toBe(4);
    expect(run.fresh()).toBe(2);
    expect(run.latest().evaluate?.done).toBe(2);
    expect([run.keptSoFar(), run.rejectedSoFar()]).toEqual([1, 1]);
    expect(run.summary()).toEqual({ found: 4, new: 2, kept: 1, rejected: 1, inserted: 1 });
    // Une page évaluée est journalisée par son titre et son verdict
    expect(run.log().map((line) => [line.step, line.text, line.kept])).toContainEqual(['evaluate', 'B', false]);
    expect(run.completed()).toBe(1);
    // Le quota a changé : c'est l'API qui le redit
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  it('should read events whatever the way the network cuts them', async () => {
    const whole = progress({ message: 'Recherche Tavily 1/1 : ingénieur', step: 'search', done: 0, total: 1 }) + RESULT;
    // Coupure au milieu d'un événement, et au milieu d'un caractère accentué
    const bytes = new TextEncoder().encode(whole);
    const cut = bytes.indexOf(0xc3) + 1;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut));
        controller.enqueue(bytes.slice(cut));
        controller.close();
      },
    });
    fetchMock.mockResolvedValue(new Response(body, { status: 200 }));

    await run.launch();

    expect(run.log()[0].text).toBe('Recherche Tavily 1/1 : ingénieur');
    expect(run.state()).toBe('done');
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  it('should show why the API refused to start, without any stream', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Quota de recherches atteint pour aujourd'hui." }), { status: 429 }),
    );

    await run.launch();

    expect(run.state()).toBe('failed');
    expect(run.error()).toBe("Quota de recherches atteint pour aujourd'hui.");
    expect(run.completed()).toBe(0);
  });

  it('should report a search that failed on the way', async () => {
    fetchMock.mockResolvedValue(
      stream([
        progress({ message: 'Recherche Tavily 1/1', step: 'search', done: 0, total: 1 }),
        'event: error\ndata: {"detail": "La recherche a échoué."}\n\n',
      ]),
    );

    await run.launch();

    expect(run.state()).toBe('failed');
    expect(run.error()).toBe('La recherche a échoué.');
    // Elle a pu consommer du quota et enregistrer des pages
    expect(run.completed()).toBe(1);
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  it('should say the search goes on when the connection drops', async () => {
    fetchMock.mockResolvedValue(stream([progress({ message: 'Recherche Tavily 1/1', step: 'search' })], true));

    await run.launch();

    expect(run.state()).toBe('lost');
    expect(run.error()).toBe('');
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  it('should say when the server cannot be reached at all', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    await run.launch();

    expect(run.state()).toBe('failed');
    expect(run.error()).toContain('Le serveur ne répond pas');
  });

  it('should go back to the login screen when the session has expired', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fetchMock.mockResolvedValue(new Response('{"detail":"Authentification requise."}', { status: 401 }));

    await run.launch();

    expect(run.state()).toBe('idle');
    expect(navigate).toHaveBeenCalledWith(['connexion']);
  });

  it('should wait for a search it does not follow, then tell the screens to reload', async () => {
    vi.useFakeTimers();
    try {
      // Page rechargée pendant une recherche : c'est l'API qui dit qu'elle tourne encore
      TestBed.inject(SessionService).refresh().subscribe();
      http.expectOne('/api/me').flush({ ...ACCOUNT, search_running: true });
      TestBed.tick();

      expect([run.background(), run.busy()]).toEqual([true, true]);
      await run.launch();
      expect(fetchMock).not.toHaveBeenCalled();

      vi.advanceTimersByTime(BACKGROUND_POLL_MS);
      http.expectOne('/api/me').flush({ ...ACCOUNT, search_running: true });
      TestBed.tick();
      expect(run.completed()).toBe(0);

      vi.advanceTimersByTime(BACKGROUND_POLL_MS);
      http.expectOne('/api/me').flush(ACCOUNT);
      TestBed.tick();
      expect([run.background(), run.busy()]).toEqual([false, false]);
      expect(run.completed()).toBe(1);

      // Plus rien à attendre : l'API n'est plus interrogée
      vi.advanceTimersByTime(BACKGROUND_POLL_MS * 3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('should close the follow-up of a finished search only', async () => {
    fetchMock.mockResolvedValue(stream([RESULT]));
    await run.launch();
    http.expectOne('/api/me').flush(ACCOUNT);

    run.dismiss();

    expect(run.state()).toBe('idle');
  });
});
