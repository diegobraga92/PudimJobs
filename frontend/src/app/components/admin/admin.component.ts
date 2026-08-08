import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

import {
  AdminService,
  AdminStats,
  QualityBySource,
  QualityJob,
  QualityOverview,
  ScrapeRun,
  SourceHealth,
} from '../../services/admin.service';

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent implements OnInit {
  stats: AdminStats | null = null;
  sources: SourceHealth[] = [];
  dlq: ScrapeRun[] = [];
  quality: QualityOverview | null = null;
  qualityBySource: QualityBySource[] = [];
  qualityJobs: QualityJob[] = [];
  showFlaggedOnly = false;
  error: string | null = null;
  loading = false;

  constructor(private service: AdminService) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service.stats().subscribe({
      next: (stats) => (this.stats = stats),
      error: () => (this.error = 'Failed to load stats'),
    });
    this.service.sourceHealth().subscribe({
      next: (sources) => (this.sources = sources),
      error: () => (this.error = 'Failed to load source health'),
    });
    this.service.dlq().subscribe({
      next: (dlq) => {
        this.dlq = dlq;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load DLQ';
        this.loading = false;
      },
    });
    this.service.qualityOverview().subscribe({
      next: (quality) => (this.quality = quality),
      error: () => (this.error = 'Failed to load quality overview'),
    });
    this.service.qualityBySource().subscribe({
      next: (bySource) => (this.qualityBySource = bySource),
      error: () => undefined,
    });
    this.loadQualityJobs();
  }

  loadQualityJobs(): void {
    this.service.qualityJobs(this.showFlaggedOnly).subscribe({
      next: (jobs) => (this.qualityJobs = jobs),
      error: () => (this.error = 'Failed to load quality jobs'),
    });
  }

  toggleFlaggedOnly(): void {
    this.showFlaggedOnly = !this.showFlaggedOnly;
    this.loadQualityJobs();
  }

  triggerScrape(sourceId: string): void {
    this.service.triggerScrape(sourceId).subscribe({
      next: () => this.refresh(),
      error: () => (this.error = 'Failed to trigger scrape'),
    });
  }

  replay(runId: string): void {
    this.service.replay(runId).subscribe({
      next: () => this.refresh(),
      error: () => (this.error = 'Failed to replay run'),
    });
  }
}

