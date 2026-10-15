import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  checkSource,
  createSource,
  deleteSource,
  deleteSourceAuth,
  getManualMetadata,
  getSourceAuth,
  listProviders,
  listSources,
  setSourceAvoided,
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

/** Cadence bounds + accepted keys for manual watchlist sources. */
export function useManualMetadata() {
  return useQuery({
    queryKey: ['sources', 'manual-metadata'],
    queryFn: getManualMetadata,
  });
}

export function useSourceAuth(id: string) {
  return useQuery({
    queryKey: ['sources', id, 'auth'],
    queryFn: () => getSourceAuth(id),
    enabled: !!id,
    retry: false,
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

/** Marks a manual watchlist source as checked by hand; schedules the next reminder. */
export function useCheckSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => checkSource(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['sources'] }),
  });
}

/**
 * Flags a source as avoided (never scraped, never reminded) or restores it.
 * The reason is optional: omitting it keeps whatever the source already has.
 */
export function useSetSourceAvoided() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, avoided, reason }: { id: string; avoided: boolean; reason?: string }) =>
      setSourceAvoided(id, avoided, reason),
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
