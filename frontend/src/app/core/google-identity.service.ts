import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';

const SCRIPT_URL = 'https://accounts.google.com/gsi/client';

interface GoogleCredentialResponse {
  credential: string;
}

interface GoogleIdentityApi {
  initialize(options: { client_id: string; callback: (response: GoogleCredentialResponse) => void }): void;
  renderButton(parent: HTMLElement, options: Record<string, string>): void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleIdentityApi } };
  }
}

/** Bouton « Se connecter avec Google » (Google Identity Services). Isolé ici pour que les tests y branchent un faux. */
@Injectable({ providedIn: 'root' })
export class GoogleIdentityService {
  private readonly document = inject(DOCUMENT);
  private script?: Promise<GoogleIdentityApi>;

  /**
   * Affiche le bouton dans l'élément donné, sur toute sa largeur, et appelle onCredential avec le jeton
   * d'identité obtenu. Google n'accepte qu'une largeur de 200 à 400 pixels.
   */
  async renderButton(parent: HTMLElement, clientId: string, onCredential: (idToken: string) => void): Promise<void> {
    const api = await this.load();
    api.initialize({ client_id: clientId, callback: (response) => onCredential(response.credential) });
    api.renderButton(parent, {
      theme: 'outline',
      size: 'large',
      shape: 'rectangular',
      text: 'continue_with',
      width: String(Math.min(400, Math.max(200, parent.clientWidth))),
      locale: 'fr',
    });
  }

  private load(): Promise<GoogleIdentityApi> {
    this.script ??= new Promise((resolve, reject) => {
      const script = this.document.createElement('script');
      script.src = SCRIPT_URL;
      script.async = true;
      script.onload = () => {
        const api = this.document.defaultView?.google?.accounts.id;
        if (api) {
          resolve(api);
        } else {
          reject(new Error('Google Identity Services indisponible'));
        }
      };
      script.onerror = () => {
        // Permet un nouvel essai au prochain affichage
        this.script = undefined;
        reject(new Error('Chargement de Google Identity Services impossible'));
      };
      this.document.head.appendChild(script);
    });
    return this.script;
  }
}
