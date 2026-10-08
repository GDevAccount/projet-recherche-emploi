import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { RejectedJob } from '../core/api.models';
import { RejectedComponent } from './rejected.component';

const NOT_AN_OFFER = 'Pas une offre valable';
const OTHER_JOB = 'Autre métier que ceux recherchés';
const SKILLS = 'Compétences insuffisantes';

function page(id: number, values: Partial<RejectedJob> = {}): RejectedJob {
  return {
    url: `https://www.exemple-emploi.fr/pages/${id}`,
    title: `Page ${id}`,
    contract_type: null,
    work_location: null,
    query: 'ingénieur IA',
    reject_reason: 'Raison du rejet.',
    motive: NOT_AN_OFFER,
    failed_criteria: [values.motive ?? NOT_AN_OFFER],
    created_at: '2026-10-08T10:00:00Z',
    ...values,
  };
}

describe('RejectedComponent', () => {
  let fixture: ComponentFixture<RejectedComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RejectedComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(RejectedComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(root: Element = element()): string {
    return (root.textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  async function serve(pages: RejectedJob[]): Promise<void> {
    http.expectOne({ method: 'GET', url: '/api/rejected-jobs' }).flush(pages);
    await fixture.whenStable();
  }

  function titles(): string[] {
    return [...element().querySelectorAll('.pages h3')].map((title) => text(title));
  }

  /** Répartition affichée : « motif | nombre | part ». */
  function bars(): string[] {
    return [...element().querySelectorAll('.bars button')].map((bar) =>
      ['.label', '.value strong', '.value small'].map((part) => text(bar.querySelector(part)!)).join(' | '),
    );
  }

  async function click(label: string, scope = 'button'): Promise<void> {
    [...element().querySelectorAll(scope)].find((button) => text(button).startsWith(label))!.dispatchEvent(
      new Event('click'),
    );
    await fixture.whenStable();
  }

  async function search(words: string): Promise<void> {
    const input = element().querySelector<HTMLInputElement>('input[name=search]')!;
    input.value = words;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  it('should say when no page has been rejected', async () => {
    await serve([]);

    expect(text()).toContain('Aucune page écartée');
    expect(element().querySelector('.bars')).toBeNull();
  });

  it('should count pages by the motive the API gives, most frequent first', async () => {
    await serve([
      page(1, { motive: OTHER_JOB }),
      page(2),
      page(3),
      page(4, { motive: SKILLS }),
      page(5),
      page(6, { motive: OTHER_JOB }),
    ]);

    expect(bars()).toEqual([`${NOT_AN_OFFER} | 3 | 50 %`, `${OTHER_JOB} | 2 | 33 %`, `${SKILLS} | 1 | 17 %`]);
    expect(text(element().querySelector('.insight h2')!)).toBe('6 pages écartées');
  });

  it('should show each page with what the API says about it', async () => {
    await serve([
      page(1, {
        title: 'Data scientist senior',
        motive: OTHER_JOB,
        failed_criteria: [OTHER_JOB, 'Hors lieu recherché'],
        contract_type: 'CDI',
        work_location: 'Lille',
        reject_reason: 'Le poste est un poste de data scientist.',
        created_at: '2026-10-08T22:30:00Z',
      }),
    ]);

    const row = text(element().querySelector('.pages > li')!);
    expect(row).toContain(OTHER_JOB);
    expect(row).toContain('9 oct.');
    expect(row).toContain('Le poste est un poste de data scientist.');
    expect(row).toContain('exemple-emploi.fr');
    expect(row).toContain('CDI');
    expect(row).toContain('Lille');
    expect(row).toContain('via « ingénieur IA »');
    // Les critères en défaut au-delà du motif, tels que l'API les liste
    expect(row).toContain('aussi : Hors lieu recherché');
  });

  it('should filter the pages by clicking a motive', async () => {
    await serve([page(1), page(2, { motive: OTHER_JOB }), page(3, { motive: SKILLS })]);

    await click(OTHER_JOB, '.bars button');
    expect(titles()).toEqual(['Page 2']);
    await click(SKILLS, '.bars button');
    expect(titles()).toEqual(['Page 2', 'Page 3']);
    // La répartition, elle, reste celle de toutes les pages
    expect(bars().length).toBe(3);

    await click('Tout afficher');
    expect(titles().length).toBe(3);
  });

  it('should filter by the search that found the page', async () => {
    await serve([page(1), page(2, { query: 'AI engineer' }), page(3, { query: null })]);

    await click('AI engineer', '.chips button');

    expect(titles()).toEqual(['Page 2']);
    expect(text(element().querySelector('.result')!)).toContain('1 sur 3');
  });

  it('should search in titles, addresses and reasons, ignoring accents and case', async () => {
    await serve([
      page(1, { title: 'Ingénieur DevOps' }),
      page(2, { url: 'https://www.linkedin.com/jobs/2' }),
      page(3, { reject_reason: 'Offre expirée depuis mars.' }),
    ]);

    await search('ingenieur');
    expect(titles()).toEqual(['Ingénieur DevOps']);
    await search('LinkedIn');
    expect(titles()).toEqual(['Page 2']);
    await search('expiree');
    expect(titles()).toEqual(['Page 3']);
    await search('introuvable');
    expect(text()).toContain('Aucune page ne correspond à ces filtres.');
  });

  it('should show a long list by pages', async () => {
    await serve(Array.from({ length: 65 }, (_, index) => page(index + 1)));

    expect(titles().length).toBe(30);
    expect(text(element().querySelector('.more')!)).toContain('35 pages restantes');

    await click('Afficher la suite');
    await click('Afficher la suite');

    expect(titles().length).toBe(65);
    expect(element().querySelector('.more')).toBeNull();
  });

  it('should say why the pages could not be read', async () => {
    http
      .expectOne('/api/rejected-jobs')
      .flush({ detail: 'Erreur du serveur.' }, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();

    expect(text()).toContain('Erreur du serveur.');
  });
});
