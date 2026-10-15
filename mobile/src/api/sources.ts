import {
  AuthTestResult,
  DiscoveryProvider,
  ManualMetadata,
  Source,
  SourceAuth,
  SourceAuthInput,
  SourceInput,
} from '@/types';
import { apiClient } from './client';

export async function listSources(): Promise<Source[]> {
  const { data } = await apiClient.get<Source[]>('/api/sources');
  return data;
}

export async function createSource(payload: SourceInput): Promise<Source> {
  const { data } = await apiClient.post<Source>('/api/sources', payload);
  return data;
}

export async function updateSource(id: string, payload: Partial<SourceInput>): Promise<Source> {
  const { data } = await apiClient.put<Source>(`/api/sources/${id}`, payload);
  return data;
}

export async function deleteSource(id: string): Promise<void> {
  await apiClient.delete(`/api/sources/${id}`);
}

/** Mark a manual (watchlist) source as checked by hand; schedules the next reminder. */
export async function checkSource(id: string): Promise<Source> {
  const { data } = await apiClient.post<Source>(`/api/sources/${id}/check`, {});
  return data;
}

/**
 * Flag a source as avoided — never fetched, never reminded about — or restore
 * it. `reason` is optional; omit it to keep the stored one.
 */
export async function setSourceAvoided(
  id: string,
  avoided: boolean,
  reason?: string,
): Promise<Source> {
  const payload: { avoided: boolean; reason?: string } = { avoided };
  if (reason !== undefined) {
    payload.reason = reason;
  }
  const { data } = await apiClient.post<Source>(`/api/sources/${id}/avoid`, payload);
  return data;
}

export async function getSourceAuth(id: string): Promise<SourceAuth> {
  const { data } = await apiClient.get<SourceAuth>(`/api/sources/${id}/auth`);
  return data;
}

export async function updateSourceAuth(id: string, payload: SourceAuthInput): Promise<SourceAuth> {
  const { data } = await apiClient.put<SourceAuth>(`/api/sources/${id}/auth`, payload);
  return data;
}

export async function deleteSourceAuth(id: string): Promise<void> {
  await apiClient.delete(`/api/sources/${id}/auth`);
}

export async function testSourceAuth(id: string): Promise<AuthTestResult> {
  const { data } = await apiClient.post<AuthTestResult>(`/api/sources/${id}/auth/test`, {});
  return data;
}

export async function listProviders(): Promise<DiscoveryProvider[]> {
  const { data } = await apiClient.get<DiscoveryProvider[]>('/api/sources/providers');
  return data;
}

/** Config contract of `manual` watchlist sources (cadence bounds + accepted keys). */
export async function getManualMetadata(): Promise<ManualMetadata> {
  const { data } = await apiClient.get<ManualMetadata>('/api/sources/manual-metadata');
  return data;
}
