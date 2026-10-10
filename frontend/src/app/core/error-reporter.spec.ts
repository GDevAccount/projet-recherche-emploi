import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ErrorHandler } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { ReportingErrorHandler, describeError } from './error-reporter';
import { SessionService } from './session.service';

function crash(name: string, message: string, stack?: string): Error {
  const error = new Error(message);
  error.name = name;
  error.stack = stack;
  return error;
}

describe('describeError', () => {
  it('should keep the type, the screen and the place in the code, never the message', () => {
    const stack = [
      "TypeError: Cannot read properties of undefined (reading 'Ingénieur IA chez Exemple')",
      '    at JobCard.title (https://jobgrep.exemple/chunk-AB12CD34.js:7:1532)',
      '    at https://jobgrep.exemple/main-5UFRYBOQ.js:1:99',
    ].join('\n');

    const report = describeError(
      crash('TypeError', 'Ingénieur IA chez Exemple', stack),
      '/offres?q=secret#haut',
    );

    expect(report).toEqual({
      error_type: 'TypeError',
      route: '/offres',
      source: 'chunk-AB12CD34.js:7:1532',
    });
    expect(JSON.stringify(report)).not.toContain('Exemple');
  });

  it('should cope with what is not an error, and with names and screens it cannot trust', () => {
    expect(describeError('une chaîne', '/offres')).toEqual({
      error_type: 'Error',
      route: '/offres',
      source: null,
    });
    expect(describeError(crash('Nom avec des espaces', 'x'), 'pas une adresse')).toEqual({
      error_type: 'Error',
      route: null,
      source: null,
    });
  });
});

describe('ReportingErrorHandler', () => {
  let handler: ErrorHandler;
  let http: HttpTestingController;
  let logged: unknown[];

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ErrorHandler, useClass: ReportingErrorHandler },
      ],
    });
    handler = TestBed.inject(ErrorHandler);
    http = TestBed.inject(HttpTestingController);
    logged = [];
    vi.spyOn(console, 'error').mockImplementation((error: unknown) => logged.push(error));
  });

  afterEach(() => {
    http.verify();
    vi.restoreAllMocks();
  });

  function openSession(): void {
    TestBed.inject(SessionService).refresh().subscribe();
    http.expectOne('/api/me').flush({ email: 'alice@exemple.fr' });
  }

  it('should report an error once to the API, and still log it', () => {
    openSession();
    const error = crash(
      'RangeError',
      'contenu',
      'at x (https://jobgrep.exemple/main-5UFRYBOQ.js:1:42)',
    );

    handler.handleError(error);
    handler.handleError(error);

    const request = http.expectOne({ method: 'POST', url: '/api/client-errors' });
    expect(request.request.body).toEqual({
      error_type: 'RangeError',
      route: TestBed.inject(Router).url,
      source: 'main-5UFRYBOQ.js:1:42',
    });
    // Un refus de l'API ne doit pas faire une erreur de plus
    request.flush(null, { status: 500, statusText: 'Erreur' });
    expect(logged).toEqual([error, error]);
  });

  it('should stay silent without a session, and for an error the server already knows', () => {
    handler.handleError(crash('TypeError', 'avant la connexion'));
    openSession();
    handler.handleError(new HttpErrorResponse({ status: 422 }));

    http.expectNone('/api/client-errors');
    expect(logged.length).toBe(2);
  });

  it('should stop after a few reports for the same page load', () => {
    openSession();
    for (let index = 0; index < 8; index++) {
      handler.handleError(crash(`Erreur${index}`, 'x'));
    }

    expect(http.match('/api/client-errors').length).toBe(5);
  });
});
