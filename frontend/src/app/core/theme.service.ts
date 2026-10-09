import { DOCUMENT } from '@angular/common';
import { Injectable, effect, inject, signal } from '@angular/core';

import { DARK_CLASS, LIGHT_CLASS } from './theme';

const STORAGE_KEY = 'theme';

/**
 * Thème clair ou sombre : celui du système à la première visite, puis le choix de l'utilisateur.
 * public/theme-init.js applique la même règle avant le démarrage d'Angular : changer l'une demande de changer l'autre.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly window = this.document.defaultView;

  private readonly _dark = signal(this.initialChoice());
  readonly dark = this._dark.asReadonly();

  constructor() {
    effect(() => {
      const classes = this.document.documentElement.classList;
      classes.toggle(DARK_CLASS, this._dark());
      classes.toggle(LIGHT_CLASS, !this._dark());
    });
  }

  toggle(): void {
    this._dark.update((dark) => !dark);
    try {
      this.window?.localStorage.setItem(STORAGE_KEY, this._dark() ? 'dark' : 'light');
    } catch {
      // Navigation privée : le choix vaut pour cette visite seulement
    }
  }

  private initialChoice(): boolean {
    let stored: string | null = null;
    try {
      stored = this.window?.localStorage.getItem(STORAGE_KEY) ?? null;
    } catch {
      // Stockage refusé par le navigateur : on suit le système
    }
    if (stored) {
      return stored === 'dark';
    }
    return this.window?.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  }
}
