import { expect, Page, test } from '@playwright/test';

// Le même que dans tests/e2e_server.py
const PASSWORD = 'mot-de-passe-e2e';
const QUERY = 'dresseur de licornes';
// Le CV versionné à la racine sert de PDF valide, comme dans les tests Python
const CV_PATH = '../cv.pdf';

// Un seul parcours, dans l'ordre : chaque étape part de l'état laissé par la précédente
test.describe.configure({ mode: 'serial' });

let page: Page;
/** Ressources refusées par la politique de contenu : elles n'apparaissent que dans la console du navigateur. */
const blocked: string[] = [];

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  page.on('console', (message) => {
    if (message.text().includes('Content Security Policy')) {
      blocked.push(message.text());
    }
  });
});

test.afterAll(async () => {
  await page.close();
});

test("sans JavaScript, l'accueil décrit l'application et renvoie aux pages légales", async ({ browser }) => {
  // Ce que lisent les robots de Google pour valider l'écran de connexion
  const context = await browser.newContext({ javaScriptEnabled: false });
  const plain = await context.newPage();

  await plain.goto('/');
  await expect(plain.getByRole('heading', { name: 'Tamis' })).toBeVisible();
  await expect(plain.getByText("Tamis cherche des offres d'emploi")).toBeVisible();

  await plain.getByRole('link', { name: 'Règles de confidentialité' }).click();
  await expect(plain.getByRole('heading', { level: 1, name: 'Règles de confidentialité' })).toBeVisible();
  await context.close();
});

test('sans session, tout mène à la connexion et les données sont refusées', async () => {
  await page.goto('/offres');

  await expect(page).toHaveURL(/\/connexion$/);
  await expect(page.getByRole('heading', { name: 'Connexion' })).toBeVisible();
  expect((await page.request.get('/api/jobs')).status()).toBe(401);
});

test('un mot de passe faux est refusé, le bon ouvre la session', async () => {
  await page.getByLabel('Mot de passe').fill('mauvais');
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page.locator('.p-message-error')).toBeVisible();
  await expect(page).toHaveURL(/\/connexion$/);

  await page.getByLabel('Mot de passe').fill(PASSWORD);
  await page.getByRole('button', { name: 'Se connecter' }).click();

  await expect(page).toHaveURL(/\/offres$/);
  // Pas de CV : la recherche n'est pas encore proposée
  await expect(page.getByText('Deux choses avant la première recherche')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Lancer une recherche' })).toHaveCount(0);
});

test('le profil se complète : un CV, puis un poste recherché', async () => {
  await page.getByRole('link', { name: 'Compléter mon profil' }).click();
  await expect(page).toHaveURL(/\/profil$/);

  await page.locator('input[type=file]').setInputFiles(CV_PATH);
  await page.getByRole('button', { name: 'Enregistrer ce CV' }).click();
  await expect(page.getByText('CV enregistré.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Votre CV est en place' })).toBeVisible();

  await page.getByLabel('Métier et spécialités').fill(QUERY);
  await page.getByRole('button', { name: 'Ajouter ce poste' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: QUERY })).toBeVisible();

  await expect(page.getByRole('button', { name: 'Lancer une recherche' })).toBeEnabled();
});

test('une recherche se suit en direct et ajoute des offres', async () => {
  await page.getByRole('button', { name: 'Lancer une recherche' }).click();

  const panel = page.locator('app-run-panel');
  await expect(panel.getByRole('status')).toHaveText('Recherche terminée', { timeout: 30_000 });
  // Les quatre étapes du graph sont passées
  await expect(panel.locator('.pipeline li[data-status=done]')).toHaveCount(4);
  await expect(panel.getByText(/nouvelles offres vous attendent/)).toBeVisible();

  await panel.getByRole('link', { name: 'Voir mes offres' }).click();
  await expect(page).toHaveURL(/\/offres$/);
  await expect(page.locator('.column.todo app-job-card').filter({ hasText: QUERY })).toBeVisible();
});

test('une offre marquée postulée change de colonne et le reste après rechargement', async () => {
  await page.locator('.column.todo app-job-card').filter({ hasText: QUERY }).getByRole('button', { name: "J'ai postulé" }).click();

  const applied = page.locator('.column.applied app-job-card').filter({ hasText: QUERY });
  await expect(applied).toContainText('Postulé le');

  await page.reload();
  await expect(applied).toContainText('Postulé le');
  await expect(page.locator('.column.todo app-job-card').filter({ hasText: QUERY })).toHaveCount(0);
});

test('une offre supprimée ne revient pas, même après une nouvelle recherche', async () => {
  const cards = page.locator('.column.todo app-job-card');
  const before = await cards.count();
  expect(before).toBeGreaterThan(0);
  const title = (await cards.first().getByRole('heading').innerText()).trim();

  await cards.first().getByRole('button', { name: /^Supprimer l'offre/ }).click();
  await cards.first().getByRole('button', { name: 'Supprimer', exact: true }).click();
  await expect(cards).toHaveCount(before - 1);

  await page.getByRole('button', { name: 'Lancer une recherche' }).click();
  const panel = page.locator('app-run-panel');
  await expect(panel.getByRole('status')).toHaveText('Recherche terminée', { timeout: 30_000 });
  // Tout est déjà connu : rien à évaluer, donc rien de payé une seconde fois
  await expect(panel.getByText(/0 pas\s+encore évaluée/)).toBeVisible();
  await panel.getByRole('button', { name: 'Fermer le suivi' }).click();

  await expect(cards).toHaveCount(before - 1);
  await expect(page.getByRole('heading', { name: title, exact: true })).toHaveCount(0);
});

test('les pages écartées sont listées avec leur motif', async () => {
  await page.getByRole('link', { name: 'Rejets', exact: true }).click();
  await expect(page).toHaveURL(/\/rejets$/);

  await expect(page.getByText(/pages écartées/).first()).toBeVisible();
  const rejected = page.locator('ol.pages > li').filter({ hasText: QUERY });
  await expect(rejected.locator('.motive')).not.toBeEmpty();
  await expect(rejected).toContainText('hors profil');
});

test('le thème choisi est gardé après rechargement', async () => {
  await page.getByRole('button', { name: 'Passer au thème sombre' }).click();
  await expect(page.locator('html')).toHaveClass(/app-dark/);

  await page.reload();
  await expect(page.locator('html')).toHaveClass(/app-dark/);
  await expect(page.getByRole('button', { name: 'Passer au thème clair' })).toBeVisible();
});

test('la déconnexion ferme la session', async () => {
  await page.getByRole('button', { name: 'Se déconnecter' }).click();
  await expect(page).toHaveURL(/\/connexion$/);

  await page.goto('/offres');
  await expect(page).toHaveURL(/\/connexion$/);
  expect((await page.request.get('/api/jobs')).status()).toBe(401);
});

test("la politique de contenu n'a rien refusé pendant le parcours", () => {
  expect(blocked).toEqual([]);
});
