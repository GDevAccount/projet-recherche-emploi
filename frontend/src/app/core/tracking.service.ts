import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  AlertTest,
  BudgetOverview,
  HealthOverview,
  JourneyOverview,
  PageEvaluation,
  SearchRun,
  SearchStats,
  UsageOverview,
} from './api.models';

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

  /** Recherches échouées et erreurs de l'API sur tous les comptes, pendant les derniers jours. */
  getHealth(days: number): Observable<HealthOverview> {
    return this.http.get<HealthOverview>(`${environment.apiUrl}/admin/health`, { params: { days } });
  }

  /** Dépense du mois en cours sur tous les comptes, sa projection et le budget de l'instance. */
  getBudget(): Observable<BudgetOverview> {
    return this.http.get<BudgetOverview>(`${environment.apiUrl}/admin/budget`);
  }

  /** Où en est chaque compte, et combien d'invités ont franchi chaque étape du parcours. */
  getJourneys(): Observable<JourneyOverview> {
    return this.http.get<JourneyOverview>(`${environment.apiUrl}/admin/journeys`);
  }

  /** Envoie une alerte d'essai, et dit si elle est partie. */
  sendTestAlert(): Observable<AlertTest> {
    return this.http.post<AlertTest>(`${environment.apiUrl}/admin/alerts/test`, null);
  }
}
