import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createApplication,
  deleteApplication,
  listApplications,
  updateApplication,
} from '@/api/applications';
import { ApplicationInput, ApplicationStatus } from '@/types';

export function useApplications() {
  return useQuery({
    queryKey: ['applications'],
    queryFn: () => listApplications(),
  });
}

export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApplicationInput) => createApplication(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['applications'] });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useUpdateApplication(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<ApplicationInput>) => updateApplication(id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['applications'] }),
  });
}

export function useDeleteApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteApplication(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['applications'] }),
  });
}

/** Maps job id → pipeline status so job cards can show "Applied / Interview / …". */
export function usePipelineMap(): Record<string, ApplicationStatus> {
  const { data } = useApplications();
  const map: Record<string, ApplicationStatus> = {};
  for (const application of data ?? []) {
    map[application.job_id] = application.status;
  }
  return map;
}
