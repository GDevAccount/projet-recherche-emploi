import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { SearchYield } from '../core/api.models';
import { CountPipe, UsdPipe } from '../core/format.pipe';

/**
 * Ce que rapporte chaque texte envoyé au moteur de recherche : chaque appel est payé, qu'il ramène du neuf
 * ou non. Les nombres et les coûts viennent de l'API, le moins rentable en premier.
 */
@Component({
  selector: 'app-yield-card',
  imports: [CountPipe, UsdPipe],
  templateUrl: './yield-card.component.html',
  styleUrl: './yield-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class YieldCardComponent {
  readonly searches = input.required<SearchYield[]>();

  /** Les largeurs sont relatives au texte qui a rendu le plus de pages. */
  protected readonly rows = computed(() => {
    const searches = this.searches();
    const largest = Math.max(1, ...searches.map((search) => search.found));
    return searches.map((search) => {
      const share = (count: number) => (search.found ? (count / search.found) * 100 : 0);
      return {
        search,
        width: (search.found / largest) * 100,
        parts: {
          kept: share(search.kept),
          rejected: share(search.rejected),
          known: share(search.known),
          repeated: share(search.repeated),
        },
      };
    });
  });
}
