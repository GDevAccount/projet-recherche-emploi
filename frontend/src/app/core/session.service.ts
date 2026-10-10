import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, of, tap } from 'rxjs';

import { environment } from '../../environments/environment';
import { Account } from './api.models';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly http = inject(HttpClient);

  private readonly _account = signal<Account | null>(null);
  /** Compte de la session ouverte, ou null sans session. */
  readonly account = this._account.asReadonly();

  /** Relit le compte de la session en cours. Renvoie false si aucune session n'est ouverte. */
  refresh(): Observable<boolean> {
    return this.http.get<Account>(`${environment.apiUrl}/me`).pipe(
      tap((account) => this._account.set(account)),
      map(() => true),
      catchError(() => {
        this._account.set(null);
        return of(false);
      }),
    );
  }

  /** Échange une preuve d'identité (jeton Google ou mot de passe) contre le cookie de session. */
  open(credential: string): Observable<Account> {
    // La preuve ne sert qu'ici : elle n'est gardée nulle part, le cookie HttpOnly prend le relais
    const headers = { Authorization: `Bearer ${credential}` };
    return this.http
      .post<Account>(`${environment.apiUrl}/session`, null, { headers })
      .pipe(tap((account) => this._account.set(account)));
  }

  /** Ouvre un compte d'essai, sans preuve d'identité : le cookie posé par l'API est sa seule identité. */
  openTrial(): Observable<Account> {
    return this.http
      .post<Account>(`${environment.apiUrl}/session/trial`, null)
      .pipe(tap((account) => this._account.set(account)));
  }

  close(): Observable<void> {
    return this.http.delete<void>(`${environment.apiUrl}/session`).pipe(tap(() => this.forget()));
  }

  /** Efface le compte et tout ce qu'il contient. L'API ferme la session : rien n'est récupérable ensuite. */
  deleteAccount(): Observable<void> {
    return this.http.delete<void>(`${environment.apiUrl}/me`).pipe(tap(() => this.forget()));
  }

  /** Oublie le compte sans appeler l'API : la session a expiré côté serveur. */
  forget(): void {
    this._account.set(null);
  }
}
