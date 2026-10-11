import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, ElementRef, afterNextRender, inject, input } from '@angular/core';

import { SearchRunService } from '../core/search-run.service';

/**
 * Encart de la première recherche : le profil est prêt, mais rien n'a encore été cherché. Sans lui, le dépôt du
 * CV se terminait sur un message de réussite, et le bouton de lancement passait inaperçu en haut de l'écran.
 */
@Component({
  selector: 'app-first-search',
  templateUrl: './first-search.component.html',
  styleUrl: './first-search.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FirstSearchComponent {
  protected readonly run = inject(SearchRunService);

  /** Vrai quand le profil vient d'être complété sous les yeux de l'utilisateur : l'encart se montre à lui. */
  readonly reveal = input(false);

  constructor() {
    const host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    const window = inject(DOCUMENT).defaultView;
    afterNextRender(() => {
      if (this.reveal()) {
        const reduced = window?.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        // Le CV vient d'être déposé plus bas dans la page : l'étape suivante ne doit pas rester hors de l'écran
        host.scrollIntoView?.({ behavior: reduced ? 'auto' : 'smooth', block: 'center' });
      }
    });
  }
}
