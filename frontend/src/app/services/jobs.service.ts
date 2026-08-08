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
  created_at: string;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  source_id: string | null;
}

export interface JobFilters {
  q?: string;
  company?: string;
  date_from?: string;
  date_to?: string;
  tags?: string;
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

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/jobs/${id}`);
  }
}
