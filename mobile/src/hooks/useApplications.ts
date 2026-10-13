import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createApplication,
  deleteApplication,
  getApplication,
  listApplications,
  updateApplication,
} from '@/api/applications';
import { ApplicationInput, ApplicationStatus, Application } from '@/types';

export function useApplications() {
  return useQuery({
    queryKey: ['applications'],
    queryFn: () => listApplications(),
  });
}

/**
 * The application tracking `jobId`, if the job is already in the pipeline.
 * Reads the cached list, so creating an application (which invalidates
 * `['applications']`) makes the job detail swap its "add" action for a link.
 */
export function useApplicationForJob(jobId: string): Application | null {
  const { data } = useApplications();
  return useMemo(
    () => (data ?? []).find((application) => application.job_id === jobId) ?? null,
    [data, jobId],
  );
}

export function useApplication(id: string) {
  return useQuery({
    queryKey: ['applications', id],
    queryFn: () => getApplication(id),
    enabled: !!id,
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
  return useMemo(() => {
    const map: Record<string, ApplicationStatus> = {};
    for (const application of data ?? []) {
      map[application.job_id] = application.status;
    }
    return map;
  }, [data]);
}
