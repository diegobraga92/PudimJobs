import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CdkDragDrop, DragDropModule } from '@angular/cdk/drag-drop';

import {
  Application,
  ApplicationStatus,
  ApplicationsService,
} from '../../services/applications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  saved: 'Saved',
  applied: 'Applied',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
};

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
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.refresh();
  }

  statusLabel(status: ApplicationStatus): string {
    return STATUS_LABELS[status];
  }

  /**
   * Handles a drag-and-drop between columns. CDK already moved the item between
   * the column data arrays; here we persist the new status and revert on error.
   */
  onDrop(event: CdkDragDrop<Application[]>): void {
    if (event.previousContainer === event.container) {
      // Intra-column reorder — not persisted.
      return;
    }
    const application = event.item.data as Application;
    const targetStatus = event.container.id as ApplicationStatus;
    this.service.update(application.id, { status: targetStatus }).subscribe({
      next: () => {
        this.toast.success(`Moved to ${STATUS_LABELS[targetStatus]}.`);
      },
      error: () => {
        this.toast.error('Failed to move application.');
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
        this.error = 'Failed to load applications';
        this.toast.error('Failed to load applications.');
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
        this.toast.success(`Moved to ${STATUS_LABELS[status]}.`);
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to update status';
        this.toast.error('Failed to update status.');
      },
    });
  }

  async remove(application: Application): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: 'Remove application?',
      message: `Remove "${application.job_title}" from your pipeline? This cannot be undone.`,
      confirmLabel: 'Remove',
      cancelLabel: 'Keep it',
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(application.id).subscribe({
      next: () => {
        this.selected = null;
        this.toast.success('Application removed.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to delete application';
        this.toast.error('Failed to delete application.');
      },
    });
  }
}
