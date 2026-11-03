import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { Application, ApplicationsService } from '../../services/applications.service';
import { JobDetail, JobInput, JobsService, ParsedJD } from '../../services/jobs.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { AppModalComponent } from '../../shared/modal/modal.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { pipelineBadgeClass, pipelineLabelFor } from '../../shared/pipeline';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

/**
 * Job detail. A reading + triage surface: it shows what the posting asks for,
 * lets the user repair what the source failed to store, and tracks the job in
 * the pipeline.
 */
@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppModalComponent, AppIconComponent, RouterLink],
  templateUrl: './job-detail.component.html',
  styleUrl: './job-detail.component.scss',
})
export class JobDetailComponent implements OnInit {
  job: JobDetail | null = null;
  parsed: ParsedJD | null = null;
  /** Set once this job is in the pipeline — the page then links to its workspace. */
  application: Application | null = null;
  error: string | null = null;
  message: string | null = null;
  saving = false;
  /** Starts true so the loading skeleton shows before the first fetch completes. */
  loading = true;

  /** Manual edit dialog (ADR 026): how a posting that stored no description is repaired. */
  editOpen = false;
  editForm;
  /** Why the last save failed — shown inside the dialog, which stays open. */
  editError: string | null = null;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private fb: FormBuilder,
    private jobs: JobsService,
    private applications: ApplicationsService,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {
    this.editForm = this.fb.group({
      title: ['', Validators.required],
      company: ['', Validators.required],
      location: [''],
      url: [''],
      posted_date: [''],
      tags: [''],
      description: [''],
    });
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.router.navigate(['/jobs']);
      return;
    }
    this.jobs.get(id).subscribe({
      next: (job) => {
        this.job = job;
        this.loading = false;
        this.loadParsed();
        this.loadPipeline();
      },
      error: () => {
        this.loading = false;
        this.error = this.i18n.t('errors.failedLoadJob');
      },
    });
  }

  /** Resolves whether this job is already tracked, so the page can offer the application workspace instead of a duplicate "add" action. */
  private loadPipeline(): void {
    if (!this.job) {
      return;
    }
    const jobId = this.job.id;
    this.applications.list().subscribe({
      next: (applications) =>
        (this.application = applications.find((item) => item.job_id === jobId) ?? null),
      error: () => (this.application = null),
    });
  }

  private loadParsed(): void {
    if (!this.job) {
      return;
    }
    this.jobs.getParsed(this.job.id).subscribe({
      next: (parsed) => (this.parsed = parsed),
      error: () => (this.parsed = null),
    });
  }

  parseNow(): void {
    if (!this.job) {
      return;
    }
    this.jobs.parse(this.job.id).subscribe({
      next: () => {
        this.message = this.i18n.t('jobDetail.parsingQueued');
        this.parsed = null;
        this.toast.info(this.i18n.t('jobDetail.parsingQueuedToast'));
      },
      error: () => {
        this.error = this.i18n.t('errors.failedEnqueueParsing');
        this.toast.error(this.i18n.t('errors.failedEnqueueParsing'));
      },
    });
  }

  addApplication(): void {
    if (!this.job || this.saving) {
      return;
    }
    this.saving = true;
    this.message = null;
    this.applications.create({ job_id: this.job.id, status: 'saved' }).subscribe({
      next: (application) => {
        this.saving = false;
        this.application = application;
        this.message = this.i18n.t('jobDetail.addedToPipeline');
        this.toast.success(this.i18n.t('jobDetail.addedToPipeline'));
      },
      error: () => {
        this.saving = false;
        this.message = this.i18n.t('jobDetail.couldNotAdd');
        this.toast.error(this.i18n.t('jobDetail.couldNotAdd'));
      },
    });
  }

  /** Badge tone for this job's pipeline status (same mapping as the jobs list). */
  pipelineBadge(status: string): string {
    return pipelineBadgeClass(status);
  }

  /** Localised pipeline status label. */
  pipelineLabel(status: string): string {
    return pipelineLabelFor(this.i18n, status);
  }

  back(): void {
    this.router.navigate(['/jobs']);
  }

  /** Toggle the soft-hide flag for the current job. */
  toggleHidden(): void {
    if (!this.job || this.saving) {
      return;
    }
    this.saving = true;
    this.message = null;
    const target = !this.job.hidden;
    this.jobs.update(this.job.id, { hidden: target }).subscribe({
      next: (job) => {
        this.saving = false;
        this.job = job;
        this.message = target
          ? this.i18n.t('jobDetail.hidden')
          : this.i18n.t('jobDetail.unhidden');
        this.toast.success(
          target ? this.i18n.t('jobs.jobHidden') : this.i18n.t('jobs.jobUnhidden')
        );
      },
      error: () => {
        this.saving = false;
        this.error = this.i18n.t('errors.failedHideJob');
        this.toast.error(this.i18n.t('errors.failedHideJob'));
      },
    });
  }

  /** Open the edit dialog pre-filled with what the source actually stored. */
  openEdit(): void {
    if (!this.job) {
      return;
    }
    this.editForm.reset({
      title: this.job.title,
      company: this.job.company,
      location: this.job.location ?? '',
      url: this.job.url ?? '',
      posted_date: this.job.posted_date ?? '',
      tags: (this.job.tags ?? []).join(', '),
      description: this.job.description ?? '',
    });
    this.editError = null;
    this.editOpen = true;
  }

  closeEdit(): void {
    this.editOpen = false;
  }

  /**
   * Persist the edit. New description text means new requirements: the API drops
   * the parse derived from the old text and parsing is re-queued here, otherwise
   * tailoring would keep ranking skills against the text the source failed to
   * read (ADR 026).
   */
  saveEdit(): void {
    if (!this.job || this.saving || this.editForm.invalid) {
      return;
    }
    const value = this.editForm.value as {
      title: string;
      company: string;
      location: string;
      url: string;
      posted_date: string;
      tags: string;
      description: string;
    };
    const payload: JobInput = {
      title: value.title?.trim(),
      company: value.company?.trim(),
      location: value.location?.trim() || null,
      url: value.url?.trim() || null,
      // A cleared date input reads `""`, which the API's `date | None` rejects.
      posted_date: value.posted_date || null,
      tags: this.parseTags(value.tags ?? ''),
      description: value.description?.trim() || null,
    };
    const descriptionChanged = (payload.description ?? '') !== (this.job.description ?? '');
    this.saving = true;
    this.message = null;
    this.jobs.update(this.job.id, payload).subscribe({
      next: (job) => {
        this.saving = false;
        this.editOpen = false;
        this.editError = null;
        this.job = job;
        this.message = this.i18n.t('jobDetail.saved');
        this.toast.success(this.i18n.t('jobDetail.saved'));
        if (descriptionChanged) {
          this.parsed = null;
          this.jobs.parse(job.id).subscribe({ error: () => undefined });
        }
      },
      error: () => {
        // Keep the page and the dialog: `error` would replace the whole detail
        // view and take the half-typed description with it.
        this.saving = false;
        this.editError = this.i18n.t('errors.failedUpdateJob');
        this.toast.error(this.i18n.t('errors.failedUpdateJob'));
      },
    });
  }

  /**
   * Description markup for the page. Scraped rows carry HTML; hand-typed text is
   * escaped and its line breaks preserved, so a pasted posting does not collapse
   * into one paragraph.
   */
  get descriptionHtml(): string {
    const text = this.job?.description;
    if (!text) {
      return this.i18n.t('jobDetail.noDescription');
    }
    if (/<[a-z][\s\S]*>/i.test(text)) {
      return text;
    }
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    return escaped.replace(/\n/g, '<br>');
  }

  private parseTags(input: string): string[] {
    return input
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);
  }

  /** Hard-delete the job (and its applications) after confirmation. */
  async remove(): Promise<void> {
    if (!this.job) {
      return;
    }
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('jobDetail.deleteTitle'),
      message: this.i18n.t('jobDetail.deleteMessage', { title: this.job.title }),
      confirmLabel: this.i18n.t('common.delete'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.jobs.delete(this.job.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('jobDetail.deleted'));
        this.router.navigate(['/jobs']);
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteJob');
        this.toast.error(this.i18n.t('errors.failedDeleteJob'));
      },
    });
  }
}


