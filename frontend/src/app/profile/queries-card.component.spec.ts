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
  has_searched: true,
  search_running: false,
  remaining_searches: 2,
  max_searches_per_day: 2,
};

function query(id: number, values: Partial<SearchQuery> = {}): SearchQuery {
  return {
    id,
    contract_type: 'CDI',
    query: `poste ${id}`,
    skills: [],
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
    return [...element().querySelectorAll('article > ul > li')].map((row) =>
      ['.contract', 'strong', '.where'].map((part) => text(row.querySelector(part)!)).join(' | '),
    );
  }

  async function serve(queries: SearchQuery[]): Promise<void> {
    http.expectOne({ method: 'GET', url: '/api/queries' }).flush(queries);
    await fixture.whenStable();
  }

  /** Le formulaire lit les réglages à son ouverture, une fois : la seconde fenêtre ne les redemande pas. */
  async function serveConfig(): Promise<void> {
    for (const request of http.match('/api/config')) {
      request.flush({
        login_mode: 'google',
        google_client_id: 'id',
        contract_types: ['CDI', 'freelance', 'stage'],
        max_skills_per_query: 3,
      });
    }
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

  function dialog(): HTMLDialogElement {
    return element().querySelector('dialog')!;
  }

  /** Ouvre la fenêtre du formulaire d'ajout. */
  async function openAdd(): Promise<void> {
    await click('Ajouter un poste');
    await serveConfig();
  }

  /** Ouvre la fenêtre du formulaire d'un poste enregistré. */
  async function openEdit(title: string): Promise<void> {
    element().querySelector<HTMLButtonElement>(`button[aria-label="Modifier le poste « ${title} »"]`)!.click();
    await fixture.whenStable();
    await serveConfig();
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
    await openAdd();

    const pills = [...element().querySelectorAll('[aria-labelledby=contract-label] button')].map((pill) => text(pill));
    expect(pills).toEqual(['CDI', 'freelance', 'stage']);
  });

  it('should add a search for all of France by default', async () => {
    await serve([]);
    // Le formulaire n'est dans la page qu'une fois sa fenêtre ouverte
    expect(element().querySelector('form')).toBeNull();
    expect(dialog().hasAttribute('open')).toBe(false);
    await openAdd();
    expect(dialog().hasAttribute('open')).toBe(true);
    expect(text(dialog().querySelector('h2')!)).toBe('Ajouter un poste');
    expect(submitButton().disabled).toBe(true);

    await type('query', 'ingénieur IA');
    await submit();

    const request = http.expectOne({ method: 'POST', url: '/api/queries' });
    expect(request.request.body).toEqual({
      contract_type: 'CDI',
      query: 'ingénieur IA',
      skills: [],
      location: '',
      remote: false,
    });
    request.flush(query(7, { query: 'ingénieur IA' }));
    // Un premier poste peut rendre la recherche possible : c'est l'API qui le dit
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    // Le poste rejoint la liste, et la fenêtre se referme
    expect(rows()).toEqual(['CDI | ingénieur IA | Toute la France']);
    expect(dialog().hasAttribute('open')).toBe(false);
    expect(element().querySelector('form')).toBeNull();
  });

  it('should send the chosen contract and place', async () => {
    await serve([]);
    await openAdd();

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
      skills: [],
      location: 'Lyon',
      remote: false,
    });
    request.flush(query(8, { contract_type: 'freelance', query: 'développeur Python', location: 'Lyon' }));
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  it('should ignore a typed place once full remote is chosen', async () => {
    await serve([]);
    await openAdd();

    await type('query', 'AI engineer');
    await click('Un lieu précis');
    await type('location', 'Lyon');
    await click('Télétravail complet');
    await submit();

    const request = http.expectOne({ method: 'POST', url: '/api/queries' });
    expect(request.request.body).toEqual({
      contract_type: 'CDI',
      query: 'AI engineer',
      skills: [],
      location: '',
      remote: true,
    });
    request.flush(query(9, { query: 'AI engineer', remote: true }));
    http.expectOne('/api/me').flush(ACCOUNT);
  });

  /** Les tags d'un groupe : ceux du formulaire, ou ceux d'un poste enregistré. */
  function tags(root: string): string[] {
    return [...element().querySelectorAll(`${root} .tag`)].map((tag) => text(tag));
  }

  async function press(key: string): Promise<KeyboardEvent> {
    const event = new KeyboardEvent('keydown', { key, cancelable: true });
    element().querySelector<HTMLInputElement>('input[name=skill]')!.dispatchEvent(event);
    await fixture.whenStable();
    return event;
  }

  it('should turn typed skills into tags that a cross removes', async () => {
    await serve([]);
    await openAdd();

    await type('skill', 'SAP');
    // Entrée valide la compétence au lieu d'envoyer le formulaire
    expect((await press('Enter')).defaultPrevented).toBe(true);
    await type('skill', ' paie ,  sap, anglais courant');
    await press('Enter');

    // Ni doublon, ni espaces superflus ; le champ est vidé pour la suivante
    expect(tags('.tag-input')).toEqual(['SAP', 'paie', 'anglais courant']);
    expect(element().querySelector<HTMLInputElement>('input[name=skill]')!.value).toBe('');

    element().querySelector<HTMLButtonElement>('button[aria-label="Retirer la compétence « paie »"]')!.click();
    await fixture.whenStable();
    expect(tags('.tag-input')).toEqual(['SAP', 'anglais courant']);

    // Sur un champ vide, la touche d'effacement retire le dernier tag, et Entrée laisse partir le formulaire
    await press('Backspace');
    expect(tags('.tag-input')).toEqual(['SAP']);
    expect((await press('Enter')).defaultPrevented).toBe(false);
  });

  it('should take no more skills than a job accepts', async () => {
    await serve([]);
    await openAdd();

    // Quatre compétences collées d'un coup : la limite donnée par l'API en garde trois
    await type('skill', 'SAP, paie, anglais, Sage');
    await press('Enter');

    expect(tags('.tag-input')).toEqual(['SAP', 'paie', 'anglais']);
    expect(skillInput().disabled).toBe(true);
    expect(text()).toContain('Un poste accepte 3 compétences au plus');

    // En retirer une rend la saisie
    element().querySelector<HTMLButtonElement>('button[aria-label="Retirer la compétence « paie »"]')!.click();
    await fixture.whenStable();
    expect(skillInput().disabled).toBe(false);
    expect(text()).not.toContain('au plus');
  });

  it('should send the skills with the job, the one still being typed included', async () => {
    await serve([]);
    await openAdd();

    await type('query', 'comptable');
    await type('skill', 'fournisseurs');
    await press('Enter');
    await type('skill', 'SAP');
    await submit();

    const request = http.expectOne({ method: 'POST', url: '/api/queries' });
    expect(request.request.body).toEqual({
      contract_type: 'CDI',
      query: 'comptable',
      skills: ['fournisseurs', 'SAP'],
      location: '',
      remote: false,
    });
    request.flush(query(7, { query: 'comptable', skills: ['fournisseurs', 'SAP'] }));
    http.expectOne('/api/me').flush(ACCOUNT);
    await fixture.whenStable();

    // Le poste enregistré montre ses compétences, et le formulaire suivant repart vide
    expect(tags('li')).toEqual(['fournisseurs', 'SAP']);
    await openAdd();
    expect(tags('.tag-input')).toEqual([]);
    expect(element().querySelector<HTMLInputElement>('input[name=query]')!.value).toBe('');
  });

  function skillInput(): HTMLInputElement {
    return element().querySelector<HTMLInputElement>('input[name=skill]')!;
  }

  /** Saisit un début de compétence, et répond à la place du référentiel. */
  async function suggest(typed: string, names: string[]): Promise<void> {
    skillInput().dispatchEvent(new Event('focus'));
    await type('skill', typed);
    // Le référentiel n'est interrogé qu'une fois la frappe arrêtée
    await new Promise((resolve) => setTimeout(resolve, 200));
    http.expectOne((request) => request.url === '/api/skills' && request.params.get('q') === typed).flush(names);
    await fixture.whenStable();
  }

  /** Les lignes de la liste ouverte sous le champ ; aucune quand elle est fermée. */
  function options(): string[] {
    const list = element().querySelector<HTMLElement>('#skill-options')!;
    return list.hidden ? [] : [...list.querySelectorAll('li')].map((option) => text(option));
  }

  it('should suggest skills from the catalog and take the one clicked', async () => {
    await serve([]);
    await openAdd();

    await suggest('compta', ['Comptabilité générale', 'Comptabilité clients']);
    expect(options()).toEqual(['Comptabilité générale', 'Comptabilité clients', 'Ajouter « compta »']);
    expect(skillInput().getAttribute('aria-expanded')).toBe('true');

    element().querySelector<HTMLElement>('#skill-option-1')!.click();
    await fixture.whenStable();

    expect(tags('.tag-input')).toEqual(['Comptabilité clients']);
    expect(skillInput().value).toBe('');
    expect(options()).toEqual([]);

    // Une compétence déjà choisie n'est plus proposée
    await suggest('comptabilité', ['Comptabilité générale', 'Comptabilité clients']);
    expect(options()).toEqual(['Comptabilité générale', 'Ajouter « comptabilité »']);
  });

  it('should pick a suggested skill with the arrow keys', async () => {
    await serve([]);
    await openAdd();

    await suggest('sa', ['SAP', 'Sage']);
    await press('ArrowDown');
    await press('ArrowDown');
    expect(skillInput().getAttribute('aria-activedescendant')).toBe('skill-option-1');
    expect(element().querySelector('#skill-option-1')!.getAttribute('aria-selected')).toBe('true');
    await press('Enter');

    expect(tags('.tag-input')).toEqual(['Sage']);

    // Échap ferme la liste sans rien prendre
    await suggest('sa', ['SAP', 'Sage']);
    await press('Escape');
    expect(options()).toEqual([]);
    expect(tags('.tag-input')).toEqual(['Sage']);
  });

  it('should offer to add a skill only when the catalog does not have it', async () => {
    await serve([]);
    await openAdd();

    // Sans accent ni majuscule, c'est la même compétence : rien à ajouter
    await suggest('redaction', ['Rédaction', 'Rédaction web']);
    expect(options()).toEqual(['Rédaction', 'Rédaction web']);

    await suggest('dressage de licornes', []);
    expect(options()).toEqual(['Ajouter « dressage de licornes »']);
    element().querySelector<HTMLElement>('#skill-options .create')!.click();
    await fixture.whenStable();

    expect(tags('.tag-input')).toEqual(['dressage de licornes']);
    expect(options()).toEqual([]);
  });

  it('should show why the API refused a search, and keep what was typed', async () => {
    await serve([query(1, { query: 'ingénieur IA' })]);
    await openAdd();

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

  it('should change a saved job in the window, with its own values to start from', async () => {
    await serve([
      query(1, { query: 'comptable', skills: ['SAP', 'Paie'], location: 'Lyon' }),
      query(2, { query: 'auditeur' }),
    ]);

    await openEdit('comptable');

    expect(dialog().hasAttribute('open')).toBe(true);
    expect(text(dialog().querySelector('h2')!)).toBe('Modifier ce poste');
    // La liste reste entière derrière la fenêtre
    expect(rows().length).toBe(2);
    const field = (name: string) => dialog().querySelector<HTMLInputElement>(`input[name=${name}]`)!;
    expect(field('query').value).toBe('comptable');
    expect(field('location').value).toBe('Lyon');
    expect(tags('.tag-input')).toEqual(['SAP', 'Paie']);
    const checked = [...dialog().querySelectorAll('[aria-checked=true]')].map((pill) => text(pill));
    expect(checked).toEqual(['CDI', 'Un lieu précis']);

    await type('query', 'comptable fournisseurs');
    dialog().querySelector<HTMLButtonElement>('button[aria-label="Retirer la compétence « Paie »"]')!.click();
    await click('freelance');
    await click('Télétravail complet');
    await click('Enregistrer');

    const request = http.expectOne({ method: 'PUT', url: '/api/queries/1' });
    expect(request.request.body).toEqual({
      contract_type: 'freelance',
      query: 'comptable fournisseurs',
      skills: ['SAP'],
      location: '',
      remote: true,
    });
    request.flush(
      query(1, { contract_type: 'freelance', query: 'comptable fournisseurs', skills: ['SAP'], remote: true }),
    );
    await fixture.whenStable();

    // Le poste garde sa place, et la fenêtre se referme
    expect(rows()).toEqual([
      'freelance | comptable fournisseurs | Télétravail complet',
      'CDI | auditeur | Toute la France',
    ]);
    expect(dialog().hasAttribute('open')).toBe(false);
  });

  it('should leave a job as it was when its change is given up or refused', async () => {
    await serve([query(1, { query: 'comptable' }), query(2, { query: 'auditeur' })]);
    const edit = () => openEdit('comptable');

    await edit();
    await type('query', 'pirate');
    await click('Annuler');
    expect(dialog().hasAttribute('open')).toBe(false);
    expect(rows()).toEqual(['CDI | comptable | Toute la France', 'CDI | auditeur | Toute la France']);

    // Ce qui avait été saisi n'est gardé ni pour la fois suivante, ni pour un ajout
    await edit();
    expect(element().querySelector<HTMLInputElement>('input[name=query]')!.value).toBe('comptable');
    await click('Annuler');
    await openAdd();
    expect(element().querySelector<HTMLInputElement>('input[name=query]')!.value).toBe('');
    await click('Annuler');

    await edit();
    await type('query', 'auditeur');
    await submit();
    http
      .expectOne({ method: 'PUT', url: '/api/queries/1' })
      .flush({ detail: 'Cette recherche existe déjà.' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    // Le refus s'affiche dans la fenêtre restée ouverte, avec la saisie
    expect(dialog().hasAttribute('open')).toBe(true);
    expect(text(dialog())).toContain('Cette recherche existe déjà.');
    expect(element().querySelector<HTMLInputElement>('input[name=query]')!.value).toBe('auditeur');
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
