import {
  AuthTestResult,
  DiscoveryProvider,
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
