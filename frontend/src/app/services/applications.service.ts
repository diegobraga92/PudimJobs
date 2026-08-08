import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

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

@Injectable({ providedIn: 'root' })
export class ApplicationsService {
  constructor(private http: HttpClient) {}

  list(status?: ApplicationStatus): Observable<Application[]> {
    let params = new HttpParams();
    if (status) {
      params = params.set('status_filter', status);
    }
    return this.http.get<Application[]>('/api/applications', { params });
  }

  create(payload: ApplicationInput): Observable<Application> {
    return this.http.post<Application>('/api/applications', payload);
  }

  update(id: string, payload: Partial<ApplicationInput>): Observable<Application> {
    return this.http.put<Application>(`/api/applications/${id}`, payload);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/applications/${id}`);
  }
}
