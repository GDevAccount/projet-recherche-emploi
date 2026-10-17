import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Account, CvDeposit, SearchQuery } from '../core/api.models';
import { QueryService } from '../core/query.service';
import { FETCH } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { CvCardComponent } from './cv-card.component';

const PDF = new File(['%PDF-1.4'], 'mon-cv.pdf', { type: 'application/pdf' });

const ACCOUNT: Account = {
  user_id: 2,
  is_owner: false, is_trial: false, is_admin: false,
  email: null,
  name: null,
  picture: null,
  can_search: true,
  has_searched: true,
  search_running: false,
  remaining_searches: 2,
  max_searches_per_day: 2,
};

const QUERY: SearchQuery = {
  id: 7,
  contract_type: 'CDI',
  query: 'comptable',
  skills: ['SAP'],
  location: 'Rhône',
  remote: false,
  created_at: '2026-10-12T08:00:00Z',
};

function deposit(changes: Partial<CvDeposit> = {}): CvDeposit {
  return {
    updated_at: '2026-12-31T23:30:00Z',
    queries_outcome: 'created',
    message: 'CV enregistré. Vos postes recherchés ont été préparés à partir de lui : vérifiez-les.',
    queries: [QUERY],
    ...changes,
  };
}

function event(name: string, data: unknown): string {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Flux d'un dépôt, que le test laisse avancer morceau par morceau. */
function controlledStream(): { response: Response; push: (chunk: string) => void; end: () => void } {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start: (given) => void (controller = given) });
  return {
    response: new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } }),
    push: (chunk) => controller.enqueue(encoder.encode(chunk)),
    end: () => controller.close(),
  };
}

