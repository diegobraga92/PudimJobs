import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { HealthCheckService, HealthResponse } from './health-check.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnInit {
  health: HealthResponse | null = null;
  error: string | null = null;

  constructor(private healthCheck: HealthCheckService) {}

  ngOnInit(): void {
    this.healthCheck.check().subscribe({
      next: (data) => {
        this.health = data;
      },
      error: (err) => {
        this.error = 'Failed to connect to backend';
        console.error('Health check failed', err);
      },
    });
  }
}