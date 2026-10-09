// Pose le thème avant le premier affichage, sans attendre Angular : sinon une page claire apparaît un instant
// à qui a choisi le thème sombre. Même règle que ThemeService (core/theme.service.ts), à garder accordée.
// Les pages légales chargent aussi ce script : « app-light » leur dit de ne pas suivre un système sombre.
(function () {
  var stored = null;
  try {
    stored = localStorage.getItem('theme');
  } catch (error) {
    // Stockage refusé par le navigateur : on suit le système
  }
  var dark = stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle('app-dark', dark);
  document.documentElement.classList.toggle('app-light', !dark);
})();
