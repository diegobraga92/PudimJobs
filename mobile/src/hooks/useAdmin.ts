import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  getAdminStats,
  getAuditActions,
  getAuditLog,
  getDlq,
  getLlmConfig,
  getQualityBySource,
  getQualityJobs,
  getQualityOverview,
  getSourceHealth,
  replayRun,
  testLlmConfig,
  triggerScrape,
  updateLlmConfig,
} from '@/api/admin';
import { AuditFilters, LlmConfigInput } from '@/types';

export function useAdminStats() {
  return useQuery({ queryKey: ['admin', 'stats'], queryFn: getAdminStats });
}

export function useSourceHealth() {
  return useQuery({ queryKey: ['admin', 'sources-health'], queryFn: getSourceHealth });
}

export function useDlq() {
  return useQuery({ queryKey: ['admin', 'dlq'], queryFn: getDlq });
}

export function useQualityOverview() {
  return useQuery({ queryKey: ['admin', 'quality', 'overview'], queryFn: getQualityOverview });
}

export function useQualityBySource() {
  return useQuery({ queryKey: ['admin', 'quality', 'by-source'], queryFn: getQualityBySource });
}

export function useQualityJobs(flaggedOnly: boolean) {
  return useQuery({
    queryKey: ['admin', 'quality', 'jobs', flaggedOnly],
    queryFn: () => getQualityJobs(flaggedOnly),
  });
}

export function useAuditLog(filters: AuditFilters) {
  return useQuery({
    queryKey: ['admin', 'audit', filters],
    queryFn: () => getAuditLog(filters),
  });
}

export function useAuditActions() {
  return useQuery({ queryKey: ['admin', 'audit', 'actions'], queryFn: getAuditActions });
}

export function useLlmConfig() {
  return useQuery({ queryKey: ['admin', 'llm'], queryFn: getLlmConfig });
}

export function useUpdateLlmConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LlmConfigInput) => updateLlmConfig(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['admin', 'llm'] }),
  });
}

export function useTestLlmConfig() {
  return useMutation({ mutationFn: () => testLlmConfig() });
}

export function useTriggerScrape() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => triggerScrape(sourceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin'] });
      void queryClient.invalidateQueries({ queryKey: ['sources'] });
    },
  });
}

export function useReplayRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => replayRun(runId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['admin'] }),
  });
}
