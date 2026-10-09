// Pose le thème avant le premier affichage, sans attendre Angular : sinon le mauvais thème apparaît un instant.
// Le thème est sombre tant que l'utilisateur n'a pas choisi le clair, quel que soit le réglage de son système.
// Même règle que ThemeService (core/theme.service.ts), à garder accordée.
// Les pages légales chargent aussi ce script : « app-light » leur dit de passer au thème clair.
(function () {
  var stored = null;
  try {
    stored = localStorage.getItem('theme');
  } catch (error) {
    // Stockage refusé par le navigateur : le thème reste sombre
  }
  var dark = stored !== 'light';
  document.documentElement.classList.toggle('app-dark', dark);
  document.documentElement.classList.toggle('app-light', !dark);
  // Couleur de la barre du navigateur mobile : celle du fond de la page
  var bar = document.querySelector('meta[name="theme-color"]');
  if (bar) {
    bar.setAttribute('content', dark ? '#0a0b0d' : '#f5f4ef');
  }
})();
