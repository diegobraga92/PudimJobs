import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { AlertRule, AlertRuleInput, AlertsService } from '../../services/alerts.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';

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
    private toast: ToastService
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
        this.error = 'Failed to load alert rules';
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
        this.toast.success(wasEditing ? 'Alert updated.' : 'Alert created.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to save alert rule';
        this.toast.error('Failed to save alert rule.');
      },
    });
  }

  toggleActive(rule: AlertRule): void {
    this.service.update(rule.id, { active: !rule.active }).subscribe({
      next: () => {
        this.toast.success(rule.active ? 'Alert paused.' : 'Alert activated.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to update rule';
        this.toast.error('Failed to update rule.');
      },
    });
  }

  async remove(rule: AlertRule): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: 'Delete alert?',
      message: `Delete alert "${rule.name}"? You will stop receiving matching job notifications.`,
      confirmLabel: 'Delete',
      cancelLabel: 'Keep alert',
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(rule.id).subscribe({
      next: () => {
        this.toast.success('Alert deleted.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to delete alert rule';
        this.toast.error('Failed to delete alert rule.');
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
