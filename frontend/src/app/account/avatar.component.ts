import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { Account } from '../core/api.models';

/**
 * Vignette d'un compte : sa photo Google, à défaut son initiale, à défaut une silhouette.
 * Décorative : c'est l'élément qui la contient qui dit à qui elle est.
 */
@Component({
  selector: 'app-avatar',
  templateUrl: './avatar.component.html',
  styleUrl: './avatar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AvatarComponent {
  readonly account = input.required<Account>();

  // Photo retirée ou refusée par Google : on retombe sur l'initiale
  protected readonly failed = signal(false);
  protected readonly picture = computed(() => (this.failed() ? null : this.account().picture));
  protected readonly initial = computed(() =>
    (this.account().name ?? this.account().email ?? '').trim().charAt(0).toUpperCase(),
  );
}
