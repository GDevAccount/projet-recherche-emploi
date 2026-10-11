// Pose le thème avant le premier affichage, sans attendre Angular : sinon le mauvais thème apparaît un instant.
// Le thème est celui du système tant que l'utilisateur n'en a pas choisi un dans le site ; sombre si le système n'en dit rien.
// Même règle que ThemeService (core/theme.service.ts), à garder accordée.
// Les pages légales chargent aussi ce script : « app-light » et « app-dark » leur disent le thème choisi dans le site.
(function () {
  var stored = null;
  try {
    stored = localStorage.getItem('theme');
  } catch (error) {
    // Stockage refusé par le navigateur : le thème suit le système
  }
  var dark = stored === 'dark';
  if (stored !== 'dark' && stored !== 'light') {
    dark = !(window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches);
  }
  document.documentElement.classList.toggle('app-dark', dark);
  document.documentElement.classList.toggle('app-light', !dark);
  // Couleur de la barre du navigateur mobile : celle du fond de la page
  var bar = document.querySelector('meta[name="theme-color"]');
  if (bar) {
    bar.setAttribute('content', dark ? '#0a0b0d' : '#f5f4ef');
  }
})();
