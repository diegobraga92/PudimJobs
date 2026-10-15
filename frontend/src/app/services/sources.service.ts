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
> & Partial<
  Pick<Source, 'id' | 'health' | 'config' | 'avoided' | 'avoided_at' | 'avoid_reason'>
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

/** Config contract published per provider/adapter (drives hints + validation). */
export interface ConfigContract {
  required_config: string[];
  /** Alternation groups: at least one key of each group must be present. */
  required_any: string[][];
  optional_config: string[];
  example_config: Record<string, unknown>;
}

export interface DiscoveryProvider extends ConfigContract {
  name: string;
  family: string;
  requires_key: boolean;
}

export interface AggregatorAdapter extends ConfigContract {
  name: string;
  description: string | null;
}

/**
 * Contract of `manual` (watchlist) sources, published by the API so neither UI
 * hard-codes the re-check cadence bounds. `cadence_days` is the default/min/max
 * the form must use; the validator rejects anything outside it with a 422.
 */
export interface ManualMetadata extends ConfigContract {
  type: string;
  cadence_days: { default: number; min: number; max: number };
}

export interface SourcePreviewJob {
  title: string;
  company: string;
  url: string | null;
  posted_date: string | null;
  tags: string[];
}

export interface SourcePreview {
  fetched_url: string;
  status_code: number | null;
  jobs_found: number;
  sample_jobs: SourcePreviewJob[];
  truncated: boolean;
  error: string | null;
}

export interface SourcePreviewInput {
  url: string;
  type: string;
  config?: Record<string, unknown> | null;
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

  /** Mark a manual (watchlist) source as checked by hand; schedules the next reminder. */
  checkSource(id: string): Observable<Source> {
    return this.http.post<Source>(`/api/sources/${id}/check`, {});
  }

  /**
   * Flag a source as avoided — never fetched, never reminded about — or restore
   * it. `reason` is optional; omit it to keep the stored one.
   */
  setSourceAvoided(id: string, avoided: boolean, reason?: string): Observable<Source> {
    const payload: { avoided: boolean; reason?: string } = { avoided };
    if (reason !== undefined) {
      payload.reason = reason;
    }
    return this.http.post<Source>(`/api/sources/${id}/avoid`, payload);
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

  /** Discovery provider metadata (drives the source form's provider dropdown). */
  listProviders(): Observable<DiscoveryProvider[]> {
    return this.http.get<DiscoveryProvider[]>('/api/sources/providers');
  }

  /** Aggregator adapter metadata (drives the source form's adapter dropdown). */
  listAdapters(): Observable<AggregatorAdapter[]> {
    return this.http.get<AggregatorAdapter[]>('/api/sources/adapters');
  }

  /** Config contract of `manual` watchlist sources (drives the cadence input). */
  manualMetadata(): Observable<ManualMetadata> {
    return this.http.get<ManualMetadata>('/api/sources/manual-metadata');
  }

  /** Dry-run a URL/type/config: fetches and parses once, persisting nothing, so selectors can be tuned before saving the source. */
  preview(payload: SourcePreviewInput): Observable<SourcePreview> {
    return this.http.post<SourcePreview>('/api/sources/preview', payload);
  }
}
