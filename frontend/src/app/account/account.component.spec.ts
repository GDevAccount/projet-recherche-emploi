import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Account } from '../core/api.models';
import { FETCH } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { AccountComponent } from './account.component';

const ALICE: Account = {
  user_id: 2,
  is_owner: false, is_admin: false,
  email: 'alice@exemple.fr',
  name: 'Alice Martin',
  picture: null,
  can_search: true,
  search_running: false,
  remaining_searches: 2,
  max_searches_per_day: 2,
};

describe('AccountComponent', () => {
  let fixture: ComponentFixture<AccountComponent>;
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AccountComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: FETCH, useValue: vi.fn() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  afterEach(() => http.verify());

  async function openSession(account: Account): Promise<void> {
    TestBed.inject(SessionService).open('preuve').subscribe();
    http.expectOne('/api/session').flush(account);
    fixture = TestBed.createComponent(AccountComponent);
    await fixture.whenStable();
  }

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function text(): string {
    return (element().textContent ?? '').replace(/\s+/g, ' ').trim();
  }

  async function click(label: string): Promise<void> {
    [...element().querySelectorAll('button')].find((button) => button.textContent?.includes(label))!.click();
    await fixture.whenStable();
  }

  it('should say who is connected, as the API tells it', async () => {
    await openSession(ALICE);

    expect(text()).toContain('Alice Martin');
    expect(text()).toContain('alice@exemple.fr');
    expect(text()).toContain('Connecté avec Google.');
    expect(text()).toContain('un compte resté un an sans servir est supprimé');
    expect(element().querySelector('a[href="/confidentialite"]')).toBeTruthy();
  });

  it('should describe a session opened with the password', async () => {
    await openSession({ ...ALICE, user_id: 1, is_owner: true, is_admin: true, email: null, name: null });

    expect(text()).toContain('Session ouverte avec le mot de passe de cette instance.');
    expect(text()).not.toContain('Votre adresse e-mail');
    // Le propriétaire n'est jamais supprimé pour inactivité
    expect(text()).not.toContain('sans servir');
    expect(text()).toContain('vous retrouverez un compte vide');
  });

  it('should not delete anything before the confirmation', async () => {
    await openSession(ALICE);

    await click('Supprimer mon compte');

    expect(text()).toContain('Supprimer définitivement votre compte et toutes vos données ?');
    http.expectNone('/api/me');

    await click('Annuler');
    expect(text()).not.toContain('Supprimer définitivement');
  });

  it('should delete the account once confirmed, then go back to the login screen', async () => {
    await openSession(ALICE);

    await click('Supprimer mon compte');
    await click('Oui, tout supprimer');
    const request = http.expectOne('/api/me');
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });

    expect(TestBed.inject(SessionService).account()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['connexion']);
  });

  it('should show why the API refused, and keep the session', async () => {
    await openSession(ALICE);

    await click('Supprimer mon compte');
    await click('Oui, tout supprimer');
    http
      .expectOne('/api/me')
      .flush({ detail: 'Une recherche est en cours.' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();

    expect(text()).toContain('Une recherche est en cours.');
    expect(TestBed.inject(SessionService).account()).not.toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  it('should close the session', async () => {
    await openSession(ALICE);

    await click('Se déconnecter');
    const request = http.expectOne('/api/session');
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });

    expect(navigate).toHaveBeenCalledWith(['connexion']);
  });
});
