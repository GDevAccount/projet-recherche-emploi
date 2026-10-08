import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { HealthComponent } from './health.component';

describe('HealthComponent', () => {
  let fixture: ComponentFixture<HealthComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HealthComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(HealthComponent);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  function text(): string {
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('should say the API is being called until it answers', () => {
    expect(text()).toContain('Appel de l\'API');
    http.expectOne('/api/health').flush({ status: 'ok' });
  });

  it('should show the API answer', () => {
    http.expectOne('/api/health').flush({ status: 'ok' });

    expect(text()).toContain('API : ok');
  });

  it('should say when the API cannot be reached', () => {
    http.expectOne('/api/health').flush('', { status: 502, statusText: 'Bad Gateway' });

    expect(text()).toContain('API injoignable');
  });
});
