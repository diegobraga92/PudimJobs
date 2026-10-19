import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { CvVariant } from './cv.service';

export interface JobSummary {
  id: string;
  title: string;
  company: string;
  url: string | null;
  posted_date: string | null;
  tags: string[];
  hidden: boolean;
  created_at: string;
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
  source_id?: string;
  created_after?: string;
  include_hidden?: boolean;
  hide_applied?: boolean;
}

export type JobInput = Partial<JobDetail>;

/**
 * Criteria for a bulk cleanup run (ADR 023). At least one of `older_than_days`
 * (matched against `created_at`) / `source_id` must be given; both may be
 * combined. `dry_run` is the default: it only counts.
 */
export interface JobCleanupRequest {
  older_than_days?: number | null;
  source_id?: string | null;
  /** Opt-in: also delete jobs in the pipeline, cascading their application away. */
  include_with_applications?: boolean;
  dry_run?: boolean;
}

/** What a cleanup run matched, deleted and deliberately spared (ADR 023). */
export interface JobCleanupResult {
  matched: number;
  deleted: number;
  protected: number;
  dry_run: boolean;
}

/** Acknowledgement of an enqueued tailor run. `variants` names the artifacts the run will produce (`rule` always, plus `llm` when the LLM is on) so the caller knows what to wait for (ADR 016). */
export interface TailorEnqueueResult {
  enqueued: boolean;
  job_id: string;
  cv_id?: string | null;
  application_id: string | null;
  variants: CvVariant[];
}

@Injectable({ providedIn: 'root' })
export class JobsService {
  constructor(private http: HttpClient) {}

  list(filters: JobFilters = {}): Observable<JobSummary[]> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) {
        params = params.set(key, value);
      }
    }
    return this.http.get<JobSummary[]>('/api/jobs', { params });
  }

  get(id: string): Observable<JobDetail> {
    return this.http.get<JobDetail>(`/api/jobs/${id}`);
  }

  create(payload: JobInput): Observable<JobDetail> {
    return this.http.post<JobDetail>('/api/jobs', payload);
  }

  update(id: string, payload: JobInput): Observable<JobDetail> {
    return this.http.put<JobDetail>(`/api/jobs/${id}`, payload);
  }

  hide(id: string): Observable<JobDetail> {
    return this.http.put<JobDetail>(`/api/jobs/${id}`, { hidden: true });
  }

  unhide(id: string): Observable<JobDetail> {
    return this.http.put<JobDetail>(`/api/jobs/${id}`, { hidden: false });
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/jobs/${id}`);
  }

  /**
   * Bulk-delete jobs by age and/or source. Jobs already in the pipeline are kept
   * unless `include_with_applications` is set, and `dry_run` (the default) only
   * counts — the UI previews first (ADR 023).
   */
  cleanup(payload: JobCleanupRequest): Observable<JobCleanupResult> {
    return this.http.post<JobCleanupResult>('/api/jobs/cleanup', payload);
  }

  parse(id: string): Observable<{ enqueued: boolean; job_id: string }> {
    return this.http.post<{ enqueued: boolean; job_id: string }>(`/api/jobs/${id}/parse`, {});
  }

  /** Enqueue CV tailoring for a job (async: the caller polls for the artifact). */
  tailor(
    id: string,
    cvId?: string,
    applicationId?: string
  ): Observable<TailorEnqueueResult> {
    const body: { cv_id?: string; application_id?: string } = {};
    if (cvId) {
      body.cv_id = cvId;
    }
    if (applicationId) {
      body.application_id = applicationId;
    }
    return this.http.post<TailorEnqueueResult>(`/api/jobs/${id}/tailor`, body);
  }

  getParsed(id: string): Observable<ParsedJD | null> {
    return this.http.get<ParsedJD | null>(`/api/jobs/${id}/parsed`);
  }
}

