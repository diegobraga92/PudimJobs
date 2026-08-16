import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

import { API_BASE_URL } from '@/api/config';
import { useAuthStore } from '@/store/auth';

/**
 * PDF helpers — the React Native analog of the web's blob download. Blobs are
 * written to the app cache directory and handed to the Android share sheet so
 * the user can save them anywhere (Downloads, Drive, …).
 */

/** Reads a fetch/axios blob into a base64 data-URL payload (no `data:` prefix). */
export function blobToBase64(blob: unknown): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string; // e.g. "data:application/pdf;base64,JVBER..."
      const comma = result.indexOf(',');
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob as Blob);
  });
}

function cacheUri(fileName: string): string {
  return `${FileSystem.cacheDirectory ?? ''}${fileName}`;
}

/** Saves a blob as a PDF in the cache dir and opens the Android share sheet. */
export async function sharePdfBlob(blob: unknown, fileName: string): Promise<void> {
  const base64 = await blobToBase64(blob);
  const uri = cacheUri(fileName);
  await FileSystem.writeAsStringAsync(uri, base64, {
    encoding: FileSystem.EncodingType.Base64,
  });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', dialogTitle: fileName });
  }
}

/** Downloads a PDF directly from an authed GET endpoint and shares it. */
export async function sharePdfFromUrl(path: string, fileName: string): Promise<void> {
  const { token } = useAuthStore.getState();
  const uri = cacheUri(fileName);
  await FileSystem.downloadAsync(`${API_BASE_URL}${path}`, uri, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', dialogTitle: fileName });
  }
}
