import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';

import { AvatarComponent } from '../account/avatar.component';
import { AssistantComponent } from '../assistant/assistant.component';
import { ACCOUNT_PATH, LOGIN_PATH, PROFILE_PATH, SECTIONS } from '../core/paths';
import { SearchRunService } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { ThemeService } from '../core/theme.service';
import { RunPanelComponent } from '../run/run-panel.component';
import { WelcomeTourComponent, tourWasSeen } from './welcome-tour.component';

/** Cadre de l'application une fois connecté : en-tête, navigation, bandeau d'état. Les écrans s'y affichent. */
@Component({
  selector: 'app-shell',
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    AssistantComponent,
    AvatarComponent,
    RunPanelComponent,
    WelcomeTourComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShellComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  protected readonly theme = inject(ThemeService);
  protected readonly run = inject(SearchRunService);

  protected readonly profilePath = PROFILE_PATH;
  protected readonly accountPath = ACCOUNT_PATH;
  protected readonly account = this.session.account;
  protected readonly sections = computed(() =>
    SECTIONS.filter((section) => !section.admin || this.account()?.is_admin),
  );
  protected readonly closing = signal(false);
  /** Vrai tant que la visite guidée est affichée. */
  protected readonly touring = signal(false);

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );
  /** Vrai sur la page Profil : le bandeau n'a pas à y renvoyer. */
  protected readonly onProfile = computed(() => this.url().split(/[?#]/)[0] === `/${PROFILE_PATH}`);

  constructor() {
    const window = inject(DOCUMENT).defaultView;
    let offered = false;
    // À la première visite d'un compte qui n'a encore rien réglé : après, elle ne s'ouvre qu'à la demande
    effect(() => {
      const account = this.account();
      if (account && !offered) {
        offered = true;
        untracked(() => this.touring.set(!account.can_search && !tourWasSeen(window)));
      }
    });
  }

  protected openTour(): void {
    this.touring.set(true);
  }

  protected closeTour(toProfile: boolean): void {
    this.touring.set(false);
    if (toProfile) {
      void this.router.navigate([PROFILE_PATH]);
    }
  }

  protected logout(): void {
    this.closing.set(true);
    // Même si l'appel échoue, on quitte l'écran : le rechargement dira si la session tient encore
    const leave = () => void this.router.navigate([LOGIN_PATH]);
    this.session.close().subscribe({ next: leave, error: leave });
  }
}
