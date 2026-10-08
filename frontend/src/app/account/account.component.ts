import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Button } from 'primeng/button';
import { Message } from 'primeng/message';

import { apiErrorMessage } from '../core/api-error';
import { LOGIN_PATH } from '../core/paths';
import { SearchRunService } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { AvatarComponent } from './avatar.component';

/** Rubrique Compte : qui est connecté, ce que l'application garde de lui, et la suppression du compte. */
@Component({
  selector: 'app-account',
  imports: [Button, Message, AvatarComponent],
  templateUrl: './account.component.html',
  styleUrl: './account.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AccountComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  protected readonly run = inject(SearchRunService);

  protected readonly account = this.session.account;
  protected readonly closing = signal(false);
  // Rien n'est récupérable après : la suppression demande une confirmation
  protected readonly confirming = signal(false);
  protected readonly deleting = signal(false);
  protected readonly error = signal('');

  protected logout(): void {
    this.closing.set(true);
    // Même si l'appel échoue, on quitte l'écran : le rechargement dira si la session tient encore
    this.session.close().subscribe({ next: () => this.leave(), error: () => this.leave() });
  }

  protected cancel(): void {
    this.confirming.set(false);
    this.error.set('');
  }

  protected deleteAccount(): void {
    this.deleting.set(true);
    this.error.set('');
    this.session.deleteAccount().subscribe({
      next: () => this.leave(),
      error: (error: unknown) => {
        this.deleting.set(false);
        this.error.set(apiErrorMessage(error));
      },
    });
  }

  private leave(): void {
    void this.router.navigate([LOGIN_PATH]);
  }
}
