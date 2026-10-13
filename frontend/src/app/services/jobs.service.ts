import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

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
  include_hidden?: boolean;
  hide_applied?: boolean;
}

export type JobInput = Partial<JobDetail>;

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

  parse(id: string): Observable<{ enqueued: boolean; job_id: string }> {
    return this.http.post<{ enqueued: boolean; job_id: string }>(`/api/jobs/${id}/parse`, {});
  }

  /**
   * Enqueue CV tailoring for a job. `cvId` picks the source master version
   * (defaults to the current one); `applicationId` links the application to the
   * tailored version once the task finishes. Runs async — the caller polls.
   */
  tailor(
    id: string,
    cvId?: string,
    applicationId?: string
  ): Observable<{ enqueued: boolean; job_id: string; application_id: string | null }> {
    const body: { cv_id?: string; application_id?: string } = {};
    if (cvId) {
      body.cv_id = cvId;
    }
    if (applicationId) {
      body.application_id = applicationId;
    }
    return this.http.post<{ enqueued: boolean; job_id: string; application_id: string | null }>(
      `/api/jobs/${id}/tailor`,
      body
    );
  }

  getParsed(id: string): Observable<ParsedJD | null> {
    return this.http.get<ParsedJD | null>(`/api/jobs/${id}/parsed`);
  }
}

