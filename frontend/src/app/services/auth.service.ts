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

interface JwtPayload {
  exp?: number;
}

/** Decodes a JWT payload without validating its signature; the API does that. */
function decodeJwtPayload(token: string): JwtPayload | null {
  const payload = token.split('.')[1];
  if (!payload) {
    return null;
  }
  try {
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return JSON.parse(atob(padded)) as JwtPayload;
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  constructor(private http: HttpClient) {}

  login(email: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>('/api/auth/login', { email, password });
  }

  me(): Observable<User> {
    return this.http.get<User>('/api/auth/me');
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

  /**
   * A stored token is only a session until it expires. Clearing stale tokens
   * here keeps route guards from rendering protected pages that can only fail
   * with 401 responses.
   */
  isAuthenticated(): boolean {
    const token = this.getToken();
    if (!token) {
      return false;
    }
    const payload = decodeJwtPayload(token);
    if (!payload?.exp || payload.exp * 1000 <= Date.now()) {
      this.logout();
      return false;
    }
    return true;
  }
}
