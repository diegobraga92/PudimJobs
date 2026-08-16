/**
 * API types for PudimJobs — mirrors the interfaces declared in the Angular
 * frontend services (frontend/src/app/services/*) so payloads stay identical.
 */

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
}

// ---- Applications ------------------------------------------------------

export type ApplicationStatus = 'saved' | 'applied' | 'interview' | 'offer' | 'rejected';

export interface Application {
  id: string;
  job_id: string;
  status: ApplicationStatus;
  applied_date: string | null;
  notes: string | null;
  cv_version: string | null;
  created_at: string;
  updated_at: string;
  job_title: string;
  job_company: string;
  job_url: string | null;
}

export interface ApplicationInput {
  job_id: string;
  status?: ApplicationStatus;
  applied_date?: string | null;
  notes?: string | null;
  cv_version?: string | null;
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
}

export type SourceInput = Pick<
  Source,
  'name' | 'url' | 'type' | 'rate_limit_seconds' | 'respect_robots_txt'
> & { config?: Record<string, unknown> | null } & Partial<Pick<Source, 'id' | 'health'>>;

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

export interface GeneratedCV {
  id: string;
  master_cv_id: string | null;
  job_id: string | null;
  job_title: string | null;
  job_company: string | null;
  created_at: string;
}
