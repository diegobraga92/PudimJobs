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

/** A labelled skills category, authored by the LLM variant. */
export interface SkillGroup {
  label: string;
  items: string[];
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
  /** Labelled skills categories from the LLM variant. Absent/empty on deterministic CVs, whose renderer groups the flat `skills` list by taxonomy instead. */
  skill_groups?: SkillGroup[];
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

/** How a tailored CV was produced (mirrors `app/models/enums.CVVariant`). */
export type CvVariant = 'rule' | 'llm';

/** A tailored CV artifact — its own document, not a master CV version. */
export interface GeneratedCV {
  id: string;
  job_id: string | null;
  job_title: string | null;
  job_company: string | null;
  source_master_cv_id: string | null;
  variant: CvVariant;
  created_at: string;
  updated_at: string;
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
  /** The deterministic baseline on its own (mirrors `score`). Optional because a report cached on an artifact before this field existed carries only `score`. */
  deterministic_score?: number | null;
  /** The ATS reviewer LLM's own 0..100 estimate, reported *beside* the baseline (never blended into it). `null` when no reviewer ran. */
  llm_score?: number | null;
  method: 'heuristic' | 'hybrid' | string;
  factors: AtsFactor[];
  matched_skills: string[];
  missing_skills: string[];
  recommendations: string[];
  warnings: string[];
  llm_summary: string | null;
  /** The LLM variant's own estimate of its rewrite (ADR 016); never blended in. */
  llm_self_score?: number | null;
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

/**
 * Download format for a tailored CV (see ADR 017). `pdf` is the canonical,
 * stored artifact; `docx` is rendered on demand from the same structure.
 */
export type CvExportFormat = 'pdf' | 'docx';

/**
 * Language a CV is exported in (see ADR 024). `en` is the stored language and
 * needs no LLM; any other language is translated on demand at export time.
 */
export type CvLanguage = 'en' | 'pt-BR';

/** What the export endpoints can produce right now (mirrors `app/schemas/master_cv.py`). */
export interface CvCapabilities {
  /** Only the non-default export languages need the LLM; `false` greys them out. */
  llm_enabled: boolean;
  export_languages: CvLanguage[];
  default_language: CvLanguage;
}

@Injectable({ providedIn: 'root' })
export class CvService {
  constructor(private http: HttpClient) {}

  /**
   * Whether translation is available and which languages the API offers. The
   * client cannot read admin settings, so this is the only way to know before
   * asking for a PT-BR export the server would refuse with a 409.
   */
  capabilities(): Observable<CvCapabilities> {
    return this.http.get<CvCapabilities>('/api/cv/capabilities');
  }

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

  /** Edit a tailored CV in place. The artifact owns its content (ADR 016), so this re-renders its PDF and clears the stale ATS cache; the master CV is never touched. */
  updateGenerated(id: string, structuredJson: CVStructure): Observable<GeneratedCV> {
    return this.http.put<GeneratedCV>(`/api/cv/generated/${id}`, {
      structured_json: structuredJson,
    });
  }

  /**
   * Download a tailored CV artifact. `format` picks the stored PDF (default) or
   * an editable DOCX rendered on demand from the artifact's own content;
   * `language` (ADR 024) downloads a fresh, LLM-translated copy — the stored PDF
   * is English, so a non-default language is always re-rendered.
   */
  downloadCv(
    id: string,
    format: CvExportFormat = 'pdf',
    language: CvLanguage = 'en',
  ): Observable<Blob> {
    const params = new HttpParams().set('format', format).set('language', language);
    return this.http.get(`/api/cv/generated/${id}/pdf`, { params, responseType: 'blob' });
  }

  deleteGenerated(id: string): Observable<void> {
    return this.http.delete<void>(`/api/cv/generated/${id}`);
  }

  /**
   * Render an (optionally edited) CV structure for download. `template` selects
   * `classic` (styled, default) or `ats` (plain, ATS-safe); `format` selects PDF
   * (default) or DOCX. The template is a PDF-only concern — DOCX always uses one
   * plain layout. `language` (ADR 024) translates the content on demand first.
   */
  exportCv(
    structure: CVStructure,
    template: CvTemplate = 'classic',
    format: CvExportFormat = 'pdf',
    language: CvLanguage = 'en',
  ): Observable<Blob> {
    const params = new HttpParams()
      .set('template', template)
      .set('format', format)
      .set('language', language);
    return this.http.post('/api/cv/pdf', structure, { params, responseType: 'blob' });
  }

  /** Score a CV structure against a stored job (`job_id`), a raw description (`job_description`) and/or a bare `job_title`. */
  atsScore(payload: AtsScoreInput): Observable<AtsReport> {
    return this.http.post<AtsReport>('/api/cv/ats-score', payload);
  }

  /** Upload a PDF/DOCX/ODT CV and get it back as a structured CVStructure (nothing is persisted — the caller pre-fills the editor for review). */
  parse(file: File): Observable<CVStructure> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<CVStructure>('/api/cv/parse', form);
  }
}
