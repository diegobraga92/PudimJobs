import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';

import { ApplicationsService } from '../../services/applications.service';
import { JobDetail, JobsService, ParsedJD } from '../../services/jobs.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule, AppIconComponent],
  templateUrl: './job-detail.component.html',
  styleUrl: './job-detail.component.scss',
})
export class JobDetailComponent implements OnInit {
  job: JobDetail | null = null;
  parsed: ParsedJD | null = null;
  error: string | null = null;
  message: string | null = null;
  saving = false;
  tailoring = false;
  /** Starts true so the loading skeleton shows before the first fetch completes. */
  loading = true;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private jobs: JobsService,
    private applications: ApplicationsService,
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
      },
      error: () => {
        this.loading = false;
        this.error = this.i18n.t('errors.failedLoadJob');
      },
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
      next: () => {
        this.saving = false;
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

  tailor(): void {
    if (!this.job || this.tailoring) {
      return;
    }
    this.tailoring = true;
    this.message = null;
    this.jobs.tailor(this.job.id).subscribe({
      next: () => {
        this.tailoring = false;
        this.message = this.i18n.t('jobDetail.tailoringStarted');
        this.toast.success(this.i18n.t('jobDetail.tailoringStartedToast'));
      },
      error: () => {
        this.tailoring = false;
        this.error = this.i18n.t('jobDetail.failedTailoring');
        this.toast.error(this.i18n.t('jobDetail.failedTailoringToast'));
      },
    });
  }

  back(): void {
    this.router.navigate(['/jobs']);
  }
}


