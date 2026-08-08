import { HttpEvent, HttpHandlerFn, HttpRequest } from '@angular/common/http';
import { Observable } from 'rxjs';

import { TOKEN_STORAGE_KEY } from '../services/auth.service';

/**
 * Functional HTTP interceptor that attaches the JWT to every request.
 * Registered in app.config.ts via `withInterceptors`.
 */
export function authInterceptor(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
): Observable<HttpEvent<unknown>> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(req);
}
