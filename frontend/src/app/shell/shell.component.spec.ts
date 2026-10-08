import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Account } from '../core/api.models';
import { FETCH } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { DARK_CLASS } from '../core/theme';
import { ShellComponent } from './shell.component';

const GUEST: Account = {
  user_id: 2,
  is_owner: false,
  email: null,
  name: null,
  picture: null,
  can_search: false,
  search_running: false,
  remaining_searches: 1,
  max_searches_per_day: 2,
};

describe('ShellComponent', () => {
  let fixture: ComponentFixture<ShellComponent>;
  let http: HttpTestingController;
  // Un flux qui ne se termine pas : la recherche reste « en cours »
  const fetchMock = vi.fn(() => Promise.resolve(new Response(new ReadableStream(), { status: 200 })));

  beforeEach(async () => {
    localStorage.clear();
    document.documentElement.classList.remove(DARK_CLASS);
    await TestBed.configureTestingModule({
      imports: [ShellComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: FETCH, useValue: fetchMock },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function openSession(account: Account): Promise<void> {
    TestBed.inject(SessionService).open('preuve').subscribe();
    http.expectOne('/api/session').flush(account);
    fixture = TestBed.createComponent(ShellComponent);
    await fixture.whenStable();
  }

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(root: Element = element()): string {
    return (root.textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  function launchButton(): HTMLButtonElement {
    return element().querySelector<HTMLButtonElement>('button.cta')!;
  }

  it('should show a guest the searches left today, as the API counts them', async () => {
    await openSession(GUEST);

    expect(text()).toContain('1 / 2 recherches');
  });

  it('should not show a quota to the owner, who has none', async () => {
    await openSession({ ...GUEST, user_id: 1, is_owner: true, remaining_searches: null });

    expect(element().querySelector('.quota')).toBeNull();
  });

  it('should send a user who cannot search yet to the profile', async () => {
    await openSession(GUEST);

    expect(element().querySelector('a.cta')?.getAttribute('href')).toBe('/profil');
    expect(text()).not.toContain('Lancer une recherche');
  });

  it('should offer to launch a search when the API finds the profile ready', async () => {
    await openSession({ ...GUEST, can_search: true });

    expect(launchButton().disabled).toBe(false);
    expect(element().querySelector('a.cta')).toBeNull();
    expect(element().querySelector('app-run-panel')).toBeNull();
  });

  it('should not offer a search once the daily quota is used up', async () => {
    await openSession({ ...GUEST, can_search: true, remaining_searches: 0 });

    expect(launchButton().disabled).toBe(true);
    expect(text()).toContain("Quota atteint pour aujourd'hui.");
  });

  it('should launch the search and follow it on the page', async () => {
    await openSession({ ...GUEST, can_search: true });

    launchButton().click();
    await fixture.whenStable();

    expect(fetchMock).toHaveBeenCalledWith('/api/searches', expect.objectContaining({ method: 'POST' }));
    expect(element().querySelector('app-run-panel')).toBeTruthy();
    // Pas de second lancement pendant que la première recherche tourne
    expect(launchButton().disabled).toBe(true);
    expect(text(launchButton())).toBe('Recherche en cours…');
  });

  it('should not offer a second search while one runs on the server', async () => {
    // Page rechargée pendant une recherche, ou recherche lancée d'un autre onglet
    await openSession({ ...GUEST, can_search: true, search_running: true });

    expect(launchButton().disabled).toBe(true);
    expect(text(launchButton())).toBe('Recherche en cours…');
    expect(text()).toContain('Une recherche est en cours sur le serveur.');
    expect(element().querySelector('app-run-panel')).toBeNull();
  });

  it('should link to every section', async () => {
    await openSession(GUEST);

    const links = [...element().querySelectorAll('nav a')].map((link) => link.getAttribute('href'));
    expect(links).toEqual(['/offres', '/rejets', '/profil']);
  });

  it('should lead to the account page from the avatar', async () => {
    await openSession({ ...GUEST, email: 'alice@exemple.fr', name: 'Alice' });

    const link = element().querySelector('a.account')!;
    expect(link.getAttribute('href')).toBe('/compte');
    expect(link.getAttribute('aria-label')).toBe('Mon compte : alice@exemple.fr');
    expect(text(link)).toBe('A');
  });

  it('should switch theme and remember the choice', async () => {
    await openSession(GUEST);

    element().querySelector<HTMLButtonElement>('button[aria-label="Passer au thème sombre"]')!.click();
    await fixture.whenStable();

    expect(document.documentElement.classList.contains(DARK_CLASS)).toBe(true);
    expect(localStorage.getItem('theme')).toBe('dark');
    expect(element().querySelector('button[aria-label="Passer au thème clair"]')).toBeTruthy();
  });

  it('should close the session and go back to the login screen', async () => {
    await openSession(GUEST);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    element().querySelector<HTMLButtonElement>('button[aria-label="Se déconnecter"]')!.click();
    const request = http.expectOne('/api/session');
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });

    expect(TestBed.inject(SessionService).account()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['connexion']);
  });
});
