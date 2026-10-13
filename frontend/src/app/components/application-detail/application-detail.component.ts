import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  ApplicationDetail,
  ApplicationStatus,
  ApplicationsService,
} from '../../services/applications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { CvPanelComponent } from '../../shared/cv-panel/cv-panel.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];

/**
 * Per-application workspace.
 *
 * One place for a single application: the job it targets (description + link),
 * the pipeline fields that used to live in the kanban modal (status, dates,
 * notes, retrospective) and — new — the CV panel holding the tailored CV and its
 * ATS check. Previously those lived apart on `/cv`, which now only manages the
 * master source document.
 */
@Component({
  selector: 'app-application-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, AppIconComponent, CvPanelComponent],
  templateUrl: './application-detail.component.html',
  styleUrl: './application-detail.component.scss',
})
export class ApplicationDetailComponent implements OnInit {
  readonly i18n = inject(I18nService);

  application: ApplicationDetail | null = null;
  statuses = STATUSES;
  loading = false;
  saving = false;
  error: string | null = null;
  notesDraft = '';
  lessonsDraft = '';
  appliedDateDraft = '';

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private service: ApplicationsService,
    private confirm: ConfirmService,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.error = this.i18n.t('errors.failedLoadApplication');
      return;
    }
    this.load(id);
  }

  private load(id: string): void {
    this.loading = true;
    this.error = null;
    this.service.get(id).subscribe({
      next: (application) => {
        this.loading = false;
        this.application = application;
        this.notesDraft = application.notes ?? '';
        this.lessonsDraft = application.lessons_learned ?? '';
        this.appliedDateDraft = application.applied_date ?? '';
      },
      error: () => {
        this.loading = false;
        this.error = this.i18n.t('errors.failedLoadApplication');
        this.toast.error(this.i18n.t('errors.failedLoadApplication'));
      },
    });
  }

  statusLabel(status: ApplicationStatus): string {
    return this.i18n.t(`pipeline.${status}`);
  }

  /** Persist the notes / retrospective / applied-date edits. */
  save(): void {
    const application = this.application;
    if (!application || this.saving) {
      return;
    }
    this.saving = true;
    this.service
      .update(application.id, {
        notes: this.notesDraft.trim() || null,
        lessons_learned: this.lessonsDraft.trim() || null,
        applied_date: this.appliedDateDraft || null,
      })
      .subscribe({
        next: (updated) => {
          this.saving = false;
          // Keep the detail payload (it also carries `job_description`).
          this.application = { ...application, ...updated };
          this.toast.success(this.i18n.t('applications.detailsSaved'));
        },
        error: () => {
          this.saving = false;
          this.error = this.i18n.t('errors.failedUpdateApplication');
          this.toast.error(this.i18n.t('errors.failedUpdateApplication'));
        },
      });
  }

  /** Move the application to another pipeline column. */
  changeStatus(status: ApplicationStatus): void {
    const application = this.application;
    if (!application || application.status === status) {
      return;
    }
    this.service.update(application.id, { status }).subscribe({
      next: (updated) => {
        this.application = { ...application, ...updated };
        this.toast.success(
          this.i18n.t('applications.movedTo', { status: this.i18n.t(`pipeline.${status}`) })
        );
      },
      error: () => {
        this.error = this.i18n.t('errors.failedUpdateStatus');
        this.toast.error(this.i18n.t('errors.failedUpdateStatus'));
      },
    });
  }

  /** Delete the application and return to the pipeline. */
  async remove(): Promise<void> {
    const application = this.application;
    if (!application) {
      return;
    }
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('applications.removeTitle'),
      message: this.i18n.t('applications.removeMessage', { title: application.job_title }),
      confirmLabel: this.i18n.t('common.remove'),
      cancelLabel: this.i18n.t('applications.keepIt'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(application.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('applications.removed'));
        this.router.navigate(['/applications']);
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteApplication');
        this.toast.error(this.i18n.t('errors.failedDeleteApplication'));
      },
    });
  }
}
