import { Routes } from '@angular/router';

import { authGuard, loginGuard } from './core/auth.guard';
import { LOGIN_PATH } from './core/paths';
import { LoginComponent } from './login/login.component';
import { ShellComponent } from './shell/shell.component';

export const routes: Routes = [
  { path: LOGIN_PATH, component: LoginComponent, canActivate: [loginGuard] },
  // Aucun écran de données n'est monté sans session. C'est l'API qui protège ; ceci évite seulement un écran vide
  { path: '', component: ShellComponent, canActivate: [authGuard], pathMatch: 'full' },
  { path: '**', redirectTo: '' },
];
