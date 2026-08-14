import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  AdminService,
  AdminStats,
  AuditActions,
  AuditEntry,
  AuditFilters,
  LlmConfig,
  LlmConfigInput,
  LlmTestResult,
  QualityBySource,
  QualityJob,
  QualityOverview,
  ScrapeRun,
  SourceHealth,
} from '../../services/admin.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { AppIconName } from '../../shared/icons/icon-name';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

type AdminTab = 'overview' | 'sources' | 'quality' | 'dlq' | 'audit' | 'llm';

interface AdminTabDef {
  id: AdminTab;
  labelKey: string;
  icon: AppIconName;
}

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, AppIconComponent],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent implements OnInit {
  readonly tabs: AdminTabDef[] = [
    { id: 'overview', labelKey: 'admin.tabs.overview', icon: 'layout-dashboard' },
    { id: 'sources', labelKey: 'admin.tabs.sources', icon: 'globe' },
    { id: 'quality', labelKey: 'admin.tabs.quality', icon: 'chart' },
    { id: 'dlq', labelKey: 'admin.tabs.dlq', icon: 'circle-alert' },
    { id: 'audit', labelKey: 'admin.tabs.audit', icon: 'history' },
    { id: 'llm', labelKey: 'admin.tabs.llm', icon: 'sparkle' },
  ];
  activeTab: AdminTab = 'overview';

  stats: AdminStats | null = null;
  sources: SourceHealth[] = [];
  dlq: ScrapeRun[] = [];
  quality: QualityOverview | null = null;
  qualityBySource: QualityBySource[] = [];
  qualityJobs: QualityJob[] = [];
  showFlaggedOnly = false;
  auditEntries: AuditEntry[] = [];
  auditActions: AuditActions = { entity_types: [], actions: [] };
  auditAction = '';
  auditEntity = '';
  auditFrom = '';
  auditTo = '';
  expandedAuditId: string | null = null;
  error: string | null = null;
  loading = false;

  /** LLM configuration tab state. */
  llmConfig: LlmConfig | null = null;
  llmEnabled = false;
  llmBaseUrl = 'https://api.openai.com/v1';
  llmModel = 'gpt-4o-mini';
  llmApiKey = '';
  llmTestResult: LlmTestResult | null = null;
  llmSaving = false;
  llmTesting = false;

  constructor(
    private service: AdminService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {}

  ngOnInit(): void {
    this.refresh();
  }

  selectTab(tab: AdminTab): void {
    this.activeTab = tab;
    // Lazy-load the tab's data the first time it is opened.
    if (tab === 'quality' && this.quality === null) {
      this.loadQuality();
    }
    if (tab === 'sources' && this.sources.length === 0) {
      this.loadSourceHealth();
    }
    if (tab === 'dlq' && this.dlq.length === 0) {
      this.loadDlq();
    }
    if (tab === 'audit' && this.auditEntries.length === 0) {
      this.loadAudit();
      this.loadAuditActions();
    }
    if (tab === 'llm' && this.llmConfig === null) {
      this.loadLlm();
    }
  }

  /** Human-readable label for the active tab (used as the tabpanel's aria-label). */
  activeTabLabel(): string {
    const tab = this.tabs.find((item) => item.id === this.activeTab);
    return tab ? this.i18n.t(tab.labelKey) : this.activeTab;
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service.stats().subscribe({
      next: (stats) => (this.stats = stats),
      error: () => {
        this.error = this.i18n.t('errors.failedLoadStats');
        this.toast.error(this.i18n.t('errors.failedLoadStats'));
      },
    });
    this.loadSourceHealth();
    this.loadDlq();
    this.loadQuality();
    this.loadQualityJobs();
    this.loadAudit();
    this.loadAuditActions();
    this.loadLlm();
  }

  loadLlm(): void {
    this.service.getLlmConfig().subscribe({
      next: (config) => {
        this.llmConfig = config;
        this.llmEnabled = config.enabled;
        this.llmBaseUrl = config.base_url;
        this.llmModel = config.model;
        this.llmApiKey = '';
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadLlm');
        this.toast.error(this.i18n.t('errors.failedLoadLlm'));
      },
    });
  }

  saveLlm(): void {
    if (this.llmSaving) {
      return;
    }
    const payload: LlmConfigInput = {
      enabled: this.llmEnabled,
      base_url: this.llmBaseUrl.trim(),
      model: this.llmModel.trim(),
    };
    if (this.llmApiKey.trim()) {
      payload.api_key = this.llmApiKey.trim();
    }
    this.llmSaving = true;
    this.service.updateLlmConfig(payload).subscribe({
      next: (config) => {
        this.llmSaving = false;
        this.llmConfig = config;
        this.llmEnabled = config.enabled;
        this.llmBaseUrl = config.base_url;
        this.llmModel = config.model;
        this.llmApiKey = '';
        this.llmTestResult = null;
        this.toast.success(this.i18n.t('admin.llmSaved'));
      },
      error: () => {
        this.llmSaving = false;
        this.error = this.i18n.t('errors.failedSaveLlm');
        this.toast.error(this.i18n.t('errors.failedSaveLlm'));
      },
    });
  }

  testLlm(): void {
    if (this.llmTesting) {
      return;
    }
    this.llmTesting = true;
    this.llmTestResult = null;
    this.service.testLlmConfig().subscribe({
      next: (result) => {
        this.llmTesting = false;
        this.llmTestResult = result;
        if (result.ok) {
          this.toast.success(this.i18n.t('admin.llmOk'));
        } else {
          this.toast.error(result.error ? this.i18n.t('admin.llmFailedWith', { error: result.error }) : this.i18n.t('admin.llmFailed'));
        }
      },
      error: () => {
        this.llmTesting = false;
        this.error = this.i18n.t('errors.failedRunLlmTest');
        this.toast.error(this.i18n.t('errors.failedRunLlmTest'));
      },
    });
  }

  private loadSourceHealth(): void {
    this.service.sourceHealth().subscribe({
      next: (sources) => (this.sources = sources),
      error: () => {
        this.error = this.i18n.t('errors.failedLoadSourceHealth');
        this.toast.error(this.i18n.t('errors.failedLoadSourceHealth'));
      },
    });
  }

  private loadDlq(): void {
    this.service.dlq().subscribe({
      next: (dlq) => {
        this.dlq = dlq;
        this.loading = false;
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadDlq');
        this.loading = false;
        this.toast.error(this.i18n.t('errors.failedLoadDlq'));
      },
    });
  }

  private loadQuality(): void {
    this.service.qualityOverview().subscribe({
      next: (quality) => (this.quality = quality),
      error: () => {
        this.error = this.i18n.t('errors.failedLoadQuality');
        this.toast.error(this.i18n.t('errors.failedLoadQuality'));
      },
    });
    this.service.qualityBySource().subscribe({
      next: (bySource) => (this.qualityBySource = bySource),
      error: () => undefined,
    });
  }

  loadQualityJobs(): void {
    this.service.qualityJobs(this.showFlaggedOnly).subscribe({
      next: (jobs) => (this.qualityJobs = jobs),
      error: () => {
        this.error = this.i18n.t('errors.failedLoadQualityJobs');
        this.toast.error(this.i18n.t('errors.failedLoadQualityJobs'));
      },
    });
  }

  toggleFlaggedOnly(): void {
    this.showFlaggedOnly = !this.showFlaggedOnly;
    this.loadQualityJobs();
  }

  loadAudit(): void {
    const filters: AuditFilters = {
      action: this.auditAction || undefined,
      entity_type: this.auditEntity || undefined,
      date_from: this.auditFrom || undefined,
      date_to: this.auditTo || undefined,
    };
    this.service.auditLog(filters).subscribe({
      next: (entries) => (this.auditEntries = entries),
      error: () => {
        this.error = this.i18n.t('errors.failedLoadAudit');
        this.toast.error(this.i18n.t('errors.failedLoadAudit'));
      },
    });
  }

  loadAuditActions(): void {
    this.service.auditActions().subscribe({
      next: (actions) => (this.auditActions = actions),
      error: () => undefined,
    });
  }

  toggleAuditDetails(id: string): void {
    this.expandedAuditId = this.expandedAuditId === id ? null : id;
  }

  triggerScrape(sourceId: string): void {
    this.service.triggerScrape(sourceId).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('admin.scrapeTriggered'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedTriggerScrape');
        this.toast.error(this.i18n.t('errors.failedTriggerScrape'));
      },
    });
  }

  replay(runId: string): void {
    this.service.replay(runId).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('admin.runReplayed'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedReplay');
        this.toast.error(this.i18n.t('errors.failedReplay'));
      },
    });
  }
}

