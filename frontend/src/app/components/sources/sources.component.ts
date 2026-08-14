import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { FormsModule } from '@angular/forms';

import {
  AuthTestResult,
  DiscoveryProvider,
  Source,
  SourceAuth,
  SourceAuthInput,
  SourceInput,
  SourcesService,
} from '../../services/sources.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ConfirmService } from '../../shared/confirm/confirm.service';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

@Component({
  selector: 'app-sources',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, AppIconComponent],
  templateUrl: './sources.component.html',
  styleUrl: './sources.component.scss',
})
export class SourcesComponent implements OnInit {
  sources: Source[] = [];
  loading = false;
  error: string | null = null;

  showForm = false;
  editingId: string | null = null;
  sourceForm;

  /** Aggregator adapter + JSON config (shown when type === 'aggregator'). */
  adapter = 'generic_html_list';
  configJson = '';

  /** Discovery provider + config (shown when type === 'discovery'). */
  providers: DiscoveryProvider[] = [];
  providersLoading = false;
  discoveryProvider = '';

  /** Per-source authentication panel state. */
  authSource: Source | null = null;
  authCurrent: SourceAuth | null = null;
  authType: SourceAuthInput['auth_type'] = 'none';
  authToken = '';
  authApiKey = '';
  authTestResult: AuthTestResult | null = null;
  authSaving = false;
  authTesting = false;

