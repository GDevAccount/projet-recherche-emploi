import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { LOGIN_PATH } from './paths';
import { SessionService } from './session.service';

// Appels dont un refus est traité par l'appelant : l'écran de connexion et les gardes de route
const HANDLED_BY_CALLER = ['/session', '/me'];

export const apiInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith(environment.apiUrl)) {
    return next(request);
  }
  const session = inject(SessionService);
  const router = inject(Router);

  // Sans effet à la même adresse ; nécessaire pour que le cookie de session suive si le front est hébergé ailleurs
  return next(request.clone({ withCredentials: true })).pipe(
    catchError((error: unknown) => {
      // Session expirée en cours de route
      const expired = error instanceof HttpErrorResponse && error.status === 401;
      if (expired && !HANDLED_BY_CALLER.some((path) => request.url.endsWith(path))) {
        session.forget();
        void router.navigate([LOGIN_PATH]);
      }
      return throwError(() => error);
    }),
  );
};
