import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AuthService } from '../../services/auth.service';
import {
  AtsReport,
  CVStructure,
  CvService,
  CvTemplate,
  GeneratedCV,
  MasterCV,
} from '../../services/cv.service';
import { JobSummary, JobsService } from '../../services/jobs.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { CvPreviewComponent } from '../../shared/cv-preview/cv-preview.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

interface ExperienceFormItem {
  company: string;
  title: string;
  start_date: string;
  end_date: string;
  bulletsText: string;
}

interface EducationFormItem {
  institution: string;
  degree: string;
  year: string;
}

interface ProjectFormItem {
  name: string;
  description: string;
  link: string;
}
@Component({
  selector: 'app-cv-editor',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppIconComponent, CvPreviewComponent],
  templateUrl: './cv-editor.component.html',
  styleUrl: './cv-editor.component.scss',
})
export class CvEditorComponent implements OnInit {
  cvForm;
  versions: MasterCV[] = [];
  generated: GeneratedCV[] = [];
  error: string | null = null;
  message: string | null = null;
  saving = false;
  importing = false;
  exporting = false;
  exportTemplate: CvTemplate = 'classic';
  mode: 'edit' | 'preview' = 'edit';
  cvName = 'Your Name';

  // ---- ATS check (see ADR 013) ------------------------------------------
  jobs: JobSummary[] = [];
  atsReport: AtsReport | null = null;
  atsLoading = false;
  atsJobId = '';
  atsJobTitle = '';
  atsJobDescription = '';
  /** Set while scoring a tailored CV, so the report is cached on it. */
  atsGeneratedId: string | null = null;

  /** Live CV structure derived from the form — drives the preview pane. */
  get previewCv(): CVStructure {
    return this.buildStructure();
  }

  /** Name shown on the preview/PDF: the typed one, else the email-derived one. */
  get displayName(): string {
    const typed = String(this.cvForm.value.fullName ?? '').trim();
    return typed || this.cvName;
  }

