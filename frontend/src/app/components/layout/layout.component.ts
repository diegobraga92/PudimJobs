import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { HealthCheckService, HealthResponse } from '../../health-check.service';
import { AuthService, User } from '../../services/auth.service';
import { NotificationsService } from '../../services/notifications.service';
import { ThemeService } from '../../services/theme.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { AppIconName } from '../../shared/icons/icon-name';

interface NavItem {
  label: string;
  route: string;
  icon: AppIconName;
  adminOnly?: boolean;
}

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, RouterOutlet, AppIconComponent],
  templateUrl: './layout.component.html',
  styleUrl: './layout.component.scss',
})
export class LayoutComponent implements OnInit {
  health: HealthResponse | null = null;
  user: User | null = null;
  unread = 0;
  sidebarOpen = false;

  readonly navItems: NavItem[] = [
    { label: 'Jobs', route: '/jobs', icon: 'briefcase' },
    { label: 'Sources', route: '/sources', icon: 'globe' },
    { label: 'Master CV', route: '/cv', icon: 'file-text' },
    { label: 'Applications', route: '/applications', icon: 'kanban' },
    { label: 'Alerts', route: '/alerts', icon: 'bell' },
    { label: 'Notifications', route: '/notifications', icon: 'bell-ring' },
    { label: 'Admin', route: '/admin', icon: 'shield-check', adminOnly: true },
  ];

  constructor(
    private auth: AuthService,
    private router: Router,
    private healthCheck: HealthCheckService,
    private notifications: NotificationsService,
    readonly theme: ThemeService
  ) {}

  ngOnInit(): void {
    this.healthCheck.check().subscribe({
      next: (health) => (this.health = health),
      error: () => (this.health = null),
    });
    this.auth.me().subscribe({
      next: (user) => (this.user = user),
      error: () => undefined,
    });
    this.loadUnread();
  }

  private loadUnread(): void {
    this.notifications.list().subscribe({
      next: (result) => (this.unread = result.unread),
      error: () => undefined,
    });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}

