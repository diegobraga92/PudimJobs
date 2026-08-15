import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { JobFilters, JobInput, JobSummary, JobsService } from '../../services/jobs.service';
import { ApplicationsService } from '../../services/applications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { OnboardingComponent } from '../../shared/onboarding/onboarding.component';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

const ONBOARDING_KEY = 'pudimjobs_onboarding_dismissed';

const PIPELINE_BADGES: Record<string, string> = {
  saved: 'badge-info',
  applied: 'badge-warning',
  interview: 'badge-warning',
  offer: 'badge-success',
  rejected: 'badge-danger',
};

@Component({
  selector: 'app-jobs',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppIconComponent, OnboardingComponent],
  templateUrl: './jobs.component.html',
  styleUrl: './jobs.component.scss',
})
export class JobsComponent implements OnInit {
  jobs: JobSummary[] = [];
  /** Starts true so the loading skeleton shows before the first search completes. */
  loading = true;
  error: string | null = null;

  /** Client-side pagination (the API returns the full per-user list). */
  page = 1;
  readonly pageSize = 12;

  onboardingDismissed = localStorage.getItem(ONBOARDING_KEY) === '1';

  /** Maps job id → pipeline status for jobs already in the application pipeline. */
  pipeline: Record<string, string> = {};

  showForm = false;
  searchForm;
  jobForm;

  /** When on, jobs the user already applied to are filtered out of the list. */
  hideApplied = false;
  /** When on, soft-hidden (dismissed) jobs are included so they can be restored. */
  showHidden = false;

  constructor(
    private fb: FormBuilder,
    private service: JobsService,
    private applications: ApplicationsService,
    private router: Router,
    private toast: ToastService,
    readonly i18n: I18nService
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
    this.loadPipeline();
  }

  /** Loads the pipeline status map so job cards can show "Applied / Interview / …". */
  private loadPipeline(): void {
    this.applications.list().subscribe({
      next: (applications) => {
        const map: Record<string, string> = {};
        for (const application of applications) {
          map[application.job_id] = application.status;
        }
        this.pipeline = map;
      },
      error: () => undefined,
    });
  }

  pipelineLabel(status: string): string {
    const key = `pipeline.${status}`;
    const label = this.i18n.t(key);
    return label === key ? this.i18n.t('pipeline.inPipeline') : label;
  }

  pipelineBadge(status: string): string {
    return PIPELINE_BADGES[status] ?? 'badge-info';
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
      include_hidden: this.showHidden || undefined,
      hide_applied: this.hideApplied || undefined,
    };
    this.service.list(filters).subscribe({
      next: (jobs) => {
        this.jobs = jobs;
        this.loading = false;
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadJobs');
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
      return this.i18n.t('jobs.zeroResults');
    }
    const start = (this.page - 1) * this.pageSize + 1;
    const end = Math.min(this.page * this.pageSize, this.jobs.length);
    return this.i18n.t('jobs.rangeLabel', { start, end, total: this.jobs.length });
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

  toggleHideApplied(): void {
    this.hideApplied = !this.hideApplied;
    this.search();
  }

  toggleShowHidden(): void {
    this.showHidden = !this.showHidden;
    this.search();
  }

  /** Hide/unhide from the card's corner action without opening the detail page. */
  hideToggle(event: Event, job: JobSummary): void {
    event.stopPropagation();
    if (job.hidden) {
      this.unhideJob(job);
    } else {
      this.hideJob(job);
    }
  }

  hideJob(job: JobSummary): void {
    this.service.hide(job.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('jobs.jobHidden'));
        this.search();
      },
      error: () => this.toast.error(this.i18n.t('errors.failedHideJob')),
    });
  }

  unhideJob(job: JobSummary): void {
    this.service.unhide(job.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('jobs.jobUnhidden'));
        this.search();
      },
      error: () => this.toast.error(this.i18n.t('errors.failedHideJob')),
    });
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
        this.toast.success(this.i18n.t('jobs.jobAdded'));
        this.search();
        this.loadPipeline();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedCreateJob');
        this.toast.error(this.i18n.t('errors.failedCreateJob'));
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
