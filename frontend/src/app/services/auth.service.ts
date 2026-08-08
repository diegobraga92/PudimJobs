import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export const TOKEN_STORAGE_KEY = 'pudimjobs_token';

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  role: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  constructor(private http: HttpClient) {}

  login(email: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>('/api/auth/login', { email, password });
  }

  getToken(): string | null {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  }

  storeToken(token: string): void {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  }

  logout(): void {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }
}
