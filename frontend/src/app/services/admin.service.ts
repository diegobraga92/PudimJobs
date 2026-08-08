import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
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
}
