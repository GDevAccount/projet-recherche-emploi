import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  AssistantConversation,
  AssistantFeedback,
  AssistantProgress,
  AssistantReply,
} from './api.models';
import { FETCH } from './search-run.service';
import { readServerSentEvents } from './sse';

const UNREACHABLE = 'Le serveur ne répond pas. Réessayez dans un instant.';
const INTERRUPTED =
  "La réponse s'est interrompue. Rouvrez l'assistant : elle a pu être enregistrée.";

/** Assistant : il répond aux questions sur l'application, à partir des textes du site. */
@Injectable({ providedIn: 'root' })
export class AssistantService {
  private readonly http = inject(HttpClient);
  private readonly fetch = inject(FETCH);
  private readonly url = `${environment.apiUrl}/assistant`;

  /** Conversation en cours de l'appelant, et ce qu'il peut encore demander aujourd'hui. */
  getConversation(): Observable<AssistantConversation> {
    return this.http.get<AssistantConversation>(this.url);
  }

  /**
   * Pose une question et suit la réponse à mesure qu'elle s'écrit : `onProgress` reçoit chaque étape, la promesse
   * rend la réponse enregistrée. Un refus de l'API, ou une panne, la rejette avec le message à afficher.
   * Le flux se lit avec `fetch` : `HttpClient` ne rend une réponse qu'une fois entière.
   */
  async ask(
    question: string,
    newConversation: boolean,
    onProgress: (event: AssistantProgress) => void,
  ): Promise<AssistantReply> {
    let response: Response;
    try {
      response = await this.fetch(`${this.url}/questions/stream`, {
        method: 'POST',
        // Le cookie de session suit, y compris si le front est un jour hébergé ailleurs
        credentials: 'include',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, new_conversation: newConversation }),
      });
    } catch {
      throw new Error(UNREACHABLE);
    }
    if (!response.ok || !response.body) {
      throw new Error(await detailOf(response));
    }

    let reply: AssistantReply | undefined;
    let failure = '';
    try {
      await readServerSentEvents(response.body, (name, payload) => {
        if (name === 'progress') {
          onProgress(payload as AssistantProgress);
        } else if (name === 'result') {
          reply = payload as AssistantReply;
        } else if (name === 'error') {
          failure = readDetail(payload) ?? UNREACHABLE;
        }
      });
    } catch {
      // La connexion a été coupée : la réponse a pu être écrite et enregistrée sans nous
      throw new Error(INTERRUPTED);
    }
    if (!reply) {
      throw new Error(failure || INTERRUPTED);
    }
    return reply;
  }

  /** Note une réponse, utile ou non ; `null` retire la note. */
  setFeedback(messageId: number, feedback: AssistantFeedback | null): Observable<void> {
    return this.http.put<void>(`${this.url}/messages/${messageId}/feedback`, { feedback });
  }
}

function readDetail(payload: unknown): string | null {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  return typeof detail === 'string' && detail ? detail : null;
}

/** Message d'un refus de l'API, qui les rédige en français dans « detail ». */
async function detailOf(response: Response): Promise<string> {
  try {
    return readDetail(await response.json()) ?? UNREACHABLE;
  } catch {
    return UNREACHABLE;
  }
}
