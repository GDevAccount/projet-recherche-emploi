import { ChangeDetectionStrategy, Component, ElementRef, signal, viewChildren } from '@angular/core';

/** Écrans montrés par la démonstration, dans l'ordre des onglets. */
const VIEWS = [
  {
    id: 'search',
    label: 'La recherche en direct',
    summary: 'Chaque annonce passe sous vos yeux, retenue ou écartée, pendant la minute que dure une recherche.',
  },
  {
    id: 'rejections',
    label: 'Les rejets expliqués',
    summary: 'Rien ne disparaît en silence : chaque page écartée garde son motif, et se remet dans vos offres.',
  },
  {
    id: 'profile',
    label: 'Votre profil',
    summary: 'Vos postes recherchés sont tirés de votre CV. Vous les corrigez, ou en ajoutez à la main.',
  },
] as const;

type ViewId = (typeof VIEWS)[number]['id'];

/**
 * Démonstration de la page d'accueil : trois écrans de l'application, redessinés avec des données inventées.
 * Seuls les onglets répondent ; les écrans sont inertes.
 */
@Component({
  selector: 'app-product-demo',
  templateUrl: './product-demo.component.html',
  styleUrl: './product-demo.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductDemoComponent {
  protected readonly views = VIEWS;
  protected readonly current = signal<ViewId>('search');

  private readonly tabs = viewChildren<ElementRef<HTMLButtonElement>>('tab');

  /** Flèches, Début et Fin : le clavier attendu d'une liste d'onglets. */
  protected move(event: KeyboardEvent, index: number): void {
    const last = VIEWS.length - 1;
    const target = {
      ArrowRight: index === last ? 0 : index + 1,
      ArrowLeft: index === 0 ? last : index - 1,
      Home: 0,
      End: last,
    }[event.key];
    if (target === undefined) {
      return;
    }
    event.preventDefault();
    this.current.set(VIEWS[target].id);
    this.tabs()[target]?.nativeElement.focus();
  }
}
