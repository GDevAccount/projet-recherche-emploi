import { defineConfig } from '@playwright/test';

const PORT = 8765;
const ORIGIN = `http://127.0.0.1:${PORT}`;

/**
 * Tests de bout en bout : un vrai navigateur devant l'application entière, servie par tests/e2e_server.py
 * avec de faux Tavily et OpenAI. Le front doit être construit avant (npm run build).
 */
export default defineConfig({
  testDir: 'e2e',
  // Pas « .spec.ts » : ce sont les tests unitaires, lancés par ng test
  testMatch: '**/*.e2e.ts',
  // Les scénarios se suivent sur un seul serveur et une seule base
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env['CI'],
  reporter: 'list',
  use: {
    baseURL: ORIGIN,
    // Le Chrome de la machine, présent aussi sur les machines de GitHub : aucun navigateur à télécharger
    channel: 'chrome',
    locale: 'fr-FR',
    timezoneId: 'Europe/Paris',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `uv run --no-sync python tests/e2e_server.py ${PORT}`,
    cwd: '..',
    url: `${ORIGIN}/api/health`,
    // Un serveur resté ouvert garderait la base du passage précédent
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
