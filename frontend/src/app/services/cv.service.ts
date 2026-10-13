import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
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
  full_name: string;
  email: string;
  phone: string;
  location: string;
  links: string[];
  summary: string;
  experience: ExperienceItem[];
  education: EducationItem[];
  skills: string[];
  projects: ProjectItem[];
  certifications: string[];
  languages: string[];
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
  structured_json: CVStructure | null;
  ats_score: number | null;
  ats_report: AtsReport | null;
}

/** One weighted component of an ATS score (mirrors `app/schemas/ats.py`). */
export interface AtsFactor {
  key: string;
  label: string;
  score: number;
  weight: number;
  detail: string;
}

export interface AtsReport {
  score: number;
  method: 'heuristic' | 'hybrid' | string;
  factors: AtsFactor[];
  matched_skills: string[];
  missing_skills: string[];
  recommendations: string[];
  warnings: string[];
  llm_summary: string | null;
}

export interface AtsScoreInput {
  cv: CVStructure;
  job_id?: string | null;
  job_title?: string | null;
  job_description?: string | null;
  generated_cv_id?: string | null;
}

/** Layout used when exporting a CV to PDF (see ADR 013). */
export type CvTemplate = 'classic' | 'ats';

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

  deleteVersion(id: string): Observable<void> {
    return this.http.delete<void>(`/api/cv/${id}`);
  }

  /** Tailored CVs, newest first; `jobId` scopes them to a single job. */
  generated(jobId?: string): Observable<GeneratedCV[]> {
    let params = new HttpParams();
    if (jobId) {
      params = params.set('job_id', jobId);
    }
    return this.http.get<GeneratedCV[]>('/api/cv/generated', { params });
  }

  getGenerated(id: string): Observable<GeneratedCV> {
    return this.http.get<GeneratedCV>(`/api/cv/generated/${id}`);
  }

  downloadPdf(id: string): Observable<Blob> {
    return this.http.get(`/api/cv/generated/${id}/pdf`, { responseType: 'blob' });
  }

  deleteGenerated(id: string): Observable<void> {
    return this.http.delete<void>(`/api/cv/generated/${id}`);
  }

  /**
   * Render an (optionally edited) CV structure to a PDF for download.
   * `template` selects `classic` (styled, default) or `ats` (plain, ATS-safe).
   */
  exportPdf(structure: CVStructure, template: CvTemplate = 'classic'): Observable<Blob> {
    const params = new HttpParams().set('template', template);
    return this.http.post('/api/cv/pdf', structure, { params, responseType: 'blob' });
  }

  /**
   * Score a CV structure against a stored job (`job_id`), a raw description
   * (`job_description`) and/or a bare `job_title`. Supplying `generated_cv_id`
   * caches the report on that generated CV so later reads are free.
   */
  atsScore(payload: AtsScoreInput): Observable<AtsReport> {
    return this.http.post<AtsReport>('/api/cv/ats-score', payload);
  }

  /**
   * Upload a PDF/DOCX/ODT CV and get it back as a structured CVStructure
   * (nothing is persisted — the caller pre-fills the editor for review).
   */
  parse(file: File): Observable<CVStructure> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<CVStructure>('/api/cv/parse', form);
  }
}
