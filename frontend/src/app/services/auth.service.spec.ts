import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';

import { AuthService, TOKEN_STORAGE_KEY } from './auth.service';

function tokenWithPayload(payload: object): string {
  const encoded = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `header.${encoded}.signature`;
}

describe('AuthService', () => {
  let service: AuthService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient()],
    });
    service = TestBed.inject(AuthService);
  });

  afterEach(() => localStorage.clear());

  it('rejects a session when no token is stored', () => {
    expect(service.isAuthenticated()).toBeFalse();
  });

  it('accepts a token that has not expired', () => {
    const token = tokenWithPayload({ exp: Math.floor(Date.now() / 1000) + 60 });
    service.storeToken(token);

    expect(service.isAuthenticated()).toBeTrue();
    expect(service.getToken()).toBe(token);
  });

  it('clears an expired token', () => {
    service.storeToken(tokenWithPayload({ exp: Math.floor(Date.now() / 1000) - 60 }));

    expect(service.isAuthenticated()).toBeFalse();
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  it('clears a token without an expiry', () => {
    service.storeToken(tokenWithPayload({ sub: 'user' }));

    expect(service.isAuthenticated()).toBeFalse();
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  it('clears a malformed token', () => {
    service.storeToken('not-a-jwt');

    expect(service.isAuthenticated()).toBeFalse();
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});
