import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import {
  JobCleanupRequest,
  JobCleanupResult,
  JobFilters,
  JobInput,
  JobSummary,
  JobsService,
} from '../../services/jobs.service';
import { ApplicationsService } from '../../services/applications.service';
import { Source, SourcesService, isJobSource } from '../../services/sources.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { AppModalComponent } from '../../shared/modal/modal.component';
import { OnboardingComponent } from '../../shared/onboarding/onboarding.component';
import { pipelineBadgeClass, pipelineLabelFor } from '../../shared/pipeline';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

const ONBOARDING_KEY = 'pudimjobs_onboarding_dismissed';

@Component({
  selector: 'app-jobs',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppIconComponent, OnboardingComponent, AppModalComponent],
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

  /** Bulk cleanup dialog (ADR 023): the form, the last preview and its sources. */
  showCleanup = false;
  cleanupForm;
  cleanupPreview: JobCleanupResult | null = null;
  cleanupRunning = false;
  cleanupSources: Source[] = [];

  /**
   * Sources known to the filter dropdown, loaded once on init. Empty while the
   * request is in flight (or when it failed): the list still works, it just
   * cannot be narrowed by board.
   */
  sources: Source[] = [];

  constructor(
    private fb: FormBuilder,
    private service: JobsService,
    private applications: ApplicationsService,
    private sourcesService: SourcesService,
    private route: ActivatedRoute,
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
      source_id: [''],
    });
    this.jobForm = this.fb.group({
      title: ['', Validators.required],
      company: ['', Validators.required],
      url: [''],
      posted_date: [''],
      tags: [''],
      description: [''],
    });
    this.cleanupForm = this.fb.group({
      older_than_days: [90],
      source_id: [''],
      include_with_applications: [false],
    });
  }

  ngOnInit(): void {
    // `/jobs?source_id=<id>` is the handoff used by the Sources page's "View
    // jobs" link: the filter is seeded before the first search, so the list
    // opens already narrowed. It seeds once — the select then owns the value.
    const sourceId = this.route.snapshot.queryParamMap.get('source_id');
    if (sourceId) {
      this.searchForm.patchValue({ source_id: sourceId });
    }
    this.loadSources();
    this.search();
    this.loadPipeline();
  }

  /** Sources offered by the filter dropdown (see `sources` for the fallback). */
  private loadSources(): void {
    this.sourcesService.list().subscribe({
      next: (sources) => (this.sources = sources),
      error: () => undefined,
    });
  }

  /**
   * Boards the dropdown offers: the ones that can own jobs. Manual watchlists
   * are never fetched, so listing them would only ever return nothing.
   */
  get sourceOptions(): Source[] {
    return this.sources.filter(isJobSource);
  }

  /**
   * Line shown above the results while the list is narrowed to one board. The
   * name comes from the loaded sources; an unknown id (a stale link, or a
   * failed sources request) falls back to a generic "narrowed" label.
   */
  get activeSourceLabel(): string {
    const id = this.searchForm.get('source_id')?.value as string;
    if (!id) {
      return '';
    }
    const name = this.sources.find((source) => source.id === id)?.name;
    return name
      ? this.i18n.t('jobs.sourceFilterActive', { name })
      : this.i18n.t('jobs.sourceFilterUnknown');
  }

  /** Drop the board narrowing from the filter bar's action. */
  clearSourceFilter(): void {
    this.searchForm.patchValue({ source_id: '' });
    this.search();
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
    return pipelineLabelFor(this.i18n, status);
  }

  pipelineBadge(status: string): string {
    return pipelineBadgeClass(status);
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
      source_id: string;
    };
    const filters: JobFilters = {
      q: value.q || undefined,
      company: value.company || undefined,
      date_from: value.date_from || undefined,
      date_to: value.date_to || undefined,
      tags: value.tags || undefined,
      source_id: value.source_id || undefined,
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

  /**
   * Open the bulk cleanup dialog. Nothing is deleted until the user previews
   * (`dry_run`) and then confirms; see ADR 023.
   */
  openCleanup(): void {
    this.cleanupForm.reset({
      older_than_days: 90,
      source_id: '',
      include_with_applications: false,
    });
    this.cleanupPreview = null;
    this.showCleanup = true;
    if (this.cleanupSources.length === 0) {
      this.sourcesService.list().subscribe({
        next: (sources) => (this.cleanupSources = sources),
        error: () => undefined,
      });
    }
  }

  closeCleanup(): void {
    this.showCleanup = false;
    this.cleanupPreview = null;
  }

  /** True only when the last preview would actually remove something. */
  get cleanupHasDeletions(): boolean {
    return (
      !!this.cleanupPreview && this.cleanupPreview.matched > this.cleanupPreview.protected
    );
  }

  /** Ask the API what a real run would delete, without deleting anything. */
  previewCleanup(): void {
    const payload = this.cleanupPayload(true);
    if (!payload) {
      return;
    }
    this.cleanupRunning = true;
    this.service.cleanup(payload).subscribe({
      next: (result) => {
        this.cleanupPreview = result;
        this.cleanupRunning = false;
      },
      error: () => {
        this.cleanupRunning = false;
        this.toast.error(this.i18n.t('errors.failedCleanupJobs'));
      },
    });
  }

  /** Delete the jobs the preview matched. */
  runCleanup(): void {
    const payload = this.cleanupPayload(false);
    if (!payload) {
      return;
    }
    this.cleanupRunning = true;
    this.service.cleanup(payload).subscribe({
      next: (result) => {
        this.cleanupRunning = false;
        this.showCleanup = false;
        this.cleanupPreview = null;
        this.toast.success(this.i18n.t('jobs.cleanup.done', { count: result.deleted }));
        this.search();
        this.loadPipeline();
      },
      error: () => {
        this.cleanupRunning = false;
        this.toast.error(this.i18n.t('errors.failedCleanupJobs'));
      },
    });
  }

  /** The two criteria are optional individually but an empty pair is refused. */
  private cleanupPayload(dryRun: boolean): JobCleanupRequest | null {
    const value = this.cleanupForm.value as {
      older_than_days: number | string | null;
      source_id: string;
      include_with_applications: boolean;
    };
    const days = value.older_than_days ? Number(value.older_than_days) : null;
    const sourceId = value.source_id || null;
    if (!days && !sourceId) {
      this.toast.error(this.i18n.t('jobs.cleanup.needCriteria'));
      return null;
    }
    return {
      older_than_days: days,
      source_id: sourceId,
      include_with_applications: value.include_with_applications ?? false,
      dry_run: dryRun,
    };
  }

  private parseTags(input: string): string[] {
    return input
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);
  }
}
