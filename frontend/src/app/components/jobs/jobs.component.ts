import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { JobFilters, JobInput, JobSummary, JobsService } from '../../services/jobs.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { OnboardingComponent } from '../../shared/onboarding/onboarding.component';
import { ToastService } from '../../shared/toast/toast.service';

const ONBOARDING_KEY = 'pudimjobs_onboarding_dismissed';

@Component({
  selector: 'app-jobs',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppIconComponent, OnboardingComponent],
  templateUrl: './jobs.component.html',
  styleUrl: './jobs.component.scss',
})
export class JobsComponent implements OnInit {
  jobs: JobSummary[] = [];
  loading = false;
  error: string | null = null;

  /** Client-side pagination (the API returns the full per-user list). */
  page = 1;
  readonly pageSize = 12;

  onboardingDismissed = localStorage.getItem(ONBOARDING_KEY) === '1';

  showForm = false;
  searchForm;
  jobForm;

  constructor(
    private fb: FormBuilder,
    private service: JobsService,
    private router: Router,
    private toast: ToastService
  ) {
    this.searchForm = this.fb.group({
      q: [''],
      company: [''],
      date_from: [''],
      date_to: [''],
      tags: [''],
    });
    this.jobForm = this.fb.group({
      title: ['', Validators.required],
      company: ['', Validators.required],
      url: [''],
      posted_date: [''],
      tags: [''],
      description: [''],
    });
  }

  ngOnInit(): void {
    this.search();
  }

  search(): void {
    this.loading = true;
    this.error = null;
    this.page = 1;
    const value = this.searchForm.value as {
      q: string;
      company: string;
      date_from: string;
      date_to: string;
      tags: string;
    };
    const filters: JobFilters = {
      q: value.q || undefined,
      company: value.company || undefined,
      date_from: value.date_from || undefined,
      date_to: value.date_to || undefined,
      tags: value.tags || undefined,
    };
    this.service.list(filters).subscribe({
      next: (jobs) => {
        this.jobs = jobs;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load jobs';
        this.loading = false;
      },
    });
  }

  /** Jobs visible on the current page. */
  get pagedJobs(): JobSummary[] {
    const start = (this.page - 1) * this.pageSize;
    return this.jobs.slice(start, start + this.pageSize);
  }

  get pageCount(): number {
    return Math.max(1, Math.ceil(this.jobs.length / this.pageSize));
  }

  get rangeLabel(): string {
    if (this.jobs.length === 0) {
      return '0 results';
    }
    const start = (this.page - 1) * this.pageSize + 1;
    const end = Math.min(this.page * this.pageSize, this.jobs.length);
    return `${start}–${end} of ${this.jobs.length}`;
  }

  goToPage(p: number): void {
    if (p < 1 || p > this.pageCount) {
      return;
    }
    this.page = p;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  dismissOnboarding(): void {
    this.onboardingDismissed = true;
    localStorage.setItem(ONBOARDING_KEY, '1');
  }

  openCreate(): void {
    this.jobForm.reset();
    this.showForm = true;
  }

  cancelForm(): void {
    this.showForm = false;
  }

  save(): void {
    if (this.jobForm.invalid) {
      return;
    }
    const value = this.jobForm.value as {
      title: string;
      company: string;
      url: string;
      posted_date: string;
      tags: string;
      description: string;
    };
    const payload: JobInput = {
      title: value.title,
      company: value.company,
      url: value.url,
      posted_date: value.posted_date,
      description: value.description,
      tags: this.parseTags(value.tags),
    };
    this.service.create(payload).subscribe({
      next: () => {
        this.showForm = false;
        this.toast.success('Job added successfully.');
        this.search();
      },
      error: () => {
        this.error = 'Failed to create job';
        this.toast.error('Failed to create job.');
      },
    });
  }

  open(id: string): void {
    this.router.navigate(['/jobs', id]);
  }

  private parseTags(input: string): string[] {
    return input
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);
  }
}
