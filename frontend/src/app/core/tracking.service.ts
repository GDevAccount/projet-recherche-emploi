import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { PageEvaluation, SearchRun, SearchStats, UsageOverview } from './api.models';

/** Suivi des recherches, réservé aux administrateurs : l'API répond 403 à tout autre compte. */
@Injectable({ providedIn: 'root' })
export class TrackingService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/searches`;

  /** Synthèse de toutes les recherches suivies de l'appelant. */
  getStats(): Observable<SearchStats> {
    return this.http.get<SearchStats>(`${this.url}/stats`);
  }

  /** Dernières recherches de l'appelant, la plus récente en premier. */
  listRuns(): Observable<SearchRun[]> {
    return this.http.get<SearchRun[]>(this.url);
  }

  /** Pages évaluées pendant une recherche, retenues ou non. */
  listEvaluations(runId: number): Observable<PageEvaluation[]> {
    return this.http.get<PageEvaluation[]>(`${this.url}/${runId}/evaluations`);
  }

  /** Consommation de chaque compte, sur les derniers jours ou, sans nombre, depuis le début. */
  getUsage(days: number | null): Observable<UsageOverview> {
    const params = days === null ? undefined : { days };
    return this.http.get<UsageOverview>(`${environment.apiUrl}/admin/usage`, { params });
  }
}
