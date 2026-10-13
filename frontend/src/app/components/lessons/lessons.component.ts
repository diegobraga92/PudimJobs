import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import {
  ApplicationStatus,
  ApplicationsService,
  LessonEntry,
} from '../../services/applications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { I18nService } from '../../services/i18n.service';

const STATUSES: ApplicationStatus[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];

@Component({
  selector: 'app-lessons',
  standalone: true,
  imports: [CommonModule, RouterLink, AppIconComponent],
  templateUrl: './lessons.component.html',
  styleUrl: './lessons.component.scss',
})
export class LessonsComponent implements OnInit {
  lessons: LessonEntry[] = [];
  error: string | null = null;
  loading = false;
  statuses = STATUSES;
  statusFilter: ApplicationStatus | '' = '';
  query = '';

  constructor(
    private service: ApplicationsService,
    readonly i18n: I18nService
  ) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true;
    this.error = null;
    this.service.lessons().subscribe({
      next: (lessons) => {
        this.lessons = lessons;
        this.loading = false;
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadLessons');
        this.loading = false;
      },
    });
  }

  /** Lessons narrowed by status and free-text (job or retrospective text). */
  get visibleLessons(): LessonEntry[] {
    const needle = this.query.trim().toLowerCase();
    return this.lessons.filter((lesson) => {
      if (this.statusFilter && lesson.status !== this.statusFilter) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return (
        lesson.lessons_learned.toLowerCase().includes(needle) ||
        lesson.job_title.toLowerCase().includes(needle) ||
        lesson.job_company.toLowerCase().includes(needle)
      );
    });
  }

  statusLabel(status: ApplicationStatus): string {
    return this.i18n.t(`pipeline.${status}`);
  }

  setStatusFilter(status: ApplicationStatus | ''): void {
    this.statusFilter = status;
  }

  setQuery(value: string): void {
    this.query = value;
  }
}
