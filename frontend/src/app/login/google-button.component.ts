import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, input, output, viewChild } from '@angular/core';

import { GoogleIdentityService } from '../core/google-identity.service';

/**
 * Bouton « Continuer avec Google », à nos couleurs. Il rend le jeton d'identité obtenu : c'est à l'appelant
 * d'ouvrir la session avec lui.
 */
@Component({
  selector: 'app-google-button',
  templateUrl: './google-button.component.html',
  styleUrl: './google-button.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GoogleButtonComponent {
  private readonly googleIdentity = inject(GoogleIdentityService);

  readonly clientId = input.required<string>();
  /** Le jeton d'identité que Google vient de donner. */
  readonly credential = output<string>();
  /** Le script de Google n'a pas pu être chargé : le bouton ne répondra pas. */
  readonly failed = output<void>();

  private readonly frame = viewChild.required<ElementRef<HTMLElement>>('googleButton');

  constructor() {
    effect(() => {
      this.googleIdentity
        .renderButton(this.frame().nativeElement, this.clientId(), (idToken) => this.credential.emit(idToken))
        .catch(() => this.failed.emit());
    });
  }
}
