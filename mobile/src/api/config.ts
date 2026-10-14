import { Platform } from 'react-native';

/** Resolve the API base URL: `EXPO_PUBLIC_API_URL` wins, else the Android emulator host `10.0.2.2`. */
declare const process: { env: Record<string, string | undefined> };

const ENV_URL = process.env.EXPO_PUBLIC_API_URL;
const DEFAULT_HOST = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
const DEFAULT_PORT = '8000';

export const API_BASE_URL = (ENV_URL || `http://${DEFAULT_HOST}:${DEFAULT_PORT}`).replace(
  /\/+$/,
  '',
);
