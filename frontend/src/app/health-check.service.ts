import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface HealthResponse {
  status: string;
  timestamp: string;
  db: string;
}

@Injectable({
  providedIn: 'root',
})
export class HealthCheckService {
  constructor(private http: HttpClient) {}

  check(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>('/api/health');
  }
}