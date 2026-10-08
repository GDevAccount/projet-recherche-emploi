import { Injectable, InjectionToken, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { environment } from '../../environments/environment';
import { SearchProgress, SearchStep, SearchSummary } from './api.models';
import { LOGIN_PATH } from './paths';
import { SessionService } from './session.service';

/** Appel réseau du navigateur. Un jeton, pour que les tests y branchent un faux flux. */
export const FETCH = new InjectionToken<typeof fetch>('fetch', {
  providedIn: 'root',
  factory: () => (input, init) => fetch(input, init),
});

/** Étapes du graph de recherche, dans l'ordre où l'API les annonce. */
export const STEPS: readonly SearchStep[] = ['search', 'dedupe', 'evaluate', 'save'];

/**
 * idle : rien en cours ; running : flux ouvert ; done : bilan reçu ; failed : refusée ou en échec ;
 * lost : la connexion a été coupée, mais la recherche va au bout sur le serveur.
 */
export type RunState = 'idle' | 'running' | 'done' | 'failed' | 'lost';

export interface LogLine {
  /** Secondes écoulées depuis le lancement */
  at: number;
  step: SearchStep | null;
  text: string;
  /** Verdict d'une page évaluée ; null pour les autres lignes */
  kept: boolean | null;
}

const GENERIC_FAILURE = 'La recherche a échoué.';
const UNREACHABLE = 'Le serveur ne répond pas. Réessayez dans un instant.';

/**
 * Une recherche lancée depuis le front, suivie en direct.
 * L'API la diffuse en Server-Sent Events sur un POST, ce que EventSource ne sait pas lire : le flux est lu avec fetch.
 */
@Injectable({ providedIn: 'root' })
export class SearchRunService {
  private readonly fetch = inject(FETCH);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  private readonly _state = signal<RunState>('idle');
  private readonly _events = signal<SearchProgress[]>([]);
  private readonly _log = signal<LogLine[]>([]);
  private readonly _summary = signal<SearchSummary | null>(null);
  private readonly _error = signal('');
  private readonly _elapsed = signal(0);
  private readonly _completed = signal(0);
  private startedAt = 0;
  private timer?: ReturnType<typeof setInterval>;

  readonly state = this._state.asReadonly();
  readonly log = this._log.asReadonly();
  readonly summary = this._summary.asReadonly();
  readonly error = this._error.asReadonly();
  /** Secondes écoulées depuis le lancement */
  readonly elapsed = this._elapsed.asReadonly();
  /** Nombre de recherches terminées depuis l'ouverture de la page : les écrans s'y abonnent pour se recharger */
  readonly completed = this._completed.asReadonly();

  /** Étape en cours : la dernière annoncée par l'API. */
  readonly step = computed(() => this.last((event) => event.step !== null)?.step ?? null);
  /** Dernier avancement annoncé par chaque étape. */
  readonly latest = computed(() => {
    const latest: Partial<Record<SearchStep, SearchProgress>> = {};
    for (const event of this._events()) {
      if (event.step) {
        latest[event.step] = event;
      }
    }
    return latest;
  });
  readonly found = computed(() => this.last((event) => event.found !== null)?.found ?? null);
  readonly fresh = computed(() => this.last((event) => event.new !== null)?.new ?? null);
  /** Verdicts reçus page par page pendant l'évaluation. */
  readonly keptSoFar = computed(() => this._events().filter((event) => event.kept === true).length);
  readonly rejectedSoFar = computed(() => this._events().filter((event) => event.kept === false).length);

  /** Lance une recherche et la suit jusqu'à son bilan. Sans effet si une recherche est déjà suivie. */
  async launch(): Promise<void> {
    if (this._state() === 'running') {
      return;
    }
    this.start();
    try {
      const response = await this.fetch(`${environment.apiUrl}/searches`, {
        method: 'POST',
        // Le cookie de session suit, y compris si le front est un jour hébergé ailleurs
        credentials: 'include',
        headers: { Accept: 'text/event-stream' },
      });
      if (!response.ok || !response.body) {
        await this.refuse(response);
        return;
      }
      await this.read(response.body);
    } catch {
      // Avant le premier événement, rien n'est parti ; après, la recherche continue sans nous
      this.finish(this._events().length ? 'lost' : 'failed', this._events().length ? '' : UNREACHABLE);
    }
  }

  /** Referme le suivi d'une recherche terminée. */
  dismiss(): void {
    if (this._state() !== 'running') {
      this._state.set('idle');
    }
  }

  private start(): void {
    this._state.set('running');
    this._events.set([]);
    this._log.set([]);
    this._summary.set(null);
    this._error.set('');
    this._elapsed.set(0);
    this.startedAt = Date.now();
    this.timer = setInterval(() => this._elapsed.set(this.seconds()), 1000);
  }

  private finish(state: RunState, error = ''): void {
    clearInterval(this.timer);
    this._elapsed.set(this.seconds());
    this._error.set(error);
    this._state.set(state);
    if (state !== 'failed' || this._events().length) {
      // Le quota et les listes ont pu changer, même si la recherche n'a pas été au bout
      this.session.refresh().subscribe();
      this._completed.update((count) => count + 1);
    }
  }

  /** Refus avant tout flux : quota atteint, profil incomplet, session expirée. L'API dit pourquoi. */
  private async refuse(response: Response): Promise<void> {
    if (response.status === 401) {
      clearInterval(this.timer);
      this._state.set('idle');
      this.session.forget();
      void this.router.navigate([LOGIN_PATH]);
      return;
    }
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = undefined;
    }
    this.finish('failed', typeof detail === 'string' && detail ? detail : UNREACHABLE);
  }

  private async read(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      // Un événement se termine par une ligne vide ; le dernier morceau peut être incomplet
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() ?? '';
      for (const block of blocks) {
        this.handle(block);
      }
      if (done) {
        break;
      }
    }
    if (this._state() === 'running') {
      // Flux clos sans bilan ni erreur : le serveur a redémarré, ou un relais a coupé
      this.finish('lost');
    }
  }

  private handle(block: string): void {
    let name = '';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) {
        name = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        data += line.slice(5).trim();
      }
    }
    if (!name || !data) {
      return;
    }
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      // Un événement illisible ne doit pas faire perdre le suivi des suivants
      return;
    }
    if (name === 'progress') {
      this.progress(payload as SearchProgress);
    } else if (name === 'result') {
      this._summary.set(payload as SearchSummary);
      this.finish('done');
    } else if (name === 'error') {
      const detail = (payload as { detail?: unknown }).detail;
      this.finish('failed', typeof detail === 'string' && detail ? detail : GENERIC_FAILURE);
    }
  }

  private progress(event: SearchProgress): void {
    this._events.update((events) => [...events, event]);
    // Une page évaluée s'affiche par son titre et son verdict ; le décompte, lui, est dans la jauge
    const text = event.title ?? event.message;
    this._log.update((log) => [...log, { at: this.seconds(), step: event.step, text, kept: event.kept }]);
  }

  private last(matches: (event: SearchProgress) => boolean): SearchProgress | undefined {
    return this._events().filter(matches).at(-1);
  }

  private seconds(): number {
    return Math.floor((Date.now() - this.startedAt) / 1000);
  }
}
