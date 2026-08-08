import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

import { Notification, NotificationsService } from '../../services/notifications.service';

@Component({
  selector: 'app-notifications',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './notifications.component.html',
  styleUrl: './notifications.component.scss',
})
export class NotificationsComponent implements OnInit {
  notifications: Notification[] = [];
  unread = 0;
  total = 0;
  error: string | null = null;

  constructor(private service: NotificationsService) {}

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
      error: () => (this.error = 'Failed to load notifications'),
    });
  }

  markRead(notification: Notification): void {
    this.service.markRead(notification.id).subscribe({
      next: () => this.refresh(),
      error: () => (this.error = 'Failed to update notification'),
    });
  }

  markAllRead(): void {
    this.service.markAllRead().subscribe({
      next: () => this.refresh(),
      error: () => (this.error = 'Failed to update notifications'),
    });
  }
}
