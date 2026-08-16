import {
  AdminStats,
  AuditActions,
  AuditEntry,
  AuditFilters,
  LlmConfig,
  LlmConfigInput,
  LlmTestResult,
  QualityBySource,
  QualityJob,
  QualityOverview,
  ScrapeRun,
  SourceHealth,
} from '@/types';
import { apiClient } from './client';

export async function getAdminStats(): Promise<AdminStats> {
  const { data } = await apiClient.get<AdminStats>('/api/admin/stats');
  return data;
}

export async function getSourceHealth(): Promise<SourceHealth[]> {
  const { data } = await apiClient.get<SourceHealth[]>('/api/admin/sources/health');
  return data;
}

export async function getDlq(): Promise<ScrapeRun[]> {
  const { data } = await apiClient.get<ScrapeRun[]>('/api/admin/dlq');
  return data;
}

export async function replayRun(runId: string): Promise<{ replayed: boolean; run_id: string; source_id: string }> {
  const { data } = await apiClient.post(`/api/admin/dlq/${runId}/replay`, {});
  return data;
}

export async function triggerScrape(sourceId: string): Promise<{ enqueued: boolean; source_id: string }> {
  const { data } = await apiClient.post(`/api/admin/sources/${sourceId}/scrape`, {});
  return data;
}

export async function getQualityOverview(): Promise<QualityOverview> {
  const { data } = await apiClient.get<QualityOverview>('/api/admin/quality/overview');
  return data;
}

export async function getQualityBySource(): Promise<QualityBySource[]> {
  const { data } = await apiClient.get<QualityBySource[]>('/api/admin/quality/by-source');
  return data;
}

export async function getQualityJobs(flaggedOnly = false): Promise<QualityJob[]> {
  const { data } = await apiClient.get<QualityJob[]>('/api/admin/quality/jobs', {
    params: flaggedOnly ? { flagged_only: 'true' } : {},
  });
  return data;
}

export async function getAuditLog(filters: AuditFilters = {}): Promise<AuditEntry[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  const { data } = await apiClient.get<AuditEntry[]>(`/api/admin/audit${query ? `?${query}` : ''}`);
  return data;
}

export async function getAuditActions(): Promise<AuditActions> {
  const { data } = await apiClient.get<AuditActions>('/api/admin/audit/actions');
  return data;
}

export async function getLlmConfig(): Promise<LlmConfig> {
  const { data } = await apiClient.get<LlmConfig>('/api/admin/settings/llm');
  return data;
}

export async function updateLlmConfig(payload: LlmConfigInput): Promise<LlmConfig> {
  const { data } = await apiClient.put<LlmConfig>('/api/admin/settings/llm', payload);
  return data;
}

export async function testLlmConfig(): Promise<LlmTestResult> {
  const { data } = await apiClient.post<LlmTestResult>('/api/admin/settings/llm/test', {});
  return data;
}
