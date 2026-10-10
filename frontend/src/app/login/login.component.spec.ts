import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Account, AppConfig } from '../core/api.models';
import { GoogleIdentityService } from '../core/google-identity.service';
import { LoginComponent } from './login.component';

const ACCOUNT: Account = {
  user_id: 1,
  is_owner: true, is_trial: false, is_admin: true,
  email: null,
  name: null,
  picture: null,
  can_search: true,
  search_running: false,
  remaining_searches: null,
  max_searches_per_day: 2,
};

class FakeGoogleIdentity {
  clientId = '';
  onCredential: (idToken: string) => void = () => undefined;

  renderButton(_parent: HTMLElement, clientId: string, onCredential: (idToken: string) => void): Promise<void> {
    this.clientId = clientId;
    this.onCredential = onCredential;
    return Promise.resolve();
  }
}

describe('LoginComponent', () => {
  let fixture: ComponentFixture<LoginComponent>;
  let http: HttpTestingController;
  let google: FakeGoogleIdentity;
  let navigate: ReturnType<typeof vi.spyOn>;

  beforeEach(async () => {
    google = new FakeGoogleIdentity();
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: GoogleIdentityService, useValue: google },
      ],
    }).compileComponents();

    http = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  async function serveConfig(config: Partial<AppConfig>): Promise<void> {
    http.expectOne('/api/config').flush({ login_mode: null, google_client_id: null, trial: null, contract_types: [], ...config });
    await fixture.whenStable();
  }

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  async function submitPassword(password: string): Promise<void> {
    const input = element().querySelector<HTMLInputElement>('input[type=password]')!;
    input.value = password;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    element().querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  it('should ask for the password of an instance without Google login', async () => {
    await serveConfig({ login_mode: 'password' });

    await submitPassword('sesame');
    const request = http.expectOne('/api/session');
    expect(request.request.headers.get('Authorization')).toBe('Bearer sesame');
    request.flush(ACCOUNT);

    expect(navigate).toHaveBeenCalledWith(['/']);
  });

  it('should say when the password is wrong', async () => {
    await serveConfig({ login_mode: 'password' });

    await submitPassword('faux');
    http
      .expectOne('/api/session')
      .flush({ detail: 'Authentification requise.' }, { status: 401, statusText: 'Unauthorized' });
    await fixture.whenStable();

    expect(element().textContent).toContain('Mot de passe incorrect.');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('should show the Google button and open the session with the token it returns', async () => {
    await serveConfig({ login_mode: 'google', google_client_id: 'id.apps.googleusercontent.com' });

    expect(google.clientId).toBe('id.apps.googleusercontent.com');
    expect(element().querySelector('input[type=password]')).toBeNull();

    google.onCredential('jeton-google');
    const request = http.expectOne('/api/session');
    expect(request.request.headers.get('Authorization')).toBe('Bearer jeton-google');
    request.flush(ACCOUNT);

    expect(navigate).toHaveBeenCalledWith(['/']);
  });

  it('should show the reason given by the API to an uninvited address', async () => {
    await serveConfig({ login_mode: 'google', google_client_id: 'id.apps.googleusercontent.com' });

    google.onCredential('jeton-inconnu');
    http
      .expectOne('/api/session')
      .flush(
        { detail: "Cette adresse n'est pas autorisée à utiliser l'application." },
        { status: 403, statusText: 'Forbidden' },
      );
    await fixture.whenStable();

    expect(element().textContent).toContain("Cette adresse n'est pas autorisée à utiliser l'application.");
  });

  it('should open a trial without any credential, when the instance offers one', async () => {
    await serveConfig({ login_mode: 'google', google_client_id: 'id.apps.googleusercontent.com', trial: 'available' });

    const button = element().querySelector<HTMLButtonElement>('.trial-button')!;
    expect(button.textContent).toContain('Essayer sans compte');
    // Le visiteur n'a rien accepté d'autre : les deux textes sont à portée de clic
    expect(element().querySelector('.terms a[href="/conditions"]')).not.toBeNull();
    expect(element().querySelector('.terms a[href="/confidentialite"]')).not.toBeNull();

    button.click();
    const request = http.expectOne('/api/session/trial');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({ ...ACCOUNT, user_id: 7, is_owner: false, is_admin: false, is_trial: true, remaining_searches: 1 });

    expect(navigate).toHaveBeenCalledWith(['/']);
  });

  it('should show why a trial is refused, and say so beforehand when none is left today', async () => {
    await serveConfig({ login_mode: 'google', google_client_id: 'id.apps.googleusercontent.com', trial: 'available' });

    element().querySelector<HTMLButtonElement>('.trial-button')!.click();
    http
      .expectOne('/api/session/trial')
      .flush({ detail: "Trop d'essais ont été ouverts depuis votre connexion aujourd'hui." }, { status: 429, statusText: 'Too Many Requests' });
    await fixture.whenStable();

    expect(element().textContent).toContain("Trop d'essais ont été ouverts depuis votre connexion");
    expect(navigate).not.toHaveBeenCalled();
  });

  it('should not offer a trial that the instance does not open, or has none left of', async () => {
    await serveConfig({ login_mode: 'google', google_client_id: 'id.apps.googleusercontent.com', trial: 'exhausted' });

    expect(element().querySelector('.trial-button')).toBeNull();
    expect(element().textContent).toContain('Les essais sans compte sont épuisés pour aujourd');
  });

  it('should say when the instance is not protected', async () => {
    await serveConfig({ login_mode: null });

    expect(element().textContent).toContain("n'est pas protégée");
  });

  it('should say when the server does not answer', async () => {
    http.expectOne('/api/config').flush('', { status: 502, statusText: 'Bad Gateway' });
    await fixture.whenStable();

    expect(element().textContent).toContain('Le serveur ne répond pas');
  });
});
