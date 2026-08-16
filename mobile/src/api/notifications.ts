import { Notification, NotificationList } from '@/types';
import { apiClient } from './client';

export async function listNotifications(): Promise<NotificationList> {
  const { data } = await apiClient.get<NotificationList>('/api/notifications');
  return data;
}

export async function markNotificationRead(id: string): Promise<Notification> {
  const { data } = await apiClient.post<Notification>(`/api/notifications/${id}/read`, {});
  return data;
}

export async function markAllNotificationsRead(): Promise<{ updated: boolean }> {
  const { data } = await apiClient.post<{ updated: boolean }>('/api/notifications/read-all', {});
  return data;
}
