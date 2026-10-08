import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Account } from '../core/api.models';
import { SessionService } from '../core/session.service';
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

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('should show a guest the searches left today, as the API counts them', async () => {
    await openSession(GUEST);

    expect(text()).toContain('Recherches restantes aujourd\'hui : 1 sur 2');
    expect(text()).toContain('Offres retenues');
    expect(text()).toContain('Pages rejetées');
  });

  it('should not show a quota to the owner, who has none', async () => {
    await openSession({ ...GUEST, user_id: 1, is_owner: true, remaining_searches: null });

    expect(text()).not.toContain('Recherches restantes');
  });

  it('should close the session and go back to the login screen', async () => {
    await openSession(GUEST);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('header button')!.click();
    const request = http.expectOne('/api/session');
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });

    expect(TestBed.inject(SessionService).account()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['connexion']);
  });
});
