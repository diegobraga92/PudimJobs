import { CVInput, CVStructure, GeneratedCV, MasterCV } from '@/types';
import { apiClient } from './client';

export async function listCvs(): Promise<MasterCV[]> {
  const { data } = await apiClient.get<MasterCV[]>('/api/cv');
  return data;
}

export async function createCv(payload: CVInput): Promise<MasterCV> {
  const { data } = await apiClient.post<MasterCV>('/api/cv', payload);
  return data;
}

export async function updateCv(id: string, payload: Partial<CVInput>): Promise<MasterCV> {
  const { data } = await apiClient.put<MasterCV>(`/api/cv/${id}`, payload);
  return data;
}

export async function deleteCvVersion(id: string): Promise<void> {
  await apiClient.delete(`/api/cv/${id}`);
}

export async function listGeneratedCvs(): Promise<GeneratedCV[]> {
  const { data } = await apiClient.get<GeneratedCV[]>('/api/cv/generated');
  return data;
}

/** Downloads a generated/tailored CV PDF (returns the raw blob). */
export async function downloadGeneratedPdf(id: string): Promise<unknown> {
  const { data } = await apiClient.get(`/api/cv/generated/${id}/pdf`, {
    responseType: 'blob',
  });
  return data;
}

export async function deleteGeneratedCv(id: string): Promise<void> {
  await apiClient.delete(`/api/cv/generated/${id}`);
}

/** Renders a CV structure to a PDF (returns the raw blob). */
export async function exportPdf(structure: CVStructure): Promise<unknown> {
  const { data } = await apiClient.post(`/api/cv/pdf`, structure, {
    responseType: 'blob',
  });
  return data;
}

/**
 * Uploads a PDF/DOCX CV and returns the parsed CVStructure (nothing is
 * persisted — the caller pre-fills the editor for review).
 */
export async function parseCvFile(uri: string, name: string): Promise<CVStructure> {
  const formData = new FormData();
  // RN FormData file entry (the type cast keeps TS happy about the blob shape).
  formData.append('file', { uri, name, type: 'application/octet-stream' } as unknown as Blob);
  const { data } = await apiClient.post<CVStructure>('/api/cv/parse', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}
