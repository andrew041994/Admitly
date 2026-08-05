import { apiRequest } from './client';

export type InAppNotification = {
  id: number;
  notification_type: string;
  title: string;
  body: string;
  is_read: boolean;
  read_at: string | null;
  route_key: 'ticket' | 'transfers' | 'wallet' | 'event' | null;
  route_params: Record<string, number | string>;
  related_entity_type: string | null;
  related_entity_id: number | null;
  created_at: string;
};

export type NotificationPreferences = {
  ticket_activity_push_enabled: boolean;
  event_reminders_push_enabled: boolean;
  nearby_events_push_enabled: boolean;
  location_discovery_enabled: boolean;
  has_saved_location: boolean;
  location_updated_at: string | null;
};

export function listNotifications(beforeId?: number) {
  const query = beforeId ? `?before_id=${beforeId}` : '';
  return apiRequest<{ items: InAppNotification[]; next_cursor: number | null }>({
    path: `/me/notifications${query}`,
  });
}

export function getUnreadNotificationCount() {
  return apiRequest<{ unread_count: number }>({ path: '/me/notifications/unread-count' });
}

export function markNotificationRead(notificationId: number) {
  return apiRequest<InAppNotification>({ path: `/me/notifications/${notificationId}/read`, method: 'POST' });
}

export function markAllNotificationsRead() {
  return apiRequest<{ updated_count: number; unread_count: number }>({ path: '/me/notifications/read-all', method: 'POST' });
}

export function getNotificationPreferences() {
  return apiRequest<NotificationPreferences>({ path: '/me/notification-preferences' });
}

export function updateNotificationPreferences(payload: Partial<NotificationPreferences> & { latitude?: number; longitude?: number }) {
  return apiRequest<NotificationPreferences>({
    path: '/me/notification-preferences',
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function registerDevicePushToken(payload: { token: string; platform: 'ios' | 'android'; installation_id: string }) {
  return apiRequest<{ success: boolean; device_registered: boolean }>({
    path: '/me/push-tokens', method: 'POST', body: JSON.stringify(payload),
  });
}

export function disableDevicePushToken(payload: { token?: string; installation_id?: string }) {
  return apiRequest<{ success: boolean }>({
    path: '/me/push-tokens', method: 'DELETE', body: JSON.stringify(payload),
  });
}