  constructor(
    private fb: FormBuilder,
    private service: CvService,
    private jobsService: JobsService,
    private auth: AuthService,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {
    this.cvForm = this.fb.group({
      fullName: [''],
      contactEmail: [''],
      phone: [''],
      location: [''],
      linksText: [''],
      summary: [''],
      skillsText: [''],
      certificationsText: [''],
      languagesText: [''],
      experience: this.fb.array([]),
      education: this.fb.array([]),
      projects: this.fb.array([]),
    });

    // Derive a display name from the signed-in user's email (e.g. "Jane Doe").
    this.auth.me().subscribe({
      next: (user) => {
        const local = user.email.split('@')[0] || '';
        this.cvName = local
          .split(/[._-]/)
          .filter(Boolean)
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join(' ');
      },
      error: () => undefined,
    });
  }

  ngOnInit(): void {
    this.refreshVersions(true);
    this.refreshGenerated();
    this.loadJobs();
  }

  /** Jobs available as ATS targets (best-effort; the panel works without one). */
  private loadJobs(): void {
    this.jobsService.list().subscribe({
      next: (jobs) => (this.jobs = jobs),
      error: () => (this.jobs = []),
    });
  }

  /** Reload master CV versions; optionally re-load the current one into the editor. */
  private refreshVersions(reloadForm: boolean): void {
    this.service.list().subscribe({
      next: (versions) => {
        this.versions = versions;
        if (reloadForm) {
          const current = versions.find((v) => v.is_current);
          if (current) {
            this.loadIntoForm(current.structured_json);
          } else {
            this.resetForm();
          }
        }
      },
      error: () => (this.error = this.i18n.t('errors.failedLoadCV')),
    });
  }

  /** Reload the tailored (generated) CV list. */
  private refreshGenerated(): void {
    this.service.generated().subscribe({
      next: (generated) => (this.generated = generated),
      error: () => undefined,
    });
  }

  private resetForm(): void {
    this.cvForm.patchValue({
      fullName: '',
      contactEmail: '',
      phone: '',
      location: '',
      linksText: '',
      summary: '',
      skillsText: '',
      certificationsText: '',
      languagesText: '',
    });
    this.experience.clear();
    this.education.clear();
    this.projects.clear();
  }

  downloadPdf(id: string): void {
    this.service.downloadPdf(id).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `tailored-cv-${id}.pdf`;
        anchor.click();
        URL.revokeObjectURL(url);
      },
      error: () => (this.error = this.i18n.t('errors.failedDownloadPdf')),
    });
  }

  /**
   * Load a tailored CV version into the editor so the user can modify it
   * before exporting a fresh PDF.
   */
  editGenerated(item: GeneratedCV): void {
    const structure = item.structured_json ?? this.masterCvVersion(item)?.structured_json;
    if (!structure) {
      this.error = this.i18n.t('errors.failedLoadCV');
      return;
    }
    this.loadIntoForm(structure);
    this.mode = 'edit';
    this.atsGeneratedId = item.id;
    this.message = this.i18n.t('cv.editingTailored', { job: item.job_title ?? '' });
    this.toast.success(
      this.i18n.t('cv.editingTailoredToast', { job: item.job_title ?? '' })
    );
  }

  /** Whether an "Edit" action is available for this generated CV. */
  canEditGenerated(item: GeneratedCV): boolean {
    return !!item.structured_json || this.masterCvVersion(item) !== undefined;
  }

  private masterCvVersion(item: GeneratedCV): MasterCV | undefined {
    if (!item.master_cv_id) {
      return undefined;
    }
    return this.versions.find((v) => v.id === item.master_cv_id);
  }

  /** Delete a master CV version (after confirmation). */
  async removeVersion(version: MasterCV): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('cv.deleteVersionTitle'),
      message: this.i18n.t('cv.deleteVersionMessage', { label: version.label }),
      confirmLabel: this.i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.deleteVersion(version.id).subscribe({
      next: () => {
        this.message = this.i18n.t('cv.versionDeleted');
        this.toast.success(this.i18n.t('cv.versionDeleted'));
        // Only re-load the editor when the current version went away, so an
        // in-progress draft isn't wiped by deleting an older version.
        this.refreshVersions(version.is_current);
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteCV');
        this.toast.error(this.i18n.t('errors.failedDeleteCV'));
      },
    });
  }

  /** Delete a tailored/generated CV (after confirmation). */
  async removeGenerated(item: GeneratedCV): Promise<void> {
    const title =
      item.job_title ?? item.job_company ?? this.i18n.t('cv.tailoredCvs');
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('cv.deleteTailoredTitle'),
      message: this.i18n.t('cv.deleteTailoredMessage', { title }),
      confirmLabel: this.i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.deleteGenerated(item.id).subscribe({
      next: () => {
        this.message = this.i18n.t('cv.tailoredDeleted');
        this.toast.success(this.i18n.t('cv.tailoredDeleted'));
        this.refreshGenerated();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteGeneratedCV');
        this.toast.error(this.i18n.t('errors.failedDeleteGeneratedCV'));
      },
    });
  }

  /** Export the current editor content as a PDF (classic or ATS-safe layout). */
  exportPdf(template: CvTemplate = this.exportTemplate): void {
    if (this.exporting) {
      return;
    }
    this.exporting = true;
    this.message = null;
    this.service.exportPdf(this.buildStructure(), template).subscribe({
      next: (blob) => {
        this.exporting = false;
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = template === 'ats' ? 'cv-ats.pdf' : 'cv.pdf';
        anchor.click();
        URL.revokeObjectURL(url);
        this.toast.success(this.i18n.t('cv.pdfExported'));
      },
      error: () => {
        this.exporting = false;
        this.error = this.i18n.t('errors.failedExportPdf');
        this.toast.error(this.i18n.t('errors.failedExportPdf'));
      },
    });
  }

  /** Pick (or clear) the stored job used as the ATS scoring target. */
  selectAtsJob(jobId: string): void {
    this.atsJobId = jobId;
    if (jobId) {
      // The backend reads the stored job's title/description itself.
      this.atsJobTitle = '';
      this.atsJobDescription = '';
    }
  }

  /** Run the ATS check for the current form content (ADR 013). */
  scoreAts(): void {
    if (this.atsLoading) {
      return;
    }
    this.atsLoading = true;
    this.service
      .atsScore({
        cv: this.buildStructure(),
        job_id: this.atsJobId || null,
        job_title: this.atsJobTitle.trim() || null,
        job_description: this.atsJobDescription.trim() || null,
        generated_cv_id: this.atsGeneratedId,
      })
      .subscribe({
        next: (report) => {
          this.atsLoading = false;
          this.atsReport = report;
          this.toast.success(
            this.i18n.t('cv.ats.scored', { score: report.score, method: report.method })
          );
          if (this.atsGeneratedId) {
            // The report was cached on the tailored CV — refresh its badge.
            this.refreshGenerated();
          }
        },
        error: () => {
          this.atsLoading = false;
          this.error = this.i18n.t('errors.failedAtsScore');
          this.toast.error(this.i18n.t('errors.failedAtsScore'));
        },
      });
  }

  clearAtsReport(): void {
    this.atsReport = null;
    this.atsGeneratedId = null;
    this.atsJobId = '';
    this.atsJobTitle = '';
    this.atsJobDescription = '';
  }

  /** Load a tailored CV into the editor and score it against its own job. */
  scoreGenerated(item: GeneratedCV): void {
    const structure = item.structured_json ?? this.masterCvVersion(item)?.structured_json;
    if (!structure) {
      this.error = this.i18n.t('errors.failedLoadCV');
      return;
    }
    this.loadIntoForm(structure as CVStructure);
    this.mode = 'edit';
    this.atsGeneratedId = item.id;
    this.atsJobId = item.job_id ?? '';
    this.atsJobTitle = item.job_title ?? '';
    this.atsJobDescription = '';
    this.atsReport = item.ats_report ?? null;
    this.scoreAts();
  }

  /** 0..100 score rendered as a bar width. */
  factorPercent(score: number): number {
    return Math.max(0, Math.min(100, Math.round(score * 100)));
  }

  /** Badge colour for an ATS score (green ≥ 75, amber ≥ 50, red below). */
  atsScoreClass(score: number): string {
    if (score >= 75) {
      return 'badge-success';
    }
    return score >= 50 ? 'badge-warning' : 'badge-danger';
  }

  atsMethodLabel(method: string): string {
    return method === 'hybrid' ? this.i18n.t('cv.ats.methodHybrid') : this.i18n.t('cv.ats.methodHeuristic');
  }

  get experience(): FormArray {
    return this.cvForm.get('experience') as FormArray;
  }

  get education(): FormArray {
    return this.cvForm.get('education') as FormArray;
  }

  get projects(): FormArray {
    return this.cvForm.get('projects') as FormArray;
  }

  addExperience(): void {
    this.experience.push(
      this.fb.group({
        company: ['', Validators.required],
        title: ['', Validators.required],
        start_date: [''],
        end_date: [''],
        bulletsText: [''],
      })
    );
  }

  removeExperience(index: number): void {
    this.experience.removeAt(index);
  }

  addEducation(): void {
    this.education.push(
      this.fb.group({
        institution: ['', Validators.required],
        degree: ['', Validators.required],
        year: [''],
      })
    );
  }

  removeEducation(index: number): void {
    this.education.removeAt(index);
  }

  addProject(): void {
    this.projects.push(
      this.fb.group({
        name: ['', Validators.required],
        description: [''],
        link: [''],
      })
    );
  }

  removeProject(index: number): void {
    this.projects.removeAt(index);
  }

  /**
   * Upload a PDF/DOCX/ODT file, parse it on the backend and pre-fill the editor
   * so the user can review/edit before saving as a new version.
   */
  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext !== 'pdf' && ext !== 'docx' && ext !== 'odt') {
      this.error = this.i18n.t('errors.unsupportedCvFile');
      this.toast.error(this.i18n.t('errors.unsupportedCvFile'));
      return;
    }
    this.importing = true;
    this.message = null;
    this.service.parse(file).subscribe({
      next: (structure) => {
        this.importing = false;
        this.loadIntoForm(structure);
        this.message = this.i18n.t('cv.imported');
        this.toast.success(this.i18n.t('cv.importedToast'));
      },
      error: () => {
        this.importing = false;
        this.error = this.i18n.t('errors.failedParseCV');
        this.toast.error(this.i18n.t('errors.failedParseCV'));
      },
    });
  }

  save(): void {
    if (this.saving) {
      return;
    }
    this.saving = true;
    this.message = null;
    this.service.create({ structured_json: this.buildStructure() }).subscribe({
      next: (saved) => {
        this.saving = false;
        this.message = this.i18n.t('cv.savedAs', { label: saved.label });
        this.toast.success(this.i18n.t('cv.savedAsToast', { label: saved.label }));
        this.ngOnInit();
      },
      error: () => {
        this.saving = false;
        this.error = this.i18n.t('errors.failedSaveCV');
        this.toast.error(this.i18n.t('errors.failedSaveCV'));
      },
    });
  }

  private loadIntoForm(cv: CVStructure): void {
    this.cvForm.patchValue({
      fullName: cv.full_name ?? '',
      contactEmail: cv.email ?? '',
      phone: cv.phone ?? '',
      location: cv.location ?? '',
      linksText: (cv.links ?? []).join(', '),
      summary: cv.summary ?? '',
      skillsText: (cv.skills ?? []).join(', '),
      certificationsText: (cv.certifications ?? []).join(', '),
      languagesText: (cv.languages ?? []).join(', '),
    });
    this.experience.clear();
    this.education.clear();
    this.projects.clear();

    for (const item of cv.experience ?? []) {
      this.experience.push(
        this.fb.group({
          company: item.company,
          title: item.title,
          start_date: item.start_date ?? '',
          end_date: item.end_date ?? '',
          bulletsText: (item.bullets ?? []).join('\n'),
        })
      );
    }
    for (const item of cv.education ?? []) {
      this.education.push(
        this.fb.group({
          institution: item.institution,
          degree: item.degree,
          year: item.year ?? '',
        })
      );
    }
    for (const item of cv.projects ?? []) {
      this.projects.push(
        this.fb.group({
          name: item.name,
          description: item.description ?? '',
          link: item.link ?? '',
        })
      );
    }
  }

  private buildStructure(): CVStructure {
    const value = this.cvForm.value;
    return {
      full_name: value.fullName ?? '',
      email: value.contactEmail ?? '',
      phone: value.phone ?? '',
      location: value.location ?? '',
      links: this.parseList(value.linksText ?? ''),
      summary: value.summary ?? '',
      skills: this.parseList(value.skillsText ?? ''),
      certifications: this.parseList(value.certificationsText ?? ''),
      languages: this.parseList(value.languagesText ?? ''),
      experience: (value.experience as ExperienceFormItem[]).map((item) => ({
        company: item.company,
        title: item.title,
        start_date: item.start_date || null,
        end_date: item.end_date || null,
        bullets: this.parseLines(item.bulletsText),
      })),
      education: (value.education as EducationFormItem[]).map((item) => ({
        institution: item.institution,
        degree: item.degree,
        year: item.year || null,
      })),
      projects: (value.projects as ProjectFormItem[]).map((item) => ({
        name: item.name,
        description: item.description || null,
        link: item.link || null,
      })),
    };
  }

  private parseList(input: string): string[] {
    return input
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }

  private parseLines(input: string): string[] {
    return input
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  }
}
