import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { LOGIN_PATH, PROFILE_PATH, SECTIONS } from '../core/paths';
import { SearchRunService } from '../core/search-run.service';
import { SessionService } from '../core/session.service';
import { ThemeService } from '../core/theme.service';
import { RunPanelComponent } from '../run/run-panel.component';

/** Cadre de l'application une fois connecté : en-tête, navigation, bandeau d'état. Les écrans s'y affichent. */
@Component({
  selector: 'app-shell',
  imports: [RouterLink, RouterLinkActive, RouterOutlet, RunPanelComponent],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShellComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  protected readonly theme = inject(ThemeService);
  protected readonly run = inject(SearchRunService);

  protected readonly sections = SECTIONS;
  protected readonly profilePath = PROFILE_PATH;
  protected readonly account = this.session.account;
  protected readonly closing = signal(false);

  protected logout(): void {
    this.closing.set(true);
    // Même si l'appel échoue, on quitte l'écran : le rechargement dira si la session tient encore
    const leave = () => void this.router.navigate([LOGIN_PATH]);
    this.session.close().subscribe({ next: leave, error: leave });
  }
}
