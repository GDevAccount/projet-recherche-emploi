import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { CvDeposit, CvProgress, CvStatus } from './api.models';
import { FETCH } from './search-run.service';
import { detailOf, readDetail, readServerSentEvents } from './sse';

const UNREACHABLE = 'Le serveur ne répond pas. Réessayez dans un instant.';
const INTERRUPTED = "L'envoi s'est interrompu. Rechargez la page : votre CV a pu être enregistré.";

@Injectable({ providedIn: 'root' })
export class CvService {
  private readonly http = inject(HttpClient);
  private readonly fetch = inject(FETCH);

  getStatus(): Observable<CvStatus> {
    return this.http.get<CvStatus>(`${environment.apiUrl}/cv`);
  }

  /**
   * Remplace le CV en place et suit son traitement : `onProgress` reçoit chaque étape, la promesse rend le
   * résultat, postes recherchés créés compris. C'est l'API qui valide le fichier (PDF lisible, avec du texte)
   * et qui décide si les postes sont tirés du CV ; `replaceQueries` lui dit de remplacer ceux en place.
   * Un refus la rejette avec le message à afficher. Le flux se lit avec `fetch` : `HttpClient` ne rend une
   * réponse qu'une fois entière.
   */
  async deposit(
    file: File,
    replaceQueries: boolean,
    onProgress: (event: CvProgress) => void,
  ): Promise<CvDeposit> {
    const form = new FormData();
    form.append('file', file);
    form.append('replace_queries', String(replaceQueries));
    let response: Response;
    try {
      response = await this.fetch(`${environment.apiUrl}/cv/stream`, {
        method: 'POST',
        // Le cookie de session suit, y compris si le front est un jour hébergé ailleurs
        credentials: 'include',
        headers: { Accept: 'text/event-stream' },
        body: form,
      });
    } catch {
      throw new Error(UNREACHABLE);
    }
    if (!response.ok || !response.body) {
      throw new Error(await detailOf(response, UNREACHABLE));
    }

    let deposit: CvDeposit | undefined;
    let failure = '';
    try {
      await readServerSentEvents(response.body, (name, payload) => {
        if (name === 'progress') {
          onProgress(payload as CvProgress);
        } else if (name === 'result') {
          deposit = payload as CvDeposit;
        } else if (name === 'error') {
          failure = readDetail(payload) ?? UNREACHABLE;
        }
      });
    } catch {
      // La connexion a été coupée : le traitement va au bout sur le serveur sans nous
      throw new Error(INTERRUPTED);
    }
    if (!deposit) {
      throw new Error(failure || INTERRUPTED);
    }
    return deposit;
  }
}
