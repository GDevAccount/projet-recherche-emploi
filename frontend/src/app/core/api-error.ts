import { HttpErrorResponse } from '@angular/common/http';

const UNREACHABLE = 'Le serveur ne répond pas. Réessayez dans un instant.';

/** Message à afficher pour une erreur de l'API, qui les rédige en français dans « detail ». */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const detail: unknown = error.error?.detail;
    if (typeof detail === 'string' && detail) {
      return detail;
    }
  }
  return UNREACHABLE;
}
