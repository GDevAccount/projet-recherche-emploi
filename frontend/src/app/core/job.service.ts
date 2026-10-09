import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Job, JobStatus, RejectedJob } from './api.models';

@Injectable({ providedIn: 'root' })
export class JobService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/jobs`;

  /** Offres retenues, de la plus récente à la plus ancienne. */
  list(): Observable<Job[]> {
    return this.http.get<Job[]>(this.url);
  }

  /** Fait passer la candidature à cet état. L'API renvoie l'offre mise à jour, avec ses dates. */
  setStatus(id: number, status: JobStatus): Observable<Job> {
    return this.http.patch<Job>(`${this.url}/${id}`, { status });
  }

  /** Pages écartées, avec le motif que l'API en a tiré. */
  listRejected(): Observable<RejectedJob[]> {
    return this.http.get<RejectedJob[]>(`${environment.apiUrl}/rejected-jobs`);
  }

  /** Supprime une offre : elle ne reviendra pas aux recherches suivantes. */
  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.url}/${id}`);
  }
}
