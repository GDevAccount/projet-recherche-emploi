import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { JOBS_PATH, LOGIN_PATH } from './paths';
import { SessionService } from './session.service';

/**
 * Lit la session avant d'ouvrir les écrans, sans rien refuser : ils sont ouverts à tous, et montrent un état
 * vide au visiteur sans session. C'est l'API qui protège les données.
 */
export const sessionGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  if (session.account()) {
    return true;
  }
  // Rechargement de la page : le cookie de session est peut-être encore valable
  return session.refresh().pipe(map(() => true));
};

/** Renvoie à l'écran de connexion qui n'a pas de session. Placée sous sessionGuard, donc la session est déjà lue. */
export const authGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.account() ? true : router.createUrlTree([LOGIN_PATH]);
};

/**
 * Évite de redemander une connexion à qui est déjà connecté. Un compte d'essai, lui, passe : c'est ici qu'il se
 * connecte pour garder ce qu'il a fait.
 */
export const loginGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.refresh().pipe(
    map((open) => (open && !session.account()?.is_trial ? router.createUrlTree([JOBS_PATH]) : true)),
  );
};

/** Montre la page d'accueil au visiteur sans session, et mène les autres à leurs offres. */
export const homeGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  if (session.account()) {
    return router.createUrlTree([JOBS_PATH]);
  }
  return session.refresh().pipe(map((open) => (open ? router.createUrlTree([JOBS_PATH]) : true)));
};

/**
 * Renvoie aux offres qui n'est pas administrateur. Placée sous sessionGuard, donc le compte est déjà lu.
 * C'est l'API qui refuse (403) ; ceci évite seulement un écran d'erreurs.
 */
export const adminGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.account()?.is_admin ? true : router.createUrlTree([JOBS_PATH]);
};
