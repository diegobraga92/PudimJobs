import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AuthService } from '../../services/auth.service';
import { CVStructure, CvService, GeneratedCV, MasterCV } from '../../services/cv.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { CvPreviewComponent } from '../../shared/cv-preview/cv-preview.component';
import { ToastService } from '../../shared/toast/toast.service';

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
  mode: 'edit' | 'preview' = 'edit';
  cvName = 'Your Name';

  /** Live CV structure derived from the form — drives the preview pane. */
  get previewCv(): CVStructure {
    return this.buildStructure();
  }

  constructor(
    private fb: FormBuilder,
    private service: CvService,
    private auth: AuthService,
    private toast: ToastService
  ) {
    this.cvForm = this.fb.group({
      summary: [''],
      skillsText: [''],
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
    this.service.list().subscribe({
      next: (versions) => {
        this.versions = versions;
        const current = versions.find((v) => v.is_current);
        if (current) {
          this.loadIntoForm(current.structured_json);
        }
      },
      error: () => (this.error = 'Failed to load CV'),
    });
    this.service.generated().subscribe({
      next: (generated) => (this.generated = generated),
      error: () => undefined,
    });
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
      error: () => (this.error = 'Failed to download PDF'),
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

  save(): void {
    if (this.saving) {
      return;
    }
    this.saving = true;
    this.message = null;
    this.service.create({ structured_json: this.buildStructure() }).subscribe({
      next: (saved) => {
        this.saving = false;
        this.message = `Saved as ${saved.label}.`;
        this.toast.success(`Master CV saved as ${saved.label}.`);
        this.ngOnInit();
      },
      error: () => {
        this.saving = false;
        this.error = 'Failed to save CV';
        this.toast.error('Failed to save CV.');
      },
    });
  }

  private loadIntoForm(cv: CVStructure): void {
    this.cvForm.patchValue({
      summary: cv.summary ?? '',
      skillsText: (cv.skills ?? []).join(', '),
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
      summary: value.summary ?? '',
      skills: this.parseList(value.skillsText ?? ''),
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
