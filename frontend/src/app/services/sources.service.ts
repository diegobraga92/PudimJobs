import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Source {
  id: string;
  name: string;
  url: string;
  type: string;
  health: string;
  last_scraped: string | null;
  created_at: string;
}

export type SourceInput = Pick<Source, 'name' | 'url' | 'type'> &
  Partial<Pick<Source, 'id' | 'health'>>;

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
}
