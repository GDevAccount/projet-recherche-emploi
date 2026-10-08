import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Button } from 'primeng/button';
import { Tab, TabList, TabPanel, TabPanels, Tabs } from 'primeng/tabs';

import { LOGIN_PATH } from '../core/paths';
import { SessionService } from '../core/session.service';

/** Cadre de l'application une fois connecté : en-tête, barre latérale et onglets. Les écrans y prendront place. */
@Component({
  selector: 'app-shell',
  imports: [Button, Tabs, TabList, Tab, TabPanels, TabPanel],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShellComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  protected readonly account = this.session.account;
  protected readonly closing = signal(false);

  protected logout(): void {
    this.closing.set(true);
    // Même si l'appel échoue, on quitte l'écran : le rechargement dira si la session tient encore
    const leave = () => void this.router.navigate([LOGIN_PATH]);
    this.session.close().subscribe({ next: leave, error: leave });
  }
}
