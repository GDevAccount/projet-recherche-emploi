import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { providePrimeNG } from 'primeng/config';

import { primeuiLicense } from '../environments/license';
import { routes } from './app.routes';
import { apiInterceptor } from './core/api.interceptor';
import { AppPreset, DARK_CLASS } from './core/theme';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch(), withInterceptors([apiInterceptor])),
    providePrimeNG({
      theme: { preset: AppPreset, options: { darkModeSelector: `.${DARK_CLASS}` } },
      license: primeuiLicense,
    }),
  ],
};
