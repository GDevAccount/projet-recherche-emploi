export const LOGIN_PATH = 'connexion';
export const JOBS_PATH = 'offres';
export const REJECTED_PATH = 'rejets';
export const PROFILE_PATH = 'profil';
export const ACCOUNT_PATH = 'compte';
export const TRACKING_PATH = 'suivi';

/** Rubriques de la navigation, dans l'ordre. « admin » : montrée aux seuls administrateurs. */
export const SECTIONS = [
  { path: JOBS_PATH, label: 'Offres', admin: false },
  { path: REJECTED_PATH, label: 'Rejets', admin: false },
  { path: PROFILE_PATH, label: 'Profil', admin: false },
  { path: TRACKING_PATH, label: 'Suivi', admin: true },
];
