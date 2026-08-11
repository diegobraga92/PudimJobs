import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

import { Notification, NotificationsService } from '../../services/notifications.service';
import { AppIconComponent } from '../../shared/icons/icon.component';
import { ToastService } from '../../shared/toast/toast.service';

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
    private toast: ToastService
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
        this.error = 'Failed to load notifications';
        this.toast.error('Failed to load notifications.');
      },
    });
  }

  markRead(notification: Notification): void {
    this.service.markRead(notification.id).subscribe({
      next: () => this.refresh(),
      error: () => {
        this.error = 'Failed to update notification';
        this.toast.error('Failed to update notification.');
      },
    });
  }

  markAllRead(): void {
    this.service.markAllRead().subscribe({
      next: () => {
        this.toast.success('All notifications marked as read.');
        this.refresh();
      },
      error: () => {
        this.error = 'Failed to update notifications';
        this.toast.error('Failed to update notifications.');
      },
    });
  }
}
