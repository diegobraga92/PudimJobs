/** API types for PudimJobs — mirrors the interfaces declared in the Angular frontend services (frontend/src/app/services/*) so payloads stay identical. */

// ---- Auth --------------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  role: string;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  db: string;
}

// ---- Jobs --------------------------------------------------------------

export interface JobSummary {
  id: string;
  title: string;
  company: string;
  url: string | null;
  posted_date: string | null;
  tags: string[];
  hidden: boolean;
  created_at: string;
  /** Relevance score (0–1) present when the list is keyword-searched. */
  score?: number;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  source_id: string | null;
}

export interface ParsedJD {
  skills: string[];
  years_experience: number | null;
  education_level: string | null;
  keywords: string[];
}

export interface JobFilters {
  q?: string;
  company?: string;
  date_from?: string;
  date_to?: string;
  tags?: string;
  include_hidden?: boolean;
  hide_applied?: boolean;
}

/** Payload for creating a job (mirrors the backend JobCreate schema). */
export interface JobCreateInput {
  title: string;
  company: string;
  description?: string | null;
  url?: string | null;
  posted_date?: string | null;
  tags?: string[];
  source_id?: string | null;
}

/** Payload for updating a job (mirrors the backend JobUpdate schema). */
export interface JobUpdateInput extends Partial<JobCreateInput> {
  hidden?: boolean;
}

export interface EnqueueResult {
  enqueued: boolean;
  job_id: string;
  cv_id?: string | null;
  /** Set when the tailor run was linked to an application. */
  application_id?: string | null;
}

/**
 * Acknowledgement of an enqueued tailor run (`POST /api/jobs/:id/tailor`, 202).
 * `variants` names the artifacts the run will produce — `rule` always, plus `llm`
 * when the LLM is on — so the caller can poll until *all* of them have landed
 * instead of stopping at the first one (ADR 016).
 */
export interface TailorEnqueueResult extends EnqueueResult {
  variants: CvVariant[];
}

// ---- Applications ------------------------------------------------------

export type ApplicationStatus = 'saved' | 'applied' | 'interview' | 'offer' | 'rejected';

export interface Application {
  id: string;
  job_id: string;
  status: ApplicationStatus;
  applied_date: string | null;
  notes: string | null;
  lessons_learned: string | null;
  /** The tailored CV artifact this application was sent with (ADR 016). */
  generated_cv_id: string | null;
  created_at: string;
  updated_at: string;
  job_title: string;
  job_company: string;
  job_url: string | null;
}

/** One application plus its job description (the per-application workspace). */
export interface ApplicationDetail extends Application {
  job_description: string | null;
}

export interface ApplicationInput {
  job_id: string;
  status?: ApplicationStatus;
  applied_date?: string | null;
  notes?: string | null;
  lessons_learned?: string | null;
  generated_cv_id?: string | null;
}

// ---- CV ----------------------------------------------------------------

// ---- Sources -----------------------------------------------------------

export interface Source {
  id: string;
  name: string;
  url: string;
  type: string;
  config?: Record<string, unknown> | null;
  health: string;
  last_scraped: string | null;
  created_at: string;
  jobs_count?: number;
  rate_limit_seconds: number;
  respect_robots_txt: boolean;
  /** Manual (watchlist) sources: when the board is next due for a hand-check. */
  next_check_at?: string | null;
  /** Manual (watchlist) sources: true when the board is due for a hand-check. */
  due?: boolean;
  /**
   * Soft-avoid flag (any source type): an avoided source is never fetched and
   * never reminded about, but stays listed as a visible reminder (ADR 019).
   */
  avoided?: boolean;
  /** When the source was flagged as avoided (`null` while active). */
  avoided_at?: string | null;
  /** Optional "why" the user wrote when avoiding the source (max 280). */
  avoid_reason?: string | null;
}

export type SourceInput = Pick<
  Source,
  'name' | 'url' | 'type' | 'rate_limit_seconds' | 'respect_robots_txt'
> & { config?: Record<string, unknown> | null } & Partial<
    Pick<Source, 'id' | 'health' | 'avoided' | 'avoided_at' | 'avoid_reason'>
  >;

export type SourceAuthType = 'none' | 'token' | 'api_key';

export interface SourceAuth {
  auth_type: SourceAuthType;
  has_auth: boolean;
  updated_at: string | null;
}

export interface SourceAuthInput {
  auth_type: SourceAuthType;
  token?: string;
  api_key?: string;
}

export interface DiscoveryProvider {
  name: string;
  family: string;
  requires_key: boolean;
}

/**
 * Contract of `manual` (watchlist) sources, published by the API so the app does
 * not hard-code the re-check cadence bounds; the API rejects anything outside
 * them with a 422.
 */
export interface ManualMetadata {
  type: string;
  cadence_days: { default: number; min: number; max: number };
  required_config: string[];
  optional_config: string[];
  example_config: Record<string, unknown>;
}

