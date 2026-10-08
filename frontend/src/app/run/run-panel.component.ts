import { ChangeDetectionStrategy, Component, ElementRef, computed, effect, inject, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';

import { SearchStep } from '../core/api.models';
import { JOBS_PATH, REJECTED_PATH } from '../core/paths';
import { STEPS, SearchRunService } from '../core/search-run.service';

type Status = 'pending' | 'active' | 'done';

/** Ce que chaque étape fait, et le nœud du graph LangGraph qui l'exécute. */
const STEP_LABELS: Record<SearchStep, { label: string; node: string; what: string }> = {
  search: { label: 'Recherche', node: 'searchJobs', what: 'Tavily interroge les sites d’emploi' },
  dedupe: { label: 'Dédoublonnage', node: 'FilterDuplicates', what: 'Les pages déjà vues sont écartées' },
  evaluate: { label: 'Évaluation', node: 'FilterJobs', what: 'Le modèle lit chaque page avec votre CV' },
  save: { label: 'Enregistrement', node: 'InsertJobs', what: 'Offres et rejets rejoignent la base' },
};

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

/**
 * Suivi d'une recherche en direct : les quatre étapes du graph, les compteurs et le journal des événements.
 * Tout ce qui s'affiche vient des événements de l'API ; le panneau ne déduit rien d'un texte.
 */
@Component({
  selector: 'app-run-panel',
  imports: [RouterLink],
  templateUrl: './run-panel.component.html',
  styleUrl: './run-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RunPanelComponent {
  protected readonly run = inject(SearchRunService);
  protected readonly jobsPath = `/${JOBS_PATH}`;
  protected readonly rejectedPath = `/${REJECTED_PATH}`;
  protected readonly clock = clock;

  private readonly console = viewChild<ElementRef<HTMLElement>>('console');

  protected readonly steps = computed(() => {
    const current = this.run.step();
    const reached = current ? STEPS.indexOf(current) : -1;
    const finished = this.run.state() === 'done';
    const latest = this.run.latest();
    return STEPS.map((step, index) => {
      let status: Status = 'pending';
      if (finished || index < reached) {
        status = 'done';
      } else if (index === reached) {
        status = this.run.state() === 'running' ? 'active' : 'done';
      }
      return { step, ...STEP_LABELS[step], status, detail: this.detail(step, latest[step] ?? null) };
    });
  });

  /** Avancement de l'évaluation, de 0 à 100 ; null tant qu'elle n'a pas commencé. */
  protected readonly evaluation = computed(() => {
    const event = this.run.latest().evaluate;
    if (!event?.total) {
      return null;
    }
    return { done: event.done ?? 0, total: event.total, percent: Math.round(((event.done ?? 0) / event.total) * 100) };
  });

  constructor() {
    effect(() => {
      // Le journal suit la dernière ligne, comme un terminal
      this.run.log();
      const console = this.console()?.nativeElement;
      if (console) {
        queueMicrotask(() => (console.scrollTop = console.scrollHeight));
      }
    });
  }

  private detail(step: SearchStep, event: { done: number | null; total: number | null; found: number | null; new: number | null } | null): string {
    if (!event) {
      return '';
    }
    switch (step) {
      case 'search':
        // L'API annonce une requête avant de la lancer : « done » compte celles déjà revenues
        return event.total ? `requête ${Math.min((event.done ?? 0) + 1, event.total)} / ${event.total}` : '';
      case 'dedupe':
        return event.new !== null && event.found !== null ? `${event.new} nouvelles sur ${event.found}` : '';
      case 'evaluate':
        return event.total ? `${event.done ?? 0} / ${event.total} pages` : '';
      default:
        return '';
    }
  }
}
