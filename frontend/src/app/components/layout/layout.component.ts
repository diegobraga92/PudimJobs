import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { HealthCheckService, HealthResponse } from '../../health-check.service';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './layout.component.html',
  styleUrl: './layout.component.scss',
})
export class LayoutComponent implements OnInit {
  health: HealthResponse | null = null;

  constructor(
    private auth: AuthService,
    private router: Router,
    private healthCheck: HealthCheckService
  ) {}

  ngOnInit(): void {
    this.healthCheck.check().subscribe({
      next: (health) => (this.health = health),
      error: () => (this.health = null),
    });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
