import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ErrorHandler, Injectable, Injector, inject } from '@angular/core';
import { Router } from '@angular/router';

import { environment } from '../../environments/environment';
import { ClientErrorReport } from './api.models';
import { SessionService } from './session.service';

/** Signalements par chargement de page : une erreur qui se répète à chaque rendu n'apprend rien de plus. */
const MAX_REPORTS = 5;

// Ce que l'API accepte : des noms et des positions, rien qui puisse porter un contenu
const ERROR_TYPE = /^[A-Za-z_][A-Za-z0-9_.]*$/;
const ROUTE = /^\/[A-Za-z0-9/_-]*$/;
/** Premier fichier du front cité par la pile, avec sa ligne et sa colonne. */
const STACK_FRAME = /([A-Za-z0-9_.-]+\.js):(\d+):(\d+)/;

/**
 * Décrit une erreur sans rien dire de ce que la page affichait : son type, l'écran, et l'endroit du code.
 * Jamais son message, qui peut contenir une donnée de l'utilisateur.
 */
export function describeError(error: unknown, url: string): ClientErrorReport {
  const name = error instanceof Error ? error.name : '';
  const frame = error instanceof Error ? STACK_FRAME.exec(error.stack ?? '') : null;
  const route = url.split(/[?#]/)[0];
  return {
    error_type: ERROR_TYPE.test(name) ? name.slice(0, 80) : 'Error',
    route: ROUTE.test(route) ? route.slice(0, 120) : null,
    source: frame ? `${frame[1]}:${frame[2]}:${frame[3]}`.slice(0, 120) : null,
  };
}

/**
 * Erreurs que rien n'a rattrapées dans le navigateur : elles restent dans la console, et sont signalées à
 * l'API, qui est seule à pouvoir les montrer à qui exploite l'instance.
 */
@Injectable()
export class ReportingErrorHandler implements ErrorHandler {
  // Résolus à la première erreur : le routeur et le client HTTP dépendent eux-mêmes du gestionnaire d'erreurs
  private readonly injector = inject(Injector);
  private readonly reported = new Set<string>();

  handleError(error: unknown): void {
    console.error(error);
    try {
      this.report(error);
    } catch {
      // Signaler une erreur ne doit jamais en provoquer une autre
    }
  }

  private report(error: unknown): void {
    // Une réponse d'erreur de l'API est déjà connue du serveur
    if (error instanceof HttpErrorResponse || this.reported.size >= MAX_REPORTS) {
      return;
    }
    // Sans session, l'API refuserait le signalement
    if (!this.injector.get(SessionService).account()) {
      return;
    }
    const report = describeError(error, this.injector.get(Router).url);
    const key = `${report.error_type} ${report.route} ${report.source}`;
    if (this.reported.has(key)) {
      return;
    }
    this.reported.add(key);
    this.injector
      .get(HttpClient)
      .post(`${environment.apiUrl}/client-errors`, report)
      .subscribe({ error: () => undefined });
  }
}
