import { TestBed } from '@angular/core/testing';
import {
  HttpClient,
  HttpErrorResponse,
  provideHttpClient,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';

import { TOKEN_STORAGE_KEY } from '../services/auth.service';
import { authInterceptor } from './auth.interceptor';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('attaches the stored token to API requests', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'stored-token');

    http.get('/api/sources').subscribe();

    const request = httpMock.expectOne('/api/sources');
    expect(request.request.headers.get('Authorization')).toBe('Bearer stored-token');
    request.flush([]);
  });

  it('clears the session and redirects to login on a protected 401', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'stale-token');
    const navigate = spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
    let status: number | undefined;

    http.get('/api/sources').subscribe({
      error: (error: HttpErrorResponse) => (status = error.status),
    });

    httpMock
      .expectOne('/api/sources')
      .flush({ detail: 'Unauthorized' }, { status: 401, statusText: 'Unauthorized' });

    expect(status).toBe(401);
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/login']);
  });

  it('does not redirect on a failed login attempt', () => {
    const navigate = spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));

    http.post('/api/auth/login', {}).subscribe({ error: () => undefined });

    httpMock
      .expectOne('/api/auth/login')
      .flush({ detail: 'Invalid credentials' }, { status: 401, statusText: 'Unauthorized' });

    expect(navigate).not.toHaveBeenCalled();
  });
});
