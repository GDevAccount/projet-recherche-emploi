import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom } from 'rxjs';

import { Account } from './api.models';
import { apiInterceptor } from './api.interceptor';
import { authGuard, homeGuard, loginGuard, sessionGuard } from './auth.guard';
import { SessionService } from './session.service';

const ACCOUNT: Account = {
  user_id: 2,
  is_owner: false, is_trial: false, is_admin: false,
  email: null,
  name: null,
  picture: null,
  can_search: false,
  has_searched: true,
  search_running: false,
  remaining_searches: 2,
  max_searches_per_day: 2,
};
const UNAUTHORIZED = { status: 401, statusText: 'Unauthorized' };

describe('session', () => {
  let http: HttpTestingController;
  let session: SessionService;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withInterceptors([apiInterceptor])), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    session = TestBed.inject(SessionService);
    router = TestBed.inject(Router);
  });

  afterEach(() => http.verify());

  function guardResult(guard: typeof authGuard): Promise<unknown> {
    const result = TestBed.runInInjectionContext(() => guard({} as never, {} as never));
    return result instanceof Observable ? firstValueFrom(result) : Promise.resolve(result);
  }

  it('should open a session with the proof in the Authorization header only', () => {
    session.open('preuve').subscribe();

    const request = http.expectOne('/api/session');
    expect(request.request.method).toBe('POST');
    expect(request.request.headers.get('Authorization')).toBe('Bearer preuve');
    expect(request.request.body).toBeNull();
    expect(request.request.withCredentials).toBe(true);
    request.flush(ACCOUNT);

    expect(session.account()).toEqual(ACCOUNT);
  });

  it('should forget the account when the session is closed', () => {
    session.open('preuve').subscribe();
    http.expectOne('/api/session').flush(ACCOUNT);

    session.close().subscribe();
    const request = http.expectOne('/api/session');
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });

    expect(session.account()).toBeNull();
  });

  it('should read the session of a reloaded page before opening the screens', async () => {
    const result = guardResult(sessionGuard);
    http.expectOne('/api/me').flush(ACCOUNT);

    expect(await result).toBe(true);
    expect(session.account()).toEqual(ACCOUNT);
  });

  it('should open the screens to a visitor without a session', async () => {
    const result = guardResult(sessionGuard);
    http.expectOne('/api/me').flush({ detail: 'Authentification requise.' }, UNAUTHORIZED);

    expect(await result).toBe(true);
    expect(session.account()).toBeNull();
  });

  it('should keep the account page for those who have a session', async () => {
    expect(router.serializeUrl((await guardResult(authGuard)) as UrlTree)).toBe('/connexion');

    session.open('preuve').subscribe();
    http.expectOne('/api/session').flush(ACCOUNT);

    expect(await guardResult(authGuard)).toBe(true);
  });

  it('should let a trial account reach the login screen, where it keeps what it holds', async () => {
    const result = guardResult(loginGuard);
    http.expectOne('/api/me').flush({ ...ACCOUNT, is_trial: true });

    expect(await result).toBe(true);
  });

  it('should open a trial account for a visitor at their first action, and only then', () => {
    let opened: Account | undefined;
    session.ensure().subscribe((account) => (opened = account));

    const request = http.expectOne('/api/session/trial');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({ ...ACCOUNT, is_trial: true });
    expect(opened?.is_trial).toBe(true);

    // Une fois la session ouverte, plus rien n'est demandé
    session.ensure().subscribe();
    http.expectNone('/api/session/trial');
  });

  it('should not ask a logged-in user to log in again', async () => {
    const result = guardResult(loginGuard);
    http.expectOne('/api/me').flush(ACCOUNT);

    expect(router.serializeUrl((await result) as UrlTree)).toBe('/offres');
  });

  it('should show the home page to a visitor without a session', async () => {
    const result = guardResult(homeGuard);
    http.expectOne('/api/me').flush({ detail: 'Authentification requise.' }, UNAUTHORIZED);

    expect(await result).toBe(true);
  });

  it('should take a logged-in user from the home page to their offers', async () => {
    const result = guardResult(homeGuard);
    http.expectOne('/api/me').flush(ACCOUNT);

    expect(router.serializeUrl((await result) as UrlTree)).toBe('/offres');
  });

  it('should not ask the API again for a session it already knows', async () => {
    session.open('preuve').subscribe();
    http.expectOne('/api/session').flush(ACCOUNT);

    expect(router.serializeUrl((await guardResult(homeGuard)) as UrlTree)).toBe('/offres');
  });

  it('should go back to the login screen when the session expires on a data call', () => {
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    session.open('preuve').subscribe();
    http.expectOne('/api/session').flush(ACCOUNT);

    TestBed.inject(HttpClient).get('/api/jobs').subscribe({ error: () => undefined });
    http.expectOne('/api/jobs').flush({ detail: 'Authentification requise.' }, UNAUTHORIZED);

    expect(session.account()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['connexion']);
  });

  it('should leave a refused login to the login screen', () => {
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    session.open('faux').subscribe({ error: () => undefined });
    http.expectOne('/api/session').flush({ detail: 'Authentification requise.' }, UNAUTHORIZED);

    expect(navigate).not.toHaveBeenCalled();
  });
});
