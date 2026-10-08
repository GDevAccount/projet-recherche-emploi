import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Job, RejectedJob } from './api.models';

@Injectable({ providedIn: 'root' })
export class JobService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/jobs`;

  /** Offres retenues, de la plus récente à la plus ancienne. */
  list(): Observable<Job[]> {
    return this.http.get<Job[]>(this.url);
  }

  /** Marque l'offre comme postulée ou non. L'API la renvoie mise à jour, avec sa date de candidature. */
  setApplied(id: number, applied: boolean): Observable<Job> {
    return this.http.patch<Job>(`${this.url}/${id}`, { applied });
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
