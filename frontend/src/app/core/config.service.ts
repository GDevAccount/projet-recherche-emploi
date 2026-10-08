import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, shareReplay } from 'rxjs';

import { environment } from '../../environments/environment';
import { AppConfig } from './api.models';

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private readonly http = inject(HttpClient);

  // Lue une fois : elle ne change qu'au redémarrage du serveur
  private readonly config$ = this.http
    .get<AppConfig>(`${environment.apiUrl}/config`)
    .pipe(shareReplay({ bufferSize: 1, refCount: false }));

  getConfig(): Observable<AppConfig> {
    return this.config$;
  }
}
