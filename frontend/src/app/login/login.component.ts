import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { catchError, of } from 'rxjs';

import { apiErrorMessage } from '../core/api-error';
import { ConfigService } from '../core/config.service';
import { JOBS_PATH } from '../core/paths';
import { SessionService } from '../core/session.service';
import { GoogleButtonComponent } from './google-button.component';

@Component({
  selector: 'app-login',
  imports: [FormsModule, RouterLink, Button, InputText, Message, GoogleButtonComponent],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  // undefined : en cours de lecture ; null : le serveur n'a pas répondu
  protected readonly config = toSignal(inject(ConfigService).getConfig().pipe(catchError(() => of(null))));
  protected readonly password = signal('');
  protected readonly pending = signal(false);
  protected readonly error = signal('');
  /** Vrai pour qui a commencé sans compte : en se connectant, il garde ce qu'il a fait. */
  protected readonly trial = this.session.account()?.is_trial ?? false;

  protected googleFailed(): void {
    this.error.set("Le bouton de connexion Google n'a pas pu être chargé. Rechargez la page.");
  }

  protected submitPassword(): void {
    if (this.password()) {
      this.open(this.password());
    }
  }

  protected open(credential: string): void {
    this.pending.set(true);
    this.error.set('');
    this.session.open(credential).subscribe({
      next: () => void this.router.navigate([JOBS_PATH]),
      error: (error: unknown) => {
        this.pending.set(false);
        this.error.set(this.refusalMessage(error));
      },
    });
  }

  private refusalMessage(error: unknown): string {
    // L'API répond « Authentification requise » à une preuve refusée : on dit plutôt laquelle
    if (error instanceof HttpErrorResponse && error.status === 401) {
      return this.config()?.login_mode === 'password'
        ? 'Mot de passe incorrect.'
        : "Google n'a pas confirmé votre identité. Réessayez.";
    }
    return apiErrorMessage(error);
  }
}
