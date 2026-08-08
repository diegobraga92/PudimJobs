import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';

import { ApplicationsService } from '../../services/applications.service';
import { JobDetail, JobsService } from '../../services/jobs.service';

@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './job-detail.component.html',
  styleUrl: './job-detail.component.scss',
})
export class JobDetailComponent implements OnInit {
  job: JobDetail | null = null;
  error: string | null = null;
  message: string | null = null;
  saving = false;

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
      next: (job) => (this.job = job),
      error: () => (this.error = 'Failed to load job'),
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

  back(): void {
    this.router.navigate(['/jobs']);
  }
}
