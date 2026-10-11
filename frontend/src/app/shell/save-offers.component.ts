import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { Message } from 'primeng/message';
import { catchError, of } from 'rxjs';

import { apiErrorMessage } from '../core/api-error';
import { ConfigService } from '../core/config.service';
import { JOBS_PATH, LOGIN_PATH } from '../core/paths';
import { SessionService } from '../core/session.service';
import { GoogleButtonComponent } from '../login/google-button.component';

/**
 * Encart montré à qui a cherché sans compte : ses offres ne sont reconnues que par son navigateur, et se
 * connecter les garde. C'est l'API qui fait passer le contenu de l'essai au compte, à l'ouverture de la session.
 */
@Component({
  selector: 'app-save-offers',
  imports: [RouterLink, Message, GoogleButtonComponent],
  templateUrl: './save-offers.component.html',
  styleUrl: './save-offers.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SaveOffersComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  protected readonly loginPath = `/${LOGIN_PATH}`;
  protected readonly account = this.session.account;
  // undefined : en cours de lecture ; null : le serveur n'a pas répondu, et l'écran de connexion le dira
  protected readonly config = toSignal(inject(ConfigService).getConfig().pipe(catchError(() => of(null))));
  protected readonly pending = signal(false);
  protected readonly error = signal('');

  protected open(credential: string): void {
    this.pending.set(true);
    this.error.set('');
    this.session.open(credential).subscribe({
      // Les offres sont celles du compte désormais : l'écran qui les montre les relit
      next: () => void this.router.navigate([JOBS_PATH]),
      error: (error: unknown) => {
        this.pending.set(false);
        const unproven = error instanceof HttpErrorResponse && error.status === 401;
        this.error.set(unproven ? "Google n'a pas confirmé votre identité. Réessayez." : apiErrorMessage(error));
      },
    });
  }

  protected googleFailed(): void {
    this.error.set("Le bouton de connexion Google n'a pas pu être chargé. Rechargez la page.");
  }
}