  constructor(
    private fb: FormBuilder,
    private service: SourcesService,
    private confirm: ConfirmService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {
    this.sourceForm = this.fb.group({
      name: ['', Validators.required],
      url: ['', [Validators.required, Validators.pattern(/^https?:\/\/.+/)]],
      type: ['career_page', Validators.required],
      rate_limit_seconds: [
        30,
        [Validators.required, Validators.min(0), Validators.max(86400)],
      ],
      respect_robots_txt: [true],
    });
  }

  ngOnInit(): void {
    this.refresh();
    this.loadProviders();
  }

  private loadProviders(): void {
    this.providersLoading = true;
    this.service.listProviders().subscribe({
      next: (providers) => {
        this.providers = providers;
        this.providersLoading = false;
      },
      error: () => {
        this.providersLoading = false;
      },
    });
  }

  /** The provider currently selected in the form (for hints/warnings). */
  get selectedProvider(): DiscoveryProvider | undefined {
    return this.providers.find((provider) => provider.name === this.discoveryProvider);
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service.list().subscribe({
      next: (sources) => {
        this.sources = sources;
        this.loading = false;
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadSources');
        this.loading = false;
      },
    });
  }

  openCreate(): void {
    this.editingId = null;
    this.sourceForm.reset({
      name: '',
      url: '',
      type: 'career_page',
      rate_limit_seconds: 30,
      respect_robots_txt: true,
    });
    this.adapter = 'generic_html_list';
    this.configJson = '';
    this.discoveryProvider = '';
    this.showForm = true;
  }

  openEdit(source: Source): void {
    this.editingId = source.id;
    this.sourceForm.setValue({
      name: source.name,
      url: source.url,
      type: source.type,
      rate_limit_seconds: source.rate_limit_seconds ?? 30,
      respect_robots_txt: source.respect_robots_txt ?? true,
    });
    this.adapter = (source.config?.['adapter'] as string) ?? 'generic_html_list';
    this.discoveryProvider = (source.config?.['provider'] as string) ?? '';
    if (source.type === 'discovery') {
      const rest = { ...(source.config ?? {}) };
      delete rest['provider'];
      this.configJson = Object.keys(rest).length ? JSON.stringify(rest, null, 2) : '';
    } else {
      this.configJson = source.config ? JSON.stringify(source.config, null, 2) : '';
    }
    this.showForm = true;
  }

  cancelForm(): void {
    this.showForm = false;
    this.editingId = null;
  }

  save(): void {
    if (this.sourceForm.invalid) {
      return;
    }
    const raw = this.sourceForm.value as {
      name: string;
      url: string;
      type: string;
      rate_limit_seconds: number;
      respect_robots_txt: boolean;
    };
    const payload: SourceInput = {
      name: raw.name,
      url: raw.url,
      type: raw.type,
      rate_limit_seconds: raw.rate_limit_seconds,
      respect_robots_txt: raw.respect_robots_txt,
    };
    if (raw.type === 'aggregator') {
      const config: Record<string, unknown> = { adapter: this.adapter };
      if (this.configJson.trim()) {
        try {
          Object.assign(config, JSON.parse(this.configJson.trim()));
        } catch {
          this.error = this.i18n.t('errors.invalidAggregatorJson');
          this.toast.error(this.i18n.t('errors.invalidAggregatorJson'));
          return;
        }
      }
      config['adapter'] = this.adapter;
      payload.config = config;
    }
    if (raw.type === 'discovery') {
      if (!this.discoveryProvider) {
        this.error = this.i18n.t('errors.chooseProvider');
        this.toast.error(this.i18n.t('errors.chooseProvider'));
        return;
      }
      const config: Record<string, unknown> = { provider: this.discoveryProvider };
      if (this.configJson.trim()) {
        try {
          Object.assign(config, JSON.parse(this.configJson.trim()));
        } catch {
          this.error = this.i18n.t('errors.invalidDiscoveryJson');
          this.toast.error(this.i18n.t('errors.invalidDiscoveryJson'));
          return;
        }
      }
      config['provider'] = this.discoveryProvider;
      payload.config = config;
    }
    const request = this.editingId
      ? this.service.update(this.editingId, payload)
      : this.service.create(payload);

    request.subscribe({
      next: () => {
        const wasEditing = !!this.editingId;
        this.showForm = false;
        this.editingId = null;
        this.toast.success(wasEditing ? this.i18n.t('sources.sourceUpdated') : this.i18n.t('sources.sourceAdded'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedSaveSource');
        this.toast.error(this.i18n.t('errors.failedSaveSource'));
      },
    });
  }

  async remove(source: Source): Promise<void> {
    const confirmed = await this.confirm.confirm({
      title: this.i18n.t('sources.deleteTitle'),
      message: this.i18n.t('sources.deleteMessage', { name: source.name }),
      confirmLabel: this.i18n.t('common.delete'),
      cancelLabel: this.i18n.t('sources.keepSource'),
      destructive: true,
    });
    if (!confirmed) {
      return;
    }
    this.service.delete(source.id).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('sources.sourceDeleted'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedDeleteSource');
        this.toast.error(this.i18n.t('errors.failedDeleteSource'));
      },
    });
  }

  /** Opens the authentication panel for a source (login-required boards). */
  openAuth(source: Source): void {
    this.authSource = source;
    this.authType = 'none';
    this.authToken = '';
    this.authApiKey = '';
    this.authTestResult = null;
    this.authSaving = false;
    this.authTesting = false;
    this.service.getAuth(source.id).subscribe({
      next: (auth) => {
        this.authCurrent = auth;
        this.authType = auth.auth_type;
      },
      error: () => {
        this.authCurrent = { auth_type: 'none', has_auth: false, updated_at: null };
      },
    });
  }

  closeAuth(): void {
    this.authSource = null;
    this.authCurrent = null;
    this.authTestResult = null;
  }

  saveAuth(): void {
    if (!this.authSource || this.authSaving) {
      return;
    }
    const payload: SourceAuthInput = { auth_type: this.authType };
    if (this.authType === 'token') {
      payload.token = this.authToken;
    }
    if (this.authType === 'api_key') {
      payload.api_key = this.authApiKey;
    }
    this.authSaving = true;
    this.service.updateAuth(this.authSource.id, payload).subscribe({
      next: (auth) => {
        this.authSaving = false;
        this.authCurrent = auth;
        this.authType = auth.auth_type;
        this.authToken = '';
        this.authApiKey = '';
        this.authTestResult = null;
        this.toast.success(this.i18n.t('sources.authSaved'));
      },
      error: () => {
        this.authSaving = false;
        this.error = this.i18n.t('errors.failedSaveAuth');
        this.toast.error(this.i18n.t('errors.failedSaveAuth'));
      },
    });
  }

  testAuth(): void {
    if (!this.authSource || this.authTesting) {
      return;
    }
    this.authTesting = true;
    this.authTestResult = null;
    this.service.testAuth(this.authSource.id).subscribe({
      next: (result) => {
        this.authTesting = false;
        this.authTestResult = result;
        if (result.ok) {
          this.toast.success(this.i18n.t('sources.authOk'));
        } else {
          this.toast.error(result.error ? this.i18n.t('sources.authFailedWith', { error: result.error }) : this.i18n.t('sources.authFailed'));
        }
      },
      error: () => {
        this.authTesting = false;
        this.error = this.i18n.t('errors.failedRunAuthTest');
        this.toast.error(this.i18n.t('errors.failedRunAuthTest'));
      },
    });
  }

  clearAuth(): void {
    if (!this.authSource) {
      return;
    }
    this.service.deleteAuth(this.authSource.id).subscribe({
      next: () => {
        this.authCurrent = { auth_type: 'none', has_auth: false, updated_at: null };
        this.authType = 'none';
        this.authToken = '';
        this.authApiKey = '';
        this.authTestResult = null;
        this.toast.success(this.i18n.t('sources.authCleared'));
      },
      error: () => {
        this.error = this.i18n.t('errors.failedClearAuth');
        this.toast.error(this.i18n.t('errors.failedClearAuth'));
      },
    });
  }
}
