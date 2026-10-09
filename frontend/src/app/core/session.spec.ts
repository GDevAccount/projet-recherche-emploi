import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom } from 'rxjs';

import { Account } from './api.models';
import { apiInterceptor } from './api.interceptor';
import { authGuard, loginGuard } from './auth.guard';
import { SessionService } from './session.service';

const ACCOUNT: Account = {
  user_id: 2,
  is_owner: false, is_admin: false,
  email: null,
  name: null,
  picture: null,
  can_search: false,
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

  it('should let a reloaded page in when its cookie is still valid', async () => {
    const result = guardResult(authGuard);
    http.expectOne('/api/me').flush(ACCOUNT);

    expect(await result).toBe(true);
    expect(session.account()).toEqual(ACCOUNT);
  });

  it('should send a visitor without a session to the login screen', async () => {
    const result = guardResult(authGuard);
    http.expectOne('/api/me').flush({ detail: 'Authentification requise.' }, UNAUTHORIZED);

    expect(router.serializeUrl((await result) as UrlTree)).toBe('/connexion');
  });

  it('should not ask a logged-in user to log in again', async () => {
    const result = guardResult(loginGuard);
    http.expectOne('/api/me').flush(ACCOUNT);

    expect(router.serializeUrl((await result) as UrlTree)).toBe('/');
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
