import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  AdminService,
  AdminStats,
  AuditActions,
  AuditEntry,
  AuditFilters,
  QualityBySource,
  QualityJob,
  QualityOverview,
  ScrapeRun,
  SourceHealth,
} from '../../services/admin.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { AppIconName } from '../../shared/icons/icon-name';
import { ToastService } from '../../shared/toast/toast.service';

type AdminTab = 'overview' | 'sources' | 'quality' | 'dlq' | 'audit';

interface AdminTabDef {
  id: AdminTab;
  label: string;
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
    { id: 'overview', label: 'Overview', icon: 'layout-dashboard' },
    { id: 'sources', label: 'Sources', icon: 'globe' },
    { id: 'quality', label: 'Quality', icon: 'chart' },
    { id: 'dlq', label: 'Dead-Letter Queue', icon: 'circle-alert' },
    { id: 'audit', label: 'Audit Log', icon: 'history' },
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

  constructor(
    private service: AdminService,
    private toast: ToastService
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
  }

  /** Human-readable label for the active tab (used as the tabpanel's aria-label). */
  activeTabLabel(): string {
    return this.tabs.find((tab) => tab.id === this.activeTab)?.label ?? this.activeTab;
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service.stats().subscribe({
      next: (stats) => (this.stats = stats),
      error: () => {
        this.error = 'Failed to load stats';
        this.toast.error('Failed to load stats.');
      },
    });
    this.loadSourceHealth();
    this.loadDlq();
    this.loadQuality();
    this.loadQualityJobs();
    this.loadAudit();
    this.loadAuditActions();
  }

  private loadSourceHealth(): void {
    this.service.sourceHealth().subscribe({
      next: (sources) => (this.sources = sources),
      error: () => {
        this.error = 'Failed to load source health';
        this.toast.error('Failed to load source health.');
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
        this.error = 'Failed to load DLQ';
        this.loading = false;
        this.toast.error('Failed to load dead-letter queue.');
      },
    });
  }

  private loadQuality(): void {
    this.service.qualityOverview().subscribe({
      next: (quality) => (this.quality = quality),
      error: () => {
        this.error = 'Failed to load quality overview';
        this.toast.error('Failed to load quality overview.');
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
        this.error = 'Failed to load quality jobs';
        this.toast.error('Failed to load quality jobs.');
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
        this.error = 'Failed to load audit log';
        this.toast.error('Failed to load audit log.');
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
        this.toast.success('Scrape triggered.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to trigger scrape';
        this.toast.error('Failed to trigger scrape.');
      },
    });
  }

  replay(runId: string): void {
    this.service.replay(runId).subscribe({
      next: () => {
        this.toast.success('Run replayed.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to replay run';
        this.toast.error('Failed to replay run.');
      },
    });
  }
}

