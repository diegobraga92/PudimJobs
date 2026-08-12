import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

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
  error?: string;
}

@Injectable({ providedIn: 'root' })
export class AdminService {
  constructor(private http: HttpClient) {}

  stats(): Observable<AdminStats> {
    return this.http.get<AdminStats>('/api/admin/stats');
  }

  sourceHealth(): Observable<SourceHealth[]> {
    return this.http.get<SourceHealth[]>('/api/admin/sources/health');
  }

  dlq(): Observable<ScrapeRun[]> {
    return this.http.get<ScrapeRun[]>('/api/admin/dlq');
  }

  replay(runId: string): Observable<{ replayed: boolean; run_id: string; source_id: string }> {
    return this.http.post<{ replayed: boolean; run_id: string; source_id: string }>(
      `/api/admin/dlq/${runId}/replay`,
      {}
    );
  }

  triggerScrape(sourceId: string): Observable<{ enqueued: boolean; source_id: string }> {
    return this.http.post<{ enqueued: boolean; source_id: string }>(
      `/api/admin/sources/${sourceId}/scrape`,
      {}
    );
  }

  qualityOverview(): Observable<QualityOverview> {
    return this.http.get<QualityOverview>('/api/admin/quality/overview');
  }

  qualityBySource(): Observable<QualityBySource[]> {
    return this.http.get<QualityBySource[]>('/api/admin/quality/by-source');
  }

  qualityJobs(flaggedOnly = false): Observable<QualityJob[]> {
    return this.http.get<QualityJob[]>('/api/admin/quality/jobs', {
      params: flaggedOnly ? { flagged_only: 'true' } : {},
    });
  }

  auditLog(filters: AuditFilters = {}): Observable<AuditEntry[]> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) {
        params = params.set(key, value);
      }
    }
    return this.http.get<AuditEntry[]>('/api/admin/audit', { params });
  }

  auditActions(): Observable<AuditActions> {
    return this.http.get<AuditActions>('/api/admin/audit/actions');
  }

  getLlmConfig(): Observable<LlmConfig> {
    return this.http.get<LlmConfig>('/api/admin/settings/llm');
  }

  updateLlmConfig(payload: LlmConfigInput): Observable<LlmConfig> {
    return this.http.put<LlmConfig>('/api/admin/settings/llm', payload);
  }

  testLlmConfig(): Observable<LlmTestResult> {
    return this.http.post<LlmTestResult>('/api/admin/settings/llm/test', {});
  }
}
