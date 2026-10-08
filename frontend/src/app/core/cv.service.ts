import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { CvStatus } from './api.models';

@Injectable({ providedIn: 'root' })
export class CvService {
  private readonly http = inject(HttpClient);

  getStatus(): Observable<CvStatus> {
    return this.http.get<CvStatus>(`${environment.apiUrl}/cv`);
  }

  /** Remplace le CV en place. C'est l'API qui valide le fichier (PDF lisible, avec du texte). */
  save(file: File): Observable<CvStatus> {
    const form = new FormData();
    form.append('file', file);
    return this.http.put<CvStatus>(`${environment.apiUrl}/cv`, form);
  }
}
