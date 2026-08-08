import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Notification {
  id: string;
  job_id: string | null;
  channel: string;
  title: string;
  message: string | null;
  status: string;
  read: boolean;
  created_at: string;
}

export interface NotificationList {
  total: number;
  unread: number;
  items: Notification[];
}

@Injectable({ providedIn: 'root' })
export class NotificationsService {
  constructor(private http: HttpClient) {}

  list(): Observable<NotificationList> {
    return this.http.get<NotificationList>('/api/notifications');
  }

  markRead(id: string): Observable<Notification> {
    return this.http.post<Notification>(`/api/notifications/${id}/read`, {});
  }

  markAllRead(): Observable<{ updated: boolean }> {
    return this.http.post<{ updated: boolean }>('/api/notifications/read-all', {});
  }
}
