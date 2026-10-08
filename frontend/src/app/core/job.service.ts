import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { Job } from './api.models';

@Injectable({ providedIn: 'root' })
export class JobService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/jobs`;

  /** Offres retenues, de la plus récente à la plus ancienne. */
  list(): Observable<Job[]> {
    return this.http.get<Job[]>(this.url);
  }

  setApplied(id: number, applied: boolean): Observable<void> {
    return this.http.patch<void>(`${this.url}/${id}`, { applied });
  }

  /** Supprime une offre : elle ne reviendra pas aux recherches suivantes. */
  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.url}/${id}`);
  }
}
