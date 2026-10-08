import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Button } from 'primeng/button';
import { InputText } from 'primeng/inputtext';
import { Message } from 'primeng/message';
import { catchError, of } from 'rxjs';

import { apiErrorMessage } from '../core/api-error';
import { ConfigService } from '../core/config.service';
import { GoogleIdentityService } from '../core/google-identity.service';
import { SessionService } from '../core/session.service';

@Component({
  selector: 'app-login',
  imports: [FormsModule, Button, InputText, Message],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  private readonly session = inject(SessionService);
  private readonly googleIdentity = inject(GoogleIdentityService);
  private readonly router = inject(Router);

  // undefined : en cours de lecture ; null : le serveur n'a pas répondu
  protected readonly config = toSignal(inject(ConfigService).getConfig().pipe(catchError(() => of(null))));
  protected readonly password = signal('');
  protected readonly pending = signal(false);
  protected readonly error = signal('');

  private readonly googleButton = viewChild<ElementRef<HTMLElement>>('googleButton');

  constructor() {
    effect(() => {
      const parent = this.googleButton()?.nativeElement;
      const clientId = this.config()?.google_client_id;
      if (parent && clientId) {
        this.googleIdentity
          .renderButton(parent, clientId, (idToken) => this.open(idToken))
          .catch(() => this.error.set("Le bouton de connexion Google n'a pas pu être chargé. Rechargez la page."));
      }
    });
  }

  protected submitPassword(): void {
    if (this.password()) {
      this.open(this.password());
    }
  }

  private open(credential: string): void {
    this.pending.set(true);
    this.error.set('');
    this.session.open(credential).subscribe({
      next: () => void this.router.navigate(['/']),
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
