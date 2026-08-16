import {
  EnqueueResult,
  JobCreateInput,
  JobDetail,
  JobFilters,
  JobSummary,
  JobUpdateInput,
  ParsedJD,
} from '@/types';
import { apiClient } from './client';

export async function listJobs(filters: JobFilters = {}): Promise<JobSummary[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  const { data } = await apiClient.get<JobSummary[]>(`/api/jobs${query ? `?${query}` : ''}`);
  return data;
}

export async function getJob(id: string): Promise<JobDetail> {
  const { data } = await apiClient.get<JobDetail>(`/api/jobs/${id}`);
  return data;
}

export async function createJob(payload: JobCreateInput): Promise<JobDetail> {
  const { data } = await apiClient.post<JobDetail>('/api/jobs', payload);
  return data;
}

export async function updateJob(id: string, payload: JobUpdateInput): Promise<JobDetail> {
  const { data } = await apiClient.put<JobDetail>(`/api/jobs/${id}`, payload);
  return data;
}

export function hideJob(id: string): Promise<JobDetail> {
  return updateJob(id, { hidden: true });
}

export function unhideJob(id: string): Promise<JobDetail> {
  return updateJob(id, { hidden: false });
}

export async function deleteJob(id: string): Promise<void> {
  await apiClient.delete(`/api/jobs/${id}`);
}

export async function parseJob(id: string): Promise<EnqueueResult> {
  const { data } = await apiClient.post<EnqueueResult>(`/api/jobs/${id}/parse`, {});
  return data;
}

export async function tailorCv(id: string, cvId?: string): Promise<EnqueueResult> {
  const { data } = await apiClient.post<EnqueueResult>(
    `/api/jobs/${id}/tailor`,
    cvId ? { cv_id: cvId } : {},
  );
  return data;
}

export async function getParsed(id: string): Promise<ParsedJD | null> {
  const { data } = await apiClient.get<ParsedJD | null>(`/api/jobs/${id}/parsed`);
  return data;
}
