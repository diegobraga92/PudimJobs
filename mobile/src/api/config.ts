import { Platform } from 'react-native';

/**
 * API base URL resolution.
 * - `EXPO_PUBLIC_API_URL` env var overrides everything (e.g. a LAN IP or HTTPS
 *   production endpoint).
 * - Otherwise the Android emulator reaches the dev host via 10.0.2.2.
 *
 * The backend is not exposed on a host port by default in docker-compose.yml;
 * add `"${PJ_BACKEND_PORT:-8000}:8000"` to the `backend` service to develop
 * against it directly.
 */
declare const process: { env: Record<string, string | undefined> };

const ENV_URL = process.env.EXPO_PUBLIC_API_URL;
const DEFAULT_HOST = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
const DEFAULT_PORT = '8000';

export const API_BASE_URL = (ENV_URL || `http://${DEFAULT_HOST}:${DEFAULT_PORT}`).replace(
  /\/+$/,
  '',
);