export interface AuthTestResult {
  ok: boolean;
  status_code: number | null;
  error?: string;
}

// ---- Alert rules -------------------------------------------------------

export interface AlertRule {
  id: string;
  name: string;
  keywords: string[];
  companies: string[];
  tags: string[];
  remote_only: boolean;
  min_years_experience: number | null;
  channels: string[];
  active: boolean;
  created_at: string;
}

export type AlertRuleInput = Partial<
  Omit<AlertRule, 'id' | 'created_at' | 'active'> & { active?: boolean }
>;

// ---- Notifications -----------------------------------------------------

export interface Notification {
  id: string;
  job_id: string | null;
  channel: string;
  title: string;
  message: string | null;
  status: string;
  read: boolean;
  created_at: string;
}

export interface NotificationList {
  total: number;
  unread: number;
  items: Notification[];
}

// ---- Admin -------------------------------------------------------------

export interface AdminStats {
  sources: number;
  jobs: number;
  jobs_last_24h: number;
  failed_runs: number;
  total_runs: number;
}

export interface SourceHealth {
  id: string;
  name: string;
  type: string;
  health: string;
  last_scraped: string | null;
  rate_limit_seconds: number;
}

export interface ScrapeRun {
  id: string;
  source_id: string;
  status: string;
  new_jobs: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface QualityOverview {
  jobs_total: number;
  assessed: number;
  avg_completeness: number;
  duplicates: number;
  normalization_coverage: number;
  jobs_with_issues: number;
}

export interface QualityBySource {
  source: string;
  jobs: number;
  avg_completeness: number;
}

export interface QualityJob {
  job_id: string;
  title: string;
  company: string;
  source_id: string | null;
  completeness_score: number;
  normalized_company: string | null;
  normalized_title: string | null;
  is_duplicate: boolean;
  issues: string[];
}

export interface AuditEntry {
  id: string;
  user_id: string | null;
  email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  changes: Record<string, unknown> | null;
  timestamp: string;
}

export interface AuditFilters {
  action?: string;
  entity_type?: string;
  date_from?: string;
  date_to?: string;
}

export interface AuditActions {
  entity_types: string[];
  actions: string[];
}

export interface LlmConfig {
  id: string;
  enabled: boolean;
  base_url: string;
  model: string;
  api_key_masked: string | null;
  updated_at: string;
}

export interface LlmConfigInput {
  enabled: boolean;
  base_url: string;
  model: string;
  api_key?: string;
}

export interface LlmTestResult {
  ok: boolean;
  status_code: number | null;
  model?: string;
  error?: string;
}

export interface ExperienceItem {
  company: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  bullets: string[];
}

export interface EducationItem {
  institution: string;
  degree: string;
  year: string | null;
}

export interface ProjectItem {
  name: string;
  description: string | null;
  link: string | null;
}

export interface CVStructure {
  summary: string;
  experience: ExperienceItem[];
  education: EducationItem[];
  skills: string[];
  projects: ProjectItem[];
}

export interface MasterCV {
  id: string;
  label: string;
  version: number;
  is_current: boolean;
  structured_json: CVStructure;
  created_at: string;
  updated_at: string;
}

export interface CVInput {
  structured_json: CVStructure;
  label?: string;
}

/** How a tailored CV was produced (mirrors `app/models/enums.CVVariant`). */
export type CvVariant = 'rule' | 'llm';

/** A tailored CV artifact — its own document, not a master CV version. */
export interface GeneratedCV {
  id: string;
  job_id: string | null;
  job_title: string | null;
  job_company: string | null;
  source_master_cv_id: string | null;
  variant: CvVariant;
  created_at: string;
  updated_at: string;
  /** The artifact's own content (drives both the preview and the editor). */
  structured_json: CVStructure | null;
  ats_score: number | null;
  ats_report: AtsReport | null;
}

/** One weighted component of an ATS score (mirrors `app/schemas/ats.py`). */
export interface AtsFactor {
  key: string;
  label: string;
  score: number;
  weight: number;
  detail: string;
}

export interface AtsReport {
  score: number;
  /** The deterministic baseline on its own (mirrors `score`). Optional because a report cached on an artifact before this field existed carries only `score`. */
  deterministic_score?: number | null;
  /** The ATS reviewer LLM's own 0..100 estimate, reported *beside* the baseline (never blended into it). `null` when no reviewer ran. */
  llm_score?: number | null;
  method: 'heuristic' | 'hybrid' | string;
  factors: AtsFactor[];
  matched_skills: string[];
  missing_skills: string[];
  recommendations: string[];
  warnings: string[];
  llm_summary: string | null;
  /** The LLM variant's own estimate of its rewrite (ADR 016); never blended in. */
  llm_self_score?: number | null;
}

export interface AtsScoreInput {
  cv: CVStructure;
  job_id?: string | null;
  generated_cv_id?: string | null;
}
