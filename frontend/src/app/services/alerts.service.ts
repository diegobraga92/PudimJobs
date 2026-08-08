import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface AlertRule {
  id: string;
  name: string;
  keywords: string[];
  companies: string[];
  tags: string[];
  remote_only: boolean;
  min_years_experience: number | null;
  channels: string[];
  active: boolean;
  created_at: string;
}

export type AlertRuleInput = Partial<
  Omit<AlertRule, 'id' | 'created_at' | 'active'> & { active?: boolean }
>;

@Injectable({ providedIn: 'root' })
export class AlertsService {
  constructor(private http: HttpClient) {}

  list(): Observable<AlertRule[]> {
    return this.http.get<AlertRule[]>('/api/alert-rules');
  }

  create(payload: AlertRuleInput): Observable<AlertRule> {
    return this.http.post<AlertRule>('/api/alert-rules', payload);
  }

  update(id: string, payload: AlertRuleInput): Observable<AlertRule> {
    return this.http.put<AlertRule>(`/api/alert-rules/${id}`, payload);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`/api/alert-rules/${id}`);
  }
}
