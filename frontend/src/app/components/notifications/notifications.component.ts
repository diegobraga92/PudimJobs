import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

import { Notification, NotificationsService } from '../../services/notifications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ToastService } from '../../shared/toast/toast.service';
import { I18nService } from '../../services/i18n.service';

@Component({
  selector: 'app-notifications',
  standalone: true,
  imports: [CommonModule, AppIconComponent],
  templateUrl: './notifications.component.html',
  styleUrl: './notifications.component.scss',
})
export class NotificationsComponent implements OnInit {
  notifications: Notification[] = [];
  unread = 0;
  total = 0;
  error: string | null = null;

  constructor(
    private service: NotificationsService,
    private toast: ToastService,
    readonly i18n: I18nService
  ) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.service.list().subscribe({
      next: (result) => {
        this.notifications = result.items;
        this.unread = result.unread;
        this.total = result.total;
      },
      error: () => {
        this.error = this.i18n.t('errors.failedLoadNotifications');
        this.toast.error(this.i18n.t('errors.failedLoadNotifications'));
      },
    });
  }

  markRead(notification: Notification): void {
    this.service.markRead(notification.id).subscribe({
      next: () => this.refresh(),
      error: () => {
        this.error = this.i18n.t('errors.failedUpdateNotification');
        this.toast.error(this.i18n.t('errors.failedUpdateNotification'));
      },
    });
  }

  markAllRead(): void {
    this.service.markAllRead().subscribe({
      next: () => {
        this.toast.success(this.i18n.t('notifications.allReadToast'));
        this.refresh();
      },
      error: () => {
        this.error = this.i18n.t('errors.failedUpdateNotifications');
        this.toast.error(this.i18n.t('errors.failedUpdateNotifications'));
      },
    });
  }
}
