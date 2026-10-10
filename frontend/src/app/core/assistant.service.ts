import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { AssistantConversation, AssistantReply } from './api.models';

/** Assistant : il répond aux questions sur l'application, à partir des textes du site. */
@Injectable({ providedIn: 'root' })
export class AssistantService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/assistant`;

  /** Derniers échanges de l'appelant, et ce qu'il peut encore demander aujourd'hui. */
  getConversation(): Observable<AssistantConversation> {
    return this.http.get<AssistantConversation>(this.url);
  }

  /** Pose une question. C'est l'API qui la refuse si elle est vide, trop longue, ou une fois le quota atteint. */
  ask(question: string): Observable<AssistantReply> {
    return this.http.post<AssistantReply>(`${this.url}/questions`, { question });
  }
}
