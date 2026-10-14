import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { Application, ApplicationsService } from '../../services/applications.service';
import { JobDetail, JobsService, ParsedJD } from '../../services/jobs.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { pipelineBadgeClass, pipelineLabelFor } from '../../shared/pipeline';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

/** Job detail. A reading + triage surface: it shows what the posting asks for and tracks the job in the pipeline. */
@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule, AppIconComponent, RouterLink],
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

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private jobs: JobsService,
    private applications: ApplicationsService,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {}

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


