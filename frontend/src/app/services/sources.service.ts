import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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
  /** Scraping ethics / politeness settings. */
  rate_limit_seconds: number;
  respect_robots_txt: boolean;
}

export type SourceInput = Pick<
  Source,
  'name' | 'url' | 'type' | 'rate_limit_seconds' | 'respect_robots_txt'
> & Partial<Pick<Source, 'id' | 'health' | 'config'>>;

export type SourceAuthType = 'none' | 'cookies' | 'token';

export interface SourceAuth {
  auth_type: SourceAuthType;
  has_auth: boolean;
  updated_at: string | null;
}

export interface SourceAuthInput {
  auth_type: SourceAuthType;
  cookies?: string;
  token?: string;
}

export interface AuthTestResult {
  ok: boolean;
  status_code: number | null;
  error?: string;
}

@Injectable({ providedIn: 'root' })
export class SourcesService {
  constructor(private http: HttpClient) {}

  list(): Observable<Source[]> {
    return this.http.get<Source[]>('/api/sources');
  }

  create(payload: SourceInput): Observable<Source> {
    return this.http.post<Source>('/api/sources', payload);
  }

  update(id: string, payload: Partial<SourceInput>): Observable<Source> {
    return this.http.put<Source>(`/api/sources/${id}`, payload);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/sources/${id}`);
  }

  getAuth(id: string): Observable<SourceAuth> {
    return this.http.get<SourceAuth>(`/api/sources/${id}/auth`);
  }

  updateAuth(id: string, payload: SourceAuthInput): Observable<SourceAuth> {
    return this.http.put<SourceAuth>(`/api/sources/${id}/auth`, payload);
  }

  deleteAuth(id: string): Observable<void> {
    return this.http.delete<void>(`/api/sources/${id}/auth`);
  }

  testAuth(id: string): Observable<AuthTestResult> {
    return this.http.post<AuthTestResult>(`/api/sources/${id}/auth/test`, {});
  }
}