describe('CvCardComponent', () => {
  let fixture: ComponentFixture<CvCardComponent>;
  let http: HttpTestingController;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    fetchMock = vi.fn();
    await TestBed.configureTestingModule({
      imports: [CvCardComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), { provide: FETCH, useValue: fetchMock }],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    // Une session ouverte : sans elle, l'écran ne lit rien
    TestBed.inject(SessionService).open('preuve').subscribe();
    http.expectOne('/api/session').flush(ACCOUNT);
    fixture = TestBed.createComponent(CvCardComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return (element().textContent ?? '').replace(/\s+/g, ' ');
  }

  async function serveStatus(updatedAt: string | null): Promise<void> {
    http.expectOne({ method: 'GET', url: '/api/cv' }).flush({ updated_at: updatedAt });
    await fixture.whenStable();
  }

  async function chooseFile(file: File): Promise<void> {
    const input = element().querySelector<HTMLInputElement>('input[type=file]')!;
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change'));
    // Le fichier est lu en mémoire avant d'être affiché
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  }

  function button(label: string): HTMLButtonElement {
    return [...element().querySelectorAll('button')].find((candidate) => candidate.textContent?.includes(label))!;
  }

  /** Laisse passer ce que le flux vient de rendre, puis l'affichage. */
  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  }

  /** Ce que le formulaire a envoyé : le fichier, et s'il faut remplacer les postes recherchés. */
  function sent(): { url: string; file: unknown; replace: unknown } {
    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    const form = request.body as FormData;
    return { url, file: form.get('file'), replace: form.get('replace_queries') };
  }

  it('should say when no CV is in place', async () => {
    await serveStatus(null);

    expect(text()).toContain("Aucun CV pour l'instant");
    expect(text()).toContain('Déposer votre CV');
  });

  it('should show the date of the current CV in Paris time', async () => {
    await serveStatus('2026-07-14T12:05:00Z');

    expect(text()).toContain('Mis à jour le 14 juillet 2026 à 14:05');
    expect(text()).toContain('Déposer un nouveau CV');
  });

  it('should send nothing until the chosen file is confirmed', async () => {
    await serveStatus('2026-07-14T12:05:00Z');

    await chooseFile(PDF);

    expect(text()).toContain('mon-cv.pdf');
    expect(text()).toContain('Les pages déjà rejetées seront réévaluées');
    expect(fetchMock).not.toHaveBeenCalled();

    button('Annuler').click();
    await fixture.whenStable();
    expect(text()).not.toContain('mon-cv.pdf');
  });

  it('should say at once when the chosen file cannot be read, as a file left in an online storage', async () => {
    await serveStatus(null);
    const unreadable = new File(['%PDF-1.4'], 'cv-drive.pdf', { type: 'application/pdf' });
    unreadable.arrayBuffer = () => Promise.reject(new DOMException('Lecture refusée', 'NotReadableError'));

    await chooseFile(unreadable);

    expect(text()).toContain("Ce fichier n'a pas pu être lu");
    expect(text()).toContain("enregistrez-le d'abord sur votre appareil");
    expect(text()).not.toContain('cv-drive.pdf');
    expect(button('Enregistrer ce CV')).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('should follow the deposit step by step, then show the searched jobs drawn from the CV', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await serveStatus(null);
    await chooseFile(PDF);
    // Sans poste recherché, rien à demander : ils seront préparés d'office
    expect(text()).toContain('Vos postes recherchés seront préparés à partir de ce CV');
    expect(element().querySelector('[role=radiogroup]')).toBeNull();

    button('Enregistrer ce CV').click();
    await settle();
    expect(sent()).toEqual({ url: '/api/cv/stream', file: expect.any(File), replace: 'false' });
    // C'est la copie lue au choix qui part, avec le contenu et le nom du fichier
    const file = sent().file as File;
    expect([file.name, file.type, await file.text()]).toEqual(['mon-cv.pdf', 'application/pdf', '%PDF-1.4']);

    stream.push(event('progress', { step: 'read' }) + event('progress', { step: 'anonymize' }));
    await settle();
    const steps = [...element().querySelectorAll('.steps li')].map((step) => step.textContent?.trim());
    expect(steps).toEqual(['Lecture du PDF', 'Retrait de vos coordonnées…']);

    stream.push(event('result', deposit()));
    stream.end();
    await settle();
    // Un premier CV, et ses postes, peuvent rendre la recherche possible : c'est l'API qui le dit
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    expect(text()).toContain('Vos postes recherchés ont été préparés à partir de lui');
    expect(text()).toContain('Mis à jour le 1 janvier 2027 à 00:30');
    expect(element().querySelector('.steps')).toBeNull();
    // La carte des postes recherchés les reçoit sans relire l'API
    expect(TestBed.inject(QueryService).queries()).toEqual([QUERY]);
  });

  it('should ask whether to replace the searched jobs already there, and wait for the answer', async () => {
    const queries = TestBed.inject(QueryService).queries;
    queries.set([QUERY, { ...QUERY, id: 8, query: 'auditeur' }]);
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await serveStatus('2026-07-14T12:05:00Z');
    await chooseFile(PDF);

    expect(text()).toContain('Vous avez déjà 2 postes recherchés');
    expect(button('Enregistrer ce CV').disabled).toBe(true);

    button('Garder mes postes').click();
    await fixture.whenStable();
    expect(button('Garder mes postes').getAttribute('aria-checked')).toBe('true');
    button('Enregistrer ce CV').click();
    await settle();
    expect(sent().replace).toBe('false');

    const message = "CV enregistré. Vos postes recherchés n'ont pas changé.";
    stream.push(event('result', deposit({ queries_outcome: 'kept', message, queries: [] })));
    stream.end();
    await settle();
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    expect(text()).toContain(message);
    expect(queries()?.length).toBe(2);
  });

  it('should send the request to replace the searched jobs', async () => {
    TestBed.inject(QueryService).queries.set([{ ...QUERY, id: 8, query: 'auditeur' }]);
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await serveStatus('2026-07-14T12:05:00Z');
    await chooseFile(PDF);
    expect(text()).toContain('Vous avez déjà 1 poste recherché.');

    button('Remplacer mes postes').click();
    await fixture.whenStable();
    button('Enregistrer ce CV').click();
    await settle();
    expect(sent().replace).toBe('true');

    stream.push(event('result', deposit()));
    stream.end();
    await settle();
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    expect(TestBed.inject(QueryService).queries()).toEqual([QUERY]);
  });

  it('should say when the CV is saved but its searched jobs could not be prepared', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await serveStatus(null);
    await chooseFile(PDF);

    button('Enregistrer ce CV').click();
    await settle();
    const message = "CV enregistré, mais vos postes recherchés n'ont pas pu être préparés pour l'instant.";
    stream.push(event('result', deposit({ queries_outcome: 'failed', message, queries: [] })));
    stream.end();
    await settle();
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    expect(text()).toContain(message);
    expect(text()).toContain('Votre CV est en place');
    expect(TestBed.inject(QueryService).queries()).toBeUndefined();
  });

  it('should show why the API refused a file, and keep it for another try', async () => {
    const stream = controlledStream();
    fetchMock.mockResolvedValue(stream.response);
    await serveStatus(null);
    await chooseFile(PDF);

    button('Enregistrer ce CV').click();
    await settle();
    // Un PDF illisible est refusé à la première étape, une fois le flux ouvert
    stream.push(event('progress', { step: 'read' }));
    stream.push(event('error', { detail: "Aucun texte n'a pu être extrait de ce PDF : est-ce un document scanné ?" }));
    stream.end();
    await settle();

    expect(text()).toContain("Aucun texte n'a pu être extrait de ce PDF");
    expect(text()).toContain('mon-cv.pdf');
    expect(text()).not.toContain('CV enregistré');
  });

  it('should show a refusal that comes before the stream', async () => {
    const refusal = new Response(JSON.stringify({ detail: 'Le CV dépasse 10 Mo.' }), { status: 422 });
    fetchMock.mockResolvedValue(refusal);
    await serveStatus(null);
    await chooseFile(PDF);

    button('Enregistrer ce CV').click();
    await settle();

    expect(text()).toContain('Le CV dépasse 10 Mo.');
    expect(text()).toContain('mon-cv.pdf');
  });

  it('should accept a dropped file', async () => {
    await serveStatus(null);

    const drop = new Event('drop') as DragEvent;
    Object.defineProperty(drop, 'dataTransfer', { value: { files: [PDF] } });
    element().querySelector('.drop')!.dispatchEvent(drop);
    await settle();

    expect(text()).toContain('mon-cv.pdf');
  });
});
