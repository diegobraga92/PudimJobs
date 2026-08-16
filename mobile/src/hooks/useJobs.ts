import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createJob,
  deleteJob,
  getJob,
  getParsed,
  hideJob,
  listJobs,
  parseJob,
  tailorCv,
  unhideJob,
  updateJob,
} from '@/api/jobs';
import { EnqueueResult, JobCreateInput, JobFilters, JobUpdateInput } from '@/types';

export function useJobs(filters: JobFilters) {
  return useQuery({
    queryKey: ['jobs', filters],
    queryFn: () => listJobs(filters),
    placeholderData: keepPreviousData,
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['jobs', id],
    queryFn: () => getJob(id),
    enabled: !!id,
  });
}

export function useParsedJd(id: string, enabled = false) {
  return useQuery({
    queryKey: ['jobs', id, 'parsed'],
    queryFn: () => getParsed(id),
    enabled,
    retry: false,
  });
}

export function useCreateJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JobCreateInput) => createJob(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

export function useUpdateJob(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JobUpdateInput) => updateJob(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useHideJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => hideJob(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  });
}

export function useUnhideJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unhideJob(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  });
}

export function useDeleteJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteJob(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['applications'] });
    },
  });
}

export function useParseJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string): Promise<EnqueueResult> => parseJob(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ['jobs', id, 'parsed'] });
    },
  });
}

export function useTailorCv() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, cvId }: { id: string; cvId?: string }) => tailorCv(id, cvId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cv', 'generated'] });
    },
  });
}
