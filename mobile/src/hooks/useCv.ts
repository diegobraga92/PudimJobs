import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  atsScore,
  createCv,
  deleteCvVersion,
  deleteGeneratedCv,
  getGeneratedCv,
  listCvs,
  listGeneratedCvs,
  updateCv,
  updateGeneratedCv,
} from '@/api/cv';
import { AtsScoreInput, CVInput, CVStructure } from '@/types';

export function useCvVersions() {
  return useQuery({
    queryKey: ['cv'],
    queryFn: listCvs,
  });
}

/**
 * How often to re-check for a tailored artifact while a run is in flight.
 * Tailoring is a Celery job, so there is nothing to await: the artifact simply
 * appears as a new row.
 */
export const CV_POLL_INTERVAL_MS = 3000;

/**
 * Tailored CVs for a job, newest first.
 *
 * `pollUntilData` keeps re-querying while the list is still empty, so a queued
 * tailor run resolves the screen on its own instead of asking the user to press
 * *Refresh*; polling stops on the first non-empty answer.
 */
export function useGeneratedCvs(jobId?: string, options?: { pollUntilData?: boolean }) {
  return useQuery({
    queryKey: ['cv', 'generated', jobId ?? 'all'],
    queryFn: () => listGeneratedCvs(jobId),
    refetchInterval: (query) =>
      options?.pollUntilData && (query.state.data?.length ?? 0) === 0 ? CV_POLL_INTERVAL_MS : false,
  });
}

/** One tailored CV artifact (drives the artifact's own editor — ADR 016). */
export function useGeneratedCv(id: string) {
  return useQuery({
    queryKey: ['cv', 'generated', 'detail', id],
    queryFn: () => getGeneratedCv(id),
    enabled: !!id,
  });
}

/** Scores a CV, optionally caching the report on a tailored CV. */
export function useAtsScore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AtsScoreInput) => atsScore(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['cv', 'generated'] }),
  });
}

export function useSaveCv() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CVInput) => createCv(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cv'] });
    },
  });
}

export function useUpdateCv(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<CVInput>) => updateCv(id, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['cv'] }),
  });
}

export function useDeleteCvVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteCvVersion(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['cv'] }),
  });
}

export function useDeleteGeneratedCv() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteGeneratedCv(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['cv', 'generated'] }),
  });
}

/** Edits a tailored CV in place (never the master CV — ADR 016). */
export function useUpdateGeneratedCv(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (structure: CVStructure) => updateGeneratedCv(id, structure),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['cv', 'generated'] }),
  });
}

export function emptyCvStructure(): CVStructure {
  return { summary: '', experience: [], education: [], skills: [], projects: [] };
}
