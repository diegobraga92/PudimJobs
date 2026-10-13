import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export type PrepCategory = 'technical' | 'behavioral' | 'research' | 'logistics' | 'other';
export type PrepStatus = 'pending' | 'in_progress' | 'done';

export interface PrepTask {
  id: string;
  title: string;
  category: PrepCategory;
  status: PrepStatus;
  due_date: string | null;
  notes: string | null;
  job_id: string | null;
  application_id: string | null;
  job_title: string | null;
  job_company: string | null;
  created_at: string;
  updated_at: string;
}

export interface PrepTaskInput {
  title: string;
  category?: PrepCategory;
  status?: PrepStatus;
  due_date?: string | null;
  notes?: string | null;
  job_id?: string | null;
  application_id?: string | null;
}

export interface PrepTaskFilters {
  status_filter?: PrepStatus | '';
  job_id?: string;
}

@Injectable({ providedIn: 'root' })
export class PrepTasksService {
  constructor(private http: HttpClient) {}

  list(filters: PrepTaskFilters = {}): Observable<PrepTask[]> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value) {
        params = params.set(key, value);
      }
    }
    return this.http.get<PrepTask[]>('/api/prep-tasks', { params });
  }

  create(payload: PrepTaskInput): Observable<PrepTask> {
    return this.http.post<PrepTask>('/api/prep-tasks', payload);
  }

  update(id: string, payload: Partial<PrepTaskInput>): Observable<PrepTask> {
    return this.http.put<PrepTask>(`/api/prep-tasks/${id}`, payload);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/prep-tasks/${id}`);
  }
}
