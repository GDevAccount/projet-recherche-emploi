import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Account } from '../core/api.models';
import { SessionService } from '../core/session.service';
import { DARK_CLASS } from '../core/theme';
import { ShellComponent } from './shell.component';

const GUEST: Account = {
  user_id: 2,
  is_owner: false,
  can_search: false,
  remaining_searches: 1,
  max_searches_per_day: 2,
};

describe('ShellComponent', () => {
  let fixture: ComponentFixture<ShellComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    localStorage.clear();
    document.documentElement.classList.remove(DARK_CLASS);
    await TestBed.configureTestingModule({
      imports: [ShellComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
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

  function text(): string {
    return (element().textContent ?? '').replace(/\s+/g, ' ');
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
    expect(text()).not.toContain('Prêt à chercher');
  });

  it('should say when the API finds the profile ready', async () => {
    await openSession({ ...GUEST, can_search: true });

    expect(text()).toContain('Prêt à chercher');
    expect(element().querySelector('a.cta')).toBeNull();
  });

  it('should link to every section', async () => {
    await openSession(GUEST);

    const links = [...element().querySelectorAll('nav a')].map((link) => link.getAttribute('href'));
    expect(links).toEqual(['/offres', '/rejets', '/profil']);
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
