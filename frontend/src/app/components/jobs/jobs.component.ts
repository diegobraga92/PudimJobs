import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { JobFilters, JobInput, JobSummary, JobsService } from '../../services/jobs.service';

@Component({
  selector: 'app-jobs',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './jobs.component.html',
  styleUrl: './jobs.component.scss',
})
export class JobsComponent implements OnInit {
  jobs: JobSummary[] = [];
  loading = false;
  error: string | null = null;

  showForm = false;
  searchForm;
  jobForm;

  constructor(
    private fb: FormBuilder,
    private service: JobsService,
    private router: Router
  ) {
    this.searchForm = this.fb.group({
      q: [''],
      company: [''],
      date_from: [''],
      date_to: [''],
      tags: [''],
    });
    this.jobForm = this.fb.group({
      title: ['', Validators.required],
      company: ['', Validators.required],
      url: [''],
      posted_date: [''],
      tags: [''],
      description: [''],
    });
  }

  ngOnInit(): void {
    this.search();
  }

  search(): void {
    this.loading = true;
    this.error = null;
    const value = this.searchForm.value as {
      q: string;
      company: string;
      date_from: string;
      date_to: string;
      tags: string;
    };
    const filters: JobFilters = {
      q: value.q || undefined,
      company: value.company || undefined,
      date_from: value.date_from || undefined,
      date_to: value.date_to || undefined,
      tags: value.tags || undefined,
    };
    this.service.list(filters).subscribe({
      next: (jobs) => {
        this.jobs = jobs;
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load jobs';
        this.loading = false;
      },
    });
  }

  openCreate(): void {
    this.jobForm.reset();
    this.showForm = true;
  }

  cancelForm(): void {
    this.showForm = false;
  }

  save(): void {
    if (this.jobForm.invalid) {
      return;
    }
    const value = this.jobForm.value as {
      title: string;
      company: string;
      url: string;
      posted_date: string;
      tags: string;
      description: string;
    };
    const payload: JobInput = {
      title: value.title,
      company: value.company,
      url: value.url,
      posted_date: value.posted_date,
      description: value.description,
      tags: this.parseTags(value.tags),
    };
    this.service.create(payload).subscribe({
      next: () => {
        this.showForm = false;
        this.search();
      },
      error: () => (this.error = 'Failed to create job'),
    });
  }

  open(id: string): void {
    this.router.navigate(['/jobs', id]);
  }

  private parseTags(input: string): string[] {
    return input
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);
  }
}
