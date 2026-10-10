// Objets renvoyés par l'API (schemas.py côté Python)

export type LoginMode = 'google' | 'password';
/** « exhausted » : plus d'essai sans compte aujourd'hui, pour personne */
export type TrialStatus = 'available' | 'exhausted';

export interface AppConfig {
  /** null : l'instance n'est pas protégée, et l'API refuse tout */
  login_mode: LoginMode | null;
  google_client_id: string | null;
  /** Essai sans compte ; null si l'instance n'en propose pas */
  trial: TrialStatus | null;
  contract_types: string[];
  /** Motifs proposés à la suppression d'une offre, dans l'ordre où les présenter */
  delete_reasons: DeleteReasonOption[];
}

export interface DeleteReasonOption {
  code: string;
  label: string;
}

export interface Account {
  user_id: number;
  is_owner: boolean;
  /** Compte d'essai, ouvert sans connexion : une seule recherche, et ce navigateur pour seule identité */
  is_trial: boolean;
  /** Le propriétaire, ou une adresse d'ADMIN_EMAILS : la rubrique Suivi lui est ouverte */
  is_admin: boolean;
  /** Adresse, nom et photo du compte Google ; null avec le mot de passe de l'instance */
  email: string | null;
  name: string | null;
  picture: string | null;
  can_search: boolean;
  /** Une recherche de cet utilisateur tourne sur le serveur, lancée d'ici ou d'ailleurs */
  search_running: boolean;
  /** null pour le propriétaire, qui n'a pas de quota ; pour un compte d'essai, ce qu'il lui reste en tout */
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

/** État d'une candidature : à traiter, postulée, entretien obtenu, refusée par l'employeur. */
export type JobStatus = 'todo' | 'applied' | 'interview' | 'rejected';

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
  status: JobStatus;
  /** Date de chaque étape franchie par la candidature ; null tant qu'elle ne l'est pas */
  applied_at: string | null;
  interview_at: string | null;
  rejected_at: string | null;
  created_at: string;
  /** États que l'offre peut prendre maintenant : l'écran n'en propose pas d'autre */
  next_statuses: JobStatus[];
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

/** État d'un lancement ; null pour ceux d'avant le suivi, qui n'ont que leur date. */
export type SearchRunStatus = 'running' | 'done' | 'failed' | 'interrupted';

/** Bilan d'une recherche. Tout sauf la date peut manquer : étape non franchie, ou lancement d'avant le suivi. */
export interface SearchRun {
  id: number;
  created_at: string;
  finished_at: string | null;
  status: SearchRunStatus | null;
  /** Type de l'erreur d'une recherche échouée, sans son message */
  error: string | null;
  model: string | null;
  prompt_version: string | null;
  found_count: number | null;
  new_count: number | null;
  kept_count: number | null;
  rejected_count: number | null;
  inserted_count: number | null;
  duration_ms: number | null;
  search_ms: number | null;
  dedupe_ms: number | null;
  evaluate_ms: number | null;
  save_ms: number | null;
  search_calls: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cache_write_tokens: number | null;
  reasoning_tokens: number | null;
  /** Coûts en dollars, calculés par l'API aux tarifs actuels */
  search_cost_usd: number | null;
  model_cost_usd: number | null;
  cost_usd: number | null;
}

/** Une page évaluée pendant une recherche, retenue ou non. */
export interface PageEvaluation {
  id: number;
  url: string;
  title: string;
  query: string | null;
  score: number | null;
  kept: boolean;
  /** Faits lus sur la page par le modèle */
  page_kind: string | null;
  contract_type: string | null;
  work_city: string | null;
  work_country: string | null;
  work_mode: string | null;
  in_accepted_area: boolean | null;
  open_to_candidates_in_france: boolean | null;
  /** Avis du modèle, puis règles appliquées par le graph */
  matches_search: boolean | null;
  matches_skills: boolean | null;
  matches_level: boolean | null;
  matches_contract: boolean | null;
  matches_location: boolean | null;
  reason: string | null;
  page_chars: number | null;
  truncated: boolean | null;
  /** Faux quand seul l'extrait du moteur de recherche a été lu */
  full_page: boolean | null;
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  duration_ms: number | null;
  model_cost_usd: number | null;
}

/** Pages évaluées qui partagent un trait : même recherche, même site, même nature. */
export interface EvaluationGroup {
  label: string;
  evaluated: number;
  kept: number;
  not_an_offer: number;
  rejected_offers: number;
  input_tokens: number;
  output_tokens: number;
  model_cost_usd: number | null;
}

/** Synthèse de toutes les recherches suivies de l'appelant. */
export interface SearchStats {
  runs: number;
  unfinished_runs: number;
  found_count: number;
  new_count: number;
  kept_count: number;
  rejected_count: number;
  search_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  reasoning_tokens: number;
  search_cost_usd: number;
  model_cost_usd: number | null;
  cost_usd: number | null;
  cost_per_kept_usd: number | null;
  average_duration_ms: number | null;
  by_query: EvaluationGroup[];
  by_site: EvaluationGroup[];
  by_page_kind: EvaluationGroup[];
  by_text: EvaluationGroup[];
  /** Les dernières semaines, la plus ancienne en premier, celle en cours en dernier */
  weeks: WeekStats[];
  /** Devenir de toutes les offres retenues, puis par poste recherché, par site et par version du prompt */
  outcomes: OutcomeGroup;
  outcomes_by_query: OutcomeGroup[];
  outcomes_by_site: OutcomeGroup[];
  outcomes_by_prompt: OutcomeGroup[];
  /** null sans candidature née d'une recherche suivie */
  cost_per_application_usd: number | null;
  /** Rendement de chaque texte envoyé au moteur de recherche, le moins rentable en premier */
  by_search: SearchYield[];
  /** Corrections du tri par version du prompt, la plus récente en premier */
  corrections: CorrectionStats[];
  /** Motifs des suppressions d'offres, le plus fréquent en premier */
  delete_reasons: ReasonCount[];
}

/**
 * Ce que sont devenues des offres retenues par le tri. Elles se partagent entre entretiens, candidatures sans
 * entretien (applied - interviews), offres à traiter et offres supprimées sans candidature.
 */
export interface OutcomeGroup {
  label: string;
  kept: number;
  /** Candidatures envoyées, quelle que soit leur suite */
  applied: number;
  /** Parmi elles, celles que l'employeur a refusées */
  refused: number;
  interviews: number;
  pending: number;
  deleted: number;
  applied_rate: number | null;
  interview_rate: number | null;
}

/** Ce qu'un texte envoyé au moteur de recherche a rapporté, tous lancements réunis. */
export interface SearchYield {
  /** Phrase saisie par l'utilisateur */
  query: string;
  /** Texte réellement envoyé */
  search_text: string;
  /** Variante en anglais d'une recherche en télétravail complet */
  international: boolean;
  calls: number;
  /** Pages rendues, qui se partagent entre les quatre nombres suivants */
  found: number;
  /** Déjà rendues par un autre appel du même lancement */
  repeated: number;
  /** Déjà connues : offres ou rejets d'une recherche passée */
  known: number;
  /** Évaluées, puis écartées */
  rejected: number;
  kept: number;
  search_cost_usd: number;
  /** null sans offre retenue */
  cost_per_kept_usd: number | null;
}

/** Ce que l'utilisateur a corrigé du tri rendu avec une version du prompt. Les taux sont des planchers. */
export interface CorrectionStats {
  /** null : pages évaluées avant le suivi */
  prompt_version: string | null;
  evaluated: number;
  kept: number;
  rejected: number;
  /** Pages écartées remises dans les offres */
  restored: number;
  /** Offres supprimées en reprochant quelque chose au tri */
  wrongly_kept: number;
  /** Offres supprimées sans motif, ou qui n'intéressaient pas */
  other_deleted: number;
  restored_rate: number | null;
  wrongly_kept_rate: number | null;
}

export interface ReasonCount {
  label: string;
  count: number;
}

export type AccountPlan = 'free' | 'paid' | 'trial';

/** Ce qu'un compte a consommé et coûté. */
export interface AccountUsage {
  user_id: number;
  /** null pour le propriétaire et pour un compte supprimé */
  email: string | null;
  is_owner: boolean;
  deleted: boolean;
  plan: AccountPlan;
  runs: number;
  found_count: number;
  kept_count: number;
  search_calls: number;
  input_tokens: number;
  output_tokens: number;
  search_cost_usd: number;
  model_cost_usd: number | null;
  cost_usd: number | null;
  last_search_at: string | null;
}

/** Recherches échouées sur une même erreur, tous comptes réunis. */
export interface RunFailureGroup {
  error_type: string;
  count: number;
  accounts: number;
  last_at: string | null;
}

/** Erreurs d'un même type rendues par une même route de l'API, tous comptes réunis. */
export interface ServerErrorGroup {
  method: string;
  /** Modèle de la route ; null quand aucune n'a été trouvée */
  route: string | null;
  status_code: number;
  error_type: string;
  /** Vrai pour une panne du serveur, faux pour une demande qu'il a refusée */
  is_failure: boolean;
  count: number;
  accounts: number;
  last_at: string | null;
}

/** Erreur survenue dans le navigateur, telle que le front la signale à l'API : jamais son message. */
export interface ClientErrorReport {
  error_type: string;
  /** Écran du front, sans paramètre */
  route: string | null;
  /** Fichier du front et position dans ce fichier */
  source: string | null;
}

/** Erreurs du front d'un même type, au même endroit et sur le même écran, tous comptes réunis. */
export interface ClientErrorGroup {
  route: string | null;
  error_type: string;
  source: string | null;
  count: number;
  accounts: number;
  last_at: string | null;
}

/** Santé de l'instance, pour les administrateurs : ce qui a échoué sur tous les comptes. */
export interface HealthOverview {
  since: string | null;
  /** Recherches échouées ou interrompues et pannes du serveur */
  incidents: number;
  healthy: boolean;
  runs: number;
  failed_runs: number;
  interrupted_runs: number;
  failure_rate: number | null;
  interrupted_accounts: number;
  last_interrupted_at: string | null;
  run_failures: RunFailureGroup[];
  /** Réponses 5xx hors d'une recherche, puis demandes refusées (4xx) */
  failures: number;
  refusals: number;
  server_errors: ServerErrorGroup[];
  /** Erreurs survenues dans le navigateur des utilisateurs */
  client_failures: number;
  client_errors: ClientErrorGroup[];
  /** Modèles utilisés sur la période dont le tarif manque : leurs coûts ne sont pas comptés */
  unpriced_models: string[];
  /** Vrai quand un incident prévient quelqu'un ; faux, il ne se voit que dans cette rubrique */
  alerts_enabled: boolean;
}

/** Issue d'une alerte d'essai. */
export interface AlertTest {
  sent: boolean;
}

/** Une semaine de recherches de l'appelant, du lundi au dimanche à l'heure de Paris. */
export interface WeekStats {
  /** Lundi à minuit, heure de Paris */
  start: string;
  runs: number;
  failed_runs: number;
  cost_usd: number | null;
  found: number;
  evaluated: number;
  /** Part des pages trouvées qui étaient déjà connues */
  known_rate: number | null;
  kept: number;
  kept_rate: number | null;
  /** Candidatures envoyées pendant la semaine */
  applications: number;
}

/** Une étape du parcours, et les comptes qui l'ont franchie. */
export interface JourneyStep {
  label: string;
  count: number;
  /** Part des comptes comptés ; null sans aucun */
  rate: number | null;
}

/** Où en est un compte : des nombres, plus son adresse. */
export interface AccountJourney {
  user_id: number;
  email: string | null;
  is_owner: boolean;
  /** Compte d'essai : il n'est pas compté parmi les utilisateurs */
  is_trial: boolean;
  created_at: string;
  last_seen_at: string | null;
  has_cv: boolean;
  queries: number;
  runs: number;
  kept: number;
  /** Offres dont l'annonce a été ouverte depuis l'application */
  opened: number;
  applied: number;
  interviews: number;
  corrections: number;
  /** Vu un autre jour que celui de la création du compte */
  returned: boolean;
  /** Jours où le compte s'est servi de l'application ; 0 pour le propriétaire */
  active_days: number;
  /** Dernière étape du parcours franchie, et jours écoulés depuis la dernière visite */
  step: string;
  idle_days: number | null;
}

/** Un moment du parcours d'un compte : ce qu'il a fait, jamais sur quoi. */
export interface JourneyEvent {
  at: string;
  kind: string;
  label: string;
  detail: string | null;
}

/** Pages écartées pour une raison donnée. */
export interface RejectionCount {
  label: string;
  count: number;
  rate: number | null;
}

/** Fiche d'un compte, pour les administrateurs : sa chronologie et ce qui écarte ses pages. */
export interface AccountDetail {
  account: AccountJourney;
  evaluated: number;
  rejected: number;
  rejections: RejectionCount[];
  /** Le plus récent en premier */
  events: JourneyEvent[];
}

/** Parcours des utilisateurs, pour les administrateurs. */
export interface JourneyOverview {
  guests: number;
  steps: JourneyStep[];
  /** Comptes d'essai encore en place, et les mêmes étapes comptées sur eux seuls */
  trials: number;
  trial_steps: JourneyStep[];
  accounts: AccountJourney[];
}

/** Dépense du mois en cours, tous comptes réunis, face au budget de l'instance. */
export interface BudgetOverview {
  month_start: string;
  /** 0 : aucun budget n'est fixé */
  budget_usd: number;
  runs: number;
  spent_usd: number;
  /** Vrai quand la dépense ne compte que le moteur de recherche, faute de tarif pour un modèle */
  partial: boolean;
  guests_spent_usd: number | null;
  day_of_month: number;
  days_left: number;
  daily_average_usd: number;
  /** Dépense à la fin du mois si le rythme des jours écoulés se maintient */
  projected_usd: number;
  spent_rate: number | null;
  projected_rate: number | null;
  over_budget: boolean;
  projected_over_budget: boolean;
  /** Budget du jour et ce qui en est dépensé ; 0 : aucun n'est fixé. Atteint, seul le propriétaire cherche encore */
  daily_budget_usd: number;
  today_spent_usd: number;
  daily_budget_reached: boolean;
}

/** Consommation de tous les comptes, pour les administrateurs. */
export interface UsageOverview {
  since: string | null;
  accounts: AccountUsage[];
  runs: number;
  kept_count: number;
  search_cost_usd: number;
  model_cost_usd: number | null;
  cost_usd: number | null;
  /** Part du coût due aux comptes autres que celui du propriétaire */
  guests_cost_usd: number | null;
}

/** Issue d'une question à l'assistant : il a répondu, les textes du site n'en disent rien, ou elle est hors sujet. */
export type AssistantOutcome = 'answered' | 'unknown' | 'off_topic';

/** Texte du site d'où vient une réponse de l'assistant. */
export interface AssistantSource {
  title: string;
  section: string | null;
  /** Adresse de la section dans sa page ; null pour le guide d'utilisation, qui n'est pas une page du site */
  url: string | null;
  /** Écran de l'application dont parle la section (« /profil ») ; null si elle ne parle d'aucun */
  screen: string | null;
}

/** Note donnée par l'utilisateur à une réponse : utile, ou non. */
export type AssistantFeedback = 'up' | 'down';

/** Où en est l'assistant : il cherche les passages, il écrit sa réponse, ou il consulte le compte. */
export type AssistantStep = 'retrieve' | 'generate' | 'consult';

/** Avancement d'une réponse en cours. */
export interface AssistantProgress {
  step: AssistantStep;
  /** Texte de la réponse écrit jusqu'ici, entier à chaque fois ; null tant que rien n'est écrit */
  answer: string | null;
}

export interface AssistantMessage {
  id: number;
  created_at: string;
  question: string;
  answer: string;
  outcome: AssistantOutcome;
  sources: AssistantSource[];
  /** Ce que l'assistant a consulté du compte pour répondre ; vide s'il n'a rien consulté */
  consulted: string[];
  /** null si l'utilisateur n'a pas noté la réponse */
  feedback: AssistantFeedback | null;
}

/** Ce que l'assistant affiche à son ouverture. */
export interface AssistantConversation {
  messages: AssistantMessage[];
  /** null pour le propriétaire, qui n'a pas de quota */
  remaining_questions: number | null;
  max_questions_per_day: number;
  /** Parmi elles, celles qui peuvent consulter le compte : ce nombre atteint, plus de question avant demain */
  max_account_questions_per_day: number;
  max_question_chars: number;
  /** Nombre de jours pendant lesquels le texte d'une question est gardé */
  retention_days: number;
}

export interface AssistantReply {
  message: AssistantMessage;
  remaining_questions: number | null;
}

/** Question posée à l'assistant, telle que la lit un administrateur : sans le compte qui l'a posée. */
export interface AssistantJournalEntry extends Omit<AssistantMessage, 'id'> {
  /** Textes d'où venaient les passages donnés au modèle, le plus proche en premier */
  retrieved: AssistantSource[];
}

/** Usage de l'assistant, tous comptes réunis, pour les administrateurs. */
export interface AssistantOverview {
  since: string | null;
  questions: number;
  answered: number;
  /** Questions sur l'application restées sans réponse : ce qui manque aux textes du site */
  unknown: number;
  off_topic: number;
  /** Questions pour lesquelles l'assistant a consulté le compte de leur auteur */
  consulting: number;
  /** Questions refusées parce qu'une limite était atteinte, la plus fréquente en premier */
  limits: { label: string; count: number; accounts: number }[];
  /** Réponses notées utiles, et pas utiles, par ceux qui les ont reçues */
  helpful: number;
  unhelpful: number;
  accounts: number;
  cost_usd: number | null;
  entries: AssistantJournalEntry[];
}

/** Passage du banc d'évaluation de l'assistant. Les parts vont de 0 à 1 ; null quand rien n'était à mesurer. */
export interface AssistantEvaluation {
  id: number;
  created_at: string;
  model: string;
  embedding_model: string;
  judge_model: string;
  prompt_version: string;
  cases: number;
  /** Questions auxquelles rien n'est à reprocher */
  passed: number;
  pass_rate: number | null;
  outcome_rate: number | null;
  retrieval_rate: number | null;
  mean_reciprocal_rank: number | null;
  citation_rate: number | null;
  correct_rate: number | null;
  faithful_rate: number | null;
  refusal_rate: number | null;
  /** Le compte est consulté quand la question le demande, et seulement alors */
  consult_rate: number | null;
  duration_ms: number;
  cost_usd: number | null;
}

/** Ce qu'une question de référence a donné pendant une évaluation. */
export interface AssistantEvaluationCase {
  id: string;
  question: string;
  expected_outcome: AssistantOutcome;
  outcome: AssistantOutcome;
  passed: boolean;
  answer: string;
  /** Titres des passages donnés au modèle, le plus proche en premier */
  retrieved: string[];
  /** Rang de la section attendue parmi eux ; null si elle n'y est pas, ou si la question n'en attend pas */
  rank: number | null;
  /** null si la question n'attend aucune section */
  cited: boolean | null;
  /** Le modèle a-t-il consulté le compte, et le devait-il ; null si la question ne le dit pas */
  consulted: boolean;
  consult_expected: boolean | null;
  /** Outils appelés, outils attendus, et si le compte a été consulté comme il le fallait ; null si rien n'est attendu */
  tools: string[];
  expected_tools: string[];
  consulted_well: boolean | null;
  faithful: boolean | null;
  correct: boolean | null;
  judge_reason: string;
}

export interface AssistantEvaluationDetail extends AssistantEvaluation {
  /** Les questions qui échouent en premier */
  results: AssistantEvaluationCase[];
}
