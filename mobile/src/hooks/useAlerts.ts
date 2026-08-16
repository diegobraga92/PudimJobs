import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createAlertRule, deleteAlertRule, listAlertRules, updateAlertRule } from '@/api/alerts';
import { AlertRuleInput } from '@/types';

export function useAlertRules() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: listAlertRules,
  });
}

export function useSaveAlertRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id?: string; payload: AlertRuleInput }) =>
      id ? updateAlertRule(id, payload) : createAlertRule(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useDeleteAlertRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAlertRule(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });
}
