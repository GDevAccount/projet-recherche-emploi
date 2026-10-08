// Objets renvoyés par l'API (schemas.py côté Python)

export type LoginMode = 'google' | 'password';

export interface AppConfig {
  /** null : l'instance n'est pas protégée, et l'API refuse tout */
  login_mode: LoginMode | null;
  google_client_id: string | null;
  contract_types: string[];
}

export interface Account {
  user_id: number;
  is_owner: boolean;
  /** Adresse, nom et photo du compte Google ; null avec le mot de passe de l'instance */
  email: string | null;
  name: string | null;
  picture: string | null;
  can_search: boolean;
  /** null pour le propriétaire, qui n'a pas de quota */
  remaining_searches: number | null;
  max_searches_per_day: number;
}

export interface CvStatus {
  /** Date UTC du CV en place ; null tant qu'aucun n'a été déposé */
  updated_at: string | null;
}

export interface SearchQuery {
  id: number;
  contract_type: string;
  query: string;
  /** Vide : toute la France */
  location: string;
  /** Télétravail complet, sans condition de lieu */
  remote: boolean;
  created_at: string;
}

export interface SearchQueryCreate {
  contract_type: string;
  query: string;
  location: string;
  remote: boolean;
}

export interface Job {
  id: number;
  url: string;
  title: string;
  content: string | null;
  score: number | null;
  /** Contrat lu sur l'annonce ; null si elle ne le dit pas */
  contract_type: string | null;
  /** Ville lue sur l'annonce, ou « Remote » ; null si elle ne le dit pas */
  work_location: string | null;
  query: string | null;
  match_reason: string | null;
  applied: boolean;
  applied_at: string | null;
  created_at: string;
}

export interface RejectedJob {
  url: string;
  title: string;
  contract_type: string | null;
  work_location: string | null;
  /** Recherche qui a trouvé la page */
  query: string | null;
  reject_reason: string | null;
  /** Motif principal du rejet, calculé par l'API : le premier critère en défaut */
  motive: string;
  /** Tous les critères en défaut, le principal en premier */
  failed_criteria: string[];
  created_at: string;
}

/** Étapes d'une recherche, dans l'ordre du graph. */
export type SearchStep = 'search' | 'dedupe' | 'evaluate' | 'save';

export interface SearchProgress {
  message: string;
  /** Étape qui signale cet avancement */
  step: SearchStep | null;
  done: number | null;
  total: number | null;
  /** Pages trouvées jusqu'ici, et celles qui restent à évaluer une fois les doublons écartés */
  found: number | null;
  new: number | null;
  /** Page qui vient d'être évaluée, et son verdict */
  title: string | null;
  kept: boolean | null;
}

export interface SearchSummary {
  found: number;
  new: number;
  kept: number;
  rejected: number;
  inserted: number;
}
