import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';

import { ApplicationsService } from '../../services/applications.service';
import { JobDetail, JobsService, ParsedJD } from '../../services/jobs.service';

@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './job-detail.component.html',
  styleUrl: './job-detail.component.scss',
})
export class JobDetailComponent implements OnInit {
  job: JobDetail | null = null;
  parsed: ParsedJD | null = null;
  error: string | null = null;
  message: string | null = null;
  saving = false;
  tailoring = false;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private jobs: JobsService,
    private applications: ApplicationsService
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.router.navigate(['/jobs']);
      return;
    }
    this.jobs.get(id).subscribe({
      next: (job) => {
        this.job = job;
        this.loadParsed();
      },
      error: () => (this.error = 'Failed to load job'),
    });
  }

  private loadParsed(): void {
    if (!this.job) {
      return;
    }
    this.jobs.getParsed(this.job.id).subscribe({
      next: (parsed) => (this.parsed = parsed),
      error: () => (this.parsed = null),
    });
  }

  parseNow(): void {
    if (!this.job) {
      return;
    }
    this.jobs.parse(this.job.id).subscribe({
      next: () => {
        this.message = 'Parsing job description… refresh to see results.';
        this.parsed = null;
      },
      error: () => (this.error = 'Failed to enqueue parsing'),
    });
  }

  addApplication(): void {
    if (!this.job || this.saving) {
      return;
    }
    this.saving = true;
    this.message = null;
    this.applications.create({ job_id: this.job.id, status: 'saved' }).subscribe({
      next: () => {
        this.saving = false;
        this.message = 'Added to your application pipeline.';
      },
      error: () => {
        this.saving = false;
        this.message = 'Could not add the application.';
      },
    });
  }

  tailor(): void {
    if (!this.job || this.tailoring) {
      return;
    }
    this.tailoring = true;
    this.message = null;
    this.jobs.tailor(this.job.id).subscribe({
      next: () => {
        this.tailoring = false;
        this.message = 'Tailoring started. Download the result from the CV page.';
      },
      error: () => {
        this.tailoring = false;
        this.error = 'Failed to start tailoring (is there a master CV yet?).';
      },
    });
  }

  back(): void {
    this.router.navigate(['/jobs']);
  }
}

