import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

import {
  Application,
  ApplicationStatus,
  ApplicationsService,
} from '../../services/applications.service';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];

@Component({
  selector: 'app-applications',
  standalone: true,
  imports: [CommonModule],
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

  constructor(private service: ApplicationsService) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.error = null;
    this.service.list().subscribe({
      next: (applications) => {
        for (const status of STATUSES) {
          this.columns[status] = [];
        }
        for (const application of applications) {
          this.columns[application.status].push(application);
        }
      },
      error: () => (this.error = 'Failed to load applications'),
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
    this.service.update(this.selected.id, { status }).subscribe({
      next: () => {
        this.selected = null;
        this.refresh();
      },
      error: () => (this.error = 'Failed to update status'),
    });
  }

  remove(application: Application): void {
    if (!window.confirm(`Remove application for "${application.job_title}"?`)) {
      return;
    }
    this.service.delete(application.id).subscribe({
      next: () => {
        this.selected = null;
        this.refresh();
      },
      error: () => (this.error = 'Failed to delete application'),
    });
  }
}
