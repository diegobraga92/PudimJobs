import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AlertRule, AlertRuleInput, AlertsService } from '../../services/alerts.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

@Component({
  selector: 'app-alerts',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AppIconComponent],
  templateUrl: './alerts.component.html',
  styleUrl: './alerts.component.scss',
})
export class AlertsComponent implements OnInit {
  rules: AlertRule[] = [];
  error: string | null = null;
  loading = false;

  showForm = false;
  editingId: string | null = null;
  alertForm;
  channelsText = 'in_app';

  constructor(
    private fb: FormBuilder,
    private service: AlertsService,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {
    this.alertForm = this.fb.group({
      name: ['', Validators.required],
      keywordsText: [''],
      companiesText: [''],
      tagsText: [''],
      remote_only: [false],
      min_years_experience: [''],
      active: [true],
    });
  }

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service.list().subscribe({
      next: (rules) => {
        this.rules = rules;
        this.loading = false;
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadAlerts');
        this.loading = false;
      },
    });
  }

  openCreate(): void {
    this.editingId = null;
    this.alertForm.reset({ name: '', remote_only: false, active: true });
    this.channelsText = 'in_app';
    this.showForm = true;
  }

  openEdit(rule: AlertRule): void {
    this.editingId = rule.id;
    this.alertForm.setValue({
      name: rule.name,
      keywordsText: rule.keywords.join(', '),
      companiesText: rule.companies.join(', '),
      tagsText: rule.tags.join(', '),
      remote_only: rule.remote_only,
      min_years_experience: String(rule.min_years_experience ?? ''),
      active: rule.active,
    });
    this.channelsText = rule.channels.join(', ');
    this.showForm = true;
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
  }

  save(): void {
    if (this.alertForm.invalid) {
      return;
    }
    const value = this.alertForm.value;
    const payload: AlertRuleInput = {
      name: value.name ?? '',
      keywords: this.parseList(value.keywordsText ?? ''),
      companies: this.parseList(value.companiesText ?? ''),
      tags: this.parseList(value.tagsText ?? ''),
      remote_only: value.remote_only ?? false,
      min_years_experience: value.min_years_experience
        ? Number(value.min_years_experience)
        : null,
      channels: this.parseList(this.channelsText),
      active: value.active ?? true,
    };
    const request = this.editingId
      ? this.service.update(this.editingId, payload)
      : this.service.create(payload);
    request.subscribe({
      next: () => {
        const wasEditing = !!this.editingId;
        this.showForm = false;
        this.editingId = null;
        this.toast.success(wasEditing ? this.i18n.t('alerts.updated') : this.i18n.t('alerts.created'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedSaveAlert');
        this.toast.error(this.i18n.t('errors.failedSaveAlert'));
      },
    });
  }

  toggleActive(rule: AlertRule): void {
    this.service.update(rule.id, { active: !rule.active }).subscribe({
      next: () => {
        this.toast.success(rule.active ? this.i18n.t('alerts.pausedToast') : this.i18n.t('alerts.activatedToast'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedUpdateRule');
        this.toast.error(this.i18n.t('errors.failedUpdateRule'));
      },
    });
  }

  async remove(rule: AlertRule): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('alerts.deleteTitle'),
      message: this.i18n.t('alerts.deleteMessage', { name: rule.name }),
      confirmLabel: this.i18n.t('common.delete'),
      cancelLabel: this.i18n.t('alerts.keepAlert'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(rule.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('alerts.deletedToast'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteAlert');
        this.toast.error(this.i18n.t('errors.failedDeleteAlert'));
      },
    });
  }

  private parseList(input: string): string[] {
    return input
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
}
