import axios, { AxiosError } from 'axios';

import { useAuthStore } from '@/store/auth';
import { API_BASE_URL } from './config';

/**
 * Shared axios instance — the React Native analog of the Angular
 * `authInterceptor` + HttpClient. Attaches the JWT to every request and
 * clears the session on 401 (the RootNavigator reacts and returns to Login).
 */
// eslint-disable-next-line import/no-named-as-default-member
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
});

apiClient.interceptors.request.use((config) => {
  const { token } = useAuthStore.getState();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      const { token, clear } = useAuthStore.getState();
      if (token) {
        clear();
      }
    }
    return Promise.reject(error);
  },
);

/** Extract a human-readable error message from an axios failure (HTTP fallback). */
export function errorMessage(error: unknown, fallback: string): string {
  // eslint-disable-next-line import/no-named-as-default-member
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { detail?: string } | undefined;
    if (typeof data?.detail === 'string' && data.detail) {
      return data.detail;
    }
    if (error.code === 'ERR_NETWORK') {
      return 'network-error';
    }
  }
  return fallback;
}
