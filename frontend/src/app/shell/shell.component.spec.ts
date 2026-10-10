import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Account } from '../core/api.models';
import { FETCH } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { DARK_CLASS, LIGHT_CLASS } from '../core/theme';
import { ShellComponent } from './shell.component';

const GUEST: Account = {
  user_id: 2,
  is_owner: false, is_trial: false, is_admin: false,
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
    document.documentElement.classList.remove(DARK_CLASS, LIGHT_CLASS);
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
    await openSession({ ...GUEST, user_id: 1, is_owner: true, is_trial: false, is_admin: true, remaining_searches: null });

    expect(element().querySelector('.quota')).toBeNull();
  });

  it('should send a user who cannot search yet to the profile', async () => {
    await openSession(GUEST);

    expect(element().querySelector('a.cta')?.getAttribute('href')).toBe('/profil');
    expect(text()).not.toContain('Lancer une recherche');
  });

  it('should not send to the profile a user who is already there, but say what to do', async () => {
    const router = TestBed.inject(Router);
    router.resetConfig([{ path: '**', children: [] }]);
    await router.navigateByUrl('/profil');
    await openSession(GUEST);

    expect(element().querySelector('a.cta')).toBeNull();
    expect(text(element().querySelector('.hero')!)).toContain('Déposez votre CV et décrivez un poste recherché');

    // De retour sur un autre écran, le renvoi vers le profil revient
    await router.navigateByUrl('/offres');
    await fixture.whenStable();
    expect(element().querySelector('a.cta')?.getAttribute('href')).toBe('/profil');
  });

  describe('visite guidée', () => {
    const tour = () => element().querySelector('app-welcome-tour');
    const title = () => text(tour()!.querySelector('h2')!);

    async function press(label: string): Promise<void> {
      tour()!.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!.click();
      await fixture.whenStable();
    }

    it('should open by itself for a newcomer, and walk through every screen with the arrows', async () => {
      await openSession(GUEST);

      expect(title()).toBe('JobGrep lit les annonces à votre place');
      expect(text(tour()!.querySelector('.app-eyebrow')!)).toBe('Comment ça marche · 1 / 5');
      expect(tour()!.querySelector<HTMLButtonElement>('button[aria-label="Écran précédent"]')!.disabled).toBe(true);

      await press('Écran suivant');
      expect(title()).toBe('1. Dites-lui qui vous êtes');
      await press('Écran suivant');
      // Le quota de l'invité est rappelé là où il compte
      expect(title()).toBe('2. Lancez une recherche');
      expect(text(tour()!.querySelector('.quota')!)).toBe('Vous disposez de 2 recherches par jour.');
      await press('Écran précédent');
      expect(title()).toBe('1. Dites-lui qui vous êtes');
      expect(tour()!.querySelector('.quota')).toBeNull();

      // Les flèches du clavier aussi, sans dépasser le dernier écran
      for (let step = 0; step < 6; step++) {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
      }
      await fixture.whenStable();
      expect(title()).toBe('4. Corrigez-le quand il se trompe');
      expect(tour()!.querySelector('button[aria-label="Écran suivant"]')).toBeNull();
    });

    it('should lead a newcomer to the profile at the end, and not come back', async () => {
      const router = TestBed.inject(Router);
      router.resetConfig([{ path: '**', children: [] }]);
      await openSession(GUEST);
      await press('Écran 5');

      const done = tour()!.querySelector<HTMLButtonElement>('button.done')!;
      expect(text(done)).toBe('Compléter mon profil');
      done.click();
      await fixture.whenStable();

      expect(tour()).toBeNull();
      expect(router.url).toBe('/profil');
      expect(localStorage.getItem('tour')).toBe('seen');
    });

    it('should not open again once seen, nor for a profile that is ready', async () => {
      localStorage.setItem('tour', 'seen');
      await openSession(GUEST);
      expect(tour()).toBeNull();
    });

    it('should not impose itself on a user whose profile is ready', async () => {
      await openSession({ ...GUEST, can_search: true });
      expect(tour()).toBeNull();
    });

    it('should open again from the footer, and close with Escape or Passer', async () => {
      await openSession({ ...GUEST, can_search: true, remaining_searches: null });
      const reopen = [...element().querySelectorAll<HTMLButtonElement>('footer button')].find(
        (button) => text(button) === 'Comment ça marche',
      )!;

      reopen.click();
      await fixture.whenStable();
      await press('Écran 3');
      // Le propriétaire n'a pas de quota : rien à rappeler
      expect(tour()!.querySelector('.quota')).toBeNull();
      await press('Écran 5');
      expect(text(tour()!.querySelector('button.done')!)).toBe("C'est parti");
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      await fixture.whenStable();
      expect(tour()).toBeNull();

      reopen.click();
      await fixture.whenStable();
      tour()!.querySelector<HTMLButtonElement>('button.skip')!.click();
      await fixture.whenStable();
      expect(tour()).toBeNull();
    });
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

  it('should add the tracking section for an administrator only', async () => {
    await openSession({ ...GUEST, is_admin: true });

    const links = [...element().querySelectorAll('nav a')].map((link) => link.getAttribute('href'));
    expect(links).toEqual(['/offres', '/rejets', '/profil', '/suivi']);
  });

  it('should lead to the account page from the avatar', async () => {
    await openSession({ ...GUEST, email: 'alice@exemple.fr', name: 'Alice' });

    const link = element().querySelector('a.account')!;
    expect(link.getAttribute('href')).toBe('/compte');
    expect(link.getAttribute('aria-label')).toBe('Mon compte : alice@exemple.fr');
    expect(text(link)).toBe('A');
  });

  it('should start in the dark theme, then switch and remember the choice', async () => {
    await openSession(GUEST);
    // Sombre d'office, sans choix enregistré et quel que soit le système
    expect(document.documentElement.classList.contains(DARK_CLASS)).toBe(true);
    expect(localStorage.getItem('theme')).toBeNull();

    element().querySelector<HTMLButtonElement>('button[aria-label="Passer au thème clair"]')!.click();
    await fixture.whenStable();

    // Le thème clair se dit aussi : les pages légales s'y fient pour quitter le thème sombre
    expect(document.documentElement.classList.contains(LIGHT_CLASS)).toBe(true);
    expect(document.documentElement.classList.contains(DARK_CLASS)).toBe(false);
    expect(localStorage.getItem('theme')).toBe('light');
    expect(element().querySelector('button[aria-label="Passer au thème sombre"]')).toBeTruthy();
  });

  it('should keep the light theme once chosen', async () => {
    localStorage.setItem('theme', 'light');
    await openSession(GUEST);

    expect(document.documentElement.classList.contains(LIGHT_CLASS)).toBe(true);
    expect(element().querySelector('button[aria-label="Passer au thème sombre"]')).toBeTruthy();
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
