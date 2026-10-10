import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterNextRender,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

import { Account } from '../core/api.models';

const STORAGE_KEY = 'tour';
const SEEN = 'seen';

/** Écrans de la visite, dans l'ordre. Le dessin est le tracé d'une icône, sur une grille de 24. */
const SLIDES = [
  {
    title: 'Tamis lit les annonces à votre place',
    icon: 'M3 5h18l-7 8v6l-4-2v-4L3 5Z',
    lines: [
      "Un agent parcourt les sites d'emploi, lit chaque annonce et la compare à votre CV. Il ne garde que celles qui correspondent à ce que vous cherchez.",
      'Voici comment il fonctionne, en quatre étapes.',
    ],
  },
  {
    title: '1. Dites-lui qui vous êtes',
    icon: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0',
    lines: [
      'Dans Profil, déposez votre CV en PDF. Vos coordonnées en sont retirées avant toute comparaison.',
      'Décrivez ensuite un ou plusieurs postes recherchés : le métier et ses spécialités, le contrat, le lieu.',
    ],
  },
  {
    title: '2. Lancez une recherche',
    icon: 'M8 5v14l11-7L8 5Z',
    lines: [
      'Elle prend environ une minute. Vous voyez chaque annonce passer, retenue ou écartée.',
      'Relancez-la quelques jours plus tard : seules les nouvelles annonces sont lues.',
    ],
  },
  {
    title: '3. Suivez vos candidatures',
    icon: 'M4 6h16M4 12h10M4 18h6m5-3 2 2 4-4',
    lines: [
      'Les annonces retenues arrivent dans Offres, avec la raison pour laquelle elles vous correspondent.',
      'Indiquez où vous en êtes pour chacune : candidature envoyée, entretien obtenu, refus.',
    ],
  },
  {
    title: '4. Corrigez-le quand il se trompe',
    icon: 'M4 12a8 8 0 0 1 14-5l2-2v6h-6l2-2a5 5 0 1 0 1 6',
    lines: [
      "Une bonne annonce écartée ? Dans Rejets, « C'était une bonne offre » la remet dans vos offres.",
      'Une offre sans intérêt ? Supprimez-la en disant pourquoi. Chaque correction aide à améliorer le tri.',
    ],
  },
] as const;

/** Rang de l'écran qui parle de la recherche : c'est là que le quota de l'utilisateur est rappelé. */
const SEARCH_SLIDE = 2;

/** Dit si la visite a déjà été vue sur ce navigateur. Vrai aussi quand le navigateur refuse de le dire. */
export function tourWasSeen(window: Window | null): boolean {
  try {
    return window?.localStorage.getItem(STORAGE_KEY) === SEEN;
  } catch {
    // Stockage refusé : mieux vaut ne pas l'imposer à chaque visite
    return true;
  }
}

/**
 * Visite guidée de l'application, en quelques écrans : elle s'ouvre d'elle-même pour un nouvel arrivant, et
 * depuis le pied de page ensuite. Le cadre qui l'affiche décide quand ; elle retient seulement qu'elle a été vue.
 */
@Component({
  selector: 'app-welcome-tour',
  templateUrl: './welcome-tour.component.html',
  styleUrl: './welcome-tour.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(document:keydown.escape)': 'close()',
    '(document:keydown.arrowRight)': 'next()',
    '(document:keydown.arrowLeft)': 'previous()',
  },
})
export class WelcomeTourComponent {
  readonly account = input.required<Account>();
  /** Émis à la fermeture ; vrai quand l'utilisateur a demandé à compléter son profil. */
  readonly closed = output<boolean>();

  private readonly window = inject(DOCUMENT).defaultView;
  private readonly panel = viewChild.required<ElementRef<HTMLElement>>('panel');

  protected readonly slides = SLIDES;
  protected readonly index = signal(0);
  protected readonly slide = computed(() => SLIDES[this.index()]);
  protected readonly first = computed(() => this.index() === 0);
  protected readonly last = computed(() => this.index() === SLIDES.length - 1);
  /** Rappel du quota sur l'écran de la recherche ; vide pour le propriétaire, qui n'en a pas. */
  protected readonly quota = computed(() => {
    const account = this.account();
    if (this.index() !== SEARCH_SLIDE || account.remaining_searches === null) {
      return '';
    }
    if (account.is_trial) {
      return 'Votre essai comprend une seule recherche.';
    }
    const count = account.max_searches_per_day;
    return `Vous disposez de ${count} ${count > 1 ? 'recherches' : 'recherche'} par jour.`;
  });

  constructor() {
    // Le clavier et les lecteurs d'écran arrivent dans la fenêtre, pas derrière elle
    afterNextRender(() => this.panel().nativeElement.focus());
  }

  protected next(): void {
    this.index.update((index) => Math.min(index + 1, SLIDES.length - 1));
  }

  protected previous(): void {
    this.index.update((index) => Math.max(index - 1, 0));
  }

  protected goTo(index: number): void {
    this.index.set(index);
  }

  protected close(toProfile = false): void {
    try {
      this.window?.localStorage.setItem(STORAGE_KEY, SEEN);
    } catch {
      // Navigation privée : la visite reviendra à la prochaine
    }
    this.closed.emit(toProfile);
  }
}
