import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { SearchProgress } from '../core/api.models';
import { FETCH, SearchRunService } from '../core/search-run.service';
import { RunPanelComponent } from './run-panel.component';

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

describe('RunPanelComponent', () => {
  let fixture: ComponentFixture<RunPanelComponent>;
  let http: HttpTestingController;
  let send: (chunk: string) => void;
  let close: () => void;
  let finished: Promise<void>;

  beforeEach(async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        send = (chunk) => controller.enqueue(encoder.encode(chunk));
        close = () => controller.close();
      },
    });
    await TestBed.configureTestingModule({
      imports: [RunPanelComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: FETCH, useValue: () => Promise.resolve(new Response(body, { status: 200 })) },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    finished = TestBed.inject(SearchRunService).launch();
    fixture = TestBed.createComponent(RunPanelComponent);
    await fixture.whenStable();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(root: Element = element()): string {
    return (root.textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  /** Laisse le lecteur du flux traiter ce qui vient d'être envoyé. */
  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  }

  function statuses(): string[] {
    return [...element().querySelectorAll('.pipeline li')].map((step) => step.getAttribute('data-status') ?? '');
  }

  function telemetry(): Record<string, string> {
    return Object.fromEntries(
      [...element().querySelectorAll('.telemetry div')].map((cell) => [
        text(cell.querySelector('dt')!),
        text(cell.querySelector('dd')!),
      ]),
    );
  }

  it('should light the steps of the graph as the API announces them', async () => {
    send(progress({ message: 'Recherche Tavily 1/2 : offre', step: 'search', done: 0, total: 2, found: 0 }));
    await settle();

    expect(text(element().querySelector('h2')!)).toBe('Recherche en cours');
    expect(statuses()).toEqual(['active', 'pending', 'pending', 'pending']);
    expect(text(element().querySelector('.pipeline li')!)).toContain('searchJobs');
    expect(text(element().querySelector('.pipeline li')!)).toContain('requête 1 / 2');

    send(progress({ message: '5 nouvelles sur 9', step: 'dedupe', found: 9, new: 5 }));
    send(progress({ message: 'Évaluation 0/5', step: 'evaluate', done: 0, total: 5 }));
    await settle();

    expect(statuses()).toEqual(['done', 'done', 'active', 'pending']);
    expect(telemetry()).toMatchObject({ 'Pages trouvées': '9', 'À évaluer': '5', Évaluées: '0 / 5' });

    close();
    await finished;
    http.expectOne('/api/me').flush({});
  });

  it('should log each evaluated page with its verdict and count them live', async () => {
    send(progress({ message: 'Évaluation 0/2', step: 'evaluate', done: 0, total: 2 }));
    send(progress({ message: 'Évaluation 1/2', step: 'evaluate', done: 1, total: 2, title: 'Ingénieur IA', kept: true }));
    send(progress({ message: 'Évaluation 2/2', step: 'evaluate', done: 2, total: 2, title: 'Data analyst', kept: false }));
    await settle();

    const lines = [...element().querySelectorAll('.console p:not(.cursor)')].map((line) => text(line));
    expect(lines[1]).toMatch(/evaluate\s*retenue\s*Ingénieur IA$/);
    expect(lines[2]).toMatch(/evaluate\s*écartée\s*Data analyst$/);
    expect(telemetry()).toMatchObject({ Retenues: '1', Écartées: '1', Évaluées: '2 / 2' });
    expect(element().querySelector('.gauge')!.getAttribute('aria-valuenow')).toBe('100');

    close();
    await finished;
    http.expectOne('/api/me').flush({});
  });

  it('should end on the summary given by the API', async () => {
    send(progress({ message: 'Enregistrement', step: 'save' }));
    send(`event: result\ndata: ${JSON.stringify({ found: 9, new: 5, kept: 2, rejected: 3, inserted: 2 })}\n\n`);
    close();
    await finished;
    http.expectOne('/api/me').flush({});
    await settle();

    expect(text(element().querySelector('h2')!)).toBe('Recherche terminée');
    expect(statuses()).toEqual(['done', 'done', 'done', 'done']);
    expect(text(element().querySelector('footer')!)).toContain('2 nouvelles offres vous attendent');
    expect(text(element().querySelector('footer')!)).toContain('9 pages trouvées, 5 pas encore évaluées, 2 retenues, 3 écartées.');
    expect(element().querySelector('footer a.cta')!.getAttribute('href')).toBe('/offres');
    expect(element().querySelector('.cursor')).toBeNull();
  });

  it('should say that the search goes on when the stream stops without a summary', async () => {
    send(progress({ message: 'Recherche Tavily 1/1', step: 'search', done: 0, total: 1 }));
    close();
    await finished;
    http.expectOne('/api/me').flush({});
    await settle();

    expect(text()).toContain('Connexion interrompue');
    expect(text()).toContain('la recherche va au bout sur le serveur');
  });
});
