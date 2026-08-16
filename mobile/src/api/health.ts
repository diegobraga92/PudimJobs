import { HealthResponse } from '@/types';
import { apiClient } from './client';

export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/api/health');
  return data;
}
