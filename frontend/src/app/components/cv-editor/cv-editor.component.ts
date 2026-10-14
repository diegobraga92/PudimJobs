import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AuthService } from '../../services/auth.service';
import { CVStructure, CvExportFormat, CvService, CvTemplate, MasterCV } from '../../services/cv.service';
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
/** Master CV page. */
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
  error: string | null = null;
  message: string | null = null;
  saving = false;
  importing = false;
  exporting = false;
  exportTemplate: CvTemplate = 'classic';
  exportFormat: CvExportFormat = 'pdf';
  mode: 'edit' | 'preview' = 'edit';
  cvName = 'Your Name';

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

  /**
   * Export the current editor content as a PDF (classic or ATS-safe layout) or as
   * an editable DOCX. The layout only applies to the PDF: Word gets one plain
   * document, so the template select is disabled for DOCX.
   */
  exportCv(
    format: CvExportFormat = this.exportFormat,
    template: CvTemplate = this.exportTemplate,
  ): void {
    if (this.exporting) {
      return;
    }
    this.exporting = true;
    this.message = null;
    this.service.exportCv(this.buildStructure(), template, format).subscribe({
      next: (blob) => {
        this.exporting = false;
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download =
          format === 'docx' ? 'cv.docx' : template === 'ats' ? 'cv-ats.pdf' : 'cv.pdf';
        anchor.click();
        URL.revokeObjectURL(url);
        this.toast.success(this.i18n.t(format === 'docx' ? 'cv.docxExported' : 'cv.pdfExported'));
      },
      error: () => {
        this.exporting = false;
        const key = format === 'docx' ? 'errors.failedExportDocx' : 'errors.failedExportPdf';
        this.error = this.i18n.t(key);
        this.toast.error(this.i18n.t(key));
      },
    });
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

  /** Upload a PDF/DOCX/ODT file, parse it on the backend and pre-fill the editor so the user can review/edit before saving as a new version. */
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
        this.refreshVersions(true);
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
