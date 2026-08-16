import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createCv,
  deleteCvVersion,
  deleteGeneratedCv,
  listCvs,
  listGeneratedCvs,
  updateCv,
} from '@/api/cv';
import { CVInput, CVStructure } from '@/types';

export function useCvVersions() {
  return useQuery({
    queryKey: ['cv'],
    queryFn: listCvs,
  });
}

export function useGeneratedCvs() {
  return useQuery({
    queryKey: ['cv', 'generated'],
    queryFn: listGeneratedCvs,
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

export function emptyCvStructure(): CVStructure {
  return { summary: '', experience: [], education: [], skills: [], projects: [] };
}
