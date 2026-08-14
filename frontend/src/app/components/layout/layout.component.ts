import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { HealthCheckService, HealthResponse } from '../../health-check.service';
import { AuthService, User } from '../../services/auth.service';
import { NotificationsService } from '../../services/notifications.service';
import { ThemeService } from '../../services/theme.service';
import { I18nService } from '../../services/i18n.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { AppIconName } from '../../shared/icons/icon-name';

interface NavItem {
  labelKey: string;
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

  private readonly destroyRef = inject(DestroyRef);

  readonly navItems: NavItem[] = [
    { labelKey: 'layout.nav.jobs', route: '/jobs', icon: 'briefcase' },
    { labelKey: 'layout.nav.sources', route: '/sources', icon: 'globe' },
    { labelKey: 'layout.nav.masterCv', route: '/cv', icon: 'file-text' },
    { labelKey: 'layout.nav.applications', route: '/applications', icon: 'kanban' },
    { labelKey: 'layout.nav.alerts', route: '/alerts', icon: 'bell' },
    { labelKey: 'layout.nav.notifications', route: '/notifications', icon: 'bell-ring' },
    { labelKey: 'layout.nav.admin', route: '/admin', icon: 'shield-check', adminOnly: true },
  ];

  constructor(
    private auth: AuthService,
    private router: Router,
    private healthCheck: HealthCheckService,
    private notifications: NotificationsService,
    readonly theme: ThemeService,
    readonly i18n: I18nService
  ) {}

  ngOnInit(): void {
    this.healthCheck
      .check()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (health) => (this.health = health),
        error: () => (this.health = null),
      });
    this.auth
      .me()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (user) => (this.user = user),
        error: () => undefined,
      });
    this.loadUnread();
  }

  private loadUnread(): void {
    this.notifications
      .list()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => (this.unread = result.unread),
        error: () => undefined,
      });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}

