import { inject } from '@angular/core';
import {
  HttpErrorResponse,
  HttpEvent,
  HttpHandlerFn,
  HttpRequest,
} from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, catchError, throwError } from 'rxjs';

import { AuthService, TOKEN_STORAGE_KEY } from '../services/auth.service';

/** Functional HTTP interceptor that attaches the JWT to every request. Registered in app.config.ts via `withInterceptors`. */
export function authInterceptor(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
): Observable<HttpEvent<unknown>> {
  const auth = inject(AuthService);
  const router = inject(Router);
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(req).pipe(
    catchError((error: unknown) => {
      // A rejected token may be expired, revoked or signed with another
      // secret. Clear it and leave protected pages instead of letting every
      // component render its generic "failed to load" banner.
      if (
        error instanceof HttpErrorResponse &&
        error.status === 401 &&
        !req.url.endsWith('/api/auth/login')
      ) {
        auth.logout();
        if (router.url !== '/login') {
          void router.navigate(['/login']);
        }
      }
      return throwError(() => error);
    })
  );
}
