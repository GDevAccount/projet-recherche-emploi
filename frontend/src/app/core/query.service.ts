import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { SearchQuery, SearchQueryCreate } from './api.models';

/** Postes recherchés : ce que l'agent cherche, et ce sur quoi il juge le métier, le contrat et le lieu d'une annonce. */
@Injectable({ providedIn: 'root' })
export class QueryService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/queries`;

  list(): Observable<SearchQuery[]> {
    return this.http.get<SearchQuery[]>(this.url);
  }

  add(creation: SearchQueryCreate): Observable<SearchQuery> {
    return this.http.post<SearchQuery>(this.url, creation);
  }

  /** Compétences du référentiel qui contiennent ce texte, les plus proches d'abord. */
  suggestSkills(text: string): Observable<string[]> {
    return this.http.get<string[]>(`${environment.apiUrl}/skills`, { params: { q: text } });
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.url}/${id}`);
  }
}
