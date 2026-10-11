import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { SearchQuery, SearchQueryCreate } from './api.models';

/** Postes recherchés : ce que l'agent cherche, et ce sur quoi il juge le métier, le contrat et le lieu d'une annonce. */
@Injectable({ providedIn: 'root' })
export class QueryService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/queries`;

  /**
   * Les postes recherchés tels que l'écran Profil les montre ; undefined tant qu'ils ne sont pas lus. Ils sont
   * ici parce que deux cartes les changent : celle des postes, et celle du CV, dont le dépôt peut les remplacer.
   */
  readonly queries = signal<SearchQuery[] | undefined>(undefined);

  list(): Observable<SearchQuery[]> {
    return this.http.get<SearchQuery[]>(this.url);
  }

  add(creation: SearchQueryCreate): Observable<SearchQuery> {
    return this.http.post<SearchQuery>(this.url, creation);
  }

  update(id: number, change: SearchQueryCreate): Observable<SearchQuery> {
    return this.http.put<SearchQuery>(`${this.url}/${id}`, change);
  }

  /** Compétences du référentiel qui contiennent ce texte, les plus proches d'abord. */
  suggestSkills(text: string): Observable<string[]> {
    return this.http.get<string[]>(`${environment.apiUrl}/skills`, { params: { q: text } });
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.url}/${id}`);
  }
}
