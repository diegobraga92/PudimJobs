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
  lessons_learned: string | null;
  /** The tailored CV artifact this application was sent with (ADR 016). */
  generated_cv_id: string | null;
  created_at: string;
  updated_at: string;
  job_title: string;
  job_company: string;
  job_url: string | null;
}

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

/** A retrospective note, joined with the job it belongs to. */
export interface LessonEntry {
  application_id: string;
  job_title: string;
  job_company: string;
  status: ApplicationStatus;
  applied_date: string | null;
  lessons_learned: string;
  updated_at: string;
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

  /** Retrospectives across every application that recorded one (newest first). */
  lessons(): Observable<LessonEntry[]> {
    return this.http.get<LessonEntry[]>('/api/applications/lessons');
  }

  /** One application plus its job description (application workspace). */
  get(id: string): Observable<ApplicationDetail> {
    return this.http.get<ApplicationDetail>(`/api/applications/${id}`);
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
