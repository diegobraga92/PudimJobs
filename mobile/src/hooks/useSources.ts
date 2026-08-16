import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createSource,
  deleteSource,
  deleteSourceAuth,
  listProviders,
  listSources,
  testSourceAuth,
  updateSource,
  updateSourceAuth,
} from '@/api/sources';
import { SourceAuthInput, SourceInput } from '@/types';

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: listSources,
  });
}

export function useProviders() {
  return useQuery({
    queryKey: ['sources', 'providers'],
    queryFn: listProviders,
  });
}

export function useSaveSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id?: string; payload: SourceInput }) =>
      id ? updateSource(id, payload) : createSource(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['sources'] }),
  });
}

export function useDeleteSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSource(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['sources'] }),
  });
}

export function useSaveSourceAuth(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SourceAuthInput) => updateSourceAuth(id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['sources', id, 'auth'] }),
  });
}

export function useClearSourceAuth(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteSourceAuth(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['sources', id, 'auth'] }),
  });
}

export function useTestSourceAuth(id: string) {
  return useMutation({
    mutationFn: () => testSourceAuth(id),
  });
}
