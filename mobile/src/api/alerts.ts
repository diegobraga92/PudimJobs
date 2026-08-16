import { AlertRule, AlertRuleInput } from '@/types';
import { apiClient } from './client';

export async function listAlertRules(): Promise<AlertRule[]> {
  const { data } = await apiClient.get<AlertRule[]>('/api/alert-rules');
  return data;
}

export async function createAlertRule(payload: AlertRuleInput): Promise<AlertRule> {
  const { data } = await apiClient.post<AlertRule>('/api/alert-rules', payload);
  return data;
}

export async function updateAlertRule(id: string, payload: AlertRuleInput): Promise<AlertRule> {
  const { data } = await apiClient.put<AlertRule>(`/api/alert-rules/${id}`, payload);
  return data;
}

export async function deleteAlertRule(id: string): Promise<void> {
  await apiClient.delete(`/api/alert-rules/${id}`);
}
