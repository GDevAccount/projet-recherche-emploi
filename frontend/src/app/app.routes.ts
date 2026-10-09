import { Routes } from '@angular/router';

import { adminGuard, authGuard, loginGuard } from './core/auth.guard';
import {
  ACCOUNT_PATH,
  JOBS_PATH,
  LOGIN_PATH,
  PROFILE_PATH,
  REJECTED_PATH,
  TRACKING_PATH,
} from './core/paths';
import { LoginComponent } from './login/login.component';

const titled = (section: string) => `${section} · Tamis`;

export const routes: Routes = [
  { path: LOGIN_PATH, component: LoginComponent, canActivate: [loginGuard], title: titled('Connexion') },
  {
    path: '',
    // Chargés à la demande : l'écran de connexion n'a pas à télécharger les écrans de données
    loadComponent: () => import('./shell/shell.component').then((module) => module.ShellComponent),
    // Aucun écran de données n'est monté sans session. C'est l'API qui protège ; ceci évite seulement un écran vide
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: JOBS_PATH },
      {
        path: JOBS_PATH,
        loadComponent: () => import('./jobs/jobs.component').then((module) => module.JobsComponent),
        title: titled('Offres'),
      },
      {
        path: REJECTED_PATH,
        loadComponent: () => import('./rejected/rejected.component').then((module) => module.RejectedComponent),
        title: titled('Rejets'),
      },
      {
        path: PROFILE_PATH,
        loadComponent: () => import('./profile/profile.component').then((module) => module.ProfileComponent),
        title: titled('Profil'),
      },
      {
        path: ACCOUNT_PATH,
        loadComponent: () => import('./account/account.component').then((module) => module.AccountComponent),
        title: titled('Compte'),
      },
      {
        path: TRACKING_PATH,
        loadComponent: () => import('./tracking/tracking.component').then((module) => module.TrackingComponent),
        canActivate: [adminGuard],
        title: titled('Suivi'),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
