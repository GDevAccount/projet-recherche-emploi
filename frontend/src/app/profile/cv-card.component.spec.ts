import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CvCardComponent } from './cv-card.component';

const PDF = new File(['%PDF-1.4'], 'mon-cv.pdf', { type: 'application/pdf' });

describe('CvCardComponent', () => {
  let fixture: ComponentFixture<CvCardComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CvCardComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
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
    await fixture.whenStable();
  }

  function button(label: string): HTMLButtonElement {
    return [...element().querySelectorAll('button')].find((candidate) => candidate.textContent?.includes(label))!;
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
    http.expectNone({ method: 'PUT', url: '/api/cv' });

    button('Annuler').click();
    await fixture.whenStable();
    expect(text()).not.toContain('mon-cv.pdf');
  });

  it('should save the confirmed file and refresh the account', async () => {
    await serveStatus(null);
    await chooseFile(PDF);

    button('Enregistrer ce CV').click();
    const request = http.expectOne({ method: 'PUT', url: '/api/cv' });
    expect((request.request.body as FormData).get('file')).toBe(PDF);
    request.flush({ updated_at: '2026-12-31T23:30:00Z' });
    // Un premier CV peut rendre la recherche possible : c'est l'API qui le dit
    http.expectOne('/api/me').flush({
      user_id: 2,
      is_owner: false, is_trial: false, is_admin: false,
      email: null,
      name: null,
      picture: null,
      can_search: true,
      search_running: false,
      remaining_searches: 2,
      max_searches_per_day: 2,
    });
    await fixture.whenStable();

    expect(text()).toContain('CV enregistré.');
    expect(text()).toContain('Mis à jour le 1 janvier 2027 à 00:30');
  });

  it('should show why the API refused a file, and keep it for another try', async () => {
    await serveStatus(null);
    await chooseFile(PDF);

    button('Enregistrer ce CV').click();
    http
      .expectOne({ method: 'PUT', url: '/api/cv' })
      .flush(
        { detail: "Aucun texte n'a pu être extrait de ce PDF : est-ce un document scanné ?" },
        { status: 422, statusText: 'Unprocessable Content' },
      );
    await fixture.whenStable();

    expect(text()).toContain("Aucun texte n'a pu être extrait de ce PDF");
    expect(text()).toContain('mon-cv.pdf');
    expect(text()).not.toContain('CV enregistré.');
  });

  it('should accept a dropped file', async () => {
    await serveStatus(null);

    const drop = new Event('drop') as DragEvent;
    Object.defineProperty(drop, 'dataTransfer', { value: { files: [PDF] } });
    element().querySelector('.drop')!.dispatchEvent(drop);
    await fixture.whenStable();

    expect(text()).toContain('mon-cv.pdf');
  });
});
