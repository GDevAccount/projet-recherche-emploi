import { expect, Page, test } from '@playwright/test';

// Le même que dans tests/e2e_server.py
const PASSWORD = 'mot-de-passe-e2e';
const QUERY = 'dresseur de licornes';
// Le PDF valide des tests Python
const CV_PATH = '../tests/fixtures/cv.pdf';

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

test('un entretien se met en avant, et un refus se range sans disparaître', async () => {
  const applied = page.locator('.column.applied app-job-card').filter({ hasText: QUERY });
  await applied.getByRole('button', { name: 'Entretien obtenu' }).click();

  const interview = page.locator('.interviews app-job-card').filter({ hasText: QUERY });
  await expect(interview).toContainText('Entretien depuis le');
  // Les entretiens passent avant les colonnes
  await expect(page.locator('.tracking > *').first()).toHaveClass(/interviews/);

  await interview.getByRole('button', { name: /^Retirer l'offre/ }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'Que faire de cette offre ?' })).toBeVisible();
  await dialog.getByRole('button', { name: /L'employeur a refusé ma candidature/ }).click();
  await expect(dialog).toBeHidden();

  // Rangée, repliée, et toujours là après rechargement
  await expect(page.locator('.interviews')).toHaveCount(0);
  await page.reload();
  const refused = page.locator('details.refused');
  await expect(refused.locator('summary')).toContainText('Candidatures refusées');
  await expect(refused.locator('app-job-card')).toBeHidden();
  await refused.locator('summary').click();
  await expect(refused.locator('app-job-card').filter({ hasText: QUERY })).toContainText('Refusée le');
});

test('une offre supprimée ne revient pas, même après une nouvelle recherche', async () => {
  const cards = page.locator('.column.todo app-job-card');
  const before = await cards.count();
  expect(before).toBeGreaterThan(0);
  const title = (await cards.first().getByRole('heading').innerText()).trim();

  await cards.first().getByRole('button', { name: /^Retirer l'offre/ }).click();
  const dialog = page.getByRole('dialog');
  // Une offre à laquelle on n'a pas postulé ne peut pas avoir été refusée : la fenêtre ne propose que de la supprimer
  await expect(dialog.getByRole('button', { name: /L'employeur a refusé/ })).toHaveCount(0);
  await dialog.getByRole('button', { name: /Supprimer cette annonce/ }).click();
  // La fenêtre demande pourquoi, avec les motifs que l'API propose
  await expect(dialog.getByRole('heading', { name: 'Pourquoi la supprimer ?' })).toBeVisible();
  await dialog.getByRole('button', { name: "Ce n'est pas mon métier" }).click();
  await expect(dialog).toBeHidden();
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

  // Une page écartée à tort se remet dans les offres, où elle attend d'être traitée
  const title = (await rejected.first().getByRole('heading').innerText()).trim();
  await rejected.first().getByRole('button', { name: "C'était une bonne offre" }).click();
  await expect(rejected.first().locator('.restored')).toContainText('De retour dans vos offres');
  await rejected.first().locator('.restored').getByRole('link', { name: 'offres' }).click();
  await expect(page.locator('.column.todo').getByRole('heading', { name: title, exact: true })).toBeVisible();
});

test('le suivi montre le bilan des recherches et le détail de leurs pages', async () => {
  // Le mot de passe de l'instance désigne le propriétaire : la rubrique lui est ouverte
  await page.getByRole('link', { name: 'Suivi', exact: true }).click();
  await expect(page).toHaveURL(/\/suivi$/);

  await expect(page.locator('app-tracking .tile').filter({ hasText: 'recherches' })).toBeVisible();
  await expect(page.getByText(/pages évaluées/).first()).toBeVisible();
  const runs = page.locator('app-run-list .row');
  await expect(runs.first()).toContainText('Terminée');

  // La dernière recherche n'a retrouvé que des pages connues : c'est la première qui a évalué les siennes
  await runs.last().click();
  const pages = page.locator('app-run-list ol.pages > li');
  await expect(pages.filter({ hasText: 'Retenue' }).first()).toBeVisible();
  await expect(pages.filter({ hasText: 'Écartée' }).first()).toContainText('en défaut : compétences');

  // Les candidatures déclarées plus haut se retrouvent dans le devenir des offres retenues
  const outcomes = page.locator('app-outcomes-card');
  await expect(outcomes.locator('header')).toContainText('mènent à une candidature');
  await expect(outcomes.locator('.outcomes li').filter({ hasText: QUERY })).toContainText('sur');

  // Deux recherches ont envoyé les mêmes textes : chacun compte deux appels, dont le second n'a rien ramené
  const searches = page.locator('app-yield-card .searches li');
  await expect(searches.first()).toContainText('2 appels');
  await expect(searches.filter({ hasText: QUERY }).first()).toContainText('par offre');

  // Une offre supprimée pour son métier, une page écartée remise : les deux corrections sont comptées
  const corrections = page.locator('app-corrections-card');
  await expect(corrections.locator('tbody tr')).toHaveCount(1);
  await expect(corrections.locator('.reasons')).toContainText("Ce n'est pas mon métier");

  await expect(page.locator('app-usage-card tbody th').first()).toHaveText('Propriétaire');
});

test('le thème est sombre au départ, et le choix du clair est gardé après rechargement', async () => {
  // Le navigateur de test annonce un système clair : le thème sombre ne vient pas de lui
  await expect(page.locator('html')).toHaveClass(/app-dark/);
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#0a0b0d');

  await page.getByRole('button', { name: 'Passer au thème clair' }).click();
  await expect(page.locator('html')).toHaveClass(/app-light/);

  await page.reload();
  await expect(page.locator('html')).toHaveClass(/app-light/);
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#f5f4ef');
  await expect(page.getByRole('button', { name: 'Passer au thème sombre' })).toBeVisible();
});

test('les pages légales prennent le thème choisi dans le site, pas celui du système', async () => {
  // Le site est en thème clair, le système annoncé sombre : seul le choix fait dans le site explique le fond clair
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.getByRole('link', { name: 'Règles de confidentialité' }).last().click();
  await expect(page.getByRole('heading', { level: 1, name: 'Règles de confidentialité' })).toBeVisible();
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(245, 244, 239)');

  // Retour au thème sombre, sous un système clair
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/offres');
  await page.getByRole('button', { name: 'Passer au thème sombre' }).click();
  await page.goto('/conditions');
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(10, 11, 13)');

  await page.goto('/offres');
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
