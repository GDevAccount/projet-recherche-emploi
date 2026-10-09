import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { JOBS_PATH, LOGIN_PATH } from './paths';
import { SessionService } from './session.service';

/** Laisse passer une session ouverte, renvoie les autres à l'écran de connexion. */
export const authGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  if (session.account()) {
    return true;
  }
  // Rechargement de la page : le cookie de session est peut-être encore valable
  return session.refresh().pipe(map((open) => open || router.createUrlTree([LOGIN_PATH])));
};

/** Évite de redemander une connexion à qui a déjà une session. */
export const loginGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.refresh().pipe(map((open) => (open ? router.createUrlTree(['/']) : true)));
};

/**
 * Renvoie aux offres qui n'est pas administrateur. Placée sous authGuard, donc le compte est déjà lu.
 * C'est l'API qui refuse (403) ; ceci évite seulement un écran d'erreurs.
 */
export const adminGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.account()?.is_admin ? true : router.createUrlTree([JOBS_PATH]);
};
