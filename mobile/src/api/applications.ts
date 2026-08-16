import { Application, ApplicationInput, ApplicationStatus } from '@/types';
import { apiClient } from './client';

export async function listApplications(status?: ApplicationStatus): Promise<Application[]> {
  const { data } = await apiClient.get<Application[]>(`/api/applications`, {
    params: status ? { status_filter: status } : undefined,
  });
  return data;
}

export async function createApplication(payload: ApplicationInput): Promise<Application> {
  const { data } = await apiClient.post<Application>('/api/applications', payload);
  return data;
}

export async function updateApplication(
  id: string,
  payload: Partial<ApplicationInput>,
): Promise<Application> {
  const { data } = await apiClient.put<Application>(`/api/applications/${id}`, payload);
  return data;
}

export async function deleteApplication(id: string): Promise<void> {
  await apiClient.delete(`/api/applications/${id}`);
}
