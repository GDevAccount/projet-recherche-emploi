import { Routes } from '@angular/router';

import { authGuard, loginGuard } from './core/auth.guard';
import { JOBS_PATH, LOGIN_PATH, PROFILE_PATH, REJECTED_PATH } from './core/paths';
import { JobsComponent } from './jobs/jobs.component';
import { LoginComponent } from './login/login.component';
import { ProfileComponent } from './profile/profile.component';
import { RejectedComponent } from './rejected/rejected.component';
import { ShellComponent } from './shell/shell.component';

export const routes: Routes = [
  { path: LOGIN_PATH, component: LoginComponent, canActivate: [loginGuard] },
  {
    path: '',
    component: ShellComponent,
    // Aucun écran de données n'est monté sans session. C'est l'API qui protège ; ceci évite seulement un écran vide
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: JOBS_PATH },
      { path: JOBS_PATH, component: JobsComponent },
      { path: REJECTED_PATH, component: RejectedComponent },
      { path: PROFILE_PATH, component: ProfileComponent },
    ],
  },
  { path: '**', redirectTo: '' },
];
