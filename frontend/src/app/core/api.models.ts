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
