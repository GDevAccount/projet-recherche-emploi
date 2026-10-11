import { Routes } from '@angular/router';

import { adminGuard, authGuard, homeGuard, loginGuard } from './core/auth.guard';
import {
  ACCOUNT_PATH,
  JOBS_PATH,
  LOGIN_PATH,
  PROFILE_PATH,
  REJECTED_PATH,
  TRACKING_PATH,
} from './core/paths';
import { LoginComponent } from './login/login.component';

const titled = (section: string) => `${section} · JobGrep`;

export const routes: Routes = [
  // Routes publiques : la page d'accueil et l'écran de connexion. Tout le reste demande une session
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./home/home.component').then((module) => module.HomeComponent),
    canActivate: [homeGuard],
    title: "JobGrep · Les offres d'emploi qui correspondent à votre CV",
  },
  { path: LOGIN_PATH, component: LoginComponent, canActivate: [loginGuard], title: titled('Connexion') },
  {
    path: '',
    // Chargés à la demande : l'écran de connexion n'a pas à télécharger les écrans de données
    loadComponent: () => import('./shell/shell.component').then((module) => module.ShellComponent),
    // Aucun écran de données n'est monté sans session. C'est l'API qui protège ; ceci évite seulement un écran vide
    canActivate: [authGuard],
    children: [
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
  // Adresse inconnue : l'accueil, dont la garde mène à ses offres qui a une session
  { path: '**', redirectTo: '' },
];
