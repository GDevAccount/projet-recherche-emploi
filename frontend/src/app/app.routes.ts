import { Routes } from '@angular/router';

import { authGuard, loginGuard } from './core/auth.guard';
import { JOBS_PATH, LOGIN_PATH, PROFILE_PATH, REJECTED_PATH } from './core/paths';
import { LoginComponent } from './login/login.component';
import { ProfileComponent } from './profile/profile.component';
import { ShellComponent } from './shell/shell.component';
import { UpcomingComponent } from './shell/upcoming.component';

export const routes: Routes = [
  { path: LOGIN_PATH, component: LoginComponent, canActivate: [loginGuard] },
  {
    path: '',
    component: ShellComponent,
    // Aucun écran de données n'est monté sans session. C'est l'API qui protège ; ceci évite seulement un écran vide
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: JOBS_PATH },
      {
        path: JOBS_PATH,
        component: UpcomingComponent,
        data: {
          title: 'Vos offres retenues',
          text: 'Les annonces qui correspondent à votre profil, et le suivi de vos candidatures.',
        },
      },
      {
        path: REJECTED_PATH,
        component: UpcomingComponent,
        data: {
          title: 'Les pages écartées',
          text: 'Chaque annonce rejetée avec son motif, pour comprendre ce qui vous fait perdre des offres.',
        },
      },
      { path: PROFILE_PATH, component: ProfileComponent },
    ],
  },
  { path: '**', redirectTo: '' },
];
