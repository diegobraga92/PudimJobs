import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CdkDragDrop, DragDropModule, moveItemInArray, transferArrayItem } from '@angular/cdk/drag-drop';

import {
  Application,
  ApplicationStatus,
  ApplicationsService,
} from '../../services/applications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];

@Component({
  selector: 'app-applications',
  standalone: true,
  imports: [CommonModule, DragDropModule, AppIconComponent],
  templateUrl: './applications.component.html',
  styleUrl: './applications.component.scss',
})
export class ApplicationsComponent implements OnInit {
  columns: Record<ApplicationStatus, Application[]> = {
    saved: [],
    applied: [],
    interview: [],
    offer: [],
    rejected: [],
  };
  statuses = STATUSES;
  selected: Application | null = null;
  error: string | null = null;
  total = 0;

  constructor(
    private service: ApplicationsService,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {}

  ngOnInit(): void {
    this.refresh();
  }

  statusLabel(status: ApplicationStatus): string {
    return this.i18n.t(`pipeline.${status}`);
  }

  /**
   * Handles a drag-and-drop between columns. CDK does not mutate the column data
   * arrays itself, so we move the item between them here; the new status is
   * persisted through PUT /api/applications/:id and reverted on error.
   */
  onDrop(event: CdkDragDrop<Application[]>): void {
    if (event.previousContainer === event.container) {
      // Intra-column reorder — visual only, not persisted.
      moveItemInArray(event.container.data, event.previousIndex, event.currentIndex);
      return;
    }
    const application = event.item.data as Application;
    const targetStatus = event.container.id as ApplicationStatus;

    transferArrayItem(
      event.previousContainer.data,
      event.container.data,
      event.previousIndex,
      event.currentIndex,
    );
    application.status = targetStatus;

    this.service.update(application.id, { status: targetStatus }).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('applications.movedTo', { status: this.i18n.t(`pipeline.${targetStatus}`) }));
      },
      error: () => {
        this.toast.error(this.i18n.t('errors.failedMoveApplication'));
        this.refresh();
      },
    });
  }

  refresh(): void {
    this.error = null;
    this.service.list().subscribe({
      next: (applications) => {
        for (const status of STATUSES) {
          this.columns[status] = [];
        }
        this.total = applications.length;
        for (const application of applications) {
          this.columns[application.status].push(application);
        }
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadApplications');
        this.toast.error(this.i18n.t('errors.failedLoadApplications'));
      },
    });
  }

  select(application: Application): void {
    this.selected = application;
  }

  closeDetail(): void {
    this.selected = null;
  }

  changeStatus(status: ApplicationStatus): void {
    if (!this.selected) {
      return;
    }
    const app = this.selected;
    this.service.update(app.id, { status }).subscribe({
      next: () => {
        this.selected = null;
        this.toast.success(this.i18n.t('applications.movedTo', { status: this.i18n.t(`pipeline.${status}`) }));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedUpdateStatus');
        this.toast.error(this.i18n.t('errors.failedUpdateStatus'));
      },
    });
  }

  async remove(application: Application): Promise<void> {
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
        this.selected = null;
        this.toast.success(this.i18n.t('applications.removed'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteApplication');
        this.toast.error(this.i18n.t('errors.failedDeleteApplication'));
      },
    });
  }
}
