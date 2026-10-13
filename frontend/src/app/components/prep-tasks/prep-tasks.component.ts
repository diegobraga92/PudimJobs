import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { JobSummary, JobsService } from '../../services/jobs.service';
import { Application, ApplicationsService } from '../../services/applications.service';
import {
  PrepCategory,
  PrepStatus,
  PrepTask,
  PrepTaskInput,
  PrepTasksService,
} from '../../services/prep-tasks.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

const CATEGORIES: PrepCategory[] = ['technical', 'behavioral', 'research', 'logistics', 'other'];
const STATUSES: PrepStatus[] = ['pending', 'in_progress', 'done'];

@Component({
  selector: 'app-prep-tasks',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, AppIconComponent],
  templateUrl: './prep-tasks.component.html',
  styleUrl: './prep-tasks.component.scss',
})
export class PrepTasksComponent implements OnInit {
  tasks: PrepTask[] = [];
  jobs: JobSummary[] = [];
  applications: Application[] = [];
  categories = CATEGORIES;
  statuses = STATUSES;
  error: string | null = null;
  loading = false;

  showForm = false;
  editingId: string | null = null;
  taskForm;
  statusFilter: PrepStatus | '' = '';
  jobFilter = '';

  constructor(
    private fb: FormBuilder,
    private service: PrepTasksService,
    private jobsService: JobsService,
    private applicationsService: ApplicationsService,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {
    this.taskForm = this.fb.group({
      title: ['', Validators.required],
      category: ['other' as PrepCategory],
      status: ['pending' as PrepStatus],
      due_date: [''],
      job_id: [''],
      application_id: [''],
      notes: [''],
    });
  }

  ngOnInit(): void {
    this.loadJobs();
    this.loadApplications();
    this.refresh();
  }

  get pendingCount(): number {
    return this.tasks.filter((task) => task.status === 'pending').length;
  }

  get doneCount(): number {
    return this.tasks.filter((task) => task.status === 'done').length;
  }

  /** Jobs offered as optional task targets. */
  loadJobs(): void {
    this.jobsService.list().subscribe({
      next: (jobs) => (this.jobs = jobs),
      error: () => (this.jobs = []),
    });
  }

  /** Applications offered as optional task targets. */
  loadApplications(): void {
    this.applicationsService.list().subscribe({
      next: (applications) => (this.applications = applications),
      error: () => (this.applications = []),
    });
  }

  /** Display label for a linked application (`job — company`). */
  applicationLabel(applicationId: string): string {
    const application = this.applications.find((item) => item.id === applicationId);
    return application ? `${application.job_title} — ${application.job_company}` : '';
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service
      .list({
        status_filter: this.statusFilter || undefined,
        job_id: this.jobFilter || undefined,
      })
      .subscribe({
        next: (tasks) => {
          this.tasks = tasks;
          this.loading = false;
        },
        error: () => {
          this.error = this.i18n.t('errors.failedLoadPrepTasks');
          this.loading = false;
        },
      });
  }

  setStatusFilter(status: PrepStatus | ''): void {
    this.statusFilter = status;
    this.refresh();
  }

  setJobFilter(jobId: string): void {
    this.jobFilter = jobId;
    this.refresh();
  }

  openCreate(): void {
    this.editingId = null;
    this.taskForm.reset({
      title: '',
      category: 'other',
      status: 'pending',
      due_date: '',
      job_id: this.jobFilter,
      application_id: '',
      notes: '',
    });
    this.showForm = true;
  }

  openEdit(task: PrepTask): void {
    this.editingId = task.id;
    this.taskForm.setValue({
      title: task.title,
      category: task.category,
      status: task.status,
      due_date: task.due_date ?? '',
      job_id: task.job_id ?? '',
      application_id: task.application_id ?? '',
      notes: task.notes ?? '',
    });
    this.showForm = true;
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
  }

  save(): void {
    if (this.taskForm.invalid) {
      return;
    }
    const value = this.taskForm.value;
    const payload: PrepTaskInput = {
      title: (value.title ?? '').trim(),
      category: value.category as PrepCategory,
      status: value.status as PrepStatus,
      due_date: value.due_date || null,
      job_id: value.job_id || null,
      application_id: value.application_id || null,
      notes: value.notes || null,
    };
    const request = this.editingId
      ? this.service.update(this.editingId, payload)
      : this.service.create(payload);
    request.subscribe({
      next: () => {
        const wasEditing = !!this.editingId;
        this.showForm = false;
        this.editingId = null;
        this.toast.success(
          wasEditing ? this.i18n.t('prepTasks.updated') : this.i18n.t('prepTasks.created')
        );
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedSavePrepTask');
        this.toast.error(this.i18n.t('errors.failedSavePrepTask'));
      },
    });
  }

  /** Cycle a task pending → in progress → done → pending. */
  cycleStatus(task: PrepTask): void {
    const next = STATUSES[(STATUSES.indexOf(task.status) + 1) % STATUSES.length];
    this.service.update(task.id, { status: next }).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('prepTasks.moved', { status: this.statusLabel(next) }));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedUpdatePrepTask');
        this.toast.error(this.i18n.t('errors.failedUpdatePrepTask'));
      },
    });
  }

  async remove(task: PrepTask): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('prepTasks.deleteTitle'),
      message: this.i18n.t('prepTasks.deleteMessage', { title: task.title }),
      confirmLabel: this.i18n.t('common.delete'),
      cancelLabel: this.i18n.t('common.cancel'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(task.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('prepTasks.deleted'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeletePrepTask');
        this.toast.error(this.i18n.t('errors.failedDeletePrepTask'));
      },
    });
  }

  categoryLabel(category: PrepCategory): string {
    return this.i18n.t(`prepTasks.category.${category}`);
  }

  statusLabel(status: PrepStatus): string {
    return this.i18n.t(`prepTasks.status.${status}`);
  }

  statusBadgeClass(status: PrepStatus): string {
    if (status === 'done') {
      return 'badge-success';
    }
    return status === 'in_progress' ? 'badge-info' : 'badge-warning';
  }

  /** A dated, unfinished task whose due date is already in the past. */
  isOverdue(task: PrepTask): boolean {
    if (!task.due_date || task.status === 'done') {
      return false;
    }
    return task.due_date < new Date().toISOString().slice(0, 10);
  }
}
