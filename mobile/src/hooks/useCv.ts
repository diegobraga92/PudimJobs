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
import { AtsScoreInput, CVInput, CVStructure, CvVariant } from '@/types';
import { hasContent } from '@/utils/cv';

export function useCvVersions() {
  return useQuery({
    queryKey: ['cv'],
    queryFn: listCvs,
  });
}

/** How often to re-check for a tailored artifact while a run is in flight. */
export const CV_POLL_INTERVAL_MS = 3000;

/**
 * Tailored CVs for a job, newest first.
 *
 * `pollUntilData` keeps re-fetching while a tailor run is in flight.
 * `expectedVariants` (from the enqueue response) keeps that polling going until
 * *every* one of them has landed: the worker commits the deterministic variant
 * before the slow AI rewrite (ADR 016), so stopping at the first artifact would
 * strand the screen until a manual refresh. Without it, any artifact settles.
 */
export function useGeneratedCvs(
  jobId?: string,
  options?: { pollUntilData?: boolean; expectedVariants?: CvVariant[] | null },
) {
  const expected = options?.expectedVariants ?? null;
  return useQuery({
    queryKey: ['cv', 'generated', jobId ?? 'all'],
    queryFn: () => listGeneratedCvs(jobId),
    refetchInterval: (query) => {
      if (!options?.pollUntilData) {
        return false;
      }
      const usable = (query.state.data ?? []).filter(hasContent);
      if (!expected || expected.length === 0) {
        return usable.length === 0 ? CV_POLL_INTERVAL_MS : false;
      }
      const settled = expected.every((variant) => usable.some((item) => item.variant === variant));
      return settled ? false : CV_POLL_INTERVAL_MS;
    },
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
