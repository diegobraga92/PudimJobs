import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ExperienceItem {
  company: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  bullets: string[];
}

export interface EducationItem {
  institution: string;
  degree: string;
  year: string | null;
}

export interface ProjectItem {
  name: string;
  description: string | null;
  link: string | null;
}

export interface CVStructure {
  summary: string;
  experience: ExperienceItem[];
  education: EducationItem[];
  skills: string[];
  projects: ProjectItem[];
}

export interface MasterCV {
  id: string;
  label: string;
  version: number;
  is_current: boolean;
  structured_json: CVStructure;
  created_at: string;
  updated_at: string;
}

export interface CVInput {
  structured_json: CVStructure;
  label?: string;
}

export interface GeneratedCV {
  id: string;
  master_cv_id: string | null;
  job_id: string | null;
  job_title: string | null;
  job_company: string | null;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class CvService {
  constructor(private http: HttpClient) {}

  list(): Observable<MasterCV[]> {
    return this.http.get<MasterCV[]>('/api/cv');
  }

  getCurrent(): Observable<MasterCV> {
    return this.http.get<MasterCV>('/api/cv/current');
  }

  create(payload: CVInput): Observable<MasterCV> {
    return this.http.post<MasterCV>('/api/cv', payload);
  }

  update(id: string, payload: Partial<CVInput>): Observable<MasterCV> {
    return this.http.put<MasterCV>(`/api/cv/${id}`, payload);
  }

  generated(): Observable<GeneratedCV[]> {
    return this.http.get<GeneratedCV[]>('/api/cv/generated');
  }

  downloadPdf(id: string): Observable<Blob> {
    return this.http.get(`/api/cv/generated/${id}/pdf`, { responseType: 'blob' });
  }
}
