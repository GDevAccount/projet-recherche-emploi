import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { LOGIN_PATH } from '../core/paths';
import { ThemeService } from '../core/theme.service';
import { SECTIONS, scrollToSection } from './sections';

/** Barre de navigation de la page d'accueil : les sections de la page, le thème, et l'entrée vers la connexion. */
@Component({
  selector: 'app-home-nav',
  imports: [RouterLink],
  templateUrl: './home-nav.component.html',
  styleUrl: './home-nav.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeNavComponent {
  private readonly document = inject(DOCUMENT);
  protected readonly theme = inject(ThemeService);

  protected readonly loginPath = `/${LOGIN_PATH}`;
  protected readonly sections = SECTIONS;

  /** Menu des sections, replié sur un petit écran. */
  protected readonly menuOpen = signal(false);

  protected goTo(event: Event, id: string): void {
    this.menuOpen.set(false);
    scrollToSection(this.document, event, id);
  }
}
